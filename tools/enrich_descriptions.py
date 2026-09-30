"""
Fetching the description for shortlist vacancies that arrived without one.

WHAT WAS BROKEN
---------------
LinkedIn's search page returns cards, and a card has no description — only
title, company and location. The fetcher enriches a capped number of them per
run (`fetch_linkedin.MAX_ENRICH`), because each description is a separate
request. Everything it does not reach keeps an empty `description_text`.

Measured 2026-08-11 over a base of 13605: **1023 cards had no description, and
251 of them were sitting in the head of the shortlist.** Every gate that reads
the text — residency, citizenship, language, industry, role complexity — was
deciding those 251 blind, on a title and a handful of tags.

That is not a small inaccuracy. The first such vacancy read by hand that day
was titled "Software Developer (Angular, .NET (C#), SQL Server stack)
PART-TIME/Remote" — an exact match for what this identity looks for, sitting in
worth_a_look at 32 because there was no text to score. Its description, once
fetched, said: "Must be US Citizen. Must be eligible to work on U.S. government
contracts." The citizenship gate would have rejected it instantly. It never saw
the words.

Both failure directions are in that one vacancy: a bullseye that scored low for
lack of text, and a hard dealbreaker that survived for the same reason.

WHY A SEPARATE STEP RATHER THAN A BIGGER CAP IN THE FETCHER
-----------------------------------------------------------
The fetcher enriches what it has just collected, guessing from the title which
cards are worth a request. This step knows something the fetcher cannot: which
cards actually reached the shortlist after full scoring. That is a far better
signal than a title, and it costs requests only for vacancies a person may
really read.

Attempts are recorded whether or not they succeed, so a page that returns
nothing is not re-fetched on every run. Same principle as link_check and
company_intel: the cache is what keeps this polite.
"""
from __future__ import annotations

import html as _html
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

# The classes worth spending a request on.
#
# `remote_unconfirmed` was added 2026-09-08, and its absence was the single
# largest hole in this step. That class holds more vacancies than every
# confident tier put together — 1334 against 119 — and it exists precisely
# because NOBODY SAID whether the work is remote. Reading the description is
# the one thing that could settle it, and it was the one thing never done: of
# Reed's 222 records, five had any text at all.
#
# `engagement_unconfirmed` joined 2026-09-13 for the same reason: a search for
# part-time work parks there everything nobody called part-time, and the
# vacancy page — LinkedIn's "Employment type", a schema.org employmentType —
# is where that is most often settled.
HEAD_CLASSES = ("hot_lead", "worth_a_look", "long_shot", "remote_unconfirmed",
                "engagement_unconfirmed")

# How many descriptions to fetch per run. A bound rather than a target: 251
# were outstanding on the first run, and clearing them over a few runs is
# better than one run making 251 requests to somebody else's server.
DEFAULT_LIMIT = 120

# A second queue with a budget of its own: vacancies refused only because
# nobody had read their stack (score.STACK_UNREAD, `description_wanted`).
# Found 2026-10-01: 238 developer titles in a single run were refused on a
# stack no one had seen, and this step never looked at them — it reads the
# shortlist, and they were not in it. A queue of their own rather than a place
# in the first one: its budget is always spent on the shortlist first, so a
# shared one would never reach them. Newest first — a vacancy a day old is
# worth more than one from last month.
WANTED_LIMIT = 300

# Days before an unsuccessful attempt is worth repeating. A page that gave
# nothing today usually gives nothing tomorrow; a month later it may have
# changed or been reposted.
RETRY_AFTER_DAYS = 30


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _attempted_recently(record: dict, days: int = RETRY_AFTER_DAYS) -> bool:
    stamp = (record.get("description_fetch") or {}).get("attempted_at")
    if not stamp:
        return False
    try:
        when = datetime.fromisoformat(stamp)
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - when).days < days


