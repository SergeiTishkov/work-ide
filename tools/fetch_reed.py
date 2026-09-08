"""
Fetcher for Reed — the largest of the UK boards.

Measured 2026-09-08: HTTP 200 to an ordinary GET, 25 cards per page,
`?pageno=N` pagination.

WHY ITS FILTERS ARE TRUSTED WHERE LINKEDIN'S ARE NOT
----------------------------------------------------
This project learned the hard way not to believe a board's own filter:
LinkedIn's guest search ignores `f_WT` entirely, and every vacancy in the base
was stamped remote on the strength of it (see fetch_linkedin). So Reed's were
tested the same way before being used, on the same day:

    /jobs/net-developer-jobs            25 results
    /jobs/remote-net-developer-jobs     25 results, only 15 shared with above
    /jobs/contract-net-developer-jobs   25 results, ZERO shared with above

They genuinely filter. The remote slug therefore sets `workplace_type`, and
the contract slug is fetched as well — a whole separate body of work that the
plain search never shows.

The `workplace_type` written here says "Reed classified this as remote", which
is weaker than an employer writing it in the posting, and a tag records where
it came from so the difference stays visible.

PARSED BY data-qa, NEVER BY CLASS NAME
--------------------------------------
Reed's CSS classes are build hashes — `index-module_jobCard__DaYuk` — and
change whenever they ship. The `data-qa` attributes are their own test hooks
and are stable. Parsing the hashes would produce a fetcher that breaks on
somebody else's deploy, silently.

WHAT THE CARD DOES NOT CARRY
----------------------------
No description: the card holds a "See more" button and the text arrives
separately. So the gates that read prose see only the title, the location and
the salary here. tools/enrich_descriptions.py fills that in afterwards for
whatever reaches the shortlist.
"""
from __future__ import annotations

import html
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOURCE_NAME = "reed"
BASE_URL = "https://www.reed.co.uk"

# Keyword slugs, as Reed spells them in its own URLs. The hash in "c#" is not
# usable in a path, and Reed's slug for it is "c-jobs" which collides with
# everything; "net-developer" and "software-developer" reach the same work.
DEFAULT_KEYWORDS = ["net-developer", "c-net-developer", "software-developer",
                    "sql-server-developer"]

# Each keyword is fetched three ways. The three sets barely overlap — measured
# 2026-09-08 — so this is not three times the requests for the same vacancies.
VARIANTS = (
    ("", None),                 # everything the keyword matches
    ("remote-", "remote"),      # Reed's remote classification
    ("contract-", None),        # contracts: zero overlap with the plain search
)

PAGES_PER_QUERY = 3
PAUSE_SECONDS = 1.5

_CARD_RE = re.compile(r'<article[^>]*data-qa="job-card"[^>]*>[\s\S]*?</article>')
_ID_RE = re.compile(r'data-id="(\d{5,})"')
# The anchor that carries the title, matched WITHOUT assuming an attribute
# order: Reed writes title="..." before data-qa="job-card-title", and a regex
# that expects the other way round matches nothing while looking correct.
_TITLE_ANCHOR_RE = re.compile(r'<a [^>]*data-qa="job-card-title"[^>]*>')
_ATTR_TITLE_RE = re.compile(r'title="([^"]+)"')
_HREF_RE = re.compile(r'href="(/jobs/[^"?]+/\d+)')
# The windows are generous on purpose: every metadata item begins with an
# inline SVG icon of its own, and that icon is longer than 200 characters.
# A window sized for the text alone matches nothing and says nothing —
# 117 records arrived with not one salary before this was measured.
_POSTED_BY_RE = re.compile(r'data-qa="job-posted-by"[^>]*>([\s\S]{0,800}?)</div>')
_SALARY_RE = re.compile(r'data-qa="job-metadata-salary"[^>]*>([\s\S]{0,800}?)</li>')
_LOCATION_RE = re.compile(r'data-qa="job-metadata-location"[^>]*>([\s\S]{0,800}?)</li>')
_TAG_RE = re.compile(r"<[^>]+>")

_MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}


def _clean(fragment: Optional[str]) -> str:
    if not fragment:
        return ""
    return " ".join(html.unescape(_TAG_RE.sub(" ", fragment)).split())


def _posted_and_company(fragment: str) -> tuple:
    """"30 July by Anglian Home Improvements" -> ("2026-07-30", "Anglian ...").

    Reed omits the year. A date that has not happened yet this year belongs to
    the last one — a posting dated 30 December read in January is three days
    old, not eleven months in the future.
    """
    text = _clean(fragment)
    if not text:
        return None, ""
    company = ""
    if " by " in text:
        date_part, company = text.split(" by ", 1)
    else:
        date_part = text
    company = company.strip()

    posted = None
    match = re.match(r"(\d{1,2})\s+([A-Za-z]+)", date_part.strip())
    if match:
        day, month_name = int(match.group(1)), match.group(2).lower()
        month = _MONTHS.get(month_name)
        if month:
            today = datetime.now(timezone.utc).date()
            year = today.year
            try:
                candidate = datetime(year, month, day).date()
                if candidate > today:
                    candidate = datetime(year - 1, month, day).date()
                posted = candidate.isoformat()
            except ValueError:
                posted = None
    return posted, company


