"""
Schedules (task 0061): the task queue's work on a timetable.

WHY
---
Collections were started by hand. With the task service (0056) running
outside any session, the owner can say when instead: "collect for every
identity at 07:00", "a clean-up every Sunday" (the owner, 2026-10-21). What a
schedule starts is an ordinary task of the queue (origin "schedule"): it is
listed in the app's panel, runs and ends like any other.

    python tools/taskq.py schedule add collect --identities all --cron "0 7 * * *"
    python tools/taskq.py schedule add clean --identities sharp --cron "0 9 * * 0" \\
        --args '{"ages": ["older"], "statuses": ["new"]}' --missed skip
    python tools/taskq.py schedule list
    python tools/taskq.py schedule off 3
    python tools/taskq.py schedule next "*/30 9-18 * * 1-5"

THE TIMETABLE is a cron line in the machine's local time: minute, hour, day
of the month, month, day of the week (0 or 7 is Sunday). `*`, lists, ranges
and steps (`*/15`, `1-5`, `9-18/3`), the names jan..dec and sun..sat, and
@hourly, @daily, @weekly, @monthly. As in cron, when both days are given a
day matching either counts.

A RUN MISSED while the computer was off or asleep (the worker found it more
than LATE_AFTER after its time): each schedule says whether it is caught up
once, or skipped (the owner, 2026-10-21: both ways, per schedule). Several
missed runs are one run caught up, never a burst. A schedule whose previous
run is still queued or going does not queue another, and says so.

The workers (tools/taskd.py) look every CHECK_EVERY_SECONDS; any of them may,
and a run is claimed in one transaction, so two workers never queue it twice.
A schedule is due only while a worker runs: with no worker registered with
Task Scheduler (`taskd.py install`), only while the app's worker is up.
Waking the computer for a schedule is not done (task 0061).
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import taskq  # noqa: E402

# what a schedule can start -> the task kind it queues ("collect": the group)
WHAT: Dict[str, str] = {
    "collect": "a collection: the top, LinkedIn, the rest, CV/CL",
    "linkedin": "LinkedIn alone",
    "rest": "the rest of the base",
    "clean": "a clean-up, with the filters of the Clean up dialog",
    "cv_batch": "a CV/CL batch",
    "links": "a re-check of the shortlist's links",
}
MISSED = ("catch_up", "skip")
ALL = "all"
CLEAN_FILTERS = ("ages", "statuses", "classes")
# found later than this after its time, a run was missed (off or asleep);
# a worker looks far more often than this while the computer is on
LATE_AFTER = timedelta(minutes=10)
CHECK_EVERY_SECONDS = 20
# a timetable that matches nothing in this many years matches nothing
SEARCH_YEARS = 5


# --- the cron line ------------------------------------------------------------------

MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
WEEKDAYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
MACROS = {"@hourly": "0 * * * *", "@daily": "0 0 * * *", "@midnight": "0 0 * * *",
          "@weekly": "0 0 * * 0", "@monthly": "0 0 1 * *"}
FIELDS = (("minute", 0, 59, None), ("hour", 0, 23, None), ("day of the month", 1, 31, None),
          ("month", 1, 12, MONTHS), ("day of the week", 0, 7, WEEKDAYS))


class CronError(ValueError):
    pass


def _value(text: str, names: Optional[List[str]], field: str) -> int:
    if names and text.lower()[:3] in names and not text.isdigit():
        return names.index(text.lower()[:3]) + (1 if names is MONTHS else 0)
    if not text.isdigit():
        raise CronError(f"{field}: {text!r} is not a number")
    return int(text)


def _field(text: str, field: str, low: int, high: int, names) -> Set[int]:
    values: Set[int] = set()
    for part in text.split(","):
        match = re.fullmatch(r"(\*|[A-Za-z0-9]+(?:-[A-Za-z0-9]+)?)(?:/(\d+))?", part)
        if not match:
            raise CronError(f"{field}: {part!r} is not understood")
        span, step = match.group(1), int(match.group(2) or 1)
        if step < 1:
            raise CronError(f"{field}: a step of 0")
        if span == "*":
            start, end = low, high
        elif "-" in span:
            a, b = span.split("-")
            start, end = _value(a, names, field), _value(b, names, field)
        else:
            start = _value(span, names, field)
            end = high if match.group(2) else start
        if not (low <= start <= high and low <= end <= high) or start > end:
            raise CronError(f"{field}: {part!r} is outside {low}-{high}")
        values.update(range(start, end + 1, step))
    return values


class Cron:
    def __init__(self, text: str) -> None:
        self.text = text.strip()
        line = MACROS.get(self.text.lower(), self.text)
        parts = line.split()
        if len(parts) != 5:
            raise CronError(f"a cron line has 5 fields (minute hour day month weekday), not {len(parts)}: {text!r}")
        sets = [_field(p, name, low, high, names) for p, (name, low, high, names) in zip(parts, FIELDS)]
        self.minutes, self.hours, self.days, self.months, weekdays = sets
        self.weekdays = {d % 7 for d in weekdays}
        self.any_day = parts[2] == "*"
        self.any_weekday = parts[4] == "*"

    def day_matches(self, day: datetime) -> bool:
        in_month = day.day in self.days
        in_week = (day.isoweekday() % 7) in self.weekdays
        if self.any_day or self.any_weekday:
            return in_month and in_week
        return in_month or in_week   # both given: either (cron's rule)

    def next_after(self, moment: datetime) -> Optional[datetime]:
        """The first time after `moment` (aware) that the line names, aware
        in UTC; None when it names none (the 30th of February)."""
        local = moment.astimezone().replace(tzinfo=None, second=0, microsecond=0) + timedelta(minutes=1)
        limit = local + timedelta(days=366 * SEARCH_YEARS)
        while local < limit:
            if local.month not in self.months:
                year, month = (local.year + 1, 1) if local.month == 12 else (local.year, local.month + 1)
                local = local.replace(year=year, month=month, day=1, hour=0, minute=0)
            elif not self.day_matches(local):
                local = (local + timedelta(days=1)).replace(hour=0, minute=0)
            elif local.hour not in self.hours:
                local = (local + timedelta(hours=1)).replace(minute=0)
            elif local.minute not in self.minutes:
                local += timedelta(minutes=1)
            else:
                return local.astimezone().astimezone(timezone.utc)
        return None


def next_runs(text: str, n: int = 3, after: Optional[datetime] = None) -> List[datetime]:
    cron, runs, moment = Cron(text), [], after or taskq.now()
    for _ in range(n):
        moment = cron.next_after(moment)
        if moment is None:
            break
        runs.append(moment)
    return runs


# --- schedules in the queue's file ----------------------------------------------------

def _parse(value: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def _local(moment: datetime) -> str:
    return moment.astimezone().strftime("%Y-%m-%d %H:%M")


def _identities(value) -> str:
    if value in (None, "", ALL) or value == [ALL]:
        return ALL
    items = value.split(",") if isinstance(value, str) else list(value)
    items = [i.strip() for i in items if i.strip()]
    if not items:
        return ALL
    for prefix in items:
        if not taskq.PREFIX_RE.match(prefix):
            raise ValueError(f"invalid identity: {prefix}")
    return ",".join(dict.fromkeys(items))


def _args(what: str, args: Optional[dict]) -> dict:
    args = dict(args or {})
    if what == "clean":
        clean = {}
        for name in CLEAN_FILTERS:
            values = args.get(name) or []
            if not isinstance(values, list) or not all(isinstance(v, str) and re.match(r"^[a-z_]+$", v)
                                                       for v in values):
                raise ValueError(f"invalid {name}: {values!r}")
            if values:
                clean[name] = values
        if not clean:
            raise ValueError("a clean-up names at least one filter (ages, statuses, classes)")
        return clean
    if what == "collect":
        return {k: False for k in ("linkedin", "documents") if args.get(k) is False}
    return {}


def _check(what: str, cron: str, missed: str) -> None:
    if what not in WHAT:
        raise ValueError(f"unknown schedule kind: {what} (known: {', '.join(WHAT)})")
    if missed not in MISSED:
        raise ValueError(f"missed runs: {missed!r} (known: {', '.join(MISSED)})")
    Cron(cron)


def add(conn: sqlite3.Connection, what: str, identities=ALL, cron: str = "", *, missed: str = "catch_up",
        args: Optional[dict] = None, name: str = "", enabled: bool = True, at: Optional[datetime] = None) -> dict:
    _check(what, cron, missed)
    at = at or taskq.now()
    schedule_id = conn.execute(
        "INSERT INTO schedules (name, what, identities, args, cron, enabled, missed, created_at, last_due_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name or "", what, _identities(identities), json.dumps(_args(what, args)), Cron(cron).text,
         1 if enabled else 0, missed, taskq.iso(at), taskq.iso(at))).lastrowid
    return get(conn, schedule_id, at)


def update(conn: sqlite3.Connection, schedule_id: int, *, at: Optional[datetime] = None, **fields) -> dict:
    """Changes what is given. A changed timetable, or a schedule turned on,
    counts from now: runs before it were not missed, they were not asked for."""
    at = at or taskq.now()
    old = get(conn, schedule_id, at)
    if old is None:
        raise ValueError(f"no schedule #{schedule_id}")
    what = fields.get("what", old["what"])
    cron = fields.get("cron", old["cron"])
    missed = fields.get("missed", old["missed"])
    _check(what, cron, missed)
    row = {
        "name": fields.get("name", old["name"]) or "",
        "what": what,
        "identities": _identities(fields.get("identities", old["identities"])),
        "args": json.dumps(_args(what, fields["args"] if "args" in fields else old["args"])),
        "cron": Cron(cron).text,
        "missed": missed,
        "enabled": 1 if fields.get("enabled", old["enabled"]) else 0,
    }
    if row["cron"] != old["cron"] or (row["enabled"] and not old["enabled"]):
        row["last_due_at"] = taskq.iso(at)
    conn.execute(f"UPDATE schedules SET {', '.join(f'{k} = ?' for k in row)} WHERE id = ?",
                 (*row.values(), schedule_id))
    return get(conn, schedule_id, at)


def remove(conn: sqlite3.Connection, schedule_id: int) -> bool:
    """The schedule goes; the tasks it queued stay in the queue."""
    return conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,)).rowcount > 0


def _result(conn: sqlite3.Connection, ids: Sequence[int]) -> Optional[str]:
    """One word for what the last run's tasks did: running, queued, failed,
    stopped, done."""
    if not ids:
        return None
    marks = ",".join("?" * len(ids))
    states = {r[0] for r in conn.execute(f"SELECT state FROM tasks WHERE id IN ({marks})", tuple(ids))}
    for state, word in (("running", "running"), ("queued", "queued"), ("failed", "failed"),
                        ("interrupted", "failed"), ("stopped", "stopped")):
        if state in states:
            return word
    return "done" if states else None


def _as_dict(conn: sqlite3.Connection, row: sqlite3.Row, at: datetime) -> dict:
    schedule = dict(row)
    schedule["enabled"] = bool(schedule["enabled"])
    schedule["args"] = json.loads(schedule["args"] or "{}")
    schedule["identities"] = schedule["identities"].split(",") if schedule["identities"] != ALL else [ALL]
    schedule["last_tasks"] = json.loads(schedule["last_tasks"] or "[]")
    schedule["last_result"] = _result(conn, schedule["last_tasks"])
    try:
        upcoming = Cron(schedule["cron"]).next_after(max(at, _parse(schedule["last_due_at"]) or at))
    except CronError:
        upcoming = None
    schedule["next_at"] = taskq.iso(upcoming) if upcoming and schedule["enabled"] else None
    return schedule


def get(conn: sqlite3.Connection, schedule_id: int, at: Optional[datetime] = None) -> Optional[dict]:
    row = conn.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
    return _as_dict(conn, row, at or taskq.now()) if row else None


def listing(conn: sqlite3.Connection, at: Optional[datetime] = None) -> List[dict]:
    at = at or taskq.now()
    return [_as_dict(conn, r, at) for r in conn.execute("SELECT * FROM schedules ORDER BY id")]


# --- due runs ---------------------------------------------------------------------------

def inactive_identities() -> Set[str]:
    import identity
    return identity.inactive_identities()


def active_identities() -> List[str]:
    """Every identity not turned off in the app's Identities window."""
    import identity
    off = inactive_identities()
    return [p for p in identity.list_identities() if p not in off]


