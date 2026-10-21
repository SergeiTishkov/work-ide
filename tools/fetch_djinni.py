"""
Fetcher for djinni.co (https://djinni.co/jobs/), a job board of the
Ukrainian IT market.

Measured 2026-10-21 and 2026-10-22, no login, no cookie:

  * GET /jobs/?primary_keyword=.NET&employment=remote&page=N is an HTML
    page with one <script type="application/ld+json"> holding a list of
    schema.org JobPosting, 15 a page;
  * `country=GEO` (ISO 3166 alpha-3) and `region=worldwide` narrow the
    search to postings that name that country, or no country, in their
    candidate locations. 2026-10-21: the plain search had 47 .NET postings,
    country=GEO 4, region=worldwide 7, every one of the 11 also in the
    plain search. The extra searches are params and cost a page or two each;
  * once a search's own results run out, the following pages are filled
    with the board's newest postings of any kind (a sales manager, an
    auditor, QA): page 4 of the plain search on 2026-10-21 held 2 .NET
    postings and 13 others, and the GEO search's page 1 held its 4 and 11
    others (on 2026-10-22, its 4 alone). Those carry their own `category` ("Sales Manager", "QA
    Automation", "Other"), while every posting of the .NET results carried
    ".NET".

The rule for that: paging stops at the first page with no new posting
whose category is ".NET" or whose title names .NET, C# or ASP.NET
(STACK_RE); a posting is kept when its category is ".NET" or its title or
text names one of them.

A JobPosting: identifier, title, url, description (the full text, 818 to
5,135 characters), datePosted, validThrough, hiringOrganization.name,
employmentType (FULL_TIME 45 of 47, PART_TIME 2: hours, nothing about a
contract), jobLocationType ("TELECOMMUTE", absent on 4 of the 47 found by
the employment=remote filter), baseSalary (on 4 of 47: USD, minValue,
maxValue, unitText MONTH) and applicantLocationRequirements: one or a list
of {address: {addressCountry, addressRegion}}. The country is "UA" on some
postings and "UKR" on others; the rest are alpha-3 ("POL", "GEO"). Of the
47 .NET postings on 2026-10-21: 16 Ukraine alone, 19 the region "Europe",
7 nothing, 4 a list that holds Georgia, 1 another list.
"""
from __future__ import annotations

import html
import json
import re
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import places  # noqa: E402

SOURCE_NAME = "djinni"
SITE = "https://djinni.co"
JOBS_URL = f"{SITE}/jobs/"
PAUSE_SECONDS = 1.0
MAX_PAGES = 15
DEFAULT_KEYWORD = ".NET"
STACK_CATEGORIES = {".net"}
STACK_RE = re.compile(r"(?<![\w.])\.net\b|\bc#|\basp\.net\b|\bdotnet\b", re.I)
_LD_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S | re.I)
# The alpha-3 codes djinni has been seen to send, and the neighbours of its
# market; places.py reads alpha-2 only. An unknown code is written as it came.
ALPHA3 = {
    "UKR": "UA", "POL": "PL", "GEO": "GE", "ARM": "AM", "AZE": "AZ", "KAZ": "KZ", "KGZ": "KG",
    "UZB": "UZ", "MDA": "MD", "ROU": "RO", "BGR": "BG", "SVK": "SK", "CZE": "CZ", "HUN": "HU",
    "LTU": "LT", "LVA": "LV", "EST": "EE", "DEU": "DE", "AUT": "AT", "CHE": "CH", "NLD": "NL",
    "BEL": "BE", "FRA": "FR", "ESP": "ES", "PRT": "PT", "ITA": "IT", "GBR": "GB", "IRL": "IE",
    "SRB": "RS", "HRV": "HR", "SVN": "SI", "MNE": "ME", "MKD": "MK", "ALB": "AL", "BIH": "BA",
    "GRC": "GR", "CYP": "CY", "MLT": "MT", "TUR": "TR", "ISR": "IL", "ARE": "AE", "USA": "US",
    "CAN": "CA", "SWE": "SE", "NOR": "NO", "DNK": "DK", "FIN": "FI", "ISL": "IS", "LUX": "LU",
    "TJK": "TJ", "TKM": "TM", "BLR": "BY", "MNG": "MN",
}
# "Georgia" alone reads as the US state in most vacancies; these are
# countries, so it is written the way the ambiguous-place rules read the country.
COUNTRY_NAMES = {"Georgia": "country of Georgia"}
SALARY_UNITS = {"HOUR": "hour", "DAY": "day", "WEEK": "week", "MONTH": "month", "YEAR": "year"}


