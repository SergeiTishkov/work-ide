"""
Fetches LinkedIn through its guest job-search endpoint.

THE ENDPOINT
------------
Measured 2026-08-04: `linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search`
answers HTTP 200 to a plain GET with no authorisation. It is the same endpoint
LinkedIn's own guest interface uses when a logged-out person opens the page.
For contrast, the same request on the same day: Indeed 403, Glassdoor 403.

WHY THIS IS THE PROJECT'S MAIN SOURCE
-------------------------------------
One fetcher covers every market of interest at once: verified for Israel, the
UAE, Saudi Arabia, Singapore, Switzerland, Germany and the Netherlands — 200
and real vacancies everywhere. The national boards of those same markets
(Bayt, GulfTalent, Drushim, NodeFlair) answer 403/404, so there is no
alternative to it for those markets.

THE PRICE OF THE DECISION
-------------------------
This is the HTML of an undocumented page. The markup can change any day, and
then the parser must return ZERO records and an error rather than a stream of
rubbish that quietly poisons the database. Hence, here:
  * every record passes a required-field check;
  * if the response contains cards but not one could be parsed, that counts as
    a format change and comes back as an error, never as an empty market;
  * contract() below states, and checks live, the quieter facts the fetcher
    depends on — the page length, where the next page starts, the date filter,
    what a vacancy page carries. A change there does not break parsing; it
    only makes the harvest thinner, which nobody notices until it is checked.
    See tools/source_contract.py and docs/sources/linkedin.md.
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

# The next page starts where this one ended: `start` advances by the number of
# cards actually received, never by an assumed page length. Until 2026-10-02
# this was a constant 25 — and the guest search serves TEN cards a page, so
# every pair stopped after its first page ("fewer than 25 came, the list must
# be over") and max_pages did nothing at all. Measured: start=0/10/20 give
# three disjoint pages of ten. The contract checks the paging every run.
#
# Only vacancies posted within this many days are asked for (LinkedIn's f_TPR
# filter, which the guest search DOES honour — unlike f_WT, sortBy and f_JT).
# A daily run needs the last week, not the same old postings again: without it
# a third of each page was older than a month. None or 0 asks for any age.
POSTED_WITHIN_DAYS = 7
# The anonymous guest search serves at most this many results per query —
# ten pages — and an empty page at start=100 whatever the total. Measured
# 2026-10-03: "C# developer" in the UK has 736 postings this week by
# LinkedIn's own count, and start=100..290 are all empty; the same in
# Germany (540) and Canada; adding geoId, position or pageNum changes nothing.
# A browser is served up to 1000; the page marks this fetcher
# data-is-bot="true". So a query that reaches the ceiling is SPLIT into
# narrower queries, each with a ceiling of its own — see SPLIT_REGIONS.
RESULTS_CEILING = 100

# What a query that reached the ceiling is split into, both measured
# 2026-10-03 on "C# developer" in the UK (100 at the ceiling):
#   * the same words with "remote" in front: 38 vacancies the plain query did
#     not show, 12 of them placed in the whole country rather than a city —
#     the shape a remote posting has, which is what most searches here want;
#   * the country's big regions: London 47 new, Manchester 41, Scotland 44,
#     West Midlands 25, Bristol 27, Leeds 26 — 322 in all against 100. Mostly
#     local work, so worth it for the larger markets only.
# Each region was checked to resolve inside its country (a page of cards,
# located there). "Washington, United States" resolves to D.C., hence Seattle.
SPLIT_REGIONS = {
    "United States": ["California, United States", "Texas, United States",
                      "New York, United States", "Seattle, Washington, United States",
                      "Florida, United States", "Illinois, United States",
                      "Massachusetts, United States", "Virginia, United States"],
    "United Kingdom": ["London, England, United Kingdom",
                       "Greater Manchester, England, United Kingdom",
                       "Scotland, United Kingdom", "West Midlands, England, United Kingdom",
                       "Bristol, England, United Kingdom", "Leeds, England, United Kingdom"],
    "Germany": ["Berlin, Germany", "Bavaria, Germany", "Hesse, Germany", "Hamburg, Germany",
                "North Rhine-Westphalia, Germany", "Baden-Württemberg, Germany"],
    "Canada": ["Ontario, Canada", "British Columbia, Canada", "Quebec, Canada",
               "Alberta, Canada"],
    "Netherlands": ["North Holland, Netherlands", "South Holland, Netherlands",
                    "Utrecht, Netherlands", "North Brabant, Netherlands"],
    "Australia": ["New South Wales, Australia", "Victoria, Australia",
                  "Queensland, Australia"],
}

# How many cards per run to enrich with a full description. A card carries no
# description — only title, company and location. Without one, the stack gate
# rejects three quarters of what was found (measured: 447 of 621), because it
# sees no familiar language. The vacancy page opens to the same plain GET
# and returns the full text, but that is one request per vacancy — hence a cap.
ENRICH_LIMIT = 120
# Pages per query. A bound, not a target: a query ends on its own at the
# ceiling (ten pages) or sooner. Higher than the ceiling on purpose — should
# LinkedIn ever serve an anonymous request deeper, the walk follows.
MAX_PAGES = 100
PAUSE_SECONDS = 1.5     # between pages; faster runs into 429s
RATE_LIMIT_PAUSE_SECONDS = 30   # after a 429, before the one retry

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


def _card_to_common_schema(card_html: str, location_query: str,
                           market: Optional[str] = None) -> Optional[dict]:
    """`market` is the country the search was for, when the query itself was
    narrower (a region of it); by default the query is the country."""
    market = market or location_query
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
        # from the guest jobPosting fragment, and from the page HTML. It
        # renders only for a logged-in session.
        "workplace_type": None,
        "tags": [f"market:{market}"],
        "description_text": "",  # a card has none; only the vacancy page does
        "posted_at": _first(_DATE_RE, card_html) or None,
        "salary_raw": None,
    }


def search_url(keyword: str, location: str, start: int,
               posted_within_days: Optional[int] = None) -> str:
    url = (
        f"{API_URL}?keywords={quote_plus(keyword)}&location={quote_plus(location)}"
        f"&f_WT={REMOTE_WORKPLACE_TYPE}&start={start}"
    )
    if posted_within_days:
        url += f"&f_TPR=r{int(posted_within_days) * 86400}"
    return url


def _fetch_page(keyword: str, location: str, start: int, timeout: int,
                posted_within_days: Optional[int] = None):
    import requests

    resp = requests.get(search_url(keyword, location, start, posted_within_days),
                        headers={"User-Agent": common.USER_AGENT}, timeout=timeout)
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

# The criteria list under a posting: "Seniority level", "Employment type",
# "Job function", "Industries". Served to the anonymous page, verified
# 2026-09-13 on three postings: "Full-time", "Full-time", "Part-time" (a Swiss
# insurer's "C# / .NET / React 80-100%"). The employer picks the value from a
# fixed list, so it is a statement rather than a phrase to interpret.
_EMPLOYMENT_TYPE_RE = re.compile(
    r'description__job-criteria-subheader">\s*Employment type\s*</h3>\s*'
    r'<span[^>]*>\s*([^<]+?)\s*</span>', re.I)

# The guest fragment of one posting. The full /jobs/view/ page on a country
# subdomain — ae., nl., il.linkedin.com — does not carry the criteria list at
# all (checked 2026-09-13 on three postings: 230-270 KB of page, no "Employment
# type"), while this fragment, served to the same anonymous GET, does. It is
# asked for only when the page said nothing: one extra request, where needed.
GUEST_POSTING_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
_JOB_ID_RE = re.compile(r"(\d{8,})(?:[/?#]|$)")


def _employment_types_from_guest_fragment(url: str, timeout: int) -> list:
    """The employment type from the guest fragment, or [] — never raises."""
    import requests

    match = _JOB_ID_RE.search(url or "")
    if not match:
        return []
    try:
        resp = requests.get(GUEST_POSTING_URL.format(job_id=match.group(1)),
                            headers={"User-Agent": common.USER_AGENT}, timeout=timeout)
        resp.raise_for_status()
    except Exception:  # noqa: BLE001
        return []
    found = _EMPLOYMENT_TYPE_RE.search(resp.text or "")
    if not found:
        return []
    import normalize

    return normalize.employment_types(html.unescape(found.group(1)))


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

    try:
        resp = requests.get(url, headers={"User-Agent": common.USER_AGENT}, timeout=timeout)
        resp.raise_for_status()
    except Exception:  # noqa: BLE001
        return page_facts("")

    facts = page_facts(resp.text)
    if not facts["employment_types"]:
        facts["employment_types"] = _employment_types_from_guest_fragment(url, timeout)
    return facts


def page_facts(body: str) -> dict:
    """What one vacancy page's HTML states — no requests. Shared by the
    fetcher and its contract, so the contract checks the parsing that is
    actually used."""
    facts = {"description": "", "workplace_type": None, "salary_raw": None,
             "closed": False, "employment_types": [], "job_posting": False}
    if not body:
        return facts
    facts["closed"] = bool(_CLOSED_RE.search(body))
    employment = _EMPLOYMENT_TYPE_RE.search(body)
    if employment:
        import normalize

        facts["employment_types"] = normalize.employment_types(
            html.unescape(employment.group(1)))

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
        facts["job_posting"] = True
        if node.get("jobLocationType") == "TELECOMMUTE":
            facts["workplace_type"] = "remote"
        facts["salary_raw"] = facts["salary_raw"] or _salary_from_ld(node)
    return facts


def _fetch_description(url: str, timeout: int) -> str:
    """The full vacancy text. Kept as the narrow entry point for callers that
    want nothing else; the work happens in fetch_page_facts."""
    return fetch_page_facts(url, timeout)["description"]


def _fetch_search_page(keyword: str, location: str, start: int, timeout: int,
                         posted_within_days: Optional[int], counts: Optional[dict] = None) -> str:
    """One search page; on a 429 or a dropped connection it waits and asks
    once more. A long walk meets both now and then (2026-10-03: one
    "connection aborted" in 1 389 requests), and one wait is cheaper than
    losing the rest of the query."""
    import requests

    try:
        return _fetch_page(keyword, location, start, timeout, posted_within_days)
    except requests.HTTPError as exc:
        if getattr(exc.response, "status_code", None) != 429:
            raise
        reason = "rate_limited"
    except (requests.ConnectionError, requests.Timeout):
        reason = "dropped"
    if counts is not None:
        counts[reason] = counts.get(reason, 0) + 1
    time.sleep(RATE_LIMIT_PAUSE_SECONDS)
    return _fetch_page(keyword, location, start, timeout, posted_within_days)


class _Walk:
    """The state of one fetch() across all its queries."""

    def __init__(self, max_pages, posted_within_days, timeout):
        self.max_pages = max_pages
        self.posted_within_days = posted_within_days
        self.timeout = timeout
        self.records: List[dict] = []
        self.seen_urls = set()
        self.cards_seen = 0
        self.pages_read = 0
        self.queries = 0
        self.split_queries = 0
        self.capped = 0
        self.errors: List[str] = []
        self.counts = {"rate_limited": 0, "dropped": 0}

    def query(self, keyword: str, location: str, market: str) -> bool:
        """Reads one query page by page. True when it reached the ceiling —
        the list went on, but the guest search would not."""
        self.queries += 1
        start = 0
        seen_here = set()
        holes = 0
        for _ in range(self.max_pages):
            try:
                page_html = _fetch_search_page(keyword, location, start, self.timeout,
                                                 self.posted_within_days, self.counts)
            except Exception as exc:  # noqa: BLE001
                self.errors.append(f"{keyword}/{location}: {type(exc).__name__}")
                return False
            time.sleep(PAUSE_SECONDS)

            cards = _CARD_RE.findall(page_html)
            if not cards:
                if start >= RESULTS_CEILING:
                    return True                 # the ceiling, not the end of the list
                # A page now and then comes back empty in the middle of a list
                # that goes on after it (measured 2026-10-03: 10 such holes in
                # a walk of 100 pages). One is stepped over; two in a row is
                # the end.
                holes += 1
                if holes > 1:
                    return False
                start += 10
                continue
            holes = 0
            self.cards_seen += len(cards)
            self.pages_read += 1
            start += len(cards)

            fresh_here = 0
            for card in cards:
                rec = _card_to_common_schema(card, location, market)
                if rec is None or rec["url"] in seen_here:
                    continue
                seen_here.add(rec["url"])
                fresh_here += 1
                if rec["url"] in self.seen_urls:  # found by an earlier query
                    continue
                self.seen_urls.add(rec["url"])
                self.records.append(rec)
            # Past the end of a list the guest search may repeat cards it has
            # already served. Only this query's own cards count: a page of
            # vacancies another query already found is still a page that
            # moved on.
            if not fresh_here:
                return False
        return start >= RESULTS_CEILING

    def split(self, keyword: str, country: str) -> None:
        """The narrower queries for a (keyword, country) at the ceiling."""
        narrower = []
        if "remote" not in keyword.lower():
            narrower.append((f"remote {keyword}", country))
        narrower += [(keyword, region) for region in SPLIT_REGIONS.get(country, [])]
        for words, place in narrower:
            self.split_queries += 1
            self.query(words, place, country)

    def note(self) -> str:
        return (f"{self.pages_read} pages, {len(self.records)} vacancies, "
                f"{self.capped} at the ceiling, {self.split_queries} narrower queries"
                + (f", {self.counts['rate_limited']} x 429" if self.counts["rate_limited"] else "")
                + (f", {len(self.errors)} errors" if self.errors else ""))


def fetch(keywords: Optional[List[str]] = None,
          locations: Optional[List[str]] = None,
          max_pages: int = MAX_PAGES,
          enrich_limit: int = ENRICH_LIMIT,
          posted_within_days: Optional[int] = POSTED_WITHIN_DAYS,
          split_at_ceiling: bool = True,
          timeout: int = common.DEFAULT_TIMEOUT):
    """Walks (keyword × country) pairs and returns (records, note).

    keywords/locations come from <prefix>_sources.yaml -> params. Locations
    default to the active identity's market tiers, so that the country list
    lives in one place (see tools/markets.py). Each pair is read page after
    page until its list ends; a pair that reaches the guest search's ceiling
    is split into narrower queries (split_at_ceiling, see SPLIT_REGIONS).
    """
    import markets
    import progress

    profile = common.load_profile()
    keywords = keywords or (profile.get("tech_stack", {}).get("core") or [])[:3]
    locations = locations or markets.target_locations(profile)

    if not keywords or not locations:
        return [], "nothing to query: the keyword or country list is empty"

    walk = _Walk(max_pages, posted_within_days, timeout)
    # A full walk reads every page of every pair and can take hours; it says
    # how far along it is rather than going quiet until the end.
    tick = progress.Progress(len(keywords) * len(locations), "linkedin pairs")

    for keyword in keywords:
        for location in locations:
            if walk.query(keyword, location, location):
                walk.capped += 1
                if split_at_ceiling:
                    walk.split(keyword, location)
            tick.note = walk.note()
            tick()

    records, cards_seen, errors, counts = walk.records, walk.cards_seen, walk.errors, walk.counts

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
        to_read = records[:enrich_limit]
        read_tick = progress.Progress(len(to_read), "linkedin descriptions")
        for rec in to_read:
            # The whole page's facts rather than only its text: the request is
            # the same, and until 2026-09-13 this loop threw away the employer's
            # stated engagement, salary and TELECOMMUTE declaration that
            # enrich_descriptions.py already knew how to keep.
            facts = fetch_page_facts(rec["url"], timeout)
            if facts.get("description"):
                rec["description_text"] = facts["description"]
                enriched += 1
            if facts.get("employment_types"):
                rec["employment_types"] = facts["employment_types"]
            if facts.get("workplace_type"):
                rec["workplace_type"] = facts["workplace_type"]
            if facts.get("salary_raw"):
                rec["salary_raw"] = facts["salary_raw"]
            time.sleep(PAUSE_SECONDS)
            read_tick.note = f"{enriched} with a description"
            read_tick()

    note_parts = [f"queries {walk.queries} ({walk.capped} at the ceiling, "
                  f"{walk.split_queries} narrower), pages {walk.pages_read}, "
                  f"cards {cards_seen}, records {len(records)}, with description {enriched}"]
    if counts["rate_limited"]:
        note_parts.append(f"rate limited {counts['rate_limited']} times")
    if counts["dropped"]:
        note_parts.append(f"connection dropped {counts['dropped']} times")
    if errors:
        note_parts.append("errors: " + "; ".join(errors[:3]))
    return records, "; ".join(note_parts)


# ---------------------------------------------------------------------------
# The contract: the facts about LinkedIn this fetcher stands on, checked live.
# A fixed probe that belongs to the source, not to anybody's search — a common
# query in a large market, so an empty answer means something.
# ---------------------------------------------------------------------------
CONTRACT_PROBE = (".NET developer", "United Kingdom")
CONTRACT_PAGES_TO_OPEN = 3


def contract(c) -> None:
    """See tools/source_contract.py for what `c` is. Each expect() is a fact a
    part of this module relies on; the comment next to it says which part."""
    from datetime import date

    keyword, location = CONTRACT_PROBE
    window = POSTED_WITHIN_DAYS or 7

    # fetch(): the search answers an anonymous GET with <li> cards.
    first = _CARD_RE.findall(c.get(search_url(keyword, location, 0, window)))
    if not c.expect("the search answers with cards", first,
                    f"{len(first)} cards for '{keyword}' in {location}"):
        return
    c.note("cards per page", str(len(first)))

    # _card_to_common_schema(): a card yields title, company and link.
    parsed = [r for r in (_card_to_common_schema(card, location) for card in first) if r]
    c.expect("cards parse into title, company and link", len(parsed) >= 0.8 * len(first),
             f"{len(parsed)} of {len(first)}")

    # POSTED_WITHIN_DAYS: f_TPR is honoured. Without it the walk re-reads old
    # postings and stops before it reaches this week's.
    today = date.today()
    ages = []
    for rec in parsed:
        try:
            ages.append((today - date.fromisoformat(rec["posted_at"])).days)
        except (TypeError, ValueError):
            pass
    c.expect("cards carry a posting date", len(ages) >= 0.8 * max(len(parsed), 1),
             f"{len(ages)} of {len(parsed)}")
    stale = [a for a in ages if a > window + 2]
    c.expect(f"the posted-within filter keeps to {window} days", len(stale) <= 1,
             f"{len(stale)} of {len(ages)} cards are older; the oldest is "
             f"{max(ages) if ages else '?'} days")

    # fetch(): the next page starts after the cards received, and brings new ones.
    urls = {r["url"] for r in parsed}
    second = [r for r in (_card_to_common_schema(card, location) for card in
                          _CARD_RE.findall(c.get(search_url(keyword, location, len(first), window))))
              if r]
    new_on_second = [r for r in second if r["url"] not in urls]
    c.expect("the next page starts where this one ended",
             second and len(new_on_second) >= 0.5 * len(second),
             f"start={len(first)}: {len(second)} cards, {len(new_on_second)} not on the first page")

    # RESULTS_CEILING: a query is served a full 100 before the guest search
    # stops. The walk takes "empty at start >= 100" for the ceiling and splits
    # the query; were the ceiling lowered, a cut-off list would pass for a
    # finished one and nothing would be split.
    last = _CARD_RE.findall(c.get(search_url(keyword, location, RESULTS_CEILING - 10, window)))
    c.expect(f"a query is served its first {RESULTS_CEILING} results", last,
             f"start={RESULTS_CEILING - 10}: {len(last)} cards for '{keyword}' in {location}")
    beyond = _CARD_RE.findall(c.get(search_url(keyword, location, RESULTS_CEILING, window)))
    c.note("the ceiling", f"start={RESULTS_CEILING}: {len(beyond)} cards"
           + (" — deeper than before; the walk follows on its own" if beyond else ""))

    # SPLIT_REGIONS: a region query stays inside its country.
    region = SPLIT_REGIONS[location][0]
    regional = [r for r in (_card_to_common_schema(card, region, location) for card in
                            _CARD_RE.findall(c.get(search_url(keyword, region, 0, window)))) if r]
    inside = [r for r in regional if location in r["location_raw"]]
    c.expect("a region query stays inside its country",
             regional and len(inside) >= 0.7 * len(regional),
             f"'{region}': {len(inside)} of {len(regional)} cards in {location}")

    # fetch_page_facts(): a vacancy page is served and carries its description
    # and its schema.org JobPosting (TELECOMMUTE and the salary come from there).
    opened = described = structured = typed = 0
    for rec in parsed[:CONTRACT_PAGES_TO_OPEN]:
        facts = page_facts(c.get(rec["url"]))
        opened += 1
        described += len(facts["description"]) >= 200
        structured += facts["job_posting"]
        typed += bool(facts["employment_types"])
    need = max(opened - 1, 1)
    c.expect("a vacancy page carries its description", described >= need,
             f"{described} of {opened} pages")
    c.expect("a vacancy page carries a schema.org JobPosting", structured >= need,
             f"{structured} of {opened} pages")
    c.note("employment type on the page itself", f"{typed} of {opened} pages "
           "(the guest fragment is asked when it is missing)")


def main() -> None:
    import argparse
    import identity as identity_mod

    parser = argparse.ArgumentParser(description="Collect vacancies from LinkedIn (guest search)")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--keyword", action="append", help="Keyword (repeatable)")
    parser.add_argument("--location", action="append", help="Country (repeatable)")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES)
    parser.add_argument("--posted-within-days", type=int, default=POSTED_WITHIN_DAYS,
                        help="only vacancies posted within N days; 0 for any age")
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)

    records, note = fetch(args.keyword, args.location, args.max_pages,
                          posted_within_days=args.posted_within_days)
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
