"""
Fetches LinkedIn through its guest job-search endpoint.

WHY THIS IS WITHIN THE PROJECT'S BOUNDS
---------------------------------------
Measured 2026-08-04: `linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search`
answers HTTP 200 to an ordinary GET carrying the project's honest User-Agent —
no authorisation, no CAPTCHA, no anti-bot block. It is the same endpoint
LinkedIn's own guest interface uses when a logged-out person opens the page.

The project's boundary (CLAUDE.md §5): "parsers of anything served to an
ordinary GET — yes; circumventing active protection — no". This is the former.
For contrast, the same request on the same day: Indeed 403, Glassdoor 403.
Those are genuinely closed, and the project does not go there.

WHY THIS IS THE PROJECT'S MAIN SOURCE
-------------------------------------
One fetcher covers every market of interest at once: verified for Israel, the
UAE, Saudi Arabia, Singapore, Switzerland, Germany and the Netherlands — 200
and real vacancies everywhere. The national boards of those same markets
(Bayt, GulfTalent, Drushim, NodeFlair) answer 403/404, so there is no


------------
THE PRICE OF THE DECISION

This is the HTML of an undocumented page. The markup can change any day, and
then the parser must return ZERO records and an error rather than a stream of
rubbish that quietly poisons the database. Hence, here:
  * every record passes a required-field check;
  * if the response contains cards but not one could be parsed, that counts as
"""
from __future__ import annotations

import html
import json
import re
import sys
import time
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote_plus

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOURCE_NAME = "linkedin"
API_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

# f_WT=2 is LinkedIn's "Remote" filter.
REMOTE_WORKPLACE_TYPE = "2"

PAGE_SIZE = 25          # what LinkedIn returns per request
# How many cards per run to enrich with a full description. A card carries no
# description — only title, company and location. Without one, the stack gate
# rejects three quarters of what was found (measured: 447 of 621), because it
# sees no familiar language. The vacancy page opens to the same ordinary GET
# and returns the full text, but that is one request per vacancy — hence a cap.
ENRICH_LIMIT = 120
MAX_PAGES = 4           # 100 vacancies per (query × country) pair is a sane cap
PAUSE_SECONDS = 1.5     # politeness: do not hammer somebody else's server

_CARD_RE = re.compile(r"<li>(.*?)</li>", re.S)
_TITLE_RE = re.compile(r'base-search-card__title[^>]*>(.*?)</h3>', re.S)
_COMPANY_RE = re.compile(r'base-search-card__subtitle[^>]*>(.*?)</h4>', re.S)
_LOCATION_RE = re.compile(r'job-search-card__location[^>]*>(.*?)</span>', re.S)
_URL_RE = re.compile(r'href="(https://[a-z]{0,3}\.?linkedin\.com/jobs/view/[^"?]+)')
_DATE_RE = re.compile(r'datetime="([\d-]+)"')
_TAG_RE = re.compile(r"<[^>]+>")
_DESCRIPTION_RE = re.compile(r'description__text[^>]*>(.*?)</div>\s*</section>', re.S)
_DESCRIPTION_FALLBACK_RE = re.compile(r'description__text[^>]*>(.*?)</div>', re.S)


def _clean(fragment: Optional[str]) -> str:
    if not fragment:
        return ""
    return html.unescape(_TAG_RE.sub(" ", fragment)).replace(" ", " ").strip()


def _first(pattern, text: str) -> str:
    m = pattern.search(text)
    return _clean(m.group(1)) if m else ""


