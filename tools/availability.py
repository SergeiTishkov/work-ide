"""
Is a vacancy still open? (task 0127)

    python tools/availability.py --identity sharp                # the listed vacancies, in the budget
    python tools/availability.py --identity sharp --minutes 10
    python tools/availability.py --identity sharp --vacancy ID   # one vacancy, now
    python tools/availability.py --identity sharp --dry-run      # verdicts printed, nothing written

The queue's "links" run (pipeline.py --links) does the listed vacancies; the
document batch asks for one vacancy right before its CV or letter
(refresh()).

WHY
---
Measured 2026-11-20 (SHARP): the list held 1,189 vacancies, 1,071 of them
LinkedIn, 967 first seen in October. link_check.py, a HEAD then a GET with
404/410 read as dead, got 429 from LinkedIn on 1,041 of the 1,071: all
"unknown", all kept. A sample of 63 of them read one by one: 13 "no longer
accepting applications", 3 404, 10 redirected from the posting to a jobs
search page (the guest fragment called 7 of those 10 closed, 3 answered
429), 12 open, 25 answered 429. 26 of the 38 with a verdict were gone.

LINKEDIN is asked through the guest posting fragment (fetch_linkedin
.GUEST_POSTING_URL): 15-65 KB against about 280 KB for the page, and the
same facts. Measured 2026-11-20:
  * an open posting: 200, a description, no closed marker;
  * a closed one: 200 with "No longer accepting applications";
  * a number that names no posting: 404.
One request at a time, paced by fetch_linkedin._Pacer: the pause doubles after
a 429 and comes back down after pages that go through. A 429 is waited out
(fetch_linkedin.RATE_LIMIT_BACKOFF, one wait longer than the last) and the
same posting asked again; LIMITED_IN_A_ROW 429s in a row end the LinkedIn
part of this run. A posting with no answer but 429 gets no verdict and stays
first in line for the next run.
OTHER BOARDS keep link_check's own checks: the devitjobs API, else HEAD/GET
with 404/410 as closed.

THE VERDICTS
------------
  open     the posting is there and takes applications
  closed   the board says so: the closed marker, 404 or 410, taken down
  unknown  anything else: 429, a timeout, a page without a posting

Stored as `link_check` (status "ok", "dead" or "unknown"), the field the list
and the documents already read (selections.listed_vacancies,
cv_tailor.gone_reason): a closed vacancy leaves the list at the next
selection. A closed verdict is not undone by an unknown one
(link_check.merge): 429 is not "open again".

WHAT AND WHEN: a vacancy is due when it has no check, or its last open or
unknown verdict is older than RECHECK_HOURS; a closed one is not asked again.
The oldest check goes first, within the run's budget (DEFAULT_MINUTES).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import fetch_linkedin  # noqa: E402
import link_check  # noqa: E402

RECHECK_HOURS = 24
# The document batch asks again when the last verdict is older than this: one
# small request against a CV and a letter made for a posting already closed.
BATCH_RECHECK_HOURS = 6
DEFAULT_MINUTES = 45
TIMEOUT = 15
LIMITED_IN_A_ROW = 5
CLOSED_MARKER = "no longer accepting applications"
BY = "availability"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def linkedin_job(vacancy: dict) -> Optional[str]:
    """The LinkedIn job number of the vacancy's address or external id."""
    return (fetch_linkedin.job_id(vacancy.get("url") or "")
            or fetch_linkedin.job_id(vacancy.get("external_id") or ""))