def _get(url: str, params: Optional[dict] = None, timeout: int = common.DEFAULT_TIMEOUT) -> str:
    import requests

    headers = {"User-Agent": common.USER_AGENT, "Accept": "text/html", "Accept-Language": "en"}
    resp = requests.get(url, params=params, timeout=timeout, headers=headers)
    resp.raise_for_status()
    return resp.text


def postings(page_html: str) -> List[dict]:
    """Every JobPosting in a page's JSON-LD blocks, a malformed block skipped."""
    found = []
    for block in _LD_RE.findall(page_html or ""):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        found += [x for x in items if isinstance(x, dict) and x.get("@type") == "JobPosting"]
    return found


def in_results(posting: dict) -> bool:
    """Looks like the search's own result: the category or the title is
    the stack. Decides whether paging goes on."""
    return (str(posting.get("category") or "").strip().lower() in STACK_CATEGORIES
            or bool(STACK_RE.search(str(posting.get("title") or ""))))


def on_stack(posting: dict) -> bool:
    """Kept: the search's own result, or a posting whose text names the
    stack (the module docstring)."""
    return in_results(posting) or bool(STACK_RE.search(str(posting.get("description") or "")))


def _country(code: str) -> str:
    code = str(code or "").strip().upper()
    name = places.country_of_code(ALPHA3.get(code, code)) or code
    return COUNTRY_NAMES.get(name, name)


def location(posting: dict, country: Optional[str] = None) -> str:
    """The candidate locations the employer ticked: "Remote; candidates in
    Poland, country of Georgia, Romania", "Remote; candidates in Europe";
    "Remote" when there are none.

    "candidates in" is one of the scoring's hiring_context_phrases, so a list
    that holds the residency is read as the employer naming it: eligibility
    "confirmed" for the 4 such postings of 2026-10-22, "unknown" with the
    bare list. A list of countries only, none of them `country` (the
    residency, alpha-3), ends in " only", as fetch_arcdev writes a country
    list without the residency: without it, 16 postings for candidates in
    Ukraine and one for five EU countries scored "unknown" eligibility on
    2026-10-22, one of them a hot lead. With no `country`, or with a region
    such as "Europe" in the list, no " only": score.py reads it as a refusal
    whoever is reading."""
    required = posting.get("applicantLocationRequirements")
    entries = required if isinstance(required, list) else [required] if required else []
    names, regions = [], False
    for entry in entries:
        address = (entry or {}).get("address") if isinstance(entry, dict) else None
        if not isinstance(address, dict):
            continue
        if address.get("addressCountry"):
            name = _country(address["addressCountry"])
        else:
            name = str(address.get("addressRegion") or address.get("addressLocality") or "").strip()
            regions = regions or bool(name)
        if name and name not in names:
            names.append(name)
    if not names:
        return "Remote"
    where = "Remote; candidates in " + ", ".join(names)
    if country and not regions and _country(country) not in names:
        where += " only"
    return where


def salary(posting: dict) -> Optional[str]:
    """baseSalary as "$6,000/month to $6,500/month", each bound with its
    unit, the shape score._extract_amounts reads."""
    base = posting.get("baseSalary")
    if not isinstance(base, dict):
        return None
    value = base.get("value") if isinstance(base.get("value"), dict) else {}
    lo, hi = value.get("minValue"), value.get("maxValue")
    if lo is None and hi is None:
        lo = value.get("value")
    numbers = [v for v in (lo, hi) if isinstance(v, (int, float))]
    if not numbers:
        return None
    unit = SALARY_UNITS.get(str(value.get("unitText") or "").upper(), "")
    currency = str(base.get("currency") or "").upper()
    if currency == "USD":
        if unit and unit != "year":
            return " to ".join(dict.fromkeys(f"${round(v):,}/{unit}" for v in numbers))
        return "-".join(dict.fromkeys(f"${round(v):,}" for v in numbers)) + (f"/{unit}" if unit else "")
    figures = "-".join(dict.fromkeys(f"{round(v):,}" for v in numbers))
    return f"{figures} {currency}" + (f"/{unit}" if unit else "")


