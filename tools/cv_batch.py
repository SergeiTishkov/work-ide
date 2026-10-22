"""
CVs and cover letters for the vacancies the identities' `cv.auto` filters
pick, in a process of its own, apart from the app (the owner, 2026-10-13).
After a collection the app starts it for the identity; it can be started by
hand as well:

    python tools/cv_batch.py sharp partsharp         # what cv_auto picks now
    python tools/cv_batch.py --stop                  # after the current document
    python tools/cv_batch.py --status

What is picked is cv_auto's choice: every vacancy of the shortlist its
filters match. A document already in the vacancy's folder, or a vacancy
found gone, is skipped — so a stopped batch goes on where it was when
started again. The documents it makes are marked "Made automatically." in
their logs (--auto to the tools).

THE PERSON'S VACANCIES ARE LEFT ALONE (task 0087, cv_auto.left_alone): before
each document, after a pause too, the batch asks again whether the person
gave feedback on the vacancy, made a document for it or has a CV or letter
task for it in the queue; then it makes nothing for it ("left alone").

ONE BATCH AT A TIME, one document at a time: each drives Word through COM.
Started while a batch runs, the request joins it (cv_batch.pending) and the
running batch takes it after its own list.

THE APP GOES FIRST. A CV the person asked for in the app should not wait
hours behind a batch: while the app has documents to make it keeps
cv_batch.HOLD (its pid inside), and the batch waits between documents, with
"holding": true in its status, until the file is gone or its process ended.

The app shows the batch in its task panel from data/:

    cv_batch.json   the status: pid, state (running, finished, stopped,
                    crashed), holding, identities, total, index, made,
                    failed, gone, the document in work, log_offset — where
                    this batch's lines begin in the log
    cv_batch.log    one line per event, appended across batches
    cv_batch.STOP   --stop, or the panel's ✕: stop after the current document
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_limit  # noqa: E402
import common  # noqa: E402
import taskq  # noqa: E402

TOOLS = {"cv": "cv_tailor.py", "letter": "cover_letter.py"}
GONE = "Vacancy not found"   # cv_tailor.GONE, without importing the model code
HOLD_POLL_SECONDS = 2


def paths(data_root: Optional[Path] = None) -> dict:
    base = Path(data_root or common.DATA_ROOT)
    return {name: base / f"cv_batch.{ext}" for name, ext in
            (("status", "json"), ("log", "log"), ("stop", "STOP"), ("pending", "pending"), ("hold", "HOLD"))}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def pid_alive(pid) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        # os.kill(pid, 0) on Windows terminates the process: ask Windows instead
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = kernel.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel.CloseHandle(handle)
        return bool(ok) and code.value == 259             # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def read_status(where: dict) -> Optional[dict]:
    try:
        return json.loads(where["status"].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def running(where: dict) -> Optional[dict]:
    status = read_status(where)
    if status and status.get("state") == "running" and pid_alive(status.get("pid")):
        return status
    return None


def request(where: dict, prefixes: List[str]) -> None:
    """Adds identities to the running batch's list (it reads them when its
    own list ends)."""
    with where["pending"].open("a", encoding="utf-8") as fh:
        for prefix in prefixes:
            fh.write(json.dumps({"identity": prefix}) + "\n")


def take_pending(where: dict) -> List[dict]:
    taking = where["pending"].with_suffix(".taking")
    try:
        os.replace(where["pending"], taking)
    except OSError:
        return []
    out = []
    for line in taking.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    taking.unlink(missing_ok=True)
    return out


def hold_active(where: dict) -> bool:
    try:
        pid = int(where["hold"].read_text(encoding="utf-8").strip() or 0)
    except (OSError, ValueError):
        return False
    return pid_alive(pid)


class Batch:
    def __init__(self, where: dict, sleep: Callable[[float], None] = time.sleep):
        self.where = where
        self.sleep = sleep
        self.status: dict = {}

    def log(self, text: str) -> None:
        line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {text}"
        with self.where["log"].open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        # and to stdout: the task queue's worker logs what the batch prints
        print(line, flush=True)

    def save(self, **changes) -> None:
        self.status.update(changes)
        tmp = self.where["status"].with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.status, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.where["status"])

    def add(self, work: list, requests: List[dict], plan: Callable[[str], list]) -> None:
        for req in requests:
            prefix = req["identity"]
            items = plan(prefix)
            self.log(f"{prefix}: {len(items)} vacancies, {sum(len(i['documents']) for i in items)} documents")
            if prefix not in self.status["identities"]:
                self.status["identities"].append(prefix)
            work += [(prefix, item, kind) for item in items for kind in item["documents"]]
        self.save(total=len(work))

    def wait_for_the_app(self) -> None:
        if not hold_active(self.where):
            return
        self.log("paused: the app is generating documents")
        self.save(holding=True)
        while hold_active(self.where) and not self.where["stop"].exists():
            self.sleep(HOLD_POLL_SECONDS)
        self.save(holding=False)
        self.log("resumed")

    def run(self, requests: List[dict], plan: Callable[[str], list],
            generate: Callable[[str, dict, str], dict],
            check: Optional[Callable[[str, dict], Optional[str]]] = None) -> dict:
        """requests: [{"identity"}]; plan(prefix) -> cv_auto items;
        generate(prefix, item, kind) -> the tool's JSON result; check(prefix,
        item) -> why the vacancy is left alone now, or None."""
        where = self.where
        where["log"].parent.mkdir(parents=True, exist_ok=True)
        other = running(where)
        if other and other.get("pid") != os.getpid():
            raise RuntimeError(f"a batch is running already (pid {other['pid']})")
        where["stop"].unlink(missing_ok=True)
        offset = where["log"].stat().st_size if where["log"].exists() else 0
        self.status = {"pid": os.getpid(), "state": "running", "holding": False, "identities": [],
                       "started_at": _now(), "ended_at": None, "total": 0, "index": 0,
                       "made": 0, "failed": 0, "gone": 0, "left_alone": 0, "current": None, "error": None,
                       "log_offset": offset}
        self.save()
        self.log(f"start: {' '.join(r['identity'] for r in requests)}")
        try:
            work: list = []
            self.add(work, requests + take_pending(where), plan)
            index = 0
            while True:
                while index < len(work):
                    if where["stop"].exists():
                        where["stop"].unlink(missing_ok=True)
                        self.log(f"stopped before {index + 1}/{len(work)}")
                        self.save(state="stopped", current=None, ended_at=_now())
                        return self.status
                    self.wait_for_the_app()
                    if where["stop"].exists():
                        continue
                    prefix, item, kind = work[index]
                    index += 1
                    why = check(prefix, item) if check else None
                    if why:
                        self.status["left_alone"] += 1
                        self.log(f"left alone [{index}/{len(work)}] {prefix} {kind} {item['vacancy_id']}: {why}")
                        self.save()
                    else:
                        self.step(index, len(work), prefix, item, kind, generate)
                    if index == len(work):
                        self.add(work, take_pending(where), plan)
                s = self.status
                self.log(f"finished: {s['made']} made, {s['gone']} gone, {s['failed']} failed, "
                         f"{s['left_alone']} left alone")
                self.save(state="finished", current=None, ended_at=_now())
                # a request that came while finishing: it found this batch
                # running and left it to this batch
                late = take_pending(where)
                if not late:
                    return self.status
                self.save(state="running", ended_at=None)
                self.add(work, late, plan)
        except ai_limit.UsageLimit as exc:
            # every document after this one would be refused too (task 0057);
            # a batch started again skips what is made
            self.log(f"stopped: {ai_limit.mark(exc)}")
            self.save(state="stopped", current=None, error=str(exc), ended_at=_now())
            raise
        except Exception as exc:  # the panel must not show a dead batch as running
            self.log(f"crashed: {exc}")
            self.save(state="crashed", current=None, error=str(exc), ended_at=_now())
            raise

    def step(self, index, total, prefix, item, kind, generate) -> None:
        self.save(index=index, current={"identity": prefix, "kind": kind, "vacancy_id": item["vacancy_id"],
                                        "title": item.get("title") or "", "company": item.get("company") or ""})
        self.log(f"[{index}/{total}] {prefix} {kind} {item['vacancy_id']}  "
                 f"{item.get('title')} — {item.get('company')}")
        started = time.monotonic()
        result = generate(prefix, item, kind)
        minutes = (time.monotonic() - started) / 60
        limit = result.get("ai_limit")
        if isinstance(limit, dict):
            self.save()
            resets = limit.get("resets_at")
            raise ai_limit.UsageLimit(str(result.get("error") or ai_limit.MARK),
                                      datetime.fromisoformat(resets) if resets else None)
        if result.get("ok"):
            self.status["made"] += 1
            self.log(f"ok      {kind} {minutes:.1f} min, {result.get('pages')} page(s)")
        elif str(result.get("error") or "").startswith(GONE):
            self.status["gone"] += 1
            self.log(f"gone    {kind} {result.get('error')}")
        else:
            self.status["failed"] += 1
            self.log(f"FAILED  {kind} {minutes:.1f} min: {result.get('error')}")
        self.save()


def plan_for(prefix: str) -> list:
    """cv_auto's pick for the identity."""
    import cv_auto
    import db
    import identity as identity_mod
    identity_mod.activate_or_exit(prefix, quiet=True)
    settings = cv_auto.auto_settings(common.load_profile(prefix))
    if settings is None or not db.exists():
        return []
    with db.session() as conn:
        return cv_auto.pick(conn, settings, prefix)


