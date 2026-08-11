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

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

HEAD_CLASSES = ("hot_lead", "worth_a_look", "long_shot")

# How many descriptions to fetch per run. A bound rather than a target: 251
# were outstanding on the first run, and clearing them over a few runs is
# better than one run making 251 requests to somebody else's server.
DEFAULT_LIMIT = 120

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


def worklist(vacancies: dict, classes=HEAD_CLASSES, limit: Optional[int] = None) -> list:
    """Shortlist vacancies with no description and no recent attempt.

    Ordered by score, highest first: if the budget runs out, it runs out on the
    vacancies a person is least likely to reach.
    """
    todo = []
    for key, record in vacancies.items():
        if record.get("duplicate_of"):
            continue
        if (record.get("description_text") or "").strip():
            continue
        if not record.get("url"):
            continue
        computed = record.get("computed") or {}
        if computed.get("classification") not in classes:
            continue
        if _attempted_recently(record):
            continue
        todo.append((computed.get("score") or 0, key))
    todo.sort(reverse=True)
    keys = [key for _, key in todo]
    return keys[:limit] if limit else keys


def enrich(vacancies: dict, classes=HEAD_CLASSES, limit: int = DEFAULT_LIMIT) -> dict:
    """Fetches the missing descriptions. Mutates `vacancies` in place.

    Never raises: a description is an improvement, and failing to get one must
    not stop a research cycle. One vacancy failing must not stop the rest
    either — the same reasoning as one source failing in the pipeline.
    """
    import fetch_linkedin

    stats = {"considered": 0, "fetched": 0, "empty": 0, "errors": 0,
             "closed": 0, "declared_remote": 0, "salary_found": 0}
    for key in worklist(vacancies, classes, limit):
        record = vacancies[key]
        stats["considered"] += 1
        facts = {"description": "", "workplace_type": None,
                 "salary_raw": None, "closed": False}
        try:
            facts = fetch_linkedin.fetch_page_facts(record["url"], common.DEFAULT_TIMEOUT)
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