def to_record(posting: dict, country: Optional[str] = None) -> Optional[dict]:
    """One JobPosting in the common schema; None for a malformed one.
    `country` is the residency (location)."""
    if not isinstance(posting, dict):
        return None
    job_id = str(posting.get("identifier") or "").strip()
    title = html.unescape(str(posting.get("title") or "")).strip()
    url = str(posting.get("url") or "").strip()
    org = posting.get("hiringOrganization") if isinstance(posting.get("hiringOrganization"), dict) else {}
    company = html.unescape(str(org.get("name") or "")).strip()
    if not job_id or not title or not url or not company:
        return None
    text = html.unescape(str(posting.get("description") or "")).strip()
    return {
        "source": SOURCE_NAME,
        "external_id": job_id,
        "title": title,
        "company": company,
        "url": url,
        "company_url": str(org.get("sameAs") or "").strip() or None,
        "location_raw": location(posting, country),
        # every posting here came from an employment=remote search; 4 of 47
        # lacked jobLocationType (2026-10-21)
        "remote": True,
        "workplace_type": "remote",
        "employment_types": posting.get("employmentType"),
        "tags": [str(posting["category"]).strip()] if posting.get("category") else [],
        "description_text": text,
        "posted_at": str(posting.get("datePosted") or "").strip() or None,
        "salary_raw": salary(posting),
    }


def searches(keyword: str = DEFAULT_KEYWORD, country: Optional[str] = None,
             worldwide: bool = True) -> List[dict]:
    """The query of each search: the plain one, then the residency's
    country, then the worldwide region."""
    base = {"primary_keyword": keyword, "employment": "remote"}
    found = [base]
    if country:
        found.append({**base, "country": str(country).strip().upper()})
    if worldwide:
        found.append({**base, "region": "worldwide"})
    return found


def _search(get: Callable, query: dict, pause: float, seen: set):
    """One search, page by page, until a page brings no new posting that
    looks like its own result; (kept, unrelated dropped, note). A first page
    that fails raises; a later one ends the search with a note."""
    kept, dropped = [], 0
    for page in range(1, MAX_PAGES + 1):
        if page > 1:
            time.sleep(pause)
        try:
            found = postings(get(JOBS_URL, {**query, "page": page}))
        except Exception as exc:  # noqa: BLE001
            if page == 1:
                raise
            return kept, dropped, f"page {page}: {type(exc).__name__}"
        fresh = [p for p in found if str(p.get("identifier") or "") not in seen]
        wanted = [p for p in fresh if on_stack(p)]
        dropped += len(fresh) - len(wanted)
        for p in fresh:
            seen.add(str(p.get("identifier") or ""))
        kept += wanted
        if not any(in_results(p) for p in fresh):
            return kept, dropped, None
    return kept, dropped, f"stopped after {MAX_PAGES} pages"


def fetch(keyword: str = DEFAULT_KEYWORD, country: Optional[str] = None, worldwide: bool = True,
          timeout: int = common.DEFAULT_TIMEOUT, get: Callable = None, pause: float = PAUSE_SECONDS,
          counts: Optional[dict] = None):
    """Every remote `keyword` posting of the plain search and, when given,
    the `country` (alpha-3, "GEO") and worldwide searches, the board's
    filler pages left out. `counts`, when given, receives how many were kept
    and how many unrelated postings were dropped."""
    get = get or (lambda url, params=None: _get(url, params, timeout))
    queries = searches(keyword, country, worldwide)
    seen, kept, errors, notes, dropped = set(), [], [], [], 0
    for i, query in enumerate(queries):
        if i:
            time.sleep(pause)
        label = query.get("country") or query.get("region") or "plain"
        try:
            found, unrelated, note = _search(get, query, pause, seen)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{label}: {type(exc).__name__}")
            continue
        kept += found
        dropped += unrelated
        if note:
            notes.append(f"{label} {note}")
    if len(errors) == len(queries):
        return [], "every search failed: " + ", ".join(errors)

    records, skipped = [], 0
    for posting in kept:
        record = to_record(posting, country)
        if record is None:
            skipped += 1
            continue
        records.append(record)
    if counts is not None:
        counts.update(kept=len(records), unrelated=dropped)
    if errors:
        notes.insert(0, "searches failed: " + ", ".join(errors))
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

    parser = argparse.ArgumentParser(description="Collect remote .NET postings from djinni.co")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--country", default=None,
                        help='ISO alpha-3 code, e.g. "GEO"; default: the identity\'s sources file, else none')
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)
    params = _configured_params()
    country = args.country or params.get("country")
    counts: dict = {}
    records, note = fetch(params.get("keyword", DEFAULT_KEYWORD), country, params.get("worldwide", True),
                          counts=counts)
    print(f"{SOURCE_NAME}: {len(records)} records, {counts.get('unrelated', 0)} unrelated left out, "
          f"country {country} ({note or 'no remarks'})")
    for r in records:
        print(f"  {r['title']} @ {r['company']} | {r['location_raw']} | {r['salary_raw']}")


if __name__ == "__main__":
    main()