# Which sources have a page worth reading, and who reads it.
#
# A source absent from here is not enriched at all — deliberately. Sending a
# LinkedIn parser at a Reed page finds nothing, returns empty, and RECORDS AN
# ATTEMPT, so the vacancy is marked as tried and never looked at again. Silence
# of that kind is the expensive kind.
#
# Measured 2026-09-08:
#   linkedin      a full page reader, plus salary, closure and TELECOMMUTE
#   reed          schema.org JobPosting: 2935 characters of description
#   contractoruk  the detail page repeats the card's summary; nothing to gain
#   outside_ir35  no structured data, no fuller text
# Measured 2026-09-13:
#   remoterocketship  schema.org JobPosting with the full text and
#                     employmentType; the card holds a two-line summary
# Measured 2026-10-01:
#   devitjobs     a single-page app, the page is an empty shell; the detail
#                 API its own front end calls has the full text (_devitjobs_facts)
#   4dayweek      the description is behind a paid "Pro" wall
#   jobs_ch       detail links of the search API answer 404
READABLE_SOURCES = ("linkedin", "reed", "remoterocketship", "devitjobs")

_DEVITJOBS_URL = r"https://(devitjobs\.(?:com|uk))/jobs/([0-9a-f]{24})$"

# Between two detail requests to devitjobs: hundreds a run go to one server.
DEVITJOBS_PAUSE_SECONDS = 0.5


