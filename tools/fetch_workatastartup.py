"""
Fetcher for Y Combinator's Work at a Startup (https://www.workatastartup.com/jobs).

The job board of YC companies. Measured 2026-10-21, no key, no cookie:

  * GET /jobs/search?q=<keyword> with `Accept: application/json` answers
    {"jobs": [...]}: up to 30 postings a query, no paging; role and remote
    parameters were ignored. A posting: id, title, jobType ("Full-time",
    "Contract", "Internship"), location, roleType, salary, companyName,
    companySlug, companyBatch, companyOneLiner. No posting date anywhere in
    the list or on the page;
  * GET /jobs/<id> with `Accept: text/html` is an Inertia page: the JSON in
    its data-page attribute holds props.job.descriptionHtml and
    props.job.sponsorsVisa ("US citizen/visa only" and the like). Without a
    text/html Accept the answer is 406 with an empty body, whatever the
    User-Agent.

The keywords come from the identity's sources file; DEFAULT_KEYWORDS stand
in when it names none. 20 queries that day gave 437 distinct postings, 160 of
them with "Remote" in the location.

The location rule. A location is " / "-separated places; the remote ones
read "Remote", "Remote - United Kingdom", "Remote (US)", "Remote (GB; DE;
GE)" or "Remote (Atlanta, GA, US)" (the country is the last part of each
";"-separated entry). The bracketed list decides when there is one
(remote_countries has the details). Of the 160 remote postings in the
2026-10-21 pool: 42 naming no country, 95 one country (81 of them the US), 23
several. A posting is kept when it is remote and not limited to one country
outside `countries` (the identity's residency, ISO codes or names, in its
sources file); with no `countries`, every remote posting is kept. A list of
several countries is kept whether or not it names the residency: the
location goes into the record as written, and the scoring's geography rules
read it. With countries [GE] the rule kept 65 of the 160.
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

SOURCE_NAME = "workatastartup"
SITE = "https://www.workatastartup.com"
SEARCH_URL = f"{SITE}/jobs/search"
JOB_URL = f"{SITE}/jobs/{{id}}"
PAUSE_SECONDS = 1.0
DEFAULT_KEYWORDS = ["remote", "worldwide", "anywhere", "europe", "emea", "forward deployed",
                    "ai engineer", "applied ai", "llm", "full stack", "backend",
                    "data engineer", ".net", "c#", "azure"]
_REMOTE_RE = re.compile(r"^remote\b\s*(?:\((?P<inside>[^)]*)\))?", re.I)
_DATA_PAGE_RE = re.compile(r'data-page="([^"]*)"')


def _get(url: str, params: Optional[dict] = None, timeout: int = common.DEFAULT_TIMEOUT):
    """JSON from the search, the page's HTML from a posting."""
    import requests

    wants_json = url == SEARCH_URL
    headers = {"User-Agent": common.USER_AGENT,
               "Accept": "application/json" if wants_json else "text/html,application/xhtml+xml"}
    resp = requests.get(url, params=params, timeout=timeout, headers=headers)
    resp.raise_for_status()
    return resp.json() if wants_json else resp.text


def _country(token: str) -> str:
    """One country as a comparable name: "GE", "Georgia" and "georgia" are one."""
    token = str(token or "").strip()
    return (places.country_of_code(token) if len(token) == 2 else None) or places.canonical(token) or token.upper()


def _named_country(text: str) -> Optional[str]:
    """The country `text` is, whole, or None: "US", "United Kingdom"."""
    text = str(text or "").strip()
    return (places.country_of_code(text) if len(text) == 2 else None) or places.canonical(text)


def remote_countries(location: str) -> Optional[set]:
    """None when the location does not say Remote; an empty set when it
    names no country for the remote work; else the countries it names.

    The bracketed list ("Remote (US; CA)") decides when there is one: in
    "Remote / Remote (US)" and "Remote - US / Remote (US)" the plain part
    says less. Words beside a plain "Remote" that are not one country
    ("Remote - UK or Europe / Remote (US)") are the employer's own and count
    as naming none. Without a list, "Remote - United Kingdom" names a
    country and a plain "Remote" names none."""
    listed, named, plain, worded = set(), set(), False, False
    for part in str(location or "").split(" / "):
        part = part.strip()
        m = _REMOTE_RE.match(part)
        if not m:
            continue
        inside = (m.group("inside") or "").strip()
        if inside:
            for entry in inside.split(";"):
                last = entry.split(",")[-1].strip()
                if last:
                    listed.add(_country(last))
            continue
        words = part[m.end():].strip(" -:,")
        country = _named_country(words)
        if country:
            named.add(country)
        else:
            plain = True
            worded = worded or bool(words)
    if listed:
        return set() if worded else listed
    if plain:
        return set()
    return named or None


