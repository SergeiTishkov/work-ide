"""
Fetcher for Arc's own job requests (https://arc.dev/remote-jobs).

Arc is a marketplace for remote work: a client posts a request, Arc matches
developers from its pool. Its site is a Next.js app over a JSON API at
api.arc.dev, no key and no cookie (measured 2026-10-21):

  * POST /job-requests/public-search with a JSON body
    {"page": n, "per_page": 1..100, "sort_by": "latest", "country_code": "GE"}
    -> {"total_job_count", "jobs"}; total_job_count counts what the filter
    left, per_page 101 is answered 409. The header `x-requested-from: arc-next`
    is required: without it the answer is 422 "csrf check failed".
    67 requests on the board that day, 56 of them contract, 11 permanent;
    45 with country_code GE (the 33 with no country list plus the 12 whose
    list holds GE);
  * GET /job-requests/<random_key>, same header: one request, adding the
    markdown `description`, `required_locations` (["worldwide"]),
    `available_hours_per_week`, `estimated_weeks`, `discipline`, `state`.

A list item has no description; it carries job_type (contract|permanent),
time_zone with time_zone_offset, client_time_zone_restriction (null, overlap,
strict), overlap_hours, required_countries (ISO codes; empty for no list; 1
to 177 codes when present), an hourly or an annual range, posted_at (unix
seconds) and categories. `company` is an object whose fields were all null in
67 of 67 items: the client is not named.

The page a person opens is arc.dev/remote-jobs/details/<url_string>-<random_key>
(the canonical link of a detail page, checked 2026-10-21).

`country_code` is the identity's residency, so it lives in the identity's
sources file; none fetches every request.

Not fetched: the board's second list, POST /p/job-posts/public-search
("externalJobs", ~9,000), is a re-index of LinkedIn postings with LinkedIn
links. Measured 2026-10-21: about zero .NET postings open worldwide in it;
LinkedIn is read directly by fetch_linkedin.py.

Measured 2026-10-21 with country_code GE: one .NET request,
"Senior C#/.NET Engineer (Trading System) - Part-time", worldwide, $40-$70 an
hour, 20 hours a week.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import places  # noqa: E402

SOURCE_NAME = "arcdev"
API = "https://api.arc.dev"
LIST_URL = f"{API}/job-requests/public-search"
DETAIL_URL = f"{API}/job-requests/{{key}}"
PAGE_URL = "https://arc.dev/remote-jobs/details/{slug}-{key}"
# Without it: 422 "csrf check failed" (2026-10-21).
HEADERS = {"x-requested-from": "arc-next", "Accept": "application/json"}
PER_PAGE = 100   # the API's ceiling: per_page 101 was answered 409 (2026-10-21)
MAX_PAGES = 10
PAUSE_SECONDS = 1.0
COMPANY_FALLBACK = "Arc.dev client"   # config/company_kinds.yaml lists "arc dev" as a marketplace
# "Georgia" alone reads as the US state in most vacancies; the codes here are
# countries, so it is written the way the ambiguous-place rules read the country.
COUNTRY_NAMES = {"Georgia": "country of Georgia"}
# available_hours_per_week as an engagement. Values on 2026-10-22: 10, 12,
# 20, 25, 30 and 40. Titles with 40 said "FT"/"Fulltime", with 10-25 "PT" or
# "Part-time"; 30 was on one "WW - FT" and one "WW-PT" title, so it is left
# to the text.
PART_TIME_MAX_HOURS = 25
FULL_TIME_MIN_HOURS = 35


def _request(method: str, url: str, body: Optional[dict] = None, timeout: int = common.DEFAULT_TIMEOUT):
    import requests

    headers = {"User-Agent": common.USER_AGENT, **HEADERS}
    resp = requests.request(method, url, json=body, timeout=timeout, headers=headers)
    resp.raise_for_status()
    return resp.json()


def _country(code: str) -> str:
    name = places.country_of_code(code) or str(code).strip().upper()
    return COUNTRY_NAMES.get(name, name)


def _zone(item: dict, detail: dict) -> str:
    """The client's time zone as a label. "Pacific Time (US & Canada)" loses
    its brackets, which would otherwise name two countries in a location; a
    zone named after a city ("Singapore", "London") is given as its offset
    only, for the same reason."""
    name = str(item.get("time_zone") or detail.get("timezone") or "").strip()
    offset = str(item.get("time_zone_offset") or detail.get("timezone_offset") or "").strip()
    if name.lower() == "no-preference":
        return ""
    name = re.sub(r"\s*\([^)]*\)", "", name).strip()
    utc = f"UTC{offset}" if offset else ""
    if name.endswith(" Time"):
        return f"{name} ({utc})" if utc else name
    return utc


def _countries(codes: List[str], country_code: Optional[str]) -> str:
    """A country list as a location. One that holds `country_code` names it
    and the count, without "only": score.py's structured-location gate reads
    " only" as a refusal whoever is reading, and these lists ran to 177 codes
    (2026-10-21). One that does not is "<names> only", the first five named."""
    asked = str(country_code or "").strip().upper()
    if asked and asked in {c.upper() for c in codes}:
        if len(codes) == 1:
            return _country(asked)
        return f"{len(codes)} countries including {_country(asked)}"
    names = [_country(c) for c in codes]
    if len(names) > 5:
        return f"{len(names)} countries ({', '.join(names[:5])}, ...) only"
    return ", ".join(names) + " only"


def location(item: dict, detail: Optional[dict] = None, country_code: Optional[str] = None) -> str:
    """Where the work may be done, then the time-zone condition:
    "Worldwide; overlap 4 h with Pacific Time (UTC-07:00)"."""
    detail = detail or {}
    places_said = [str(p).strip() for p in detail.get("required_locations") or [] if str(p).strip()]
    codes = [str(c).strip() for c in (item.get("required_countries")
                                      or detail.get("required_countries") or []) if str(c).strip()]
    if codes:
        where = _countries(codes, country_code)
    elif places_said:
        where = ", ".join(p[:1].upper() + p[1:] for p in places_said)
    else:
        where = "Worldwide"
    restriction = item.get("client_time_zone_restriction") or detail.get("client_timezone_restriction")
    hours = item.get("overlap_hours") or detail.get("overlap_hours")
    zone = _zone(item, detail)
    if zone and restriction == "overlap":
        where += f"; overlap {hours} h with {zone}" if hours else f"; overlap with {zone}"
    elif zone and restriction == "strict":
        where += f"; working hours of {zone}"
    return where


def salary(item: dict) -> Optional[str]:
    for lo_key, hi_key, unit in (("min_hourly_rate", "max_hourly_rate", "hour"),
                                 ("min_annual_salary", "max_annual_salary", "year")):
        lo, hi = item.get(lo_key), item.get(hi_key)
        if lo and hi:
            return f"${int(lo):,}-${int(hi):,}/{unit}"
        if lo or hi:
            return f"${int(lo or hi):,}/{unit}"
    return None


def employment(item: dict, detail: Optional[dict] = None) -> List[str]:
    """contract from job_type; part-time or full-time from the client's
    available_hours_per_week. "permanent" says how long, not how many hours
    (normalize.py), so it adds nothing on its own."""
    found = ["contract"] if item.get("job_type") == "contract" else []
    hours = (detail or {}).get("available_hours_per_week")
    if isinstance(hours, (int, float)) and hours > 0:
        if hours <= PART_TIME_MAX_HOURS:
            found.append("part-time")
        elif hours >= FULL_TIME_MIN_HOURS:
            found.append("full-time")
    return found


def description(item: dict, detail: Optional[dict] = None) -> str:
    """The request's markdown, then the facts the list gives in fields. With
    no detail, the facts alone."""
    detail = detail or {}
    parts = [str(detail.get("description") or "").strip()]
    hours, weeks = detail.get("available_hours_per_week"), detail.get("estimated_weeks")
    if hours:
        parts.append(f"Engagement: {hours} hours a week" + (f", estimated {weeks} weeks" if weeks else ""))
    skills = [str(c.get("name")).strip() for c in item.get("categories") or []
              if isinstance(c, dict) and c.get("name")]
    if skills:
        parts.append("Skills: " + ", ".join(skills))
    if item.get("experience_level"):
        parts.append(f"Level: {item['experience_level']}")
    return "\n\n".join(p for p in parts if p)


def to_record(item: dict, detail: Optional[dict] = None, country_code: Optional[str] = None) -> Optional[dict]:
    """One list item (with its detail, when fetched) in the common schema;
    None for a malformed item."""
    if not isinstance(item, dict):
        return None
    key = str(item.get("random_key") or "").strip()
    title = str(item.get("title") or "").strip()
    slug = str(item.get("url_string") or (detail or {}).get("url_string") or "").strip()
    if not key or not title or not slug:
        return None
    company = item.get("company") if isinstance(item.get("company"), dict) else {}
    epoch = item.get("posted_at")
    return {
        "source": SOURCE_NAME,
        "external_id": key,
        "title": title,
        "company": str(company.get("name") or "").strip() or COMPANY_FALLBACK,
        "url": PAGE_URL.format(slug=slug, key=key),
        "location_raw": location(item, detail, country_code),
        "remote": True,
        "workplace_type": "remote",
        "employment_types": employment(item, detail),
        "tags": [str(c.get("name")).strip() for c in item.get("categories") or []
                 if isinstance(c, dict) and c.get("name")][:6],
        "description_text": description(item, detail),
        "posted_at": None,
        "posted_at_epoch": epoch if isinstance(epoch, (int, float)) else None,
        "salary_raw": salary(item),
    }


def fetch(country_code: Optional[str] = None, details: bool = True,
          timeout: int = common.DEFAULT_TIMEOUT, get: Callable = None, post: Callable = None,
          pause: float = PAUSE_SECONDS):
    """Every request open to `country_code` (every request when none), each
    with its full text when `details`."""
    post = post or (lambda url, body: _request("POST", url, body, timeout))
    get = get or (lambda url: _request("GET", url, None, timeout))
    body = {"per_page": PER_PAGE, "sort_by": "latest"}
    if country_code:
        body["country_code"] = str(country_code).strip().upper()
    try:
        items, page, total = [], 1, None
        while page <= MAX_PAGES:
            payload = post(LIST_URL, {"page": page, **body})
            jobs = payload.get("jobs") if isinstance(payload, dict) else None
            if not isinstance(jobs, list):
                raise ValueError("the answer has no `jobs` list")
            items += jobs
            total = payload.get("total_job_count")
            if len(jobs) < PER_PAGE or (isinstance(total, int) and page * PER_PAGE >= total):
                break
            page += 1
            time.sleep(pause)
    except Exception as exc:  # noqa: BLE001
        return [], f"{type(exc).__name__}: {exc}"

    records, skipped, closed, notes, seen = [], 0, 0, [], set()
    for item in items:
        key = str(item.get("random_key") or "").strip() if isinstance(item, dict) else ""
        if key and key in seen:
            continue
        seen.add(key)
        detail = None
        if details and key:
            try:
                time.sleep(pause)
                detail = get(DETAIL_URL.format(key=key))
            except Exception as exc:  # noqa: BLE001
                notes.append(f"{key}: {type(exc).__name__}")   # the list's fields stand in
            # 2026-10-21 an open one said state "opened", closed false.
            if isinstance(detail, dict) and (detail.get("closed") is True or detail.get("state") == "closed"):
                closed += 1
                continue
        record = to_record(item, detail if isinstance(detail, dict) else None, country_code)
        if record is None:
            skipped += 1
            continue
        records.append(record)
    if skipped:
        notes.append(f"skipped {skipped} malformed")
    if closed:
        notes.append(f"{closed} closed on their detail page")
    if isinstance(total, int) and len(items) < total:   # total_job_count counts the filtered list
        notes.append(f"read {len(items)} of {total}")
    return records, ("; ".join(notes) or None)


def main() -> None:
    import argparse
    import identity as identity_mod

    parser = argparse.ArgumentParser(description="Collect Arc's own job requests")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--country-code", default=None,
                        help="ISO code; default: the identity's sources file, else every request")
    parser.add_argument("--no-details", action="store_true", help="the list's fields only")
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)
    country = args.country_code or _configured_params().get("country_code")
    records, note = fetch(country, details=not args.no_details)
    print(f"{SOURCE_NAME}: {len(records)} records, country_code {country} ({note or 'no remarks'})")
    for r in records:
        print(f"  {r['title']} | {r['location_raw']} | {r['salary_raw']} | {r['employment_types']}")


def _configured_params() -> dict:
    """The params the active identity's sources file gives this source."""
    for src in common.load_sources():
        if src.get("name") == SOURCE_NAME:
            return dict(src.get("params") or {})
    return {}


if __name__ == "__main__":
    main()