def _latest_due(cron: Cron, since: datetime, at: datetime) -> Optional[datetime]:
    """The last time the line names in (since, at], or None."""
    due = cron.next_after(since)
    if due is None or due > at:
        return None
    while True:
        following = cron.next_after(due)
        if following is None or following > at:
            return due
        due = following


def _queue(conn: sqlite3.Connection, schedule: dict, identities: Sequence[str]) -> List[int]:
    what, args, ids = schedule["what"], schedule["args"], []
    for prefix in identities:
        if what == "collect":
            made = taskq.collection(conn, prefix, origin="schedule", linkedin=args.get("linkedin", True),
                                    documents=args.get("documents", True))
            ids += [t["id"] for t in made["group"]] if made["added"] else []
        else:
            made = taskq.add(conn, what, prefix, origin="schedule", args=args)
            ids += [made["task"]["id"]] if made["added"] else []
    return ids


def run_due(conn: sqlite3.Connection, at: Optional[datetime] = None,
            identities_of=active_identities, inactive_of=inactive_identities) -> List[str]:
    """Queues what is due; one line per schedule that did something."""
    at = at or taskq.now()
    said = []
    for (schedule_id,) in conn.execute("SELECT id FROM schedules WHERE enabled = 1 ORDER BY id").fetchall():
        with taskq.transaction(conn):
            row = conn.execute("SELECT * FROM schedules WHERE id = ? AND enabled = 1", (schedule_id,)).fetchone()
            if row is None:
                continue
            schedule = _as_dict(conn, row, at)
            try:
                due = _latest_due(Cron(schedule["cron"]), _parse(row["last_due_at"]) or at, at)
            except CronError:
                continue
            if due is None:
                continue
            late = at - due > LATE_AFTER
            label = f"schedule #{schedule_id} ({schedule['name'] or schedule['what']}), the run of {_local(due)}"
            if late and schedule["missed"] == "skip":
                note = f"{label}: missed (the computer was off or asleep); skipped"
            elif schedule["last_result"] in ("running", "queued"):
                note = f"{label}: skipped, the previous run is still {schedule['last_result']}"
            else:
                note = None
            conn.execute("UPDATE schedules SET last_due_at = ?, last_note = COALESCE(?, last_note) WHERE id = ?",
                         (taskq.iso(due), note, schedule_id))
        if note:
            said.append(note)
            continue
        # one turned off is not collected (the app's Identities window)
        wanted = schedule["identities"]
        if wanted == [ALL]:
            prefixes = identities_of()
        else:
            off = inactive_of()
            prefixes = [p for p in wanted if p not in off]
        ids = _queue(conn, schedule, prefixes)
        note = (f"{label}: {'caught up, ' if late else ''}"
                + (f"queued #{', #'.join(map(str, ids))}" if ids else "nothing queued (no active identity, "
                   "or the same work was already queued)"))
        conn.execute("UPDATE schedules SET last_run_at = ?, last_tasks = ?, last_note = ? WHERE id = ?",
                     (taskq.iso(at), json.dumps(ids), note, schedule_id))
        said.append(note)
    return said