def linkedin_verdict(job_id: str, session, timeout: int = TIMEOUT) -> dict:
    """One posting through the guest fragment. Never raises."""
    try:
        resp = session.get(fetch_linkedin.GUEST_POSTING_URL.format(job_id=job_id),
                           timeout=timeout, allow_redirects=False)
    except Exception as exc:  # noqa: BLE001 - the network is unpredictable
        return {"status": "unknown", "http_code": None, "error": f"{type(exc).__name__}: {exc}"}
    code = resp.status_code
    if code in link_check.DEAD_STATUS_CODES:
        return {"status": "dead", "http_code": code, "reason": f"the board answers {code}"}
    if code != 200:
        return {"status": "unknown", "http_code": code}
    facts = fetch_linkedin.page_facts(resp.text or "")
    if facts["closed"]:
        return {"status": "dead", "http_code": code, "reason": CLOSED_MARKER}
    if facts["description"]:
        return {"status": "ok", "http_code": code}
    return {"status": "unknown", "http_code": code, "error": "no posting in the answer"}


def other_verdict(vacancy: dict, session, timeout: int = TIMEOUT, devitjobs_listed=None) -> dict:
    """A board other than LinkedIn: link_check's own checks."""
    job_id = link_check._devitjobs_id(vacancy)
    if job_id:
        return link_check._devitjobs_results(vacancy, job_id, devitjobs_listed, session, timeout)
    return link_check._check_one(session, vacancy["url"], timeout)


def due(vacancy: dict, now: datetime, recheck_hours: float = RECHECK_HOURS) -> bool:
    if vacancy.get("duplicate_of") or not vacancy.get("url"):
        return False
    before = vacancy.get("link_check") or {}
    if before.get("status") == "dead":
        return False
    try:
        checked = datetime.fromisoformat(before["checked_at"])
    except (KeyError, TypeError, ValueError):
        return True
    return now - checked > timedelta(hours=recheck_hours)


def _order_key(vacancy: dict) -> str:
    return (vacancy.get("link_check") or {}).get("checked_at") or ""


def check(vacancies: Iterable[dict], *, minutes: float = DEFAULT_MINUTES,
          recheck_hours: float = RECHECK_HOURS, session=None,
          sleep: Callable[[float], None] = time.sleep,
          clock: Callable[[], float] = time.monotonic,
          now: Optional[datetime] = None) -> dict:
    """Checks the due vacancies, oldest check first, until the budget ends.
    Mutates each checked record's `link_check`; returns the statistics and
    {"changed": {vacancy id: link_check}} for save()."""
    now = now or _now()
    todo = sorted((v for v in vacancies if due(v, now, recheck_hours)), key=_order_key)
    stats = {"due": len(todo), "checked": 0, "ok": 0, "dead": 0, "unknown": 0, "rate_limited": 0,
             "left_for_next_run": 0, "linkedin_stopped": None, "changed": {}}
    if not todo:
        return stats
    if session is None:
        import requests

        session = requests.Session()
        session.headers.update({"User-Agent": common.USER_AGENT})
    deadline = clock() + minutes * 60
    pacer = fetch_linkedin._Pacer()
    limited_in_a_row = 0
    devitjobs = [v for v in todo if link_check._devitjobs_id(v)]
    listed = link_check._devitjobs_listed(session) if devitjobs else None
    import progress

    tick = progress.Progress(len(todo), "availability")
    linkedin_asked = False
    for vacancy in todo:
        if clock() > deadline:
            break
        job_id = linkedin_job(vacancy)
        if not job_id and link_check.is_linkedin_url(vacancy["url"]):
            # a LinkedIn address without a job number: HEAD gets 429 there
            result = {"status": "unknown", "http_code": None, "error": "no job number in the address"}
        elif job_id:
            if stats["linkedin_stopped"]:
                continue
            result = None
            while True:
                if linkedin_asked:
                    sleep(pacer.pause)
                if clock() > deadline:
                    stats["linkedin_stopped"] = "the budget ended"
                    break
                linkedin_asked = True
                result = linkedin_verdict(job_id, session)
                if result.get("http_code") != 429:
                    pacer.passed()
                    limited_in_a_row = 0
                    break
                pacer.limited()
                limited_in_a_row += 1
                stats["rate_limited"] += 1
                if limited_in_a_row >= LIMITED_IN_A_ROW:
                    stats["linkedin_stopped"] = f"{limited_in_a_row} answers 429 in a row"
                    break
                # the same posting again after a wait, one longer each time
                backoff = fetch_linkedin.RATE_LIMIT_BACKOFF
                sleep(backoff[min(limited_in_a_row, len(backoff)) - 1])
            if result is None or result.get("http_code") == 429:
                # no verdict: it stays due, first in line next run
                continue
        else:
            result = other_verdict(vacancy, session, devitjobs_listed=listed)
        tick()
        merged = link_check.merge(vacancy.get("link_check"), result, _now(), by=BY)
        vacancy["link_check"] = merged
        stats["changed"][vacancy["id"]] = merged
        stats["checked"] += 1
        stats[result["status"]] += 1
    stats["left_for_next_run"] = stats["due"] - stats["checked"]
    return stats