def check_now(prefix: str, item: dict) -> Optional[str]:
    """cv_auto.left_alone for one vacancy, asked right before its document."""
    import cv_auto
    import db
    import identity as identity_mod
    identity_mod.activate_or_exit(prefix, quiet=True)
    if not db.exists():
        return None
    with db.session() as conn:
        return cv_auto.left_alone(conn, prefix, [item["vacancy_id"]]).get(item["vacancy_id"])


def generate_with_tools(prefix: str, item: dict, kind: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(common.ROOT / "tools" / TOOLS[kind]), "--identity", prefix,
         "--vacancy", item["vacancy_id"], "--json", "--auto"],
        cwd=common.ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    for line in reversed(proc.stdout.splitlines()):
        if line.strip().startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    tail = (proc.stderr or "").strip().splitlines()[-3:]
    return {"ok": False, "error": f"exit {proc.returncode}: {' | '.join(tail)}"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="CVs and cover letters for what the cv.auto filters pick")
    parser.add_argument("identities", nargs="*", help="Identity prefixes, in the order to go through them")
    parser.add_argument("--stop", action="store_true", help="Stop after the current document")
    parser.add_argument("--status", action="store_true", help="Print the status")
    args = parser.parse_args(argv)
    where = paths()
    where["status"].parent.mkdir(parents=True, exist_ok=True)
    if args.stop:
        where["stop"].touch()
        print("the batch stops after the current document")
        return 0
    if args.status:
        status = read_status(where)
        if status and status.get("state") == "running" and not pid_alive(status.get("pid")):
            status["state"] = "crashed"
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0
    if not args.identities:
        parser.error("name the identities, e.g. sharp partsharp")
    requests = [{"identity": p} for p in args.identities]
    other = running(where)
    if other:
        request(where, args.identities)
        print(f"queued behind the running batch (pid {other['pid']})")
        return 0
    try:
        # Listed in the task queue (tools/taskq.py) when started by hand.
        with taskq.Registered("cv_batch", args.identities[0] if len(args.identities) == 1 else None,
                              log_path=where["log"], args={"identities": args.identities}):
            Batch(where).run(requests, plan_for, generate_with_tools, check_now)
    except ai_limit.UsageLimit as exc:
        ai_limit.record(exc)
        print(ai_limit.mark(exc), flush=True)
        return ai_limit.EXIT_CODE
    except RuntimeError as exc:
        common.eprint(f"cv_batch: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
