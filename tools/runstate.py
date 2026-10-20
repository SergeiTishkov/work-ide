"""
Whether a pipeline run is going right now, in the shared database.

WHY
---
A run takes an hour, and it can be started from the desktop app, by the agent
in a terminal, or by hand. The app shows whether one is going — whoever
started it — and two runs on one base must not overlap: each loads the base,
works for an hour and saves it whole, so the second save would silently undo
the first. The base is shared by every identity (tools/db.py), so that holds
across identities too: one run at a time, whichever identity it is for.

HOW, AND WHY IT CANNOT GET STUCK
--------------------------------
A run inserts a `pipeline_runs` row with status 'running' and, from a
background thread, refreshes its `heartbeat_at` every HEARTBEAT_SECONDS. It
also records the current stage (tools/progress.py reports stages here).

  * Normal end or an exception: the `finally` marks the row 'finished' or
    'failed' — the indicator goes back by itself.
  * A hard kill (the app's Stop, a crash, a power cut) skips `finally`. The
    heartbeat stops with the process, so after STALE_AFTER_SECONDS every
    reader treats the row as not running, and the next run marks it
    'interrupted'. The app, on the same machine, also checks the pid and
    sees a dead run at once.

Nothing here depends on the operating system: a timestamp in a database file.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import db  # noqa: E402
import progress  # noqa: E402

HEARTBEAT_SECONDS = 10
# Four missed beats. Short enough that a killed run frees the base quickly,
# long enough that one slow write (saving the base holds the lock for seconds)
# does not make a live run look dead.
STALE_AFTER_SECONDS = 45
# How often a run that waits for the base (PipelineRun(wait=True)) or for
# LinkedIn (LinkedInFetch) asks again, and how often it says it is waiting.
WAIT_POLL_SECONDS = 15
WAIT_LOG_SECONDS = 600


class AlreadyRunningError(RuntimeError):
    """Another pipeline run is alive."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def is_stale(heartbeat_at: str, now: Optional[datetime] = None) -> bool:
    try:
        beat = datetime.fromisoformat(heartbeat_at)
    except (TypeError, ValueError):
        return True
    return (now or _now()) - beat > timedelta(seconds=STALE_AFTER_SECONDS)


def current() -> Optional[dict]:
    """The live run, of whichever identity, or None."""
    if not db.exists():
        return None
    with db.session() as conn:
        row = conn.execute(
            "SELECT id, identity_id, started_at, heartbeat_at, stage, pid, host "
            "FROM pipeline_runs WHERE status = 'running' ORDER BY id DESC LIMIT 1").fetchone()
    if row is None or is_stale(row[3]):
        return None
    return dict(zip(("id", "identity", "started_at", "heartbeat_at", "stage", "pid", "host"),
                    row))


def _wait(what: str, exc: Exception, since: float, told: Optional[float]) -> float:
    """One poll of a wait: says so now and then, sleeps. Returns when it last
    said so."""
    now = time.monotonic()
    if told is None or now - told >= WAIT_LOG_SECONDS:
        waited = progress.duration(now - since)
        progress.log(f"   waiting for {what} ({waited} so far): {exc}")
        told = now
    time.sleep(WAIT_POLL_SECONDS)
    return told