def _card_to_common_schema(card_html: str, location_query: str) -> Optional[dict]:
    title = _first(_TITLE_RE, card_html)
    company = _first(_COMPANY_RE, card_html)
    url_match = _URL_RE.search(card_html)
    url = url_match.group(1) if url_match else ""

    # Required fields. Their absence means either somebody else's card (an ad,
    # a "similar companies" block) or changed markup — in both cases the record
    # must not be taken.
    if not title or not company or not url:
        return None

    location = _first(_LOCATION_RE, card_html)
    return {
        "source": SOURCE_NAME,
        "external_id": url,
        "title": title,
        "company": company,
        "url": url,
        # The queried country is stored separately: it is more dependable than
        # free text on the card, and the report needs it to show which market
        "location_raw": location or location_query,
        # NOT True. This used to be hardcoded, on the reasoning that the query
        # carries LinkedIn's f_WT=2 ("Remote") filter.
        #
        # Measured 2026-08-11, after the owner opened the top vacancy in the
        # shortlist and found it badged "Hybrid": THE GUEST SEARCH IGNORES
        # f_WT ENTIRELY. The same job id comes back under f_WT=1 (on-site),
        # f_WT=2 (remote) and f_WT=3 (hybrid), and the result sets for
        # "remote" and "on-site" were identical. So the flag was not a weak
        # signal, it was a fabrication — and it was clearing the "not
        # confirmed as remote" gate for every LinkedIn vacancy in the base.
        #
        # None means "nobody said". The vacancy page can still say TELECOMMUTE
        # (see fetch_page_facts), and the description can still say "remote".
        "remote": None,
        # Filled in from the vacancy page when there is one to fill in;
        # "remote" only where the employer declares it. The on-site/hybrid
        # badge a logged-in person sees is NOT served to an anonymous request
        # — checked three ways on 2026-08-11: absent from the search results,
        # from the guest jobPosting fragment, and from the page HTML. Reading
        # it would take a logged-in session, which is over the line in §5.
        "workplace_type": None,
        "tags": [f"market:{location_query}"],
        "description_text": "",  # a card has none; only the vacancy page does
        "posted_at": _first(_DATE_RE, card_html) or None,
        "salary_raw": None,
    }


