"""
Fetcher for ContractorUK — a UK board of CONTRACTS rather than staff jobs.

WHY THIS ONE FIRST
------------------
Every other board in this project lists employment. ContractorUK lists
contracts: a day rate, a duration, and an IR35 status. For somebody invoicing
from outside the UK that is the shape of work that can actually be taken, and
the rate is stated on the card rather than hidden behind "competitive".

Measured 2026-09-08: HTTP 200 to an ordinary GET with the project's honest
User-Agent, 20 cards per page, `&page=N` pagination.

A TRAP WORTH RECORDING
----------------------
There are two listing paths and they behave differently:

    /contract_jobs?q=.net       silently IGNORES the query and returns
                                whatever is newest — building trades, mostly
    /all_contract_jobs?q=.net   actually filters

Half an hour was lost to that on the day this was written.

WHAT THE CARD GIVES, AND WHAT IT DOES NOT
-----------------------------------------
Rich for a listing page: title, location, day rate, a summary paragraph, and
badges — "Outside IR35", "Remote"/"Hybrid"/"Onsite", a sector.

The badge is the important one. It is the board's own structured statement of
where the work happens, so it goes straight into `workplace_type`, the field
that already decides the arrangement gate (see score._check_location_field_
arrangement). Not a guess from prose: the employer ticked a box.

The board ALSO offers `&remote=remote` and `&ir35=outside` filters, and this
fetcher deliberately does not use them. Collecting broadly and letting the
gates decide is what makes the result measurable — filtering at the source
would hide from our own scoring exactly the vacancies whose rejection a person
might want to argue with.

**No company name.** The board never publishes the recruiter — `cuk-jhero__firm`
is empty on the detail page too. `company` is a required field, so it gets an
honest placeholder rather than a guess. There is nothing to look up a
reputation for, and the report will say so.

**A summary, not a description.** Roughly 200 characters, cut with an ellipsis;
the full text lives behind the apply link. So the gates that read text work on
a snippet here, as they do for a LinkedIn card.
"""
from __future__ import annotations

import html
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote_plus

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOURCE_NAME = "contractoruk"
BASE_URL = "https://www.contractoruk.com"
SEARCH_URL = BASE_URL + "/all_contract_jobs"

# Measured 2026-09-08, by counting how many titles on the first page name
# this stack. The board searches the whole posting as a loose substring, which
# is why ".net" also returns "Biodiversity Net Gain Officer" — harmless, our
# own gates deal with it, and a narrower query loses real work.
#
# Deliberately absent: "c#" returns ZERO — the hash is not searchable there
# however it is encoded — and "dotnet"/"csharp" likewise. C# work is reached
# through "software developer" and "sql server" instead.
DEFAULT_QUERIES = [".net", ".net developer", "sql server", "software developer"]
PAGES_PER_QUERY = 3          # 20 cards a page; three is plenty per keyword
# The pager is ZERO-BASED: the first page carries no `page` at all and the
# link marked "next page" is `page=1`. Starting the loop at 1 silently skips
# the best-matching page, which is the one a relevance sort puts first.
FIRST_PAGE = 0
PAUSE_SECONDS = 1.5          # politeness, as everywhere else in this project

# The company is genuinely absent from the board, not merely unparsed. Kept as
# a constant so the report and the tests agree about the wording.
UNDISCLOSED_COMPANY = "Undisclosed agency (ContractorUK)"

_CARD_RE = re.compile(r'<article class="cuk-job-card">([\s\S]*?)</article>')
_TITLE_RE = re.compile(r'cuk-job-card__title">\s*<a href="(/job/(\d+)-[^"]*)">([^<]+)</a>')
_LOCATION_RE = re.compile(r'cuk-job-card__loc">([\s\S]*?)</span>')
_SUMMARY_RE = re.compile(r'cuk-job-card__summary">([\s\S]*?)</p>')
_RATE_RE = re.compile(r'cuk-job-card__rate">([^<]*)</span>')
_POSTED_RE = re.compile(r'cuk-job-card__posted">([^<]*)</span>')
_BADGE_RE = re.compile(r'cuk-badge cuk-badge--(\w+)"[^>]*>([^<]*)<')
_TAG_RE = re.compile(r"<[^>]+>")

# The badge text, as the board writes it, mapped onto the vocabulary the
# scoring already understands.
_WORKPLACE_FROM_BADGE = {
    "remote": "remote",
    "hybrid": "hybrid",
    "onsite": "on-site",
    "on-site": "on-site",
}


def _clean(fragment: Optional[str]) -> str:
    """Tags out, entities decoded, whitespace collapsed. The board uses a
    non-breaking space inside its rate ranges."""
    if not fragment:
        return ""
    text = html.unescape(_TAG_RE.sub(" ", fragment))
    return " ".join(text.replace("\xa0", " ").split())