def _card_to_common_schema(card_html: str, workplace: Optional[str],
                           variant: str) -> Optional[dict]:
    id_match = _ID_RE.search(card_html)
    anchor_match = _TITLE_ANCHOR_RE.search(card_html)
    if not (id_match and anchor_match):
        return None
    anchor = anchor_match.group(0)
    title_match = _ATTR_TITLE_RE.search(anchor)
    href_match = _HREF_RE.search(anchor)
    if not (title_match and href_match):
        return None

    job_id = id_match.group(1)
    title = _clean(title_match.group(1))
    if not title:
        return None

    posted, company = _posted_and_company(
        _POSTED_BY_RE.search(card_html).group(1) if _POSTED_BY_RE.search(card_html) else "")
    salary = _clean(_SALARY_RE.search(card_html).group(1)) if _SALARY_RE.search(card_html) else ""
    location = _clean(_LOCATION_RE.search(card_html).group(1)) if _LOCATION_RE.search(card_html) else ""

    tags = ["market:United Kingdom"]
    if variant:
        # Where the record came from, so that a workplace_type set by Reed's
        # classification can be told apart from one the employer wrote.
        tags.append(f"reed-filter:{variant.rstrip('-')}")

    return {
        "source": SOURCE_NAME,
        "external_id": f"{SOURCE_NAME}:{job_id}",
        "title": title,
        # A board this size names the recruiter or the employer on the card.
        "company": company or "Undisclosed (Reed)",
        "url": BASE_URL + href_match.group(1),
        "location_raw": location or "United Kingdom",
        "remote": None,
        "workplace_type": workplace,
        "tags": tags,
        # The card carries no description. enrich_descriptions fills it in for
        # whatever reaches the shortlist.
        "description_text": "",
        "posted_at": posted,
        "salary_raw": salary or None,
    }


def parse_page(body: str, workplace: Optional[str] = None,
               variant: str = "") -> tuple:
    """(records, note). Zero and an explicit note when the markup changed."""
    cards = _CARD_RE.findall(body)
    if not cards:
        return [], None
    records = [rec for rec in
               (_card_to_common_schema(c, workplace, variant) for c in cards) if rec]
    if not records:
        return [], f"markup changed: {len(cards)} cards on the page, none parsed"
    return records, None


def _fetch_page(keyword: str, variant: str, page: int, timeout: int) -> str:
    """The page's HTML, or "" when the board says there is no such page.

    Reed answers 404 past the last page of a search. That is not an error and
    must not be reported as one: an exhausted pagination looks identical to a
    broken parser in the source-health panel, and a panel full of harmless
    noise is a panel nobody reads.
    """
    import requests

    url = f"{BASE_URL}/jobs/{variant}{keyword}-jobs"
    if page > 1:
        url += f"?pageno={page}"
    resp = requests.get(url, headers={"User-Agent": common.USER_AGENT}, timeout=timeout)
    if resp.status_code in (404, 410):
        return ""
    resp.raise_for_status()
    return resp.text


def fetch(keywords: Optional[List[str]] = None,
          max_pages: int = PAGES_PER_QUERY,
          timeout: int = common.DEFAULT_TIMEOUT):
    keywords = keywords or DEFAULT_KEYWORDS
    records: List[dict] = []
    seen = set()
    errors: List[str] = []

    for keyword in keywords:
        for variant, workplace in VARIANTS:
            for page in range(1, max_pages + 1):
                try:
                    body = _fetch_page(keyword, variant, page, timeout)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{variant}{keyword} p{page}: {type(exc).__name__}")
                    break
                page_records, note = parse_page(body, workplace, variant)
                if note:
                    errors.append(f"{variant}{keyword} p{page}: {note}")
                    break
                if not page_records:
                    break
                fresh = 0
                for record in page_records:
                    if record["external_id"] in seen:
                        continue
                    seen.add(record["external_id"])
                    records.append(record)
                    fresh += 1
                time.sleep(PAUSE_SECONDS)
                if not fresh:
                    break

    note = "; ".join(errors[:3]) if errors else None
    return records, note


def main() -> None:
    import argparse

    import identity as identity_mod

    parser = argparse.ArgumentParser(description="Collect UK vacancies from Reed")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--keyword", action="append")
    parser.add_argument("--pages", type=int, default=PAGES_PER_QUERY)
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)

    records, note = fetch(args.keyword, max_pages=args.pages)
    print(f"{SOURCE_NAME}: {len(records)} records ({note or 'no remarks'})")


if __name__ == "__main__":
    main()