def _fetch_page(keyword: str, location: str, start: int, timeout: int):
    import requests

    url = (
        f"{API_URL}?keywords={quote_plus(keyword)}&location={quote_plus(location)}"
        f"&f_WT={REMOTE_WORKPLACE_TYPE}&start={start}"
    )
    resp = requests.get(url, headers={"User-Agent": common.USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    return resp.text


_DEV_TITLE_RE = re.compile(
    r"develop|engineer|programm|architect|\.net|dotnet|c#|javascript|typescript|"
    r"backend|back-end|frontend|front-end|full[ -]?stack|software",
    re.IGNORECASE,
)


def _looks_like_dev_role(title: str) -> bool:
    return bool(_DEV_TITLE_RE.search(title or ""))


_LD_JSON_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)

# LinkedIn renders this for a posting that has stopped taking applications.
# Verified 2026-08-11 on three vacancies the owner labelled by hand: present
# for the closed one (Jobstronaut), absent for both open ones. Two independent
# spellings, because one of them is a CSS class and classes get renamed.
_CLOSED_RE = re.compile(r"no longer accepting applications|closed-job", re.I)


def _salary_from_ld(node: dict) -> Optional[str]:
    """schema.org baseSalary as a line a person can read.

    Free: it arrives in the same response as the description. Worth taking —
    a salary stated in the vacancy itself is the highest of the three levels
    of trust (CLAUDE.md §5), and every LinkedIn vacancy was storing None.
    """
    base = node.get("baseSalary")
    if not isinstance(base, dict):
        return None
    value = base.get("value")
    if not isinstance(value, dict):
        return None
    low = value.get("minValue") or value.get("value")
    if low is None:
        return None
    high = value.get("maxValue")
    amount = f"{low}-{high}" if high and high != low else f"{low}"
    return " ".join(str(part) for part in
                    (base.get("currency"), amount, value.get("unitText")) if part)


def fetch_page_facts(url: str, timeout: int) -> dict:
    """Everything the vacancy page states, in ONE request.

    The page is served to an anonymous ordinary GET, just like the search page.

    Three of these four facts were being thrown away until 2026-08-11, and all
    three came free with a request the pipeline was already making:

    * `workplace_type` — "remote" only where schema.org says TELECOMMUTE. The
      absence of it means the employer declared nothing, NOT that the job is
      onsite; the on-site/hybrid badge is not served to anonymous requests at
      all. Do not infer from silence here — the scoring has its own class for
      "nobody said".
    * `salary_raw` — see _salary_from_ld.
    * `closed` — a posting that no longer accepts applications. The owner found
      one leading the shortlist at 65.

    Never raises. Everything empty means "it did not work": not a failure of
    the run, the vacancy simply keeps what it already had.
    """
    import requests

    facts = {"description": "", "workplace_type": None,
             "salary_raw": None, "closed": False}
    try:
        resp = requests.get(url, headers={"User-Agent": common.USER_AGENT}, timeout=timeout)
        resp.raise_for_status()
    except Exception:  # noqa: BLE001
        return facts

    body = resp.text
    facts["closed"] = bool(_CLOSED_RE.search(body))

    match = _DESCRIPTION_RE.search(body) or _DESCRIPTION_FALLBACK_RE.search(body)
    if match:
        facts["description"] = " ".join(_clean(match.group(1)).split())

    for block in _LD_JSON_RE.findall(body):
        try:
            node = json.loads(block)
        except Exception:  # noqa: BLE001 — one malformed block must not matter
            continue
        if not isinstance(node, dict) or node.get("@type") != "JobPosting":
            continue
        if node.get("jobLocationType") == "TELECOMMUTE":
            facts["workplace_type"] = "remote"
        facts["salary_raw"] = facts["salary_raw"] or _salary_from_ld(node)
    return facts


def _fetch_description(url: str, timeout: int) -> str:
    """The full vacancy text. Kept as the narrow entry point for callers that
    want nothing else; the work happens in fetch_page_facts."""
    return fetch_page_facts(url, timeout)["description"]


def fetch(keywords: Optional[List[str]] = None,
          locations: Optional[List[str]] = None,
          max_pages: int = MAX_PAGES,
          enrich_limit: int = ENRICH_LIMIT,
          timeout: int = common.DEFAULT_TIMEOUT):
    """Walks (keyword × country) pairs and returns (records, note).

    keywords/locations come from <prefix>_sources.yaml -> params. Locations
    default to the active identity's market tiers, so that the country list
    lives in one place (see tools/markets.py).
    """
    import markets

    profile = common.load_profile()
    keywords = keywords or (profile.get("tech_stack", {}).get("core") or [])[:3]
    locations = locations or markets.target_locations(profile)

    if not keywords or not locations:
        return [], "nothing to query: the keyword or country list is empty"

    records: List[dict] = []
    seen_urls = set()
    cards_seen = 0
    errors: List[str] = []

    for keyword in keywords:
        for location in locations:
            for page in range(max_pages):
                try:
                    page_html = _fetch_page(keyword, location, page * PAGE_SIZE, timeout)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{keyword}/{location}: {type(exc).__name__}")
                    break

                cards = _CARD_RE.findall(page_html)
                if not cards:
                    break
                cards_seen += len(cards)

                added_here = 0
                for card in cards:
                    rec = _card_to_common_schema(card, location)
                    if rec is None or rec["url"] in seen_urls:
                        continue
                    seen_urls.add(rec["url"])
                    records.append(rec)
                    added_here += 1

                time.sleep(PAUSE_SECONDS)
                if len(cards) < PAGE_SIZE:
                    break

    # The key defence against changed markup: cards arrived, but not one parsed.
    # Returning empty silently will not do — it would look like "the market has
    # nothing", when in fact the parser broke.
    if cards_seen and not records:
        return [], (
            f"the page format changed: {cards_seen} cards received, "
            "none could be parsed"
        )

    # Description enrichment. The order matters: those whose title looks like
    # development at all come first — if the budget runs out, it runs out on the
    # less interesting records rather than on whatever came first.
    enriched = 0
    if enrich_limit:
        records.sort(key=lambda r: 0 if _looks_like_dev_role(r["title"]) else 1)
        for rec in records[:enrich_limit]:
            description = _fetch_description(rec["url"], timeout)
            if description:
                rec["description_text"] = description
                enriched += 1
            time.sleep(PAUSE_SECONDS)

    note_parts = [f"cards {cards_seen}, records {len(records)}, with description {enriched}"]
    if errors:
        note_parts.append("errors: " + "; ".join(errors[:3]))
    return records, "; ".join(note_parts)


def main() -> None:
    import argparse
    import identity as identity_mod

    parser = argparse.ArgumentParser(description="Collect vacancies from LinkedIn (guest search)")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--keyword", action="append", help="Keyword (repeatable)")
    parser.add_argument("--location", action="append", help="Country (repeatable)")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES)
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)

    records, note = fetch(args.keyword, args.location, args.max_pages)
    print(f"{SOURCE_NAME}: {len(records)} records ({note})")
    for r in records[:10]:
        # Company names sometimes carry characters the Windows console encoding
        # has no room for. Dying on a print because of that is silly: the data
        # is collected, only the output breaks.
        line = f"  - {r['title']} @ {r['company']} [{r['location_raw']}]"
        print(line.encode(sys.stdout.encoding or "utf-8", "replace")
                  .decode(sys.stdout.encoding or "utf-8", "replace"))


if __name__ == "__main__":
    main()
