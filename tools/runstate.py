"""
Whether a pipeline run is going right now, in the identity's database.

WHY
---
A run takes an hour, and it can be started from the desktop app, by the agent
in a terminal, or by hand. The app shows whether one is going — whoever
started it — and two runs on one base must not overlap: each loads the base,
works for an hour and saves it whole, so the second save would silently undo
the first.

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

import os
import socket
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402
import progress  # noqa: E402

HEARTBEAT_SECONDS = 10
# Four missed beats. Short enough that a killed run frees the base quickly,
# long enough that one slow write (saving the base holds the lock for seconds)
# does not make a live run look dead.
STALE_AFTER_SECONDS = 45


class AlreadyRunningError(RuntimeError):
    """Another run of this identity's pipeline is alive."""


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
    """The live run of the active identity, or None."""
    if not db.exists():
        return None
    with db.session() as conn:
        row = conn.execute(
            "SELECT id, started_at, heartbeat_at, stage, pid, host FROM pipeline_runs "
            "WHERE status = 'running' ORDER BY id DESC LIMIT 1").fetchone()
    if row is None or is_stale(row[2]):
        return None
    return dict(zip(("id", "started_at", "heartbeat_at", "stage", "pid", "host"), row))


class PipelineRun:
    """`with PipelineRun(log_path=...):` around a whole pipeline run."""

    def __init__(self, log_path: Optional[Path] = None) -> None:
        self.log_path = str(log_path) if log_path else None
        self.run_id: Optional[int] = None
        self.stage: Optional[str] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def __enter__(self) -> "PipelineRun":
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
                        "SELECT started_at, pid, host, stage FROM pipeline_runs WHERE id = ?",
                        (run_id,)).fetchone()
                    raise AlreadyRunningError(
                        f"another pipeline run of this identity is going: started "
                        f"{other[0]}, pid {other[1]} on {other[2]}, stage: {other[3] or '?'}. "
                        f"Two runs at once would overwrite each other's work. If that "
                        f"process is gone, its heartbeat expires within "
                        f"{STALE_AFTER_SECONDS} s.")
            self.run_id = conn.execute(
                "INSERT INTO pipeline_runs (started_at, heartbeat_at, status, pid, host, log_path) "
                "VALUES (?, ?, 'running', ?, ?, ?)",
                (_iso(now), _iso(now), os.getpid(), socket.gethostname(), self.log_path),
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
