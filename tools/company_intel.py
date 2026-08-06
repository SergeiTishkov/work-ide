"""
Automatic collection of company facts from open sources.

Why: `ideal_company_traits` in the profile records "mature company (10+ years
old)" — a mature company matters because it usually means settled processes,
legacy systems and a calm pace rather than a race. But until this module the
trait was checked nowhere: the system simply did not know a company's age.

What is used, and why exactly this (measured 2026-07-31):
  * Wikidata / Wikipedia — open APIs, answering 200, returning structured
    facts: year founded (P571), employee count (P1128).
  * Reputation sites (Glassdoor, Trustpilot, Indeed, levels.fyi) and even the
    official Glassdoor API are unreachable programmatically: 403 behind
    Cloudflare and 410 Gone respectively. Getting in by script would take
    impersonating a live browser, which this project does not do (see
    CLAUDE.md, the boundary of what is allowed). Ratings and reviews from
    there are gathered by the agent through ordinary web search and entered
    via `tools/kb.py set-company-reputation` — that works, and is legal.

Small companies are usually absent from Wikidata, and that is fine: it is
precisely the large, mature enterprises we want that are represented there.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

WIKIDATA_SEARCH = "https://www.wikidata.org/w/api.php"
WIKIDATA_ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"

PROP_INCEPTION = "P571"
PROP_EMPLOYEES = "P1128"
PROP_INSTANCE_OF = "P31"

# Q-identifiers meaning "this is a company or organisation". Needed so that a
# library, song or town of the same name is not taken for a company.
COMPANY_LIKE_QIDS = {
    "Q4830453",   # business
    "Q783794",    # company
    "Q6881511",   # enterprise
    "Q891723",    # public company
    "Q167037",    # corporation
    "Q1058914",   # software company
    "Q18388277",  # technology company
    "Q43229",     # organization
}


def _session():
    import requests

    s = requests.Session()
    s.headers.update({"User-Agent": common.USER_AGENT})
    return s


def _search_entity(session, name: str, timeout: int) -> Optional[str]:
    resp = session.get(
        WIKIDATA_SEARCH,
        params={
            "action": "wbsearchentities",
            "search": name,
            "language": "en",
            "format": "json",
            "limit": 5,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    for item in resp.json().get("search", []):
        desc = (item.get("description") or "").lower()
        # Quick rejection of the obviously-not-a-company by description.
        if any(w in desc for w in ("company", "corporation", "business", "platform", "service", "software")):
            return item.get("id")
    hits = resp.json().get("search", [])
    return hits[0].get("id") if hits else None


def _parse_year(time_value: str) -> Optional[int]:
    m = re.match(r"[+-](\d{4})", time_value or "")
    return int(m.group(1)) if m else None


def fetch_company_facts(name: str, timeout: int = common.DEFAULT_TIMEOUT) -> dict:
    """Returns a dict of facts about a company. Never raises: absence of data
    is the ordinary, expected case (small companies are not in Wikidata).
    """
    result = {"source": "wikidata", "checked_at": datetime.now(timezone.utc).isoformat()}
    try:
        session = _session()
        qid = _search_entity(session, name, timeout)
        if not qid:
            result["found"] = False
            return result

        resp = session.get(WIKIDATA_ENTITY.format(qid=qid), timeout=timeout)
        resp.raise_for_status()
        claims = resp.json()["entities"][qid].get("claims", {})

        result["found"] = True
        result["wikidata_id"] = qid

        inception = claims.get(PROP_INCEPTION)
        if inception:
            value = inception[0]["mainsnak"].get("datavalue", {}).get("value", {})
            year = _parse_year(value.get("time", ""))
            if year:
                result["founded_year"] = year
                result["age_years"] = datetime.now(timezone.utc).year - year

        employees = claims.get(PROP_EMPLOYEES)
        if employees:
            value = employees[0]["mainsnak"].get("datavalue", {}).get("value", {})
            amount = value.get("amount")
            if amount:
                try:
                    result["employees"] = int(float(str(amount).lstrip("+")))
                except ValueError:
                    pass

        instance_qids = {
            c["mainsnak"].get("datavalue", {}).get("value", {}).get("id")
            for c in claims.get(PROP_INSTANCE_OF, [])
        }
        result["looks_like_company"] = bool(instance_qids & COMPANY_LIKE_QIDS)
        return result
    except Exception as exc:  # noqa: BLE001 - external source; no data is not fatal
        result["found"] = False
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result


def enrich_companies(companies: dict, only_names: Optional[set] = None,
                     recheck_after_days: int = 30, limit: Optional[int] = None) -> dict:
    """Adds facts to companies.json. Checks only the companies named in
    only_names (normally the ones appearing in the report), so as not to make
    hundreds of requests for companies that were filtered out anyway."""
    now = datetime.now(timezone.utc)
    stats = {"checked": 0, "found": 0, "skipped": 0}

    for slug, entry in companies.items():
        if only_names is not None and entry.get("name") not in only_names:
            continue
        intel = entry.get("intel")
        if intel and intel.get("checked_at"):
            try:
                checked = datetime.fromisoformat(intel["checked_at"])
                if (now - checked).days < recheck_after_days:
                    stats["skipped"] += 1
                    continue
            except ValueError:
                pass

        entry["intel"] = fetch_company_facts(entry.get("name", slug))
        stats["checked"] += 1
        if entry["intel"].get("found"):
            stats["found"] += 1
        if limit and stats["checked"] >= limit:
            break

    return stats


def main() -> None:
    import identity as identity_mod
    import kb

    parser = argparse.ArgumentParser(
        description="Collects open facts about companies (age, size) from Wikidata"
    )
    parser.add_argument("--all", action="store_true",
                        help="Walk every company, not only those in the report")
    parser.add_argument("--limit", type=int, default=60)
    identity_mod.add_identity_arg(parser)
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)

    companies = kb.load_companies()
    only = None
    if not args.all:
        vacancies = kb.load_vacancies()
        only = {
            v["company"] for v in vacancies.values()
            if v.get("computed", {}).get("classification") in ("hot_lead", "worth_a_look", "long_shot")
            and not v.get("duplicate_of")
        }
        print(f"Companies from the report to check: {len(only)}")

    stats = enrich_companies(companies, only_names=only, limit=args.limit)
    kb.save_companies(companies)
    print(f"Done: checked {stats['checked']}, found in Wikidata {stats['found']}, "
          f"skipped (data still fresh) {stats['skipped']}")


if __name__ == "__main__":
    main()
