"""
Fetcher for freelancermap.de (https://www.freelancermap.de/projekte), a
German board of freelance projects.

Measured 2026-10-21 and 2026-10-22, no key, no cookie:

  * GET /projekte?query=.net&remoteInPercent[0]=100
    &projectContractTypes[0]=contracting is a page whose
    <script class="js-react-on-rails-component"
    data-component-name="ProjectSearch"> holds the search as JSON:
    initialState.result.projects (22) and result.count (96 that day);
  * the page's own script asks GET or POST /project/search/ajax?<the same
    query> (body {"changed": [...]}) and gets the same result as JSON:
    projects, count, currentPage, pagination, aggregations. That answer is
    read here: 0.65 MB against 1.3 MB for the page, and no HTML to cut;
  * paging does not reach an anonymous request: pagenr=2, 3 and 5, on the
    page (in the site's own paginator links, with every parameter) and on
    the ajax endpoint, all answered currentPage 1 and the same 22. page=2 and
    p=2 did the same (2026-10-21);
  * the search defaults to clients in Germany (countries[0]=1) when no
    country is given in the URL: 96; an empty `countries=` widens it to
    every country: 101 (2026-10-22). The fetcher sends the empty one;
  * sort=1 is newest first, sort=2 relevance: for ".net" the relevance
    order brought 19 postings the newest-first one did not.

So each query is asked twice (newest and relevance), several queries are
asked, and the results are merged on id. The 22 newest for ".net" on
2026-10-22 went back 15 days (2026-10-06 to 2026-10-21), so a daily run sees
every new posting of a query; what is older than that and not among the 22
most relevant is not reached.

A project carries id, slug, title, company (null on some; then
poster.company, then nothing), poster, city, country {nameEn, iso2},
projectContractType {type, remoteInPercent}, contractType, created (ISO),
description (the full HTML), beginningText ("ab sofort", a date),
durationText, budget (null or an empty list in 22 of 22), links.project and
a 1,000-number `embedding`.

`query=.net` also matches roles outside the stack (two accessibility
testers and a C++ desktop role among the 22 of 2026-10-22); they are kept
and the scoring judges the stack. 14 of 22 were written in German on
2026-10-21; the scoring's German gate reads the "(m/w/d)" marker and
German words.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Callable, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOURCE_NAME = "freelancermap"
SITE = "https://www.freelancermap.de"
SEARCH_URL = f"{SITE}/project/search/ajax"
PROJECT_URL = f"{SITE}/projekt/{{slug}}"
PAUSE_SECONDS = 1.0
DEFAULT_QUERIES = [".net", "c#", "asp.net", "blazor"]
SORTS = (1, 2)   # newest first, relevance
COMPANY_FALLBACK = "freelancermap client"
CONTRACT_TYPES = {"contracting": ["contract"], "permanent_position": [], "employee_leasing": ["contract"]}


def _get(url: str, params: Optional[dict] = None, timeout: int = common.DEFAULT_TIMEOUT):
    import requests

    headers = {"User-Agent": common.USER_AGENT, "Accept": "application/json"}
    resp = requests.get(url, params=params, timeout=timeout, headers=headers)
    resp.raise_for_status()
    return resp.json()


def search_params(query: str, sort: int, remote_percent: Optional[int] = 100,
                  contract_type: Optional[str] = "contracting") -> dict:
    params = {"query": query, "sort": sort, "countries": ""}
    if remote_percent is not None:
        params["remoteInPercent[0]"] = remote_percent
    if contract_type:
        params["projectContractTypes[0]"] = contract_type
    return params


def _contract(project: dict) -> dict:
    value = project.get("projectContractType")
    return value if isinstance(value, dict) else {}


def location(project: dict) -> str:
    """"100% remote; client in Frankfurt am Main, Germany". No " only":
    score.py reads it as a refusal, and the board's field does not say
    one."""
    percent = _contract(project).get("remoteInPercent")
    head = f"{percent}% remote" if isinstance(percent, (int, float)) else "Remote"
    country = project.get("country") if isinstance(project.get("country"), dict) else {}
    city = str(project.get("city") or "").strip()
    if city.lower() == "remote":
        city = ""
    place = ", ".join(p for p in (city, str(country.get("nameEn") or "").strip()) if p)
    return f"{head}; client in {place}" if place else head


def salary(project: dict) -> Optional[str]:
    """`budget` as given; it was null or an empty list in 22 of 22 projects
    (2026-10-22), so its shape when filled is unknown."""
    budget = project.get("budget")
    if budget in (None, "", [], {}):
        return None
    if isinstance(budget, (int, float)):
        return f"{budget:,} EUR"
    return str(budget).strip() or None


def description(project: dict) -> str:
    parts = [common.strip_html(str(project.get("description") or "")).strip()]
    start = str(project.get("beginningText") or "").strip()
    duration = str(project.get("durationText") or "").strip()
    if start:
        parts.append(f"Start: {start}")
    if duration:
        parts.append(f"Duration: {duration}")
    return "\n\n".join(p for p in parts if p)


def to_record(project: dict) -> Optional[dict]:
    """One project in the common schema; None for a malformed one."""
    if not isinstance(project, dict):
        return None
    pid = str(project.get("id") or "").strip()
    slug = str(project.get("slug") or "").strip()
    title = str(project.get("title") or "").strip()
    if not pid or not slug or not title:
        return None
    poster = project.get("poster") if isinstance(project.get("poster"), dict) else {}
    company = str(project.get("company") or poster.get("company") or "").strip() or COMPANY_FALLBACK
    contract = _contract(project)
    percent = contract.get("remoteInPercent")
    employment = list(CONTRACT_TYPES.get(str(contract.get("type") or ""), []))
    if not employment and str(project.get("contractType") or "").upper() == "CONTRACT":
        employment = ["contract"]
    skills = [str(s.get("en") or s.get("de")).strip() for s in project.get("skills") or []
              if isinstance(s, dict) and (s.get("en") or s.get("de"))]
    return {
        "source": SOURCE_NAME,
        "external_id": pid,
        "title": title,
        "company": company,
        "url": PROJECT_URL.format(slug=slug),
        "location_raw": location(project),
        "remote": percent == 100 if isinstance(percent, (int, float)) else None,
        "workplace_type": ("remote" if percent == 100 else "hybrid" if percent else "on-site")
        if isinstance(percent, (int, float)) else None,
        "employment_types": employment,
        "tags": skills[:8],
        "description_text": description(project),
        "posted_at": str(project.get("created") or "").strip() or None,
        "salary_raw": salary(project),
    }


def fetch(queries: Optional[List[str]] = None, remote_percent: Optional[int] = 100,
          contract_type: Optional[str] = "contracting", timeout: int = common.DEFAULT_TIMEOUT,
          get: Callable = None, pause: float = PAUSE_SECONDS, counts: Optional[dict] = None):
    """Every project the queries find, newest and most relevant, with the
    remote share and contract type given. `counts`, when given, receives how
    many were found and the count the board gave each query."""
    get = get or (lambda url, params=None: _get(url, params, timeout))
    queries = [q for q in (queries or DEFAULT_QUERIES) if str(q).strip()]
    asks = [(q, s) for q in queries for s in SORTS]
    hits, errors, totals = {}, [], {}
    for i, (query, sort) in enumerate(asks):
        if i:
            time.sleep(pause)
        try:
            payload = get(SEARCH_URL, search_params(query, sort, remote_percent, contract_type))
            projects = payload.get("projects") if isinstance(payload, dict) else None
            if not isinstance(projects, list):
                raise ValueError("the answer has no `projects` list")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{query} sort={sort}: {type(exc).__name__}")
            continue
        if isinstance(payload.get("count"), int):
            totals[query] = payload["count"]
        for project in projects:
            if isinstance(project, dict) and project.get("id") is not None:
                hits.setdefault(str(project["id"]), project)
    if len(errors) == len(asks):
        return [], "every search failed: " + ", ".join(errors)

    records, skipped = [], 0
    for project in hits.values():
        record = to_record(project)
        if record is None:
            skipped += 1
            continue
        records.append(record)
    if counts is not None:
        counts.update(found=len(hits), kept=len(records), totals=totals)
    notes = []
    if errors:
        notes.append("searches failed: " + ", ".join(errors))
    if skipped:
        notes.append(f"skipped {skipped} malformed")
    return records, ("; ".join(notes) or None)


def _configured_params() -> dict:
    """The params the active identity's sources file gives this source."""
    for src in common.load_sources():
        if src.get("name") == SOURCE_NAME:
            return dict(src.get("params") or {})
    return {}


def main() -> None:
    import argparse
    import identity as identity_mod

    parser = argparse.ArgumentParser(description="Collect fully remote contract projects from freelancermap.de")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--queries", nargs="*", default=None,
                        help="default: the identity's sources file, else DEFAULT_QUERIES")
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)
    params = _configured_params()
    counts: dict = {}
    records, note = fetch(args.queries or params.get("queries"),
                          params.get("remote_percent", 100), params.get("contract_type", "contracting"),
                          counts=counts)
    print(f"{SOURCE_NAME}: {len(records)} records of {counts.get('found', 0)} found; "
          f"the board's counts {counts.get('totals')} ({note or 'no remarks'})")
    for r in records:
        print(f"  {r['title']} @ {r['company']} | {r['location_raw']} | {r['posted_at']}")


if __name__ == "__main__":
    main()
