"""
Fetcher for Remote Rocketship (https://www.remoterocketship.com).

A remote-jobs aggregator that reads employers' own application systems and
classifies every posting: employment type, location type, a salary converted to
US dollars, a tech stack. Its listing pages are ordinary server-rendered HTML
carrying the whole result set as Next.js page data, served to an ordinary GET
with no authorisation and no anti-bot challenge (measured 2026-09-13).

WHY IT IS HERE
--------------
It is the one open board found that FILTERS BY ENGAGEMENT for real. A URL of
the shape /jobs/<title-or-technology>/<employment-type>/ returns only that
type — every record on /jobs/net/contract/ says "contract", every record on
/jobs/developer/part-time/ says "part-time" — and the type arrives as a field,
not a phrase. For a search that needs part-time or contract work, that is the
difference between a structured statement and a guess.

WHAT WAS MEASURED BEFORE TRUSTING IT
------------------------------------
* Each listing gives the TWENTY newest matches and no more. `?page=2` returns
  19 of the same 20 — there is no paging for an anonymous page. So breadth
  comes from several slugs, not from depth.
* Some slugs are not what they look like. /jobs/c-sharp/part-time/ claims 2689
  results and lists pharmacists, adjunct faculty and customer service — the
  slug falls back to "everything part-time". /jobs/net/contract/ is the real
  thing: 115 results, nearly all .NET. A slug is added only after its first
  page has been read.
* An unknown slug is a 404, not an empty page. That is a configuration
  mistake, and it is reported as one.
* The job page carries schema.org JobPosting with the full description,
  `employmentType` and `applicantLocationRequirements`, so the shared JSON-LD
  reader in enrich_descriptions.py can fill in text for the shortlist.

WHAT A RECORD LOOKS LIKE
------------------------
`url` is the Remote Rocketship page — the one the description reader and the
link checker can work with. `company_url` is the employer's own posting, which
the report shows as the place to apply directly.
"""
from __future__ import annotations

import html
import json
import re
import sys
import time
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOURCE_NAME = "remoterocketship"
BASE_URL = "https://www.remoterocketship.com"
LISTING_URL = BASE_URL + "/jobs/{slug}/{employment}/"
JOB_URL = BASE_URL + "/company/{company}/jobs/{job}/"

# Read one by one before being listed (see the module docstring). Broad titles
# for reach, .NET for fit.
DEFAULT_SLUGS = ["net", "net-developer", "developer", "software-engineer",
                 "fullstack-engineer", "backend-engineer"]
DEFAULT_EMPLOYMENT = ["part-time", "contract"]
PAUSE_SECONDS = 1.0

_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)</script>')

# Remote Rocketship's own words for a salary period, to the units score.py
# reads. A day and a week are converted here, because the amount extractor
# knows hours, months and years only — "$80 per day" would otherwise read as
# eighty dollars an hour.
_HOURS_PER_DAY = 8
_WEEKS_PER_YEAR = 52


def parse_listing(body: str) -> tuple:
    """(job dicts, note). Zero jobs and a note when the page data is missing.

    The page data is the whole contract with this site: if it is gone, the
    markup changed, and a half-parsed page would be worse than none.
    """
    match = _NEXT_DATA_RE.search(body or "")
    if not match:
        return [], "the page format changed: no __NEXT_DATA__ block"
    try:
        data = json.loads(match.group(1))
    except ValueError:
        return [], "the page format changed: __NEXT_DATA__ is not JSON"
    props = ((data.get("props") or {}).get("pageProps") or {}) if isinstance(data, dict) else {}
    jobs = props.get("initialJobOpenings")
    if not isinstance(jobs, list):
        return [], "the page format changed: no initialJobOpenings list"
    return jobs, None


def _salary(item: dict) -> Optional[str]:
    """The salary in US dollars, in a unit the scoring understands."""
    salary = item.get("salaryRange")
    if not isinstance(salary, dict):
        return None
    low = salary.get("minSalaryAsUSD")
    high = salary.get("maxSalaryAsUSD")
    if low is None and high is None:
        return None
    period = str(salary.get("salaryType") or "").strip().lower()
    factor, unit = 1.0, period or "per year"
    if period == "per day":
        factor, unit = 1.0 / _HOURS_PER_DAY, "per hour"
    elif period == "per week":
        factor, unit = float(_WEEKS_PER_YEAR), "per year"

    def money(value):
        value = float(value) * factor
        return f"${value:,.0f}"

    if low is not None and high is not None and high != low:
        return f"{money(low)} - {money(high)} {unit}"
    return f"{money(low if low is not None else high)} {unit}"