def _json_ld_facts(url: str, timeout: int) -> dict:
    """The same four facts, from schema.org markup rather than a site's HTML.

    Generic on purpose: any board that publishes a JobPosting can be added to
    READABLE_SOURCES without another parser.
    """
    import json as _json
    import re as _re

    import requests

    facts = {"description": "", "workplace_type": None,
             "salary_raw": None, "closed": False, "employment_types": []}
    try:
        resp = requests.get(url, headers={"User-Agent": common.USER_AGENT},
                            timeout=timeout)
        resp.raise_for_status()
    except Exception:  # noqa: BLE001
        return facts

    body = resp.text
    for block in _re.findall(
            r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', body, _re.S):
        try:
            data = _json.loads(block)
        except Exception:  # noqa: BLE001
            continue
        for node in (data if isinstance(data, list) else [data]):
            if not isinstance(node, dict) or "JobPosting" not in str(node.get("@type")):
                continue
            description = _re.sub(r"<[^>]+>", " ", str(node.get("description") or ""))
            description = " ".join(_html.unescape(description).split())
            if description and len(description) > len(facts["description"]):
                facts["description"] = description
            if node.get("jobLocationType") == "TELECOMMUTE":
                facts["workplace_type"] = "remote"
            # "PART_TIME", ["FULL_TIME", "CONTRACTOR"] — schema.org allows both
            # a string and a list; normalize reads either.
            if node.get("employmentType") and not facts["employment_types"]:
                import normalize

                facts["employment_types"] = normalize.employment_types(
                    node.get("employmentType"))
            base = node.get("baseSalary")
            if isinstance(base, dict) and not facts["salary_raw"]:
                value = base.get("value")
                if isinstance(value, dict):
                    low = value.get("minValue") or value.get("value")
                    if low is not None:
                        high = value.get("maxValue")
                        amount = f"{low}-{high}" if high and high != low else f"{low}"
                        facts["salary_raw"] = " ".join(
                            str(part) for part in
                            (base.get("currency"), amount, value.get("unitText"))
                            if part)
    return facts


def _devitjobs_facts(url: str, timeout: int) -> dict:
    """The facts of a devitjobs vacancy, from the detail API (/api/job/<id>)
    its own front end calls: the list the fetcher reads ("jobsLight") has no
    text, and the page is a shell that JavaScript fills in.

    The text is the description plus the requirement and responsibility
    lists, which the board keeps in fields of their own — that is where the
    stack usually is. `workplace` is the employer's own structured answer;
    only "remote" is taken, as everywhere in this step."""
    import re as _re
    import time

    import requests

    facts = {"description": "", "workplace_type": None,
             "salary_raw": None, "closed": False, "employment_types": []}
    match = _re.match(_DEVITJOBS_URL, url or "")
    if not match:
        return facts
    host, job_id = match.groups()
    time.sleep(DEVITJOBS_PAUSE_SECONDS)
    resp = requests.get(f"https://{host}/api/job/{job_id}",
                        headers={"User-Agent": common.USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    parts = [
        ("", data.get("description")),
        ("Requirements: ", data.get("requirementsMustTextArea")),
        ("Nice to have: ", data.get("requirementsNiceTextArea")),
        ("Responsibilities: ", data.get("responsibilitiesTextArea")),
    ]
    text = "\n\n".join(label + common.strip_html(str(value)).strip()
                       for label, value in parts if str(value or "").strip())
    facts["description"] = text
    if str(data.get("workplace") or "").lower() == "remote":
        facts["workplace_type"] = "remote"
    if data.get("jobType"):
        import normalize

        facts["employment_types"] = normalize.employment_types(data.get("jobType"))
    facts["closed"] = bool(data.get("isDisabledOrOutdated") or data.get("isPaused"))
    return facts


def _reader_for(source: str):
    """The right page reader for a source, or None if there is none."""
    if source == "devitjobs":
        return _devitjobs_facts
    if source == "linkedin":
        import fetch_linkedin

        return fetch_linkedin.fetch_page_facts
    if source in READABLE_SOURCES:
        return _json_ld_facts
    return None


def worklist(vacancies: dict, classes=HEAD_CLASSES, limit: Optional[int] = None,
             need_employment_types: bool = False) -> list:
    """Shortlist vacancies with no description and no recent attempt.

    With `need_employment_types`, also those that HAVE a description but no
    stated engagement. A search that asks about hours (an `engagement_fit`
    block) needs the page for that fact alone: the first part-time run held 73
    LinkedIn vacancies in remote_unconfirmed, 69 of them with a description
    fetched at collection time and 47 with no employment type — the one thing
    the page would have settled.

    Ordered by score, highest first: if the budget runs out, it runs out on the
    vacancies a person is least likely to reach.
    """
    todo = []
    for key, record in vacancies.items():
        if record.get("duplicate_of"):
            continue
        has_text = bool((record.get("description_text") or "").strip())
        wants_type = need_employment_types and not record.get("employment_types")
        if has_text and not wants_type:
            continue
        if not record.get("url"):
            continue
        computed = record.get("computed") or {}
        if computed.get("classification") not in classes:
            continue
        # No reader, no request. Sending the wrong parser at a page wastes a
        # request AND marks the vacancy as tried, which is worse than leaving
        # it alone. See READABLE_SOURCES.
        if record.get("source") not in READABLE_SOURCES:
            continue
        if _attempted_recently(record):
            continue
        todo.append((computed.get("score") or 0, key))
    todo.sort(reverse=True)
    keys = [key for _, key in todo]
    return keys[:limit] if limit else keys


def wanted_worklist(vacancies: dict, limit: Optional[int] = WANTED_LIMIT) -> list:
    """Vacancies whose verdict waits on their description (see WANTED_LIMIT),
    newest first."""
    todo = []
    for key, record in vacancies.items():
        if record.get("duplicate_of") or not record.get("url"):
            continue
        if not (record.get("computed") or {}).get("description_wanted"):
            continue
        if (record.get("description_text") or "").strip():
            continue
        if record.get("source") not in READABLE_SOURCES or _attempted_recently(record):
            continue
        todo.append((str(record.get("first_seen") or ""), key))
    todo.sort(reverse=True)
    keys = [key for _, key in todo]
    return keys[:limit] if limit else keys


def enrich(vacancies: dict, classes=HEAD_CLASSES, limit: int = DEFAULT_LIMIT,
           need_employment_types: bool = False,
           wanted_limit: int = WANTED_LIMIT) -> dict:
    """Fetches the missing descriptions. Mutates `vacancies` in place.

    Never raises: a description is an improvement, and failing to get one must
    not stop a research cycle. One vacancy failing must not stop the rest
    either — the same reasoning as one source failing in the pipeline.
    """
    import progress

    stats = {"considered": 0, "fetched": 0, "empty": 0, "errors": 0,
             "closed": 0, "declared_remote": 0, "salary_found": 0}
    keys = list(worklist(vacancies, classes, limit, need_employment_types))
    head = set(keys)
    wanted = [key for key in wanted_worklist(vacancies, wanted_limit) if key not in head]
    stats["unread_stack"] = len(wanted)
    keys += wanted
    tick = progress.Progress(len(keys), "descriptions")
    for key in keys:
        tick()
        record = vacancies[key]
        stats["considered"] += 1
        facts = {"description": "", "workplace_type": None,
                 "salary_raw": None, "closed": False}
        reader = _reader_for(record.get("source"))
        try:
            if reader is not None:
                facts = reader(record["url"], common.DEFAULT_TIMEOUT)
        except Exception:  # noqa: BLE001 — one page must not stop the rest
            stats["errors"] += 1
        text = facts.get("description") or ""
        record["description_fetch"] = {
            "attempted_at": _now(),
            "chars": len(text),
        }
        if text.strip():
            record["description_text"] = text
            stats["fetched"] += 1
        else:
            stats["empty"] += 1

        # The employer's own declaration, where there is one. Only ever set to
        # "remote": silence is not evidence of onsite, and the scoring has a
        # class of its own for "nobody said".
        if facts.get("workplace_type"):
            record["workplace_type"] = facts["workplace_type"]
            stats["declared_remote"] += 1
        # The engagement as the page states it. Merged rather than replaced: a
        # board's card may already have said "contract", and the page adding
        # "part-time" does not make the first statement untrue.
        if facts.get("employment_types"):
            import normalize

            record["employment_types"] = normalize.employment_types(
                list(record.get("employment_types") or []) + list(facts["employment_types"]))
            stats["employment_type_found"] = stats.get("employment_type_found", 0) + 1
        # A salary stated in the vacancy is the highest level of trust there
        # is (CLAUDE.md §5) and it was being discarded on every LinkedIn card.
        if facts.get("salary_raw") and not record.get("salary_raw"):
            record["salary_raw"] = facts["salary_raw"]
            stats["salary_found"] += 1
        # A posting that no longer accepts applications is not a candidate.
        # Recorded through link_check, which the report already filters on —
        # the same treatment as a 404, and for the same reason: there is
        # nothing on the other end of the link. Found by the owner 2026-08-11,
        # leading the shortlist at 65.
        if facts.get("closed"):
            record["link_check"] = {
                "status": "dead",
                "reason": "no longer accepting applications",
                "checked_at": _now(),
            }
            stats["closed"] += 1
    return stats


def coverage(vacancies: dict, classes=HEAD_CLASSES) -> dict:
    """How much of the shortlist is still being scored blind."""
    total = blind = 0
    for record in vacancies.values():
        if record.get("duplicate_of"):
            continue
        if (record.get("computed") or {}).get("classification") not in classes:
            continue
        total += 1
        if not (record.get("description_text") or "").strip():
            blind += 1
    return {"in_shortlist": total, "without_description": blind}


def main() -> None:
    import argparse

    import identity as identity_mod
    import kb

    parser = argparse.ArgumentParser(
        description="Fetch descriptions for shortlist vacancies that arrived without one")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--coverage", action="store_true",
                        help="Only report how many are scored blind, fetch nothing")
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)

    vacancies = kb.load_vacancies()
    if args.coverage:
        stats = coverage(vacancies)
        print("In the shortlist: %d, of them without a description: %d"
              % (stats["in_shortlist"], stats["without_description"]))
        return

    stats = enrich(vacancies, limit=args.limit)
    kb.save_vacancies(vacancies)
    print("Considered %(considered)d, fetched %(fetched)d, "
          "came back empty %(empty)d, errors %(errors)d" % stats)
    print("Rescore to apply them: python tools/pipeline.py --identity "
          + common.ACTIVE_IDENTITY)


if __name__ == "__main__":
    main()
