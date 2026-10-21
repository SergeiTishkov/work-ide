"""
What each LinkedIn search brings to the shortlist (task 0050).

The paced LinkedIn run asks hundreds of (keyword, place) searches and takes
hours. A search is worth its time when vacancies it alone found reach the
shortlist (hot_lead, worth_a_look, long_shot); one whose shortlisted
vacancies every other search found too can go without losing anything.

Reads `found_by` on each LinkedIn vacancy: every search that ever served it
(tools/fetch_linkedin.py, kept across runs by kb.merge_vacancy). Vacancies
fetched before 2026-10-21 carry none and are counted apart.

    python tools/linkedin_yield.py --identity sharp [--by query|keyword|country] [--json]
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_linkedin  # noqa: E402

SHORTLIST = ("hot_lead", "worth_a_look", "long_shot")
# A narrower query names a region; its country is the one split.
REGION_COUNTRY = {region: country for country, regions in fetch_linkedin.SPLIT_REGIONS.items()
                  for region in regions}


def group_of(query: str, by: str) -> str:
    """The query itself, its keyword, or the country it searched."""
    keyword, _, place = query.rpartition(" @ ")
    if by == "keyword":
        return keyword
    if by == "country":
        return REGION_COUNTRY.get(place, place)
    return query


def tally(vacancies: Iterable[dict], by: str = "query") -> dict:
    """{"rows": [{group, served, shortlisted, alone}], "unknown": n}, rows in
    the order to cut first: fewest shortlisted found by that group alone,
    then the most served (the longest to read). `alone`: shortlisted
    vacancies no other group found."""
    rows: Dict[str, dict] = defaultdict(lambda: {"served": 0, "shortlisted": 0, "alone": 0})
    unknown = 0
    for v in vacancies:
        if v.get("source") != "linkedin" or v.get("duplicate_of"):
            continue
        queries: List[str] = v.get("found_by") or []
        if not queries:
            unknown += 1
            continue
        groups = list(dict.fromkeys(group_of(q, by) for q in queries))
        short = (v.get("computed") or {}).get("classification") in SHORTLIST
        for g in groups:
            rows[g]["served"] += 1
            rows[g]["shortlisted"] += short
            rows[g]["alone"] += short and len(groups) == 1
    ordered = sorted(({"group": g, **r} for g, r in rows.items()),
                     key=lambda r: (r["alone"], r["shortlisted"], -r["served"], r["group"]))
    return {"rows": ordered, "unknown": unknown}


def main() -> None:
    import argparse
    import identity as identity_mod
    import kb

    parser = argparse.ArgumentParser(description="What each LinkedIn search brings to the shortlist")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--by", choices=("query", "keyword", "country"), default="query")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)
    result = tally(kb.load_vacancies().values(), args.by)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return
    print(f"{'alone':>5} {'short':>5} {'served':>6}  {args.by}")
    for r in result["rows"]:
        print(f"{r['alone']:>5} {r['shortlisted']:>5} {r['served']:>6}  {r['group']}")
    if result["unknown"]:
        print(f"{result['unknown']} LinkedIn vacancies were fetched before searches were recorded")


if __name__ == "__main__":
    main()
