"""Deletes vacancies from the shared base for good: the app's "Clean up" button.

The owner, 2026-10-17: vacancies seldom live a month, outdated feedback piles
up, and a closed vacancy reopened by its employer should come back as a new
one rather than stay "expired". No shadow ban: what matches is deleted, rows
and all, and the file is compacted afterwards.

A vacancy is deleted when, for EVERY identity that holds it, it matches the
filters: the age band of its posted date (else of its first sighting, as
schemas/queries.sql reads it), the identity's feedback status and its class.
An unset filter matches everything. The base is shared, so a filter chosen in
one identity's tab never removes what another identity still has a different
answer for.

Never deleted, whatever the filters:
  - a vacancy in the application funnel of any identity (applied ... started,
    declined): the person's own history;
  - feedback not yet read by /feedback (bugged or rejected, no
    feedback_reviewed_at): a report on the filter that nobody has used yet.

    python tools/cleanup.py --identity sharp --ages older --dry-run
    python tools/cleanup.py --identity sharp --statuses expired rejected --json

A vacancy deleted here and still live at its board comes back on the next
collection as a new one.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date

import db
import report
import runstate
import selections

AGES = ("today", "week", "month", "older")
CLASSES = ("hot_lead", "worth_a_look", "long_shot", "remote_unconfirmed",
           "engagement_unconfirmed", "low_priority", "rejected")
# Feedback the pipeline owner has not read yet (tools/feedback.py collect).
UNREVIEWED = ("bugged", "rejected")


def age_band(posted_at, first_seen, today: date | None = None) -> str:
    """The app's AGE: days since it was posted, else since we first saw it;
    no date at all reads as today."""
    day = report.calendar_date(posted_at) or report.calendar_date(first_seen)
    if not day:
        return "today"
    days = ((today or date.today()) - date.fromisoformat(day)).days
    if days < 1:
        return "today"
    if days <= 7:
        return "week"
    if days <= 30:
        return "month"
    return "older"


def _check(name, chosen, allowed):
    unknown = sorted(set(chosen or ()) - set(allowed))
    if unknown:
        raise ValueError(f"unknown {name}: {', '.join(unknown)}")


def plan(conn, identity: str, ages=None, statuses=None, classes=None, today: date | None = None) -> dict:
    """What a cleanup with these filters would delete, and what it keeps.

    `identity` is the tab the filters were chosen in; every other identity
    holding the vacancy has to match them too. Returns {"delete": [ids],
    "kept_funnel": n, "kept_unreviewed": n, "kept_other_identity": n}."""
    _check("age", ages, AGES)
    _check("status", statuses, selections.STATUSES)
    _check("class", classes, CLASSES)
    if not (ages or statuses or classes):
        raise ValueError("choose at least one filter: a cleanup without one would delete the base")
    bands = {row[0]: age_band(row[1], row[2], today) for row in conn.execute(
        "SELECT id, json_extract(data, '$.posted_at'), json_extract(data, '$.first_seen') FROM vacancies")}
    rows = {}
    for vid, ident, status, cls, reviewed in conn.execute(
            "SELECT vacancy_id, identity_id, feedback_status, class, feedback_reviewed_at FROM vacancy_identity"):
        rows.setdefault(vid, []).append((ident, status, cls, reviewed))

    def matches(vid, status, cls):
        return ((not ages or bands.get(vid) in ages)
                and (not statuses or status in statuses)
                and (not classes or cls in classes))

    result = {"delete": [], "kept_funnel": 0, "kept_unreviewed": 0, "kept_other_identity": 0}
    for vid, held in rows.items():
        own = [r for r in held if r[0] == identity]
        if not own or not matches(vid, own[0][1], own[0][2]):
            continue
        if any(r[1] in selections.FUNNEL for r in held):
            result["kept_funnel"] += 1
        elif any(r[1] in UNREVIEWED and not r[3] for r in held):
            result["kept_unreviewed"] += 1
        elif not all(matches(vid, r[1], r[2]) for r in held):
            result["kept_other_identity"] += 1
        else:
            result["delete"].append(vid)
    return result


def delete(conn, ids) -> None:
    """Every row that names the vacancies, then the vacancies. Duplicates
    pointing at a deleted one lose the pointer; the next collection marks
    duplicates again."""
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS doomed (id TEXT PRIMARY KEY)")
    conn.execute("DELETE FROM doomed")
    conn.executemany("INSERT OR IGNORE INTO doomed (id) VALUES (?)", ((i,) for i in ids))
    conn.execute("DELETE FROM selection_items WHERE vacancy_id IN (SELECT id FROM doomed)")
    conn.execute("UPDATE vacancy_identity SET duplicate_of = NULL WHERE duplicate_of IN (SELECT id FROM doomed)")
    conn.execute("DELETE FROM ai_screens WHERE vacancy_id IN (SELECT id FROM doomed)")
    conn.execute("DELETE FROM vacancy_identity WHERE vacancy_id IN (SELECT id FROM doomed)")
    conn.execute("DELETE FROM vacancies WHERE id IN (SELECT id FROM doomed)")
    conn.execute("DELETE FROM doomed")


def run(identity: str, ages=None, statuses=None, classes=None, dry_run=False, vacuum=True) -> dict:
    alive = runstate.current()
    if alive and not dry_run:
        raise runstate.AlreadyRunningError(
            f"a collection of '{alive.get('identity')}' is running; clean up after it ends")
    with db.session() as conn:
        found = plan(conn, identity, ages, statuses, classes)
        ids = found.pop("delete")
        summary = {"matched": len(ids), **found, "deleted": 0, "dry_run": dry_run}
        if dry_run or not ids:
            return summary
        with conn:
            delete(conn, ids)
        summary["deleted"] = len(ids)
    if vacuum:
        # Gives the space back to the disk. Best effort: an open reader (the
        # app) can keep it from running, and the rows are gone either way.
        try:
            with db.session() as conn:
                conn.execute("VACUUM")
            summary["vacuumed"] = True
        except Exception as exc:  # noqa: BLE001
            summary["vacuumed"] = False
            summary["vacuum_error"] = str(exc)
    return summary


def main() -> None:
    import identity as identity_mod

    parser = argparse.ArgumentParser(description="Delete vacancies from the base for good")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--ages", nargs="*", default=None, help=", ".join(AGES))
    parser.add_argument("--statuses", nargs="*", default=None, help="feedback statuses")
    parser.add_argument("--classes", nargs="*", default=None, help=", ".join(CLASSES))
    parser.add_argument("--dry-run", action="store_true", help="count, delete nothing")
    parser.add_argument("--no-vacuum", action="store_true", help="do not compact the file afterwards")
    parser.add_argument("--json", action="store_true", help="one JSON line, for the app")
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)
    try:
        summary = run(db.identity(), args.ages or None, args.statuses or None, args.classes or None,
                      dry_run=args.dry_run, vacuum=not args.no_vacuum)
    except (ValueError, runstate.AlreadyRunningError) as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}))
        else:
            print(f"!! {exc}", file=sys.stderr)
        sys.exit(2)
    if args.json:
        print(json.dumps(summary))
        return
    verb = "would delete" if args.dry_run else "deleted"
    print(f"{verb} {summary['matched']} vacancies; kept: {summary['kept_funnel']} in the funnel, "
          f"{summary['kept_unreviewed']} with feedback not yet reviewed, "
          f"{summary['kept_other_identity']} another identity answers differently")


if __name__ == "__main__":
    main()