_ANYWHERE = {"worldwide", "anywhere", "global", "remote", ""}


def _location(item: dict) -> str:
    """Where the applicant must be, in the phrase score.py reads as a restriction.

    The board's location for a remote job is not an office address: its own
    job page publishes the same value as schema.org
    `applicantLocationRequirements` (measured 2026-09-13 — "Brazil" on a
    "Senior Back-End Developer, .NET" whose slug says "worldwide-remote" is the
    one exception we have seen, and the slug is not a field). Written as "X
    only", the way fetch_himalayas writes its locationRestrictions, so the
    structured-location gate treats it as the requirement it is. Without that,
    Brazil-only and Peru-only contracts sat in "hours not confirmed" in the
    first part-time run — a person asked to check the hours of work they could
    not take from where they live.
    """
    countries = item.get("locationCountries")
    if isinstance(countries, list) and countries:
        names = [str(c).strip() for c in countries if str(c or "").strip()]
    else:
        names = [str(item.get("location") or "").strip()]
    names = [n for n in names if n.lower() not in _ANYWHERE]
    if not names:
        return "Worldwide"
    return ", ".join(names) + " only"


def _to_common_schema(item: dict) -> Optional[dict]:
    if not isinstance(item, dict):
        return None
    title = str(item.get("roleTitle") or "").strip()
    company = item.get("company") if isinstance(item.get("company"), dict) else {}
    company_name = str(company.get("name") or "").strip()
    company_slug = str(company.get("slug") or "").strip()
    job_slug = str(item.get("slug") or "").strip()
    if not title or not company_name or not company_slug or not job_slug or not item.get("id"):
        return None

    tech = [str(t) for t in (item.get("techStack") or []) if t]
    summary = " ".join(str(item.get(k) or "") for k in
                       ("twoLineJobDescriptionSummary", "jobDescriptionSummary")).strip()
    description = summary
    if tech:
        description += f"\n\nTech stack: {', '.join(tech)}"
    if item.get("salaryRange") and (item["salaryRange"] or {}).get("salaryHumanReadableText"):
        description += f"\n\nPay as posted: {item['salaryRange']['salaryHumanReadableText']}"

    location_type = str(item.get("locationType") or "").strip().lower()
    return {
        "source": SOURCE_NAME,
        "external_id": f"{SOURCE_NAME}:{item['id']}",
        "title": html.unescape(title),
        "company": html.unescape(company_name),
        "url": JOB_URL.format(company=company_slug, job=job_slug),
        # The employer's own posting: where a person actually applies.
        "company_url": str(item.get("url") or "").strip() or None,
        "location_raw": _location(item),
        "remote": True if location_type == "remote" else None,
        "workplace_type": location_type or None,
        "employment_types": item.get("employmentType"),
        "tags": tech,
        "description_text": description,
        "posted_at": item.get("created_at"),
        "salary_raw": _salary(item),
    }


def _fetch_page(slug: str, employment: str, timeout: int) -> Optional[str]:
    """The listing's HTML, or None when the slug does not exist (404)."""
    import requests

    url = LISTING_URL.format(slug=slug, employment=employment)
    resp = requests.get(url, headers={"User-Agent": common.USER_AGENT}, timeout=timeout)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.text


def fetch(slugs: Optional[List[str]] = None,
          employment_types: Optional[List[str]] = None,
          timeout: int = common.DEFAULT_TIMEOUT):
    """Every (slug x employment type) listing. Returns (records, note)."""
    slugs = slugs or DEFAULT_SLUGS
    employment_types = employment_types or DEFAULT_EMPLOYMENT

    records: List[dict] = []
    seen = set()
    notes: List[str] = []
    for slug in slugs:
        for employment in employment_types:
            try:
                body = _fetch_page(slug, employment, timeout)
            except Exception as exc:  # noqa: BLE001
                notes.append(f"{slug}/{employment}: {type(exc).__name__}")
                continue
            if body is None:
                notes.append(f"{slug}/{employment}: no such listing (404) — check the slug")
                continue
            jobs, problem = parse_listing(body)
            if problem:
                notes.append(f"{slug}/{employment}: {problem}")
                continue
            for item in jobs:
                rec = _to_common_schema(item)
                if rec is None or rec["external_id"] in seen:
                    continue
                seen.add(rec["external_id"])
                records.append(rec)
            time.sleep(PAUSE_SECONDS)

    return records, ("; ".join(notes[:4]) or None)


if __name__ == "__main__":
    import identity as identity_mod

    identity_mod.standalone_main(fetch, SOURCE_NAME)
