"""
The task queue (task 0056): every long piece of work, in data/tasks.sqlite.

WHY
---
Until 2026-10-21 the queue lived in the memory of the app's window: closing
the window stopped every task, and a run the agent or a terminal started was
never in the bottom panel (it showed one old CV batch for weeks). A
collection takes hours, and the owner switches Windows users meanwhile.

Now a task is a row. Whoever asks — the app, the agent, a terminal, a
schedule — adds a row here; the workers (tools/taskd.py, started by Windows
Task Scheduler) take the rows and run them; the app lists the rows and asks
for a stop. Closing the app stops nothing.

    python tools/taskq.py collect sharp              # top, LinkedIn, the rest, CV/CL
    python tools/taskq.py add rest --identity sharp
    python tools/taskq.py add cv --identity sharp --vacancy <id>
    python tools/taskq.py list                       # what is queued and going
    python tools/taskq.py show 12
    python tools/taskq.py log 12 --follow
    python tools/taskq.py wait 12                    # until it ends; exit 0 if done
    python tools/taskq.py stop 12
    python tools/taskq.py status                     # the workers
    python tools/taskq.py schedule list              # work on a timetable (tools/schedules.py)

SLOTS, NEEDS, ORDER
-------------------
A kind names its slot and what it needs (KINDS). One task runs per slot:
`collect` (collections, the rest of the base, clean-ups — they write the
shared base), `linkedin` (its walk takes hours and shares one address's rate
limit), `documents` (Word, through COM), `reputation`. Within a slot tasks
start in the order they came, except that one waiting for another task
(task_after) lets the next go ahead. `needs`: `desktop` (Word needs a signed-in
session) and `ai` (the claude CLI: it may not run without the owner signed in,
and it has a usage limit, task 0057). A task nobody can run now waits, with
the reason in `waiting_for`.

A COLLECTION IS A GROUP: the top (the agent's /top), LinkedIn beside it, the
rest of the base after both, and a CV/CL batch after each of the three for
what it brought or raised into a class (collection()). It is going until
the last task of the group ends, and no second one is queued meanwhile
(active_collection(), task 0089).

NOTHING STAYS "RUNNING" FOR A DEAD PROCESS: the one running a task refreshes
its heartbeat_at; sweep() finds a task not refreshed for STALE_AFTER_SECONDS,
and queues it again (up to MAX_ATTEMPTS starts; the pipeline is safe to run
twice) or, for a process that registered itself, marks it interrupted.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sqlite3
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SCHEMA = common.ROOT / "schemas" / "tasks.sql"
NAME = "tasks.sqlite"

# kind -> (slot, needs). The rest of the base and a full run screen the top
# classes with the cheap model (tools/ai_screen.py), so they need AI too.
KINDS: Dict[str, tuple] = {
    "collect": ("collect", ("ai",)),        # the agent's /top: fetch, rank, read the top
    "rest": ("collect", ("ai",)),           # pipeline.py --rest
    "pipeline": ("collect", ("ai",)),       # pipeline.py started by hand (--top or full)
    "clean": ("collect", ()),               # tools/cleanup.py
    "linkedin": ("linkedin", ()),           # pipeline.py --linkedin
    "cv": ("documents", ("desktop", "ai")),  # tools/cv_tailor.py
    "letter": ("documents", ("desktop", "ai")),  # tools/cover_letter.py
    "cv_batch": ("documents", ("desktop", "ai")),  # tools/cv_batch.py
    "reputation": ("reputation", ("ai",)),  # tools/reputation_lookup.py
    "links": ("collect", ()),               # pipeline.py --links: the shortlist's links again
    "ai": ("collect", ("ai",)),             # pipeline.py --ai: what waits for the AI read (task 0078)
}
ACTIVE = ("queued", "running")
ENDED = ("done", "failed", "stopped", "skipped", "interrupted")
ORIGINS = ("app", "agent", "terminal", "schedule", "auto")
# The same rule as identity.PREFIX_RE (not imported: identity.py is heavy).
PREFIX_RE = re.compile(r"^[a-z][a-z0-9]{2,9}$")
# Three missed beats of HEARTBEAT_SECONDS and one slow write.
HEARTBEAT_SECONDS = 10
STALE_AFTER_SECONDS = 45
MAX_ATTEMPTS = 3
# The worker runs a task with this set; a pipeline.py or cv_batch.py started
# under it does not register a second row (register()).
TASK_ENV = "WORK_IDE_TASK_ID"


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: Optional[datetime] = None) -> str:
    return (moment or now()).isoformat(timespec="seconds")


def is_stale(beat: Optional[str], at: Optional[datetime] = None) -> bool:
    try:
        moment = datetime.fromisoformat(beat)
    except (TypeError, ValueError):
        return True
    return (at or now()) - moment > timedelta(seconds=STALE_AFTER_SECONDS)


def path() -> Path:
    """Beside the shared base, so a test's isolated base takes its queue along."""
    return Path(common.DB_PATH).parent / NAME


