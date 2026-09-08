"""
Fetcher for JobServe — a long-standing UK contract board.

The richest of the four UK sources added in September 2026, and the only one
that needs work to reach: the search is an ASP.NET WebForms flow, so a keyword
search is three requests rather than one.

    GET  /gb/en/Job-Search/                    the form, and its hidden fields
    POST /gb/en/Job-Search/  txtKey + btnSearch  -> redirects with a search id
    GET  /gb/en/JobListing.aspx?shid=...&ovrpp=jl   20 results

That is a form submission, the same one a browser makes, using the page's own
fields. It is not a way round anything: nothing here fakes a browser, solves a
challenge or rotates an identity.

WHY THE `&ovrpp=jl` MATTERS
--------------------------
Without it the listing sometimes comes back with no results at all — measured
on the day this was written, one run in three. A source that intermittently
returns nothing is worse than no source: every empty run reads as "the markup
changed" and teaches a person to ignore the warning. With it, three runs out of
three returned 20.

WHAT A RESULT CARRIES
---------------------
More than any other board here: title, the agency's name ("Employment
Business"), a location that is often stated as "Remote, UK", a day rate, the
contract type, and a real paragraph of description rather than a snippet.

The search is a keyword one, so the results are genuinely about the keyword —
unlike ContractorUK, whose ".net" also matches "Biodiversity Net Gain".
"""
from __future__ import annotations

import html
import re
import sys
import time
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOURCE_NAME = "jobserve"
BASE_URL = "https://www.jobserve.com"
SEARCH_URL = BASE_URL + "/gb/en/Job-Search/"
LISTING_URL = BASE_URL + "/gb/en/JobListing.aspx?shid={shid}&ovrpp=jl"

# The form field names, as the page writes them. WebForms prefixes everything
# with its control tree, and a bare "txtKey" is ignored silently.
KEYWORD_FIELD = "ctl00$main$srch$ctl_qs$txtKey"
SEARCH_BUTTON = "ctl00$main$srch$ctl_qs$btnSearch"

DEFAULT_QUERIES = [".net developer", "c# developer", "asp.net", "sql server developer"]
PAUSE_SECONDS = 2.0          # three requests per keyword: be gentle

_HIDDEN_RE = re.compile(
    r'<input[^>]+type="hidden"[^>]+name="([^"]+)"[^>]+value="([^"]*)"')
_SHID_RE = re.compile(r"shid=([A-Z0-9]+)")

_ITEM_RE = re.compile(
    r'<div class="jobListItem[^"]*" id="([A-Z0-9]+)">([\s\S]*?)(?=<div class="jobListItem|<div class="jobListingPaging|\Z)')
_TITLE_RE = re.compile(r'<a href="([^"]+)"[^>]*class="jobListPosition"[^>]*>([\s\S]*?)</a>')
_TITLE_ALT_RE = re.compile(r'class="jobListPosition"[^>]*>([\s\S]*?)</a>')
_DETAIL_RE = re.compile(
    r'<span id="summ(location|rate|type)"[^>]*>([\s\S]*?)</span>')
_AGENCY_RE = re.compile(
    r'Employment Business</label>[\s\S]{0,400}?<a [^>]*>([\s\S]*?)</a>')
_SKILLS_RE = re.compile(r'<p class="jobListSkills">([\s\S]*?)</p>')
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(fragment: Optional[str]) -> str:
    if not fragment:
        return ""
    return " ".join(html.unescape(_TAG_RE.sub(" ", fragment)).split())


def _item_to_common_schema(job_id: str, item_html: str) -> Optional[dict]:
    title_match = _TITLE_RE.search(item_html)
    if not title_match:
        return None
    href, title = title_match.group(1), _clean(title_match.group(2))
    if not title:
        return None

    details = {key: _clean(value) for key, value in _DETAIL_RE.findall(item_html)}
    agency_match = _AGENCY_RE.search(item_html)
    agency = _clean(agency_match.group(1)) if agency_match else ""
    skills = _clean(_SKILLS_RE.search(item_html).group(1)) if _SKILLS_RE.search(item_html) else ""

    tags = ["market:United Kingdom"]
    if details.get("type"):
        tags.append(details["type"])

    return {
        "source": SOURCE_NAME,
        "external_id": f"{SOURCE_NAME}:{job_id}",
        "title": title,
        # The agency, where the board names one. It usually does — this is the
        # only one of the four UK sources that publishes it on the listing.
        "company": agency or "Undisclosed agency (JobServe)",
        "url": BASE_URL + href if href.startswith("/") else href,
        # Often literally "Remote, UK", which the location gate reads properly.
        "location_raw": details.get("location") or "United Kingdom",
        "remote": None,
        # The board states no workplace badge; the location text is where it
        # says "Remote", and inferring from it here would duplicate a rule that
        # already lives in the scoring.
        "workplace_type": None,
        "tags": tags,
        "description_text": skills,
        "posted_at": None,
        "salary_raw": details.get("rate") or None,
    }


def parse_listing(body: str) -> tuple:
    """(records, note). Zero and an explicit note when the markup changed."""
    items = _ITEM_RE.findall(body)
    if not items:
        return [], None
    records = [rec for rec in
               (_item_to_common_schema(i, h) for i, h in items) if rec]
    if not records:
        return [], f"markup changed: {len(items)} items on the page, none parsed"
    return records, None


def _search(session, query: str, timeout: int) -> str:
    """The three-step form flow. Returns the listing HTML, or "" if the search
    produced no handle."""
    page = session.get(SEARCH_URL, timeout=timeout)
    page.raise_for_status()
    data = dict(_HIDDEN_RE.findall(page.text))
    data[KEYWORD_FIELD] = query
    data[SEARCH_BUTTON] = "Search"

    resp = session.post(SEARCH_URL, data=data, timeout=timeout)
    resp.raise_for_status()
    found = _SHID_RE.search(resp.url)
    if not found:
        return ""

    listing = session.get(LISTING_URL.format(shid=found.group(1)), timeout=timeout)
    listing.raise_for_status()
    return listing.text


def fetch(queries: Optional[List[str]] = None,
          timeout: int = common.DEFAULT_TIMEOUT):
    import requests

    queries = queries or DEFAULT_QUERIES
    session = requests.Session()
    session.headers.update({"User-Agent": common.USER_AGENT})

    records: List[dict] = []
    seen = set()
    errors: List[str] = []

    for query in queries:
        try:
            body = _search(session, query, timeout)
        except Exception as exc:  # noqa: BLE001 — one keyword must not stop the rest
            errors.append(f"{query}: {type(exc).__name__}")
            continue
        if not body:
            errors.append(f"{query}: the search returned no handle")
            continue
        page_records, note = parse_listing(body)
        if note:
            errors.append(f"{query}: {note}")
            continue
        for record in page_records:
            if record["external_id"] in seen:
                continue
            seen.add(record["external_id"])
            records.append(record)
        time.sleep(PAUSE_SECONDS)

    note = "; ".join(errors[:3]) if errors else None
    return records, note


def main() -> None:
    import argparse

    import identity as identity_mod

    parser = argparse.ArgumentParser(
        description="Collect UK contracts from JobServe")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--query", action="append")
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)

    records, note = fetch(args.query)
    print(f"{SOURCE_NAME}: {len(records)} records ({note or 'no remarks'})")


if __name__ == "__main__":
    main()