def save(changed: dict) -> int:
    """Writes each vacancy's new `link_check` into its row as it is now in
    the base: a run beside this one (LinkedIn's merge) keeps what it wrote to
    the rest of the record. Returns the number of rows written."""
    import db

    written = 0
    with db.session() as conn:
        for vacancy_id, value in changed.items():
            row = conn.execute("SELECT data FROM vacancies WHERE id = ?", (vacancy_id,)).fetchone()
            if not row:
                continue
            data = json.loads(row[0])
            data["link_check"] = value
            conn.execute("UPDATE vacancies SET data = ? WHERE id = ?", (db.dumps(data), vacancy_id))
            written += 1
    return written


def refresh(vacancy_id: str, recheck_hours: float = BATCH_RECHECK_HOURS, session=None) -> Optional[dict]:
    """One vacancy from the base, checked when due and saved: its
    `link_check` after that, or None when the base has no such vacancy."""
    import db

    vacancy = db.load_vacancy(vacancy_id)
    if not vacancy:
        return None
    vacancy.setdefault("id", vacancy_id)
    # a 429 is waited out once (RATE_LIMIT_BACKOFF[0]), then the batch goes on
    stats = check([vacancy], minutes=0.25, recheck_hours=recheck_hours, session=session)
    if stats["changed"]:
        save(stats["changed"])
    return vacancy.get("link_check")


def note(stats: dict) -> str:
    note = (f"{stats['checked']} of {stats['due']} due: {stats['ok']} open, {stats['dead']} closed, "
            f"{stats['unknown']} unknown")
    if stats.get("left_for_next_run"):
        note += f"; {stats['left_for_next_run']} left for the next run"
    if stats.get("linkedin_stopped"):
        note += f"; LinkedIn stopped: {stats['linkedin_stopped']}"
    return note


def main(argv=None) -> int:
    import identity

    parser = argparse.ArgumentParser(description="Is a vacancy still open: the listed vacancies, or one")
    identity.add_identity_arg(parser)
    parser.add_argument("--vacancy", default=None, help="One vacancy id, checked now")
    parser.add_argument("--minutes", type=float, default=DEFAULT_MINUTES, help="The budget of the run")
    parser.add_argument("--dry-run", action="store_true", help="Print the verdicts, write nothing")
    args = parser.parse_args(argv)
    identity.activate_or_exit(args.identity)
    import db
    import kb
    import selections

    if args.vacancy:
        vacancy = db.load_vacancy(args.vacancy)
        if not vacancy:
            common.eprint(f"availability: no vacancy {args.vacancy}")
            return 1
        vacancy.setdefault("id", args.vacancy)
        stats = check([vacancy], minutes=1, recheck_hours=0)
    else:
        stats = check(selections.shown_vacancies(kb.load_vacancies()), minutes=args.minutes)
    for vacancy_id, value in stats["changed"].items():
        print(vacancy_id, value["status"], value.get("reason") or value.get("http_code") or "")
    if not args.dry_run and stats["changed"]:
        save(stats["changed"])
        print("Run pipeline.py --links (or wait for the next selection) for the list to drop the closed ones.")
    print(note(stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