def logs_dir() -> Path:
    return path().parent / "tasks"


def default_origin() -> str:
    """Claude Code sets CLAUDECODE in the commands it runs."""
    return "agent" if os.environ.get("CLAUDECODE") else "terminal"


def connect(where: Optional[Path] = None) -> sqlite3.Connection:
    where = Path(where or path())
    where.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(where), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    return conn


@contextmanager
def session(where: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    conn = connect(where)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """BEGIN IMMEDIATE: two workers claiming at once take turns."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def as_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    if row is None:
        return None
    task = dict(row)
    for key in ("args", "result"):
        try:
            task[key] = json.loads(task[key]) if task.get(key) else ({} if key == "args" else None)
        except ValueError:
            pass
    task["needs"] = [n for n in (task.get("needs") or "").split(",") if n]
    return task


def get(conn: sqlite3.Connection, task_id: int) -> Optional[dict]:
    task = as_dict(conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())
    if task is not None:
        task["after"] = [dict(r) for r in conn.execute(
            "SELECT after_id, needs_done FROM task_after WHERE task_id = ? ORDER BY after_id", (task_id,))]
    return task


def tasks(conn: sqlite3.Connection, active_only: bool = False, include_hidden: bool = False) -> List[dict]:
    where, params = [], []
    if active_only:
        where.append("state IN ('queued', 'running')")
    if not include_hidden:
        where.append("hidden = 0")
    sql = "SELECT * FROM tasks" + (f" WHERE {' AND '.join(where)}" if where else "") + " ORDER BY id"
    return [as_dict(r) for r in conn.execute(sql, params)]


def _validate(kind: str, identity: Optional[str], origin: str) -> None:
    if kind not in KINDS:
        raise ValueError(f"unknown task kind: {kind} (known: {', '.join(KINDS)})")
    if origin not in ORIGINS:
        raise ValueError(f"unknown origin: {origin} (known: {', '.join(ORIGINS)})")
    if identity is not None and not PREFIX_RE.match(identity):
        raise ValueError(f"invalid identity: {identity}")


def _insert(conn, kind, identity, *, origin, vacancy_id=None, title="", company="", args=None,
            group_id=None, after: Sequence = (), state="queued", **fields) -> int:
    slot, needs = KINDS[kind]
    columns = dict(kind=kind, identity=identity, vacancy_id=vacancy_id, title=title or "",
                   company=company or "", args=json.dumps(args or {}, ensure_ascii=False), slot=slot,
                   needs=",".join(needs), origin=origin, group_id=group_id, state=state,
                   queued_at=iso(), **fields)
    task_id = conn.execute(
        f"INSERT INTO tasks ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
        tuple(columns.values())).lastrowid
    for item in after:
        after_id, needs_done = item if isinstance(item, tuple) else (item, True)
        conn.execute("INSERT INTO task_after (task_id, after_id, needs_done) VALUES (?, ?, ?)",
                     (task_id, int(after_id), 1 if needs_done else 0))
    conn.execute("UPDATE tasks SET log_path = COALESCE(log_path, ?) WHERE id = ?",
                 (str(logs_dir() / f"{task_id}.log"), task_id))
    return task_id


def same_active(conn, kind: str, identity: Optional[str], vacancy_id: Optional[str]) -> Optional[dict]:
    row = conn.execute(
        "SELECT id FROM tasks WHERE state IN ('queued', 'running') AND kind = ? AND identity IS ? "
        "AND vacancy_id IS ? ORDER BY id LIMIT 1", (kind, identity, vacancy_id)).fetchone()
    return get(conn, row[0]) if row else None


def add(conn: sqlite3.Connection, kind: str, identity: Optional[str] = None, *,
        origin: Optional[str] = None, vacancy_id: Optional[str] = None, title: str = "",
        company: str = "", args: Optional[dict] = None, after: Sequence = ()) -> dict:
    """Queues one task. The same kind for the same identity and vacancy,
    already queued or going, is not queued twice: {"added": False, "task": it}."""
    origin = origin or default_origin()
    _validate(kind, identity, origin)
    with transaction(conn):
        existing = same_active(conn, kind, identity, vacancy_id)
        if existing:
            return {"added": False, "task": existing}
        task_id = _insert(conn, kind, identity, origin=origin, vacancy_id=vacancy_id, title=title,
                          company=company, args=args, after=after)
    return {"added": True, "task": get(conn, task_id)}


def active_collection(conn: sqlite3.Connection, identity: Optional[str]) -> Optional[dict]:
    """A task of a collection of the identity still queued or going: its top,
    or any task of its group: LinkedIn, the rest, a CV/CL batch (the owner,
    2026-10-23, task 0089: a collection is a batch of tasks, going until the
    last of them ends). The running one first."""
    row = conn.execute(
        "SELECT id FROM tasks WHERE identity IS ? AND state IN ('queued', 'running') "
        "AND (kind = 'collect' OR group_id IS NOT NULL) "
        "ORDER BY state = 'running' DESC, id LIMIT 1", (identity,)).fetchone()
    return get(conn, row[0]) if row else None


def collection(conn: sqlite3.Connection, identity: str, *, origin: Optional[str] = None,
               linkedin: bool = True, documents: bool = True) -> dict:
    """One collection as a group (the owner, 2026-10-21): the top; LinkedIn
    beside it; the rest of the base after both, if the top ended done; a
    CV/CL batch after the top, one after LinkedIn and one after the rest, each
    if that ended done (the rest's AI read raises stretch roles into a class).
    A collection of the identity still going is not queued again, a click or
    a schedule alike: going until the last task of its group ends
    (active_collection; task 0089). Until 2026-10-23 only the top counted,
    and with the top done and LinkedIn, the rest and two batches still
    waiting, a second group could be queued beside the first."""
    origin = origin or default_origin()
    _validate("collect", identity, origin)
    with transaction(conn):
        existing = active_collection(conn, identity)
        if existing:
            return {"added": False, "task": existing,
                    "group": group(conn, existing["group_id"]) or [existing]}
        top = _insert(conn, "collect", identity, origin=origin)
        conn.execute("UPDATE tasks SET group_id = ? WHERE id = ?", (top, top))
        made = {"top": top}
        after_rest = [(top, True)]
        if linkedin and not same_active(conn, "linkedin", identity, None):
            made["linkedin"] = _insert(conn, "linkedin", identity, origin=origin, group_id=top)
            after_rest.append((made["linkedin"], False))
        made["rest"] = _insert(conn, "rest", identity, origin=origin, group_id=top, after=after_rest)
        if documents:
            made["cv_batch"] = _insert(conn, "cv_batch", identity, origin=origin, group_id=top,
                                       after=[(top, True)])
            if "linkedin" in made:
                made["cv_batch_linkedin"] = _insert(conn, "cv_batch", identity, origin=origin,
                                                    group_id=top, after=[(made["linkedin"], True)])
            made["cv_batch_rest"] = _insert(conn, "cv_batch", identity, origin=origin, group_id=top,
                                            after=[(made["rest"], True)])
    return {"added": True, "task": get(conn, top), "group": group(conn, top), "ids": made}


def group(conn: sqlite3.Connection, group_id: Optional[int]) -> List[dict]:
    if group_id is None:
        return []
    return [as_dict(r) for r in conn.execute("SELECT * FROM tasks WHERE group_id = ? ORDER BY id", (group_id,))]


def stop(conn: sqlite3.Connection, task_id: int) -> dict:
    """A queued task ends at once; a running one is asked to stop (the worker
    or the process itself acts on stop_requested)."""
    with transaction(conn):
        task = get(conn, task_id)
        if task is None:
            return {"ok": False, "error": f"no task #{task_id}"}
        if task["state"] == "queued":
            conn.execute("UPDATE tasks SET state = 'stopped', ended_at = ?, waiting_for = NULL, "
                         "error = 'stopped before it started' WHERE id = ?", (iso(), task_id))
        elif task["state"] == "running":
            conn.execute("UPDATE tasks SET stop_requested = 1 WHERE id = ?", (task_id,))
        else:
            return {"ok": False, "error": f"#{task_id} already ended: {task['state']}"}
    return {"ok": True, "task": get(conn, task_id)}


def hide(conn: sqlite3.Connection, ids: Optional[Iterable[int]] = None) -> int:
    """Clears ended tasks from the panel, for good (task 0060: a cleared
    batch came back after every restart). None: every ended task."""
    if ids is None:
        cur = conn.execute("UPDATE tasks SET hidden = 1 WHERE hidden = 0 AND state NOT IN ('queued', 'running')")
    else:
        ids = [int(i) for i in ids]
        if not ids:
            return 0
        cur = conn.execute(
            f"UPDATE tasks SET hidden = 1 WHERE state NOT IN ('queued', 'running') "
            f"AND id IN ({', '.join('?' * len(ids))})", ids)
    return cur.rowcount


# --- the workers' side ----------------------------------------------------------

def live_workers(conn: sqlite3.Connection, at: Optional[datetime] = None) -> List[dict]:
    rows = [dict(r) for r in conn.execute("SELECT * FROM workers")]
    alive = []
    for row in rows:
        if not is_stale(row["heartbeat_at"], at):
            row["capabilities"] = [c for c in (row["capabilities"] or "").split(",") if c]
            alive.append(row)
    return alive


def state_value(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM queue_state WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_state_value(conn: sqlite3.Connection, key: str, value: Optional[str]) -> None:
    if value is None:
        conn.execute("DELETE FROM queue_state WHERE key = ?", (key,))
    else:
        conn.execute("INSERT INTO queue_state (key, value) VALUES (?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


# With no reset time in the refusal, the limit is checked again this often
# (the owner, 2026-10-21).
AI_CHECK_EVERY = timedelta(hours=8)
AI_LIMIT_EXIT = 75   # ai_limit.EXIT_CODE


def ai_block(conn: sqlite3.Connection) -> Optional[datetime]:
    """When the AI usage limit was expected to reset (task 0057). It holds
    the AI tasks until a worker has checked, at or after that moment, that
    `claude` answers again (taskd.py), so a run is not started only to meet
    the limit an hour in."""
    value = state_value(conn, "ai_blocked_until")
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def ai_blocked_until(conn: sqlite3.Connection, at: Optional[datetime] = None) -> Optional[datetime]:
    """The expected reset, while it is still ahead."""
    until = ai_block(conn)
    return until if until and until > (at or now()) else None


def block_ai(conn: sqlite3.Connection, resets_at: Optional[datetime] = None,
             at: Optional[datetime] = None) -> datetime:
    """The usage limit was met: AI tasks wait until `resets_at`, or
    AI_CHECK_EVERY when the refusal named no time."""
    at = at or now()
    until = resets_at if resets_at and resets_at > at else at + AI_CHECK_EVERY
    set_state_value(conn, "ai_blocked_until", iso(until.astimezone(timezone.utc)))
    return until


def unblock_ai(conn: sqlite3.Connection) -> None:
    set_state_value(conn, "ai_blocked_until", None)


def _local_clock(moment: datetime) -> str:
    return moment.astimezone().strftime("%H:%M")


def _needs_reason(need: str, workers: List[dict], blocked: Optional[datetime],
                  at: Optional[datetime] = None) -> Optional[str]:
    if need == "ai" and blocked:
        if blocked > (at or now()):
            return f"the AI usage limit; tried again at {_local_clock(blocked)}"
        return "the AI usage limit; checking whether it has reset"
    if any(need in w["capabilities"] for w in workers):
        return None
    if not workers:
        return "no worker is running (python tools/taskd.py status)"
    if need == "desktop":
        return "the owner's sign-in: Word needs a desktop session"
    if need == "ai":
        return "the owner's sign-in: AI does not run without it"
    return f"a worker that can {need}"


def plan(conn: sqlite3.Connection, at: Optional[datetime] = None) -> Dict[int, Optional[str]]:
    """What every queued task waits for, None for one that can start now;
    skips a task whose prerequisite ended other than done. Runs inside the
    caller's transaction."""
    at = at or now()
    workers = live_workers(conn, at)
    blocked = ai_block(conn)
    # A CV/CL batch paused between documents for the app's own (taskd.py
    # documents_hold) leaves the documents slot to a CV or a cover letter.
    yielding = state_value(conn, "documents_yield") == "1"
    queued = [as_dict(r) for r in conn.execute("SELECT * FROM tasks WHERE state = 'queued' ORDER BY id")]
    busy = {r["slot"]: r["id"] for r in conn.execute(
        "SELECT slot, id, kind FROM tasks WHERE state = 'running'")
        if not (r["slot"] == "documents" and r["kind"] == "cv_batch" and yielding)}
    reasons: Dict[int, Optional[str]] = {}
    first_in_slot: Dict[str, int] = {}
    for task in queued:
        reason = None
        for dep in conn.execute(
                "SELECT a.after_id, a.needs_done, t.state FROM task_after a "
                "LEFT JOIN tasks t ON t.id = a.after_id WHERE a.task_id = ?", (task["id"],)):
            if dep["state"] in ACTIVE:
                reason = reason or f"#{dep['after_id']} to end"
            elif dep["needs_done"] and dep["state"] != "done":
                conn.execute("UPDATE tasks SET state = 'skipped', ended_at = ?, waiting_for = NULL, "
                             "error = ? WHERE id = ?",
                             (iso(at), f"#{dep['after_id']} ended {dep['state'] or 'missing'}", task["id"]))
                reason = "skipped"
                break
        if reason == "skipped":
            continue
        if reason is None:
            for need in task["needs"]:
                reason = _needs_reason(need, workers, blocked, at)
                if reason:
                    break
        if reason is None and task["slot"] in busy:
            reason = f"#{busy[task['slot']]} to end"
        elif reason is None and yielding and task["kind"] == "cv_batch":
            reason = "the documents the app asked for"
        if reason is None and task["slot"] in first_in_slot:
            reason = f"#{first_in_slot[task['slot']]} to end"
        if reason is None:
            first_in_slot[task["slot"]] = task["id"]
        reasons[task["id"]] = reason
    return reasons


def refresh_waiting(conn: sqlite3.Connection, reasons: Dict[int, Optional[str]]) -> None:
    for task_id, reason in reasons.items():
        conn.execute("UPDATE tasks SET waiting_for = ? WHERE id = ? AND state = 'queued' "
                     "AND waiting_for IS NOT ?", (reason, task_id, reason))


def claim(conn: sqlite3.Connection, role: str, capabilities: Sequence[str], pid: int,
          at: Optional[datetime] = None, base_holder=None) -> Optional[dict]:
    """The next task this worker may run, marked running, or None.

    The desktop worker takes what needs the desktop, and anything else only
    while no live background worker can run it: the background one outlives
    a sign-out. base_holder(): who holds the shared base outside the queue,
    or None (tools/runstate.py); a collect-slot task waits for it."""
    at = at or now()
    with transaction(conn):
        reasons = plan(conn, at)
        background = [w for w in live_workers(conn, at) if w["role"] != role and w["role"] == "background"]
        chosen = None
        for task_id, reason in reasons.items():
            if reason is not None:
                continue
            task = get(conn, task_id)
            if not set(task["needs"]) <= set(capabilities):
                continue
            if role == "desktop" and "desktop" not in task["needs"] and any(
                    set(task["needs"]) <= set(w["capabilities"]) for w in background):
                continue
            if task["slot"] == "collect" and base_holder is not None:
                holder = base_holder()
                if holder:
                    reasons[task_id] = f"the base: {holder}"
                    continue
            chosen = task
            break
        refresh_waiting(conn, reasons)
        if chosen is None:
            return None
        conn.execute(
            "UPDATE tasks SET state = 'running', worker = ?, pid = ?, host = ?, started_at = ?, "
            "heartbeat_at = ?, waiting_for = NULL, attempts = attempts + 1, error = NULL WHERE id = ?",
            (role, pid, socket.gethostname(), iso(at), iso(at), chosen["id"]))
    return get(conn, chosen["id"])


def beat(conn: sqlite3.Connection, task_ids: Iterable[int], pid: Optional[int] = None) -> None:
    for task_id in task_ids:
        if pid is None:
            conn.execute("UPDATE tasks SET heartbeat_at = ? WHERE id = ? AND state = 'running'", (iso(), task_id))
        else:
            conn.execute("UPDATE tasks SET heartbeat_at = ?, pid = ? WHERE id = ? AND state = 'running'",
                         (iso(), pid, task_id))


def finish(conn: sqlite3.Connection, task_id: int, state: str, error: Optional[str] = None,
           result: Optional[dict] = None) -> None:
    if state not in ENDED:
        raise ValueError(f"not an end state: {state}")
    conn.execute(
        "UPDATE tasks SET state = ?, ended_at = ?, heartbeat_at = ?, error = ?, result = ?, "
        "waiting_for = NULL WHERE id = ? AND state = 'running'",
        (state, iso(), iso(), error, json.dumps(result, ensure_ascii=False) if result is not None else None,
         task_id))


def requeue(conn: sqlite3.Connection, task_id: int, why: str) -> None:
    """Back to the queue, keeping its attempts: a worker gave up on it
    without its fault (the AI limit, the worker's own end)."""
    conn.execute("UPDATE tasks SET state = 'queued', worker = NULL, pid = NULL, started_at = NULL, "
                 "heartbeat_at = NULL, waiting_for = ?, error = ? WHERE id = ? AND state = 'running'",
                 (why, why, task_id))


def stop_requested(conn: sqlite3.Connection, task_id: int) -> bool:
    row = conn.execute("SELECT stop_requested FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return bool(row and row[0])


def sweep(conn: sqlite3.Connection, at: Optional[datetime] = None, kill=None) -> List[str]:
    """Running tasks nobody beats for: a worker's task is queued again (its
    process, if any is left, is killed first: kill(pid)), until MAX_ATTEMPTS;
    a process that registered itself is marked interrupted. Returns a line
    per task it touched."""
    at = at or now()
    said = []
    with transaction(conn):
        for row in conn.execute("SELECT * FROM tasks WHERE state = 'running'").fetchall():
            if not is_stale(row["heartbeat_at"], at):
                continue
            if row["pid"] and kill is not None and row["worker"] != "external":
                try:
                    kill(row["pid"])
                except Exception:  # noqa: BLE001 — a process already gone is the usual case
                    pass
            if row["worker"] == "external" or row["stop_requested"]:
                state = "stopped" if row["stop_requested"] else "interrupted"
                conn.execute("UPDATE tasks SET state = ?, ended_at = ?, error = ? WHERE id = ?",
                             (state, iso(at), "stopped beating: killed or crashed", row["id"]))
                said.append(f"#{row['id']} {row['kind']}: {state} (stopped beating)")
            elif row["attempts"] >= MAX_ATTEMPTS:
                conn.execute("UPDATE tasks SET state = 'failed', ended_at = ?, error = ? WHERE id = ?",
                             (iso(at), f"interrupted {row['attempts']} times", row["id"]))
                said.append(f"#{row['id']} {row['kind']}: failed after {row['attempts']} interruptions")
            else:
                conn.execute("UPDATE tasks SET state = 'queued', worker = NULL, pid = NULL, "
                             "heartbeat_at = NULL, started_at = NULL, error = ? WHERE id = ?",
                             (f"interrupted (its worker stopped beating); queued again", row["id"]))
                said.append(f"#{row['id']} {row['kind']}: queued again after an interruption")
    return said


def append_log(task: dict, text: str) -> None:
    """Lines into the task's log file, which the app and `log` read."""
    target = Path(task["log_path"] or logs_dir() / f"{task['id']}.log")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as out:
        for line in str(text).splitlines():
            if line.strip():
                out.write(line.rstrip() + "\n")


# --- a process that runs itself: pipeline.py, cv_batch.py -------------------------

class Registered:
    """`with Registered("rest", identity, log_path=...)`: a run started by hand
    is listed like any other task (the owner, 2026-10-21: "every task is in
    the list"). Under a worker (TASK_ENV set) it is that task already, and
    nothing is added. A failure to reach the queue never stops the run.

    A stop asked in the panel interrupts the main thread (KeyboardInterrupt),
    so the run ends the way Ctrl+C ends it."""

    def __init__(self, kind: str, identity: Optional[str], log_path: Optional[Path] = None,
                 title: str = "", args: Optional[dict] = None, interrupt=None) -> None:
        self.kind, self.identity, self.log_path = kind, identity, log_path
        self.title, self.args = title, args
        self.task_id: Optional[int] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._interrupt = interrupt
        self._asked = False

    def __enter__(self) -> "Registered":
        if os.environ.get(TASK_ENV):
            return self
        try:
            with session() as conn, transaction(conn):
                self.task_id = _insert(
                    conn, self.kind, self.identity, origin=default_origin(), title=self.title, args=self.args,
                    state="running", worker="external", pid=os.getpid(), host=socket.gethostname(),
                    started_at=iso(), heartbeat_at=iso(), attempts=1,
                    log_path=str(self.log_path) if self.log_path else None)
        except (sqlite3.Error, OSError) as exc:
            common.eprint(f"(not listed in the task queue: {type(exc).__name__}: {exc})")
            return self
        self._thread = threading.Thread(target=self._beat, name="taskq-heartbeat", daemon=True)
        self._thread.start()
        return self

    def _beat(self) -> None:
        while not self._stop.wait(HEARTBEAT_SECONDS):
            try:
                with session() as conn:
                    beat(conn, [self.task_id])
                    asked = stop_requested(conn, self.task_id)
            except (sqlite3.Error, OSError):
                continue
            if asked and not self._asked:
                self._asked = True
                (self._interrupt or _interrupt_main)()

    def __exit__(self, exc_type, exc, _tb) -> bool:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=HEARTBEAT_SECONDS + 5)
        if self.task_id is None:
            return False
        if exc_type is None or (issubclass(exc_type, SystemExit) and not exc.code):
            state, error = "done", None
        elif issubclass(exc_type, KeyboardInterrupt):
            state, error = ("stopped" if self._asked else "interrupted"), "interrupted"
        elif issubclass(exc_type, SystemExit) and exc.code == AI_LIMIT_EXIT:
            # the tool met the usage limit and recorded it (block_ai)
            state, error = "failed", f"stopped at the AI usage limit (exit {exc.code})"
        elif issubclass(exc_type, SystemExit):
            state, error = "failed", f"exit {exc.code}"
        else:
            state, error = "failed", f"{exc_type.__name__}: {exc}"
        try:
            with session() as conn:
                finish(conn, self.task_id, state, error)
        except (sqlite3.Error, OSError):
            pass
        return False


def _interrupt_main() -> None:
    import _thread
    _thread.interrupt_main()


# --- the command line ----------------------------------------------------------------

def _line(task: dict) -> str:
    who = task["identity"] or "-"
    what = task["kind"] + (f" {task['vacancy_id']}" if task.get("vacancy_id") else "")
    tail = ""
    if task["state"] == "queued" and task.get("waiting_for"):
        tail = f"  waits for {task['waiting_for']}"
    elif task.get("error"):
        tail = f"  {task['error']}"
    return f"#{task['id']:<5} {task['state']:<11} {who:<10} {what}  ({task['origin']}){tail}"


def _print(value, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, indent=2, default=str))
    elif isinstance(value, list):
        for task in value:
            print(_line(task))
        if not value:
            print("no tasks")
    elif isinstance(value, dict) and "id" in value:
        print(_line(value))
    else:
        print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _follow(task_id: int, follow: bool, out=None) -> int:
    out = out or sys.stdout
    offset = 0
    while True:
        with session() as conn:
            task = get(conn, task_id)
        if task is None:
            print(f"no task #{task_id}", file=sys.stderr)
            return 1
        log = Path(task["log_path"]) if task.get("log_path") else None
        if log and log.exists():
            with log.open("r", encoding="utf-8", errors="replace") as fh:
                fh.seek(offset)
                chunk = fh.read()
                offset = fh.tell()
            if chunk:
                out.write(chunk)
                out.flush()
        if not follow or task["state"] not in ACTIVE:
            return 0
        time.sleep(1)


def wait(task_ids: Sequence[int], timeout: Optional[float] = None, poll: float = 5.0) -> Dict[int, str]:
    since = time.monotonic()
    while True:
        with session() as conn:
            states = {i: (get(conn, i) or {"state": "missing"})["state"] for i in task_ids}
        if all(s not in ACTIVE for s in states.values()):
            return states
        if timeout is not None and time.monotonic() - since > timeout:
            return states
        time.sleep(poll)


def _schedule_parser(parser: argparse.ArgumentParser) -> None:
    import schedules
    sub = parser.add_subparsers(dest="action", required=True)

    def fields(p, new: bool) -> None:
        if new:
            p.add_argument("what", choices=sorted(schedules.WHAT))
        else:
            p.add_argument("id", type=int)
            p.add_argument("--what", choices=sorted(schedules.WHAT))
        p.add_argument("--identities", help="comma-separated prefixes, or 'all' (every active one)",
                       default="all" if new else None)
        p.add_argument("--cron", required=new, help='minute hour day month weekday, local time: "0 7 * * *"')
        p.add_argument("--missed", choices=schedules.MISSED, default="catch_up" if new else None,
                       help="a run missed while the computer was off or asleep")
        p.add_argument("--args", help="JSON: a clean-up's filters, {\"all\": true} for a batch")
        p.add_argument("--name")
        p.add_argument("--json", action="store_true")

    fields(sub.add_parser("add", help="a new schedule"), True)
    fields(sub.add_parser("set", help="change a schedule"), False)
    for name, text in (("on", "turn a schedule on"), ("off", "turn a schedule off"),
                       ("remove", "delete a schedule (its tasks stay)")):
        sub.add_parser(name, help=text).add_argument("id", type=int)
    sub.add_parser("list", help="every schedule, its next run and its last result").add_argument(
        "--json", action="store_true")
    p = sub.add_parser("next", help="the next runs of a cron line")
    p.add_argument("cron")
    p.add_argument("-n", type=int, default=3)
    sub.add_parser("due", help="queue what is due now (the workers do this every few seconds)")


def _schedule_main(args) -> int:
    import schedules
    try:
        with session() as conn:
            if args.action in ("add", "set"):
                fields = {k: getattr(args, k) for k in ("what", "identities", "cron", "missed", "name")
                          if getattr(args, k, None) is not None}
                if args.args is not None:
                    fields["args"] = json.loads(args.args)
                if args.action == "add":
                    what = fields.pop("what")
                    reply = schedules.add(conn, what, **fields)
                else:
                    reply = schedules.update(conn, args.id, **fields)
                _print(reply, True)
            elif args.action in ("on", "off"):
                _print(schedules.update(conn, args.id, enabled=args.action == "on"), True)
            elif args.action == "remove":
                removed = schedules.remove(conn, args.id)
                print(json.dumps({"removed": removed}))
                return 0 if removed else 1
            elif args.action == "list":
                rows = schedules.listing(conn)
                if args.json:
                    _print(rows, True)
                for s in [] if args.json else rows:
                    print(f"#{s['id']:<4} {'on ' if s['enabled'] else 'off'} {s['cron']:<18} {s['what']:<9} "
                          f"{','.join(s['identities']):<16} next {s['next_at'] or '-'}  "
                          f"last {s['last_result'] or '-'}: {s['last_note'] or ''}")
            elif args.action == "next":
                print(json.dumps([iso(m.astimezone()) for m in schedules.next_runs(args.cron, args.n)]))
            elif args.action == "due":
                for line in schedules.run_due(conn):
                    print(line)
    except ValueError as exc:   # CronError, a bad field, bad JSON
        print(f"taskq schedule: {exc}", file=sys.stderr)
        return 2
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="The task queue: every long piece of work (data/tasks.sqlite)")
    common_args = argparse.ArgumentParser(add_help=False)
    common_args.add_argument("--json", action="store_true", help="print JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    def command(name: str, **kw) -> argparse.ArgumentParser:
        return sub.add_parser(name, parents=[common_args], **kw)


    p = command("add", help="queue one task")
    p.add_argument("kind", choices=sorted(KINDS))
    p.add_argument("--identity")
    p.add_argument("--vacancy")
    p.add_argument("--title", default="")
    p.add_argument("--company", default="")
    p.add_argument("--instructions", default="", help="for a CV or a cover letter")
    p.add_argument("--args", default=None, help="JSON object for the tool (clean-up filters, ...)")
    p.add_argument("--after", type=int, nargs="*", default=[], help="start after these tasks ended done")
    p.add_argument("--origin", choices=ORIGINS)

    p = command("collect", help="a whole collection: top, LinkedIn, the rest, CV/CL")
    p.add_argument("identities", nargs="+")
    p.add_argument("--no-linkedin", action="store_true")
    p.add_argument("--no-documents", action="store_true")
    p.add_argument("--origin", choices=ORIGINS)

    p = command("list", help="queued and running tasks (--all: every task)")
    p.add_argument("--all", action="store_true")
    command("show", help="one task").add_argument("id", type=int)
    p = command("log", help="a task's log")
    p.add_argument("id", type=int)
    p.add_argument("--follow", "-f", action="store_true")
    command("stop", help="stop a task").add_argument("id", type=int)
    p = command("wait", help="until the tasks end; exit 0 when all ended done")
    p.add_argument("ids", type=int, nargs="+")
    p.add_argument("--timeout", type=float)
    p = command("hide", help="clear ended tasks from the panel (no ids: all ended)")
    p.add_argument("ids", type=int, nargs="*")
    command("status", help="the workers and what they run")
    command("current", help="the queue task this process runs in, if a worker started it")
    _schedule_parser(command("schedule", help="work on a timetable (tools/schedules.py)"))
    args = parser.parse_args(argv)
    if args.command == "schedule":
        return _schedule_main(args)

    try:
        with session() as conn:
            if args.command == "add":
                extra = json.loads(args.args) if args.args else {}
                if args.instructions:
                    extra["instructions"] = args.instructions
                _print(add(conn, args.kind, args.identity, origin=args.origin, vacancy_id=args.vacancy,
                           title=args.title, company=args.company, args=extra, after=args.after), True)
            elif args.command == "collect":
                made = [collection(conn, p, origin=args.origin, linkedin=not args.no_linkedin,
                                   documents=not args.no_documents) for p in args.identities]
                if args.json:
                    _print(made, True)
                else:
                    for one in made:
                        print(("queued:" if one["added"] else "already queued:"))
                        _print(one["group"], False)
            elif args.command == "list":
                _print(tasks(conn, active_only=not args.all), args.json)
            elif args.command == "show":
                task = get(conn, args.id)
                if task is None:
                    print(f"no task #{args.id}", file=sys.stderr)
                    return 1
                _print(task, True)
            elif args.command == "stop":
                reply = stop(conn, args.id)
                _print(reply, True)
                return 0 if reply["ok"] else 1
            elif args.command == "hide":
                print(json.dumps({"hidden": hide(conn, args.ids or None)}))
            elif args.command == "current":
                # An agent session asks this before long work: started by a
                # worker it is that task already; otherwise it adds one.
                own = os.environ.get(TASK_ENV)
                task = get(conn, int(own)) if own and own.isdigit() else None
                _print({"task": task["id"] if task else None,
                        "kind": task["kind"] if task else None,
                        "identity": task["identity"] if task else None}, True)
            elif args.command == "status":
                _print({"workers": live_workers(conn), "ai_blocked_until": state_value(conn, "ai_blocked_until"),
                        "running": tasks(conn, active_only=True, include_hidden=True)}, True)
        if args.command == "log":
            return _follow(args.id, args.follow)
        if args.command == "wait":
            states = wait(args.ids, args.timeout)
            print(json.dumps(states))
            return 0 if all(s == "done" for s in states.values()) else 1
    except ValueError as exc:
        print(f"taskq: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
