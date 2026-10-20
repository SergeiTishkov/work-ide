#!/usr/bin/env python3
"""The AI usage limit: one recogniser and one error for every `claude -p`
call (task 0057).

When the account's usage limit runs out, every call is refused until it
resets, hours later. Before this module a refused call was an ordinary
error: `ai_screen` went on to the next posting and sent one refused call per
posting left. Now each `call_model` passes its finished process to
`check()`, which raises `UsageLimit`; a stage that meets it stops sending,
keeps what it finished, and the tool exits with `EXIT_CODE`. The task queue
(tools/taskd.py) reads that code, or the line `mark()` prints, puts the task
back and holds every task that needs AI until the reset.

The answer's exact shape at the limit was not captured on this machine
(2026-10-21: no refused call in any log). The recogniser takes the wordings
Claude Code is known to print: "Claude AI usage limit reached|<epoch>",
"5-hour limit reached ∙ resets 3pm", "You've hit your limit · resets 5pm
(Europe/Berlin)", "Your limit will reset at 5pm". It looks only at an
answer that failed (`is_error`, or a non-zero exit), so a posting or a CV
that mentions a limit is never read as one.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

# EX_TEMPFAIL: "try again later".
EXIT_CODE = 75
# The line a tool prints when it stops at the limit; the worker looks for it.
MARK = "AI usage limit reached"

_LIMIT = re.compile(
    r"usage limit reached|hit your (?:usage )?limit|"
    r"(?:5-hour|five-hour|session|daily|weekly|opus|sonnet)(?: usage)? limit (?:reached|hit)|"
    r"limit will reset|out of (?:extra )?usage",
    re.I)
_EPOCH = re.compile(r"\|\s*(\d{10})\b")
_ISO = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?")
_CLOCK = re.compile(r"\bresets?\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?(?:\s*\(([A-Za-z_]+/[A-Za-z_/]+)\))?",
                    re.I)
_IN = re.compile(r"\bresets?\s+in\s+(\d+)\s*(h|hours?|m|min|minutes?)\b", re.I)


class UsageLimit(Exception):
    """The account's usage limit: no call goes through until `resets_at`
    (None when the answer did not say)."""

    def __init__(self, text: str, resets_at: Optional[datetime] = None) -> None:
        self.text = (text or "").strip()[:300]
        self.resets_at = resets_at
        super().__init__(f"{MARK}; resets at {self.when()}: {self.text}")

    def when(self) -> str:
        return self.resets_at.isoformat(timespec="minutes") if self.resets_at else "unknown"

    def as_json(self) -> dict:
        return {"ok": False, "error": str(self), "ai_limit": {"resets_at": self.resets_at.isoformat()
                                                              if self.resets_at else None}}


def _zone(name: Optional[str]):
    if not name:
        return None
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 — no tz database here (Windows without tzdata): local time
        return None


def reset_time(text: str, now: Optional[datetime] = None) -> Optional[datetime]:
    """When the limit resets, as the text says it; None when it does not."""
    now = now or datetime.now(timezone.utc)
    found = _EPOCH.search(text)
    if found:
        return datetime.fromtimestamp(int(found.group(1)), timezone.utc)
    found = _IN.search(text)
    if found:
        amount, unit = int(found.group(1)), found.group(2).lower()
        return now + (timedelta(hours=amount) if unit.startswith("h") else timedelta(minutes=amount))
    found = _CLOCK.search(text)
    if found:
        hour, minute, half, zone = int(found.group(1)), int(found.group(2) or 0), found.group(3), found.group(4)
        if half:
            hour = hour % 12 + (12 if half.lower().startswith("p") else 0)
        if hour > 23 or minute > 59:
            return None
        tz = _zone(zone)
        here = now.astimezone(tz) if tz else now.astimezone()
        moment = here.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if moment <= here:
            moment += timedelta(days=1)
        return moment.astimezone(timezone.utc)
    found = _ISO.search(text)
    if found:
        try:
            moment = datetime.fromisoformat(found.group(0).replace("Z", "+00:00"))
        except ValueError:
            return None
        return moment if moment.tzinfo else moment.astimezone()
    return None


def recognise(text: str, now: Optional[datetime] = None) -> Optional[UsageLimit]:
    """A UsageLimit when the text of a refused call says the limit is used up."""
    if not text or not _LIMIT.search(text):
        return None
    return UsageLimit(text, reset_time(text, now))


def check(completed, now: Optional[datetime] = None) -> None:
    """Raises UsageLimit when a finished `claude -p --output-format json`
    process was refused for the usage limit. Anything else is left to the
    caller's own error handling."""
    stdout, stderr = getattr(completed, "stdout", "") or "", getattr(completed, "stderr", "") or ""
    try:
        answer = json.loads(stdout)
    except ValueError:
        answer = None
    failed = (getattr(completed, "returncode", 0) or 0) != 0 or not isinstance(answer, dict) or answer.get("is_error")
    if not failed:
        return
    parts = [stderr]
    if isinstance(answer, dict):
        parts.append(str(answer.get("result") or ""))
        parts.append(str(answer.get("subtype") or ""))
    else:
        parts.append(stdout)
    limit = recognise("\n".join(p for p in parts if p), now)
    if limit is not None:
        raise limit


def mark(limit: UsageLimit) -> str:
    """The line a tool prints when it stops at the limit."""
    return str(limit)


def record(limit: UsageLimit) -> None:
    """Holds the queue's AI tasks until the reset (tools/taskq.py), whoever
    ran the tool: a worker, the agent or a terminal. Never raises: the
    tool's own exit code and line still say it."""
    try:
        import taskq
        with taskq.session() as conn:
            taskq.block_ai(conn, limit.resets_at)
    except Exception:  # noqa: BLE001 — no queue file yet, or it is locked for a moment
        pass


def from_line(line: str, now: Optional[datetime] = None) -> Optional[UsageLimit]:
    """A UsageLimit from one line of a task's output: a tool's `mark()`
    line, or the agent's final stream-json event refused for the limit."""
    text = line.strip()
    if text.startswith("{"):
        try:
            event = json.loads(text)
        except ValueError:
            return None
        if isinstance(event, dict):
            limit = event.get("ai_limit")
            if isinstance(limit, dict):
                resets = limit.get("resets_at")
                try:
                    return UsageLimit(str(event.get("error") or MARK),
                                      datetime.fromisoformat(resets) if resets else None)
                except ValueError:
                    return UsageLimit(str(event.get("error") or MARK))
            if event.get("type") == "result" and event.get("is_error"):
                return recognise(str(event.get("result") or ""), now)
        return None
    at = text.find(MARK + "; resets at ")
    if at < 0:
        return None
    rest = text[at + len(MARK + "; resets at "):]
    when, _, said = rest.partition(": ")
    try:
        resets = None if when == "unknown" else datetime.fromisoformat(when)
    except ValueError:
        resets = None
    return UsageLimit(said or MARK, resets)