class PipelineRun:
    """`with PipelineRun(log_path=...):` around a whole pipeline run.
    wait=True: while another run holds the base, wait for it rather than
    raise AlreadyRunningError (the LinkedIn run's merge, pipeline.py
    --linkedin)."""

    def __init__(self, log_path: Optional[Path] = None, wait: bool = False) -> None:
        self.log_path = str(log_path) if log_path else None
        self.wait = wait
        self.run_id: Optional[int] = None
        self.stage: Optional[str] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def __enter__(self) -> "PipelineRun":
        since, told = time.monotonic(), None
        while True:
            try:
                return self._enter()
            except AlreadyRunningError as exc:
                if not self.wait:
                    raise
                told = _wait("the base", exc, since, told)

    def _enter(self) -> "PipelineRun":
        now = _now()
        with db.session() as conn:
            for run_id, heartbeat_at in conn.execute(
                    "SELECT id, heartbeat_at FROM pipeline_runs WHERE status = 'running'"
            ).fetchall():
                if is_stale(heartbeat_at, now):
                    conn.execute(
                        "UPDATE pipeline_runs SET status = 'interrupted', finished_at = ?, "
                        "error = 'stopped beating: killed or crashed' WHERE id = ?",
                        (_iso(now), run_id))
                else:
                    other = conn.execute(
                        "SELECT started_at, pid, host, stage, identity_id FROM pipeline_runs "
                        "WHERE id = ?", (run_id,)).fetchone()
                    raise AlreadyRunningError(
                        f"another pipeline run is going (identity {other[4] or '?'}): started "
                        f"{other[0]}, pid {other[1]} on {other[2]}, stage: {other[3] or '?'}. "
                        f"The base is shared, and two runs at once would overwrite each "
                        f"other's work. If that process is gone, its heartbeat expires "
                        f"within {STALE_AFTER_SECONDS} s.")
            self.run_id = conn.execute(
                "INSERT INTO pipeline_runs (identity_id, started_at, heartbeat_at, status, pid, "
                "host, log_path) VALUES (?, ?, ?, 'running', ?, ?, ?)",
                (common.ACTIVE_IDENTITY, _iso(now), _iso(now), os.getpid(),
                 socket.gethostname(), self.log_path),
            ).lastrowid
        progress.set_stage_listener(self._on_stage)
        self._thread = threading.Thread(target=self._beat, name="pipeline-heartbeat", daemon=True)
        self._thread.start()
        return self

    def _on_stage(self, name: str) -> None:
        self.stage = name

    def _write(self, sql: str, params: tuple) -> None:
        with db.session() as conn:
            conn.execute(sql, params)

    def _beat(self) -> None:
        while not self._stop.wait(HEARTBEAT_SECONDS):
            try:
                self._write("UPDATE pipeline_runs SET heartbeat_at = ?, stage = ? WHERE id = ?",
                            (_iso(_now()), self.stage, self.run_id))
            except Exception as exc:  # noqa: BLE001 — a missed beat must not kill the run
                progress.log(f"   (heartbeat not recorded: {type(exc).__name__}: {exc})")

    def __exit__(self, exc_type, exc, _tb) -> bool:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=HEARTBEAT_SECONDS + 5)
        progress.set_stage_listener(None)
        if exc_type is None:
            status, error = "finished", None
        elif issubclass(exc_type, KeyboardInterrupt):
            status, error = "interrupted", "interrupted by the user"
        else:
            status, error = "failed", f"{exc_type.__name__}: {exc}"
        self._write(
            "UPDATE pipeline_runs SET status = ?, finished_at = ?, heartbeat_at = ?, "
            "stage = ?, error = ? WHERE id = ?",
            (status, _iso(_now()), _iso(_now()), self.stage, error, self.run_id))
        return False


class LinkedInFetch:
    """`with LinkedInFetch():` around a LinkedIn fetch: one at a time on this
    machine, whichever identity it is for. They share one address, and
    LinkedIn's rate limit is per address: two walks at once would each meet
    twice the 429s (the owner, 2026-10-20: LinkedIn runs beside the other
    sources, in a lane of its own).

    A file beside the shared base, not a row in it: the fetch must not write
    the base while another run holds it. Its time is refreshed every
    HEARTBEAT_SECONDS; a file not refreshed for STALE_AFTER_SECONDS was left
    by a killed process and is taken over. With wait=False a held lock raises
    AlreadyRunningError; otherwise the fetch waits its turn."""

    NAME = "linkedin_fetch.lock"

    def __init__(self, wait: bool = True) -> None:
        self.wait = wait
        self.path = Path(common.DB_PATH).parent / self.NAME
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def holder(self) -> str:
        try:
            info = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return "another LinkedIn fetch"
        return (f"the LinkedIn fetch of {info.get('identity') or '?'} (pid {info.get('pid')} "
                f"on {info.get('host')}, started {info.get('started_at')})")

    def _stale(self) -> bool:
        try:
            age = time.time() - self.path.stat().st_mtime
        except OSError:
            return False
        return age > STALE_AFTER_SECONDS

    def _take(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self._stale():
            self.path.unlink(missing_ok=True)
        try:
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise AlreadyRunningError(f"{self.holder()} is going; one at a time: "
                                      f"the address and its rate limit are shared") from None
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump({"identity": common.ACTIVE_IDENTITY, "pid": os.getpid(),
                       "host": socket.gethostname(), "started_at": _iso(_now())}, out)

    def __enter__(self) -> "LinkedInFetch":
        since, told = time.monotonic(), None
        while True:
            try:
                self._take()
                break
            except AlreadyRunningError as exc:
                if not self.wait:
                    raise
                told = _wait("LinkedIn", exc, since, told)
        self._thread = threading.Thread(target=self._beat, name="linkedin-heartbeat", daemon=True)
        self._thread.start()
        return self

    def _beat(self) -> None:
        while not self._stop.wait(HEARTBEAT_SECONDS):
            try:
                os.utime(self.path)
            except OSError:
                pass

    def __exit__(self, *_exc) -> bool:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=HEARTBEAT_SECONDS + 5)
        self.path.unlink(missing_ok=True)
        return False
