"""
Progress lines for long runs: what the pipeline is doing, and how far along.

WHY
---
A full run takes an hour and used to print nothing between its first line and
its last. On 2026-09-30 the only way to learn what a silent run was doing was
to attach a profiler to it (it was rescoring, fine — but it should have said
so). A person watching the desktop app's log, or an agent waiting on the
command, deserves the same answer without a profiler.

WHAT IT PRINTS
--------------
    [00:15:02] >> rescore the base (28 455 vacancies)
    [00:15:17]    rescore: 6 000/28 455 (21%), ~0:56 left
    [00:16:14] ok rescore the base - 1:12

Every stage says when it starts and how long it took; long loops report at most
every PROGRESS_EVERY seconds. Lines go to stderr (stdout stays the result a
caller parses) and, once open_log() was called, into a log file as well.
ASCII only: a Windows console in a legacy code page must not crash a run over
an arrow.
"""
from __future__ import annotations

import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

PROGRESS_EVERY = 15.0

_log_file = None
# Told the name of every stage as it starts; tools/runstate.py records it so
# the desktop app can show what a run is doing.
_stage_listener = None


def set_stage_listener(listener) -> None:
    global _stage_listener
    _stage_listener = listener


def open_log(path: Path) -> Path:
    """Mirrors every line into `path` (appending) until close_log()."""
    global _log_file
    close_log()
    path.parent.mkdir(parents=True, exist_ok=True)
    _log_file = path.open("a", encoding="utf-8")
    return path


def close_log() -> None:
    global _log_file
    if _log_file is not None:
        _log_file.close()
        _log_file = None


def log(message: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
    print(line, file=sys.stderr, flush=True)
    if _log_file is not None:
        _log_file.write(line + "\n")
        _log_file.flush()


def duration(seconds: float) -> str:
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds} s"
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02}:{secs:02}" if hours else f"{minutes}:{secs:02}"


def number(n: int) -> str:
    return f"{n:,}".replace(",", " ")


class Stage:
    """Handed to the body of `with stage(...)`: `.note` becomes part of the
    closing line, so a stage can report what it found."""

    def __init__(self) -> None:
        self.note = ""


@contextmanager
def stage(name: str) -> Iterator[Stage]:
    started = time.monotonic()
    log(f">> {name}")
    if _stage_listener is not None:
        _stage_listener(name)
    current = Stage()
    try:
        yield current
    except BaseException as exc:
        log(f"!! {name} - failed after {duration(time.monotonic() - started)}: "
            f"{type(exc).__name__}: {exc}")
        raise
    note = f" ({current.note})" if current.note else ""
    log(f"ok {name} - {duration(time.monotonic() - started)}{note}")


class Progress:
    """Counts through a long loop and reports now and then:

        tick = Progress(len(items), "rescore")
        for item in items:
            ...
            tick()
    """

    def __init__(self, total: int, label: str, every: Optional[float] = None) -> None:
        self.total = total
        self.label = label
        self.every = PROGRESS_EVERY if every is None else every
        self.done = 0
        self.started = time.monotonic()
        self.last_report = self.started
        self.done_at_last_report = 0

    def __call__(self, step: int = 1) -> None:
        self.done += step
        now = time.monotonic()
        if now - self.last_report < self.every or self.done >= self.total:
            return
        # The estimate uses the pace since the last report, not the average
        # since the start: in the link check the fast answers come first and
        # the slow ones last, and an average promised "2:30 left" for many
        # minutes on end (2026-09-30).
        window = now - self.last_report
        recent = self.done - self.done_at_last_report
        self.last_report = now
        self.done_at_last_report = self.done
        elapsed = now - self.started
        if recent and window > 0:
            rate = recent / window
        else:
            rate = self.done / elapsed if elapsed > 0 else 0
        left = (self.total - self.done) / rate if rate else 0
        share = 100 * self.done // self.total if self.total else 100
        log(f"   {self.label}: {number(self.done)}/{number(self.total)} ({share}%), "
            f"~{duration(left)} left")
