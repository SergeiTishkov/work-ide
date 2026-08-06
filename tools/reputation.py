"""
Employer reputation: the link between the shortlist and its verification.

WHAT WAS BROKEN
---------------
Measured 2026-08-06: 55 companies sat in hot_lead and worth_a_look, and NOT ONE
of them had a reputation. Two of the 55 had even had their age looked up.

The cause was not that somebody forgot. It was structural: enrichment ran only
from `pipeline.py`, which ties it to COLLECTING vacancies. But the shortlist
changes for another reason too — every time a filter or a weight is edited and
everything is rescored. Over one session that happened a dozen times, and each
time companies arrived in the shortlist that enrichment had never seen.

The link was "fetch -> check" where it needed to be "shortlist -> check". The
difference was silent: the report wrote "reputation not checked" against every
one of them, a person read that as "no data exists", and it actually meant "we
never even tried".

THREE STATES INSTEAD OF TWO
---------------------------
That indistinguishability was the real damage, so there are now three states:

  found                 data exists: rating, work-life balance, review count;
  insufficient_sources  we LOOKED and found nothing credible — a small,
                        little-known company with no reviews about it;
  (no record)           nobody looked. For hot_lead and worth_a_look that is a
                        defect in the process, and the report must shout about
                        it rather than stay quiet.

The second state was added at the owner's direct request on 2026-08-06: if the
automation ran and the company is small and unknown, say so — reputation was
checked but could not be determined for want of sources.

WHY COLLECTION IS NOT FULLY AUTOMATIC
-------------------------------------
Review sites are closed to scripts: Glassdoor, Indeed, Trustpilot and levels.fyi
answer 403 behind Cloudflare, and the official Glassdoor API is 410 Gone
(measured 2026-07-31). Getting in would require impersonating a browser, which
the constitution forbids (§5, the boundary of what is allowed).

So what is collected automatically is what is given honestly — company age and
size from Wikidata — while ratings are searched for by the agent, exactly as a
person would search for them. The automation is elsewhere: the system computes
the worklist itself, records the outcome of every attempt itself, and complains
by itself while the list is not empty. None of that rests on an agent
remembering; rules of that kind have broken here before.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

# Shortlist classes for which reputation is REQUIRED. long_shot is
# deliberately absent: it is the tail, people rarely reach it, and checking
# every company there would cost hundreds of requests for vacancies nobody
# will open.
REQUIRED_CLASSES = ("hot_lead", "worth_a_look")

VERDICT_FOUND = "found"
VERDICT_INSUFFICIENT = "insufficient_sources"

# How long a result stays fresh. Company reputation changes slowly, but not
# infinitely slowly.
FRESH_DAYS = 90


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_fresh(record: dict, days: int = FRESH_DAYS) -> bool:
    stamp = (record or {}).get("checked_at")
    if not stamp:
        return False
    try:
        checked = datetime.fromisoformat(stamp)
    except ValueError:
        return False
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - checked).days < days


def shortlist_companies(vacancies: dict, classes=REQUIRED_CLASSES) -> dict:
    """{company name: the best class among its vacancies} in the current shortlist."""
    order = {"hot_lead": 3, "worth_a_look": 2, "long_shot": 1}
    found = {}
    for rec in vacancies.values():
        if rec.get("duplicate_of"):
            continue
        name = rec.get("company")
        cls = (rec.get("computed") or {}).get("classification")
        if not name or cls not in classes:
            continue
        if order.get(cls, 0) > order.get(found.get(name, ""), 0):
            found[name] = cls
    return found


def worklist(vacancies: dict, companies: dict, classes=REQUIRED_CLASSES,
             limit: Optional[int] = None) -> List[dict]:
    """Shortlist companies with no recent ATTEMPT to check their reputation.

    An attempt, not data: a company about which nothing was found drops off
    the list — otherwise every run would search again for reviews of a
    five-person outfit that has none.
    """
    by_name = {entry.get("name"): entry for entry in companies.values()}
    todo = []
    for name, cls in sorted(shortlist_companies(vacancies, classes).items(),
                            key=lambda kv: (kv[1] != "hot_lead", kv[0])):
        entry = by_name.get(name) or {}
        if _is_fresh(entry.get("reputation")):
            continue
        todo.append({
            "company": name,
            "classification": cls,
            "url": _sample_url(vacancies, name),
        })
        if limit and len(todo) >= limit:
            break
    return todo


def _sample_url(vacancies: dict, name: str) -> Optional[str]:
    for rec in vacancies.values():
        if rec.get("company") == name and rec.get("url"):
            return rec["url"]
    return None


def coverage(vacancies: dict, companies: dict, classes=REQUIRED_CLASSES) -> dict:
    """How many shortlist companies were checked, and with what outcome."""
    by_name = {entry.get("name"): entry for entry in companies.values()}
    stats = {"companies": 0, "found": 0, "insufficient": 0, "unchecked": 0}
    for name in shortlist_companies(vacancies, classes):
        stats["companies"] += 1
        rep = (by_name.get(name) or {}).get("reputation")
        if not _is_fresh(rep):
            stats["unchecked"] += 1
        elif rep.get("verdict") == VERDICT_INSUFFICIENT:
            stats["insufficient"] += 1
        else:
            stats["found"] += 1
    return stats


def mark_insufficient(companies: dict, name: str, searched: str = "") -> bool:
    """Records "we looked and found nothing". False if the company is unknown.

    This is a FULL result of a check, not the absence of one. Without it the
    report cannot tell "a small, unremarkable company" from "nobody got round
    to it", and for a person those are very different: the first is a property
    of the company, the second a defect in the process.
    """
    slug = common.normalize_company_name(name)
    entry = companies.get(slug)
    if entry is None:
        return False
    entry["reputation"] = {
        "verdict": VERDICT_INSUFFICIENT,
        "checked_at": _now(),
        "searched": searched or "Glassdoor, Indeed, Trustpilot, general web search",
        "overall_rating": None,
        "work_life_balance": None,
        "red_flags": [],
    }
    return True


def main() -> None:
    import argparse
    import identity as identity_mod
    import kb

    parser = argparse.ArgumentParser(
        description="Reputation of shortlist companies: what is checked, what is left")
    identity_mod.add_identity_arg(parser)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("worklist", help="Which companies are still unchecked")
    p_list.add_argument("--limit", type=int, default=None)
    p_list.add_argument("--include-long-shot", action="store_true",
                        help="Include the tail of the shortlist (rarely needed)")

    sub.add_parser("coverage", help="How much of the shortlist has been checked")

    p_none = sub.add_parser(
        "mark-insufficient",
        help="Record: searched, found no credible reviews")
    p_none.add_argument("--company", required=True)
    p_none.add_argument("--searched", default="",
                        help="Where you searched — this appears in the report")

    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)

    vacancies = kb.load_vacancies()
    companies = kb.load_companies()
    classes = REQUIRED_CLASSES + (("long_shot",) if getattr(args, "include_long_shot", False) else ())

    if args.cmd == "worklist":
        todo = worklist(vacancies, companies, classes, args.limit)
        if not todo:
            print("Every shortlist company has been checked — nothing to do.")
            return
        print("Companies without a recent check: %d\n" % len(todo))
        for item in todo:
            print("  %-11s %s" % (item["classification"], item["company"]))
        print("\n  Found data:  python tools/kb.py set-company-reputation "
              "--company \"<name>\" --rating N --wlb N --source Glassdoor")
        print("  Found none:  python tools/reputation.py mark-insufficient "
              "--company \"<name>\"")
        return

    if args.cmd == "coverage":
        stats = coverage(vacancies, companies, classes)
        print("Companies in the shortlist (%s): %d" % ("+".join(classes), stats["companies"]))
        print("  reputation found:             %d" % stats["found"])
        print("  checked, too few sources:     %d" % stats["insufficient"])
        print("  NOT CHECKED:                  %d" % stats["unchecked"])
        return

    if args.cmd == "mark-insufficient":
        if not mark_insufficient(companies, args.company, args.searched):
            print("Company '%s' is not in the database." % args.company)
            sys.exit(1)
        kb.save_companies(companies)

        # Rescoring is required, not merely nice. The report reads the SAVED
        # computed block rather than recomputing on the fly, so without this
        # step the record is stored while the vacancy still shows "not checked
        # yet" — the work is done and the person sees the opposite. That is
        # exactly what happened on the first run, 2026-08-06.
        import score

        vacancies = kb.load_vacancies()
        kb.attach_company_reputation(vacancies, companies)
        criteria, profile = score.load_criteria(), score.load_profile()
        touched = 0
        for rec in vacancies.values():
            if rec.get("company") != args.company:
                continue
            view = {k: v for k, v in rec.items() if k not in ("computed", "manual")}
            rec["computed"] = score.score_vacancy(view, criteria, profile)
            touched += 1
        kb.save_vacancies(vacancies)
        print("Recorded: '%s' — searched, no credible reviews found. "
              "Vacancies rescored: %d" % (args.company, touched))


if __name__ == "__main__":
    main()
