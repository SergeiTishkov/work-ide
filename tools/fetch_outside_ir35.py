"""
Fetcher for Outside IR35 Jobs — small, narrow, and narrow on purpose.

Every posting on this board is a UK contract declared outside IR35. That is the
shape of work a contractor invoicing from another country can actually take:
inside-IR35 work is taxed as employment and generally run through a UK umbrella
company, which is a different arrangement entirely.

Measured 2026-09-08: HTTP 200 to an ordinary GET, 50 contracts on one page —
the whole board fits in a single request, so there is no pagination to walk.

A NOTE ON THE DOMAIN
--------------------
Only `outsideir35jobs.com` resolves. The `.co.uk` does not exist in DNS at all,
and a fetcher pointed there fails with a connection error that looks like the
site being down.

PARSED BY STRUCTURE, NOT BY CLASS
---------------------------------
The site is built with utility CSS — `class="group block rounded-lg border..."`
— where the class list describes appearance and changes whenever the design
does. So the anchor is found by its href shape (`/job/<cuid>`), and the fields
by the tags around it. The one thing a redesign cannot casually change is the
URL of a job.

WHAT A CARD CARRIES
-------------------
Title, company, location, a day rate, how long ago it was posted, the IR35
determination, and the working mode as its own badge — which goes into
`workplace_type`, the field the arrangement gate already reads.

No description: the card shows none, so the gates that read prose see the title
and the badges here. enrich_descriptions fills that in for what reaches the
shortlist.
"""
from __future__ import annotations

import html
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote_plus

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOURCE_NAME = "outside_ir35"
BASE_URL = "https://www.outsideir35jobs.com"
SEARCH_URL = BASE_URL + "/jobs"

# The board holds a few dozen contracts in total, so an unfiltered fetch takes
# all of them in one request. A keyword search exists (`?q=`) and is not used:
# the whole board is smaller than one page of Reed, and our own gates are a
# better filter than a substring match.
DEFAULT_QUERIES = [""]

_JOB_HREF_RE = re.compile(r'href="(/job/[a-z0-9]{16,})"')
_CARD_SPLIT_RE = re.compile(r'(?=<a class="group block)')
_TITLE_RE = re.compile(r"<h3[^>]*>([^<]+)</h3>")
_SUBTITLE_RE = re.compile(r"<h3[^>]*>[^<]*</h3>\s*<p[^>]*>([\s\S]{0,200}?)</p>")
_RATE_RE = re.compile(r">([£$€][\d,]+(?:\s*[–\-—]\s*[£$€]?[\d,]+)?)<")
_PER_RE = re.compile(r">/(?:<!-- -->)?(\w+)<")
_POSTED_RE = re.compile(r">(\d+)([dhwm]) ago<")
_TAG_RE = re.compile(r"<[^>]+>")

# The working mode, as the board writes it on its badge.
_MODES = {
    "remote": "remote",
    "hybrid": "hybrid",
    "on-site": "on-site",
    "onsite": "on-site",
    "office": "on-site",
}


def _clean(fragment: Optional[str]) -> str:
    if not fragment:
        return ""
    # The site renders React comment markers (<!-- -->) between text nodes.
    text = html.unescape(_TAG_RE.sub(" ", (fragment or "").replace("<!-- -->", "")))
    return " ".join(text.split())


def _posted_at(amount: str, unit: str) -> Optional[str]:
    days = {"h": 0, "d": 1, "w": 7, "m": 30}.get(unit)
    if days is None:
        return None
    today = datetime.now(timezone.utc).date()
    return (today - timedelta(days=int(amount) * days)).isoformat()


def _card_to_common_schema(card_html: str) -> Optional[dict]:
    href_match = _JOB_HREF_RE.search(card_html)
    title_match = _TITLE_RE.search(card_html)
    if not (href_match and title_match):
        return None
    path = href_match.group(1)
    title = _clean(title_match.group(1))
    if not title:
        return None
    job_id = path.rsplit("/", 1)[-1]

    company, location = "", ""
    subtitle = _SUBTITLE_RE.search(card_html)
    if subtitle:
        parts = [p.strip() for p in _clean(subtitle.group(1)).split("·")]
        company = parts[0] if parts else ""
        location = parts[1] if len(parts) > 1 else ""

    rate = ""
    rate_match = _RATE_RE.search(card_html)
    if rate_match:
        per_match = _PER_RE.search(card_html)
        rate = _clean(rate_match.group(1))
        if per_match:
            rate += f"/{per_match.group(1)}"

    posted = None
    posted_match = _POSTED_RE.search(card_html)
    if posted_match:
        posted = _posted_at(*posted_match.groups())

    # The badges are read from the card's plain text: each is a span holding an
    # icon and a word, and matching the spans themselves would mean matching
    # the icon markup too.
    text = _clean(card_html)
    workplace = None
    for word, value in _MODES.items():
        if re.search(r"\b%s\b" % re.escape(word), text, re.IGNORECASE):
            workplace = value
            break

    tags = ["market:United Kingdom"]
    if "outside ir35" in text.lower():
        tags.append("Outside IR35")

    return {
        "source": SOURCE_NAME,
        "external_id": f"{SOURCE_NAME}:{job_id}",
        "title": title,
        "company": company or "Undisclosed (Outside IR35 Jobs)",
        "url": BASE_URL + path,
        "location_raw": location or "United Kingdom",
        "remote": None,
        "workplace_type": workplace,
        "tags": tags,
        "description_text": "",
        "posted_at": posted,
        "salary_raw": rate or None,
    }


def parse_page(body: str) -> tuple:
    """(records, note). Zero and an explicit note when the markup changed."""
    cards = [c for c in _CARD_SPLIT_RE.split(body) if _JOB_HREF_RE.search(c)]
    if not cards:
        return [], None
    records = [rec for rec in (_card_to_common_schema(c) for c in cards) if rec]
    if not records:
        return [], f"markup changed: {len(cards)} cards on the page, none parsed"
    return records, None


def _fetch_page(query: str, timeout: int) -> str:
    import requests

    url = SEARCH_URL + (f"?q={quote_plus(query)}" if query else "")
    resp = requests.get(url, headers={"User-Agent": common.USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def fetch(queries: Optional[List[str]] = None,
          timeout: int = common.DEFAULT_TIMEOUT):
    queries = queries if queries is not None else DEFAULT_QUERIES
    records: List[dict] = []
    seen = set()
    errors: List[str] = []

    for query in queries:
        try:
            body = _fetch_page(query, timeout)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{query or 'all'}: {type(exc).__name__}")
            continue
        page_records, note = parse_page(body)
        if note:
            errors.append(f"{query or 'all'}: {note}")
            continue
        for record in page_records:
            if record["external_id"] in seen:
                continue
            seen.add(record["external_id"])
            records.append(record)

    note = "; ".join(errors[:3]) if errors else None
    return records, note


def main() -> None:
    import argparse

    import identity as identity_mod

    parser = argparse.ArgumentParser(
        description="Collect outside-IR35 UK contracts")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--query", action="append")
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)

    records, note = fetch(args.query)
    print(f"{SOURCE_NAME}: {len(records)} records ({note or 'no remarks'})")


if __name__ == "__main__":
    main()