def _posted_at(phrase: str) -> Optional[str]:
    """"24 days ago" / "Today" / "Yesterday" as an ISO date.

    The detail page carries an exact date, but reaching it costs one request
    per vacancy. A relative phrase resolved against today is accurate to the
    day, which is all the freshness signals need.
    """
    text = (phrase or "").strip().lower()
    if not text:
        return None
    today = datetime.now(timezone.utc).date()
    if text in ("today", "just now"):
        return today.isoformat()
    if text == "yesterday":
        return (today - timedelta(days=1)).isoformat()
    match = re.match(r"(\d+)\s+(day|week|month|hour|minute)s?\s+ago", text)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    days = {"minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30}[unit]
    return (today - timedelta(days=amount * days)).isoformat()


def _card_to_common_schema(card_html: str) -> Optional[dict]:
    title_match = _TITLE_RE.search(card_html)
    if not title_match:
        return None
    path, job_id, title = title_match.groups()
    title = _clean(title)
    if not title or not job_id:
        return None

    badges = [(kind.lower(), _clean(text)) for kind, text in _BADGE_RE.findall(card_html)]
    workplace = None
    for kind, text in badges:
        workplace = _WORKPLACE_FROM_BADGE.get(kind) or _WORKPLACE_FROM_BADGE.get(text.lower())
        if workplace:
            break

    location = _clean(_LOCATION_RE.search(card_html).group(1)) if _LOCATION_RE.search(card_html) else ""
    summary = _clean(_SUMMARY_RE.search(card_html).group(1)) if _SUMMARY_RE.search(card_html) else ""
    rate = _clean(_RATE_RE.search(card_html).group(1)) if _RATE_RE.search(card_html) else ""
    posted = _clean(_POSTED_RE.search(card_html).group(1)) if _POSTED_RE.search(card_html) else ""

    tags = ["market:United Kingdom"] + [text for _, text in badges if text]

    return {
        "source": SOURCE_NAME,
        "external_id": f"{SOURCE_NAME}:{job_id}",
        "title": title,
        "company": UNDISCLOSED_COMPANY,
        "url": BASE_URL + path,
        # "Nationwide" is the board's way of saying "anywhere in the UK". Left
        # as written: turning it into a country name here would hide from the
        # location gate that the employer said something broader than a city.
        "location_raw": location or "United Kingdom",
        # Not True. The badge below is the board's own statement; inventing a
        # remote flag from the mere fact of collection is the mistake that cost
        # this project every LinkedIn vacancy in the base (see fetch_linkedin).
        "remote": None,
        "workplace_type": workplace,
        "tags": tags,
        "description_text": summary,
        "posted_at": _posted_at(posted),
        "salary_raw": rate or None,
    }


def _fetch_page(query: str, page: int, timeout: int) -> str:
    import requests

    url = f"{SEARCH_URL}?q={quote_plus(query)}"
    if page > FIRST_PAGE:
        url += f"&page={page}"
    resp = requests.get(url, headers={"User-Agent": common.USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def parse_page(body: str) -> tuple:
    """(records, note). Separated from the network so a snapshot can test it.

    If the page holds cards but none of them parses, that is a MARKUP CHANGE
    and it returns zero records with an explicit note — never a stream of
    half-filled records that quietly poison the database. The same obligation
    fetch_linkedin carries, and for the same reason.
    """
    cards = _CARD_RE.findall(body)
    if not cards:
        return [], None
    records = [rec for rec in (_card_to_common_schema(c) for c in cards) if rec]
    if not records:
        return [], (f"markup changed: {len(cards)} cards on the page, none parsed")
    return records, None


def fetch(queries: Optional[List[str]] = None,
          max_pages: int = PAGES_PER_QUERY,
          timeout: int = common.DEFAULT_TIMEOUT):
    queries = queries or DEFAULT_QUERIES
    records: List[dict] = []
    seen = set()
    errors: List[str] = []

    for query in queries:
        for page in range(FIRST_PAGE, FIRST_PAGE + max_pages):
            try:
                body = _fetch_page(query, page, timeout)
            except Exception as exc:  # noqa: BLE001 — one page must not stop the rest
                errors.append(f"{query} p{page}: {type(exc).__name__}")
                break
            page_records, note = parse_page(body)
            if note:
                errors.append(f"{query} p{page}: {note}")
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
                break        # the board repeated a page: stop paging this query

    note = "; ".join(errors[:3]) if errors else None
    return records, note


def main() -> None:
    import argparse

    import identity as identity_mod

    parser = argparse.ArgumentParser(
        description="Collect UK contracts from ContractorUK")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--query", action="append")
    parser.add_argument("--pages", type=int, default=PAGES_PER_QUERY)
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)

    records, note = fetch(args.query, max_pages=args.pages)
    print(f"{SOURCE_NAME}: {len(records)} records ({note or 'no remarks'})")


if __name__ == "__main__":
    main()