def wanted(location: str, countries: Optional[List[str]] = None) -> bool:
    """Remote, and not limited to one country outside `countries`."""
    scope = remote_countries(location)
    if scope is None:
        return False
    if not scope or not countries or len(scope) > 1:
        return True
    return bool(scope & {_country(c) for c in countries})


def page_job(page_html: str) -> dict:
    """props.job from a posting page's Inertia data-page attribute."""
    m = _DATA_PAGE_RE.search(page_html or "")
    if not m:
        raise ValueError("no data-page attribute")
    job = json.loads(html.unescape(m.group(1))).get("props", {}).get("job")
    if not isinstance(job, dict):
        raise ValueError("no props.job in data-page")
    return job


def to_record(item: dict, job: Optional[dict] = None) -> Optional[dict]:
    """One search hit (with its page's job, when fetched) in the common
    schema; None for a malformed hit."""
    if not isinstance(item, dict):
        return None
    job_id = str(item.get("id") or "").strip()
    title = str(item.get("title") or "").strip()
    company = str(item.get("companyName") or "").strip()
    if not job_id or not title or not company:
        return None
    if job:
        text = common.strip_html(str(job.get("descriptionHtml") or "")).strip()
        visa = str(job.get("sponsorsVisa") or "").strip()
        if visa:
            text = (text + "\n\n" if text else "") + f"Visa: {visa}"
    else:
        text = str(item.get("companyOneLiner") or "").strip()
    location = str(item.get("location") or "").strip()
    return {
        "source": SOURCE_NAME,
        "external_id": job_id,
        "title": title,
        "company": company,
        "url": JOB_URL.format(id=job_id),
        "location_raw": location,
        "remote": remote_countries(location) is not None,
        "workplace_type": "remote" if remote_countries(location) is not None else None,
        "employment_types": item.get("jobType"),
        "tags": [str(item["roleType"]).strip()] if item.get("roleType") else [],
        "description_text": text,
        "posted_at": None,
        "salary_raw": str(item.get("salary") or "").strip() or None,
    }


def fetch(keywords: Optional[List[str]] = None, countries: Optional[List[str]] = None,
          details: bool = True, timeout: int = common.DEFAULT_TIMEOUT, get: Callable = None,
          pause: float = PAUSE_SECONDS, counts: Optional[dict] = None):
    """Every remote posting the keywords find that is not limited to one
    country outside `countries`, each with its page's text when `details`.
    `counts`, when given, receives how many were found and kept."""
    get = get or (lambda url, params=None: _get(url, params, timeout))
    keywords = keywords or DEFAULT_KEYWORDS
    hits, errors = {}, []
    for i, keyword in enumerate(keywords):
        if i:
            time.sleep(pause)
        try:
            payload = get(SEARCH_URL, {"q": keyword})
            jobs = payload.get("jobs") if isinstance(payload, dict) else None
            if not isinstance(jobs, list):
                raise ValueError("the answer has no `jobs` list")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{keyword}: {type(exc).__name__}")
            continue
        for item in jobs:
            if isinstance(item, dict) and item.get("id") is not None:
                hits.setdefault(str(item["id"]), item)
    if len(errors) == len(keywords):
        return [], "every search failed: " + ", ".join(errors)

    kept = [item for item in hits.values() if wanted(str(item.get("location") or ""), countries)]
    if counts is not None:
        counts.update(found=len(hits), kept=len(kept))
    records, skipped, notes = [], 0, []
    for item in kept:
        job = None
        if details:
            try:
                time.sleep(pause)
                job = page_job(get(JOB_URL.format(id=item["id"])))
            except Exception as exc:  # noqa: BLE001
                notes.append(f"{item['id']}: {type(exc).__name__}")   # the company's one-liner stands in
        record = to_record(item, job)
        if record is None:
            skipped += 1
            continue
        records.append(record)
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

    parser = argparse.ArgumentParser(description="Collect remote postings from Work at a Startup")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--keywords", nargs="*", default=None,
                        help="default: the identity's sources file, else DEFAULT_KEYWORDS")
    parser.add_argument("--countries", nargs="*", default=None,
                        help='ISO codes or names, e.g. "GE"; default: the identity\'s sources file')
    parser.add_argument("--no-details", action="store_true", help="the search hits only")
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)
    params = _configured_params()
    countries = args.countries if args.countries is not None else params.get("countries")
    counts: dict = {}
    records, note = fetch(args.keywords or params.get("keywords"), countries,
                          details=not args.no_details, counts=counts)
    print(f"{SOURCE_NAME}: {len(records)} records of {counts.get('found', 0)} found, "
          f"countries {countries} ({note or 'no remarks'})")
    for r in records:
        print(f"  {r['title']} @ {r['company']} | {r['location_raw']} | {r['salary_raw']}")


if __name__ == "__main__":
    main()
