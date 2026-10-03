"""
Tests for the LinkedIn parser.

This is the project's only HTML source: the guest page is undocumented and can
change any day. So what is checked is not only "it parses correct markup" but
— more importantly — "with changed markup it returns ZERO and an error rather
than a stream of rubbish". A silently poisoned database is worse than an empty one.
"""
import fetch_linkedin


# A snapshot of the real markup, taken 2026-08-04 (cut down to two cards).
SNAPSHOT = """
<li>
  <div class="base-card relative job-search-card">
    <a class="base-card__full-link" href="https://il.linkedin.com/jobs/view/dotnet-developer-at-ravendb-4123456789?trk=guest">
    </a>
    <div class="base-search-card__info">
      <h3 class="base-search-card__title">
        Dotnet Developer
      </h3>
      <h4 class="base-search-card__subtitle">
        <a class="hidden-nested-link" href="https://il.linkedin.com/company/ravendb">RavenDB</a>
      </h4>
      <div class="base-search-card__metadata">
        <span class="job-search-card__location">Hadera, Haifa District, Israel</span>
        <time class="job-search-card__listdate" datetime="2026-08-01">2 days ago</time>
      </div>
    </div>
  </div>
</li>
<li>
  <div class="base-card relative job-search-card">
    <a class="base-card__full-link" href="https://ch.linkedin.com/jobs/view/net-engineer-at-acme-9876543210?trk=guest">
    </a>
    <div class="base-search-card__info">
      <h3 class="base-search-card__title">.NET Engineer</h3>
      <h4 class="base-search-card__subtitle">
        <a class="hidden-nested-link" href="https://ch.linkedin.com/company/acme">Acme AG</a>
      </h4>
      <div class="base-search-card__metadata">
        <span class="job-search-card__location">Z&uuml;rich, Switzerland</span>
      </div>
    </div>
  </div>
</li>
"""

# What arrives if LinkedIn changes its markup: cards in place, classes different.
CHANGED_LAYOUT = """
<li><div class="jobCard"><span class="jobCard__heading">Dotnet Developer</span>
<span class="jobCard__org">RavenDB</span></div></li>
<li><div class="jobCard"><span class="jobCard__heading">.NET Engineer</span>
<span class="jobCard__org">Acme AG</span></div></li>
"""


def _parse(page_html, location="Israel"):
    return [rec for card in fetch_linkedin._CARD_RE.findall(page_html)
            for rec in [fetch_linkedin._card_to_common_schema(card, location)]
            if rec is not None]


def test_snapshot_parses_into_complete_records():
    records = _parse(SNAPSHOT)
    assert len(records) == 2

    first = records[0]
    assert first["title"] == "Dotnet Developer"
    assert first["company"] == "RavenDB"
    assert first["url"].startswith("https://il.linkedin.com/jobs/view/")
    assert "?" not in first["url"], "tracking parameters must not reach the id"
    assert first["location_raw"] == "Hadera, Haifa District, Israel"
    assert first["posted_at"] == "2026-08-01"
    # NOT True. Measured 2026-08-11: the guest search ignores f_WT entirely —
    # the same job id comes back under "on-site", "remote" and "hybrid" alike —
    # so claiming remoteness from the query was a fabrication, and it was
    # clearing the remote gate for every LinkedIn vacancy in the base.
    assert first["remote"] is None, "a card says nothing about the arrangement"
    assert first["workplace_type"] is None, "only the vacancy page can say"


def test_html_entities_are_decoded():
    """Otherwise «Z&uuml;rich» and «&amp;» would go into the report instead of text."""
    records = _parse(SNAPSHOT, location="Switzerland")
    assert records[1]["location_raw"] == "Zürich, Switzerland"


def test_market_is_recorded_as_a_tag():
    """The queried country is more dependable than free text on the card, and the
    report needs it to show which market the vacancy was found in."""
    records = _parse(SNAPSHOT, location="Israel")
    assert "market:Israel" in records[0]["tags"]


def test_changed_layout_yields_nothing_rather_than_garbage():
    """The source's main safety net: better zero records and an explicit error
    than rubbish that quietly poisons the database and surfaces as a vacancy."""
    assert _parse(CHANGED_LAYOUT) == []


def test_card_without_mandatory_fields_is_skipped():
    """Ads and «similar companies» blocks arrive as the same <li>."""
    promo = '<li><div class="base-card"><h3 class="base-search-card__title">Advert</h3></div></li>' 
    assert _parse(promo) == []


def test_fetch_reports_format_change_as_an_error(monkeypatch):
    """When cards are present but not one can be parsed, that is a format failure,
    and it has to reach state.json rather than look like «the market is empty»."""
    monkeypatch.setattr(fetch_linkedin, "_fetch_page",
                        lambda *a, **k: CHANGED_LAYOUT)
    monkeypatch.setattr(fetch_linkedin.time, "sleep", lambda *_: None)

    records, note = fetch_linkedin.fetch(keywords=["C#"], locations=["Israel"], max_pages=1)
    assert records == []
    assert "the page format changed" in note


def test_fetch_deduplicates_across_keywords(monkeypatch):
    """One vacancy is found by several keywords — it must enter the database once,
    or duplicates multiply by the number of words."""
    monkeypatch.setattr(fetch_linkedin, "_fetch_page", lambda *a, **k: SNAPSHOT)
    monkeypatch.setattr(fetch_linkedin.time, "sleep", lambda *_: None)

    records, _ = fetch_linkedin.fetch(
        keywords=["C#", ".NET"], locations=["Israel"], max_pages=1
    )
    assert len(records) == 2


# ---------------------------------------------------------------------------
# Paging. Until 2026-10-02 the fetcher stepped by an assumed 25 cards and
# stopped when "fewer than 25" came — and the guest search serves ten, so every
# pair ended after its first page and max_pages did nothing.
# ---------------------------------------------------------------------------

def _card(job_id, posted="2026-10-01", title="C# Developer", where="London"):
    return (f'<li><div class="base-card"><a class="base-card__full-link" '
            f'href="https://uk.linkedin.com/jobs/view/dev-{job_id}?trk=guest"></a>'
            f'<h3 class="base-search-card__title">{title}</h3>'
            f'<h4 class="base-search-card__subtitle"><a>Company {job_id}</a></h4>'
            f'<span class="job-search-card__location">{where}</span>'
            f'<time datetime="{posted}">1 day ago</time></div></li>')


def _pages(total, size=10):
    """A fake search: `total` vacancies served `size` at a time from `start`;
    past the end it repeats the last page, as the guest search does."""
    calls = []

    def fake(keyword, location, start, timeout, posted_within_days=None):
        calls.append({"keyword": keyword, "start": start, "within": posted_within_days})
        first = min(start, max(total - size, 0))
        return "".join(_card(1000 + i) for i in range(first, min(first + size, total)))
    return fake, calls


def _quiet(monkeypatch, fake):
    monkeypatch.setattr(fetch_linkedin, "_fetch_page", fake)
    monkeypatch.setattr(fetch_linkedin.time, "sleep", lambda *_: None)


def test_paging_steps_by_the_cards_actually_received(monkeypatch):
    fake, calls = _pages(35)
    _quiet(monkeypatch, fake)
    records, note = fetch_linkedin.fetch(keywords=["C#"], locations=["UK"],
                                         max_pages=10, enrich_limit=0)
    assert [c["start"] for c in calls][:4] == [0, 10, 20, 30]
    assert len(records) == 35, "every page of the list is read, not only the first"


def test_paging_stops_when_a_page_brings_nothing_new(monkeypatch):
    """Past the end the guest search repeats its last cards instead of
    answering empty: a repeated page is the end of the list."""
    fake, calls = _pages(20)
    _quiet(monkeypatch, fake)
    records, _ = fetch_linkedin.fetch(keywords=["C#"], locations=["UK"],
                                      max_pages=10, enrich_limit=0)
    assert len(records) == 20
    assert len(calls) == 3, "two pages of news, one repeat, then stop"


def test_two_empty_pages_in_a_row_end_the_list(monkeypatch):
    calls = []

    def fake(keyword, location, start, timeout, posted_within_days=None):
        calls.append(start)
        return "".join(_card(i) for i in range(start, start + 10)) if start < 10 else ""
    _quiet(monkeypatch, fake)
    records, _ = fetch_linkedin.fetch(keywords=["C#"], locations=["UK"],
                                      max_pages=10, enrich_limit=0)
    assert len(records) == 10 and calls == [0, 10, 20]


def test_one_empty_page_in_the_middle_is_stepped_over(monkeypatch):
    """Measured 2026-10-03: a walk of 100 pages met ten empty ones scattered
    through a list that went on after each. Stopping at the first lost the
    rest of the list."""
    def fake(keyword, location, start, timeout, posted_within_days=None):
        if start == 30 or start >= 60:
            return ""
        return "".join(_card(i) for i in range(start, start + 10))
    _quiet(monkeypatch, fake)
    records, _ = fetch_linkedin.fetch(keywords=["C#"], locations=["UK"],
                                      max_pages=20, enrich_limit=0, split_at_ceiling=False)
    assert len(records) == 50, "the pages after the hole are read too"


# ---------------------------------------------------------------------------
# The ceiling. The anonymous guest search serves 100 results per query and an
# empty page at start=100 however long the list (2026-10-03: 736 postings in
# the UK, 100 served). A query that reaches it is split into narrower ones.
# ---------------------------------------------------------------------------

def _ceiling_search(calls, sizes=None):
    """Every query serves `sizes.get(location, 100)` cards, and nothing from
    start=100 on — the guest search as measured. Card ids are unique per
    (keywords, location), so narrower queries bring vacancies of their own."""
    sizes = sizes or {}

    def fake(keyword, location, start, timeout, posted_within_days=None):
        calls.append((keyword, location, start))
        total = min(sizes.get(location, 100), fetch_linkedin.RESULTS_CEILING)
        if start >= total:
            return ""
        base = abs(hash((keyword, location))) % 10_000_000 * 1000
        return "".join(_card(base + i) for i in range(start, min(start + 10, total)))
    return fake


def test_a_query_at_the_ceiling_is_split_into_narrower_ones(monkeypatch):
    calls = []
    _quiet(monkeypatch, _ceiling_search(calls))
    records, note = fetch_linkedin.fetch(keywords=["C# developer"], locations=["United Kingdom"],
                                         enrich_limit=0)
    queries = {(k, loc) for k, loc, _ in calls}
    assert ("remote C# developer", "United Kingdom") in queries
    for region in fetch_linkedin.SPLIT_REGIONS["United Kingdom"]:
        assert ("C# developer", region) in queries
    expected = 100 * (2 + len(fetch_linkedin.SPLIT_REGIONS["United Kingdom"]))
    assert len(records) == expected
    assert "1 at the ceiling" in note


def test_the_ceiling_costs_one_request_not_a_walk_to_max_pages(monkeypatch):
    calls = []
    _quiet(monkeypatch, _ceiling_search(calls))
    fetch_linkedin.fetch(keywords=["C#"], locations=["Iceland"], enrich_limit=0,
                         split_at_ceiling=False)
    assert [start for _, _, start in calls] == list(range(0, 110, 10))


def test_a_region_found_vacancy_belongs_to_the_country(monkeypatch):
    """The market is the country searched for, not the region the narrower
    query named: segments and the hiring country read the market tag."""
    calls = []
    _quiet(monkeypatch, _ceiling_search(calls))
    records, _ = fetch_linkedin.fetch(keywords=["C# developer"], locations=["Germany"],
                                      enrich_limit=0)
    assert {t for r in records for t in r["tags"]} == {"market:Germany"}


def test_a_query_below_the_ceiling_is_not_split(monkeypatch):
    calls = []
    _quiet(monkeypatch, _ceiling_search(calls, sizes={"United Kingdom": 42}))
    records, note = fetch_linkedin.fetch(keywords=["C# developer"],
                                         locations=["United Kingdom"], enrich_limit=0)
    assert {loc for _, loc, _ in calls} == {"United Kingdom"}
    assert len(records) == 42 and "0 at the ceiling" in note


def test_a_country_without_regions_is_split_by_remote_only(monkeypatch):
    calls = []
    _quiet(monkeypatch, _ceiling_search(calls))
    fetch_linkedin.fetch(keywords=["C# developer"], locations=["Iceland"], enrich_limit=0)
    assert {(k, loc) for k, loc, _ in calls} == {("C# developer", "Iceland"),
                                                ("remote C# developer", "Iceland")}


def test_a_remote_query_is_not_made_more_remote(monkeypatch):
    calls = []
    _quiet(monkeypatch, _ceiling_search(calls))
    fetch_linkedin.fetch(keywords=["remote .NET"], locations=["Iceland"], enrich_limit=0)
    assert {k for k, _, _ in calls} == {"remote .NET"}


def test_splitting_can_be_switched_off(monkeypatch):
    calls = []
    _quiet(monkeypatch, _ceiling_search(calls))
    fetch_linkedin.fetch(keywords=["C# developer"], locations=["United Kingdom"],
                         enrich_limit=0, split_at_ceiling=False)
    assert {loc for _, loc, _ in calls} == {"United Kingdom"}


def test_every_split_region_names_its_country():
    for country, regions in fetch_linkedin.SPLIT_REGIONS.items():
        for region in regions:
            assert region.endswith(country), (country, region)


def test_max_pages_caps_a_long_list(monkeypatch):
    fake, calls = _pages(500)
    _quiet(monkeypatch, fake)
    records, _ = fetch_linkedin.fetch(keywords=["C#"], locations=["UK"],
                                      max_pages=3, enrich_limit=0)
    assert len(calls) == 3 and len(records) == 30


def test_a_page_another_keyword_already_found_does_not_end_the_pair(monkeypatch):
    """The second keyword's first page may be all vacancies the first keyword
    found. That page still moved on — its second page must be read."""
    fake, calls = _pages(25)
    _quiet(monkeypatch, fake)
    records, _ = fetch_linkedin.fetch(keywords=["C#", ".NET"], locations=["UK"],
                                      max_pages=10, enrich_limit=0)
    assert len(records) == 25, "each vacancy once"
    assert [c["start"] for c in calls if c["keyword"] == ".NET"] == [0, 10, 20, 30]


def test_the_date_window_reaches_the_request(monkeypatch):
    fake, calls = _pages(5)
    _quiet(monkeypatch, fake)
    fetch_linkedin.fetch(keywords=["C#"], locations=["UK"], enrich_limit=0,
                         posted_within_days=3)
    assert calls[0]["within"] == 3


def test_search_url_asks_for_the_posting_window():
    url = fetch_linkedin.search_url(".NET developer", "United Kingdom", 20, 7)
    assert "f_TPR=r604800" in url and "start=20" in url
    assert "keywords=.NET+developer" in url
    assert "f_TPR" not in fetch_linkedin.search_url("C#", "UK", 0, None)
    assert "f_TPR" not in fetch_linkedin.search_url("C#", "UK", 0, 0), "0 means any age"


def test_a_dropped_connection_is_asked_once_more(monkeypatch):
    import requests

    fake, _ = _pages(5)
    attempts = []

    def dropped_once(*args):
        attempts.append(args[2])
        if len(attempts) == 1:
            raise requests.ConnectionError("Remote end closed connection without response")
        return fake(*args)
    _quiet(monkeypatch, dropped_once)
    records, note = fetch_linkedin.fetch(keywords=["C#"], locations=["UK"], enrich_limit=0)
    assert len(records) == 5 and "connection dropped 1 times" in note


def test_a_rate_limited_page_is_asked_once_more(monkeypatch):
    import requests

    fake, _ = _pages(5)
    attempts = []

    def limited_once(*args):
        attempts.append(args[2])
        if len(attempts) == 1:
            response = requests.Response()
            response.status_code = 429
            raise requests.HTTPError(response=response)
        return fake(*args)
    _quiet(monkeypatch, limited_once)
    records, note = fetch_linkedin.fetch(keywords=["C#"], locations=["UK"], enrich_limit=0)
    assert len(records) == 5 and "errors" not in note
    assert attempts[:2] == [0, 0]


# ---------------------------------------------------------------------------
# The contract, against canned answers: it must pass on what LinkedIn serves
# today and fail on each of the quiet changes it exists to catch.
# ---------------------------------------------------------------------------
import datetime as _dt  # noqa: E402

import source_contract  # noqa: E402

_TODAY = _dt.date.today()
_RECENT = (_TODAY - _dt.timedelta(days=2)).isoformat()
_OLD = (_TODAY - _dt.timedelta(days=60)).isoformat()
_VACANCY_PAGE = ('<div class="show-more-less-html__markup description__text">'
                 + "We build .NET services for insurers. " * 10 + '</div></section>'
                 '<script type="application/ld+json">{"@type": "JobPosting", '
                 '"title": "C# Developer"}</script>')


_UK = "London, England, United Kingdom"


def _linkedin(first_page=None, second_page=None, vacancy_page=_VACANCY_PAGE,
              last_page=None, region_page=None):
    """A canned LinkedIn: the probe's pages 1 and 2, its page at start=90, an
    empty start=100 (the ceiling), a region query, and vacancy pages."""
    if first_page is None:
        first_page = "".join(_card(i, _RECENT, where=_UK) for i in range(10))
    if second_page is None:
        second_page = "".join(_card(i, _RECENT, where=_UK) for i in range(10, 20))
    if last_page is None:
        last_page = "".join(_card(i, _RECENT, where=_UK) for i in range(90, 100))
    if region_page is None:
        region_page = "".join(_card(i, _RECENT, where=_UK) for i in range(500, 510))

    def get(url):
        if "/jobs/view/" in url:
            return vacancy_page
        if "location=London" in url:
            return region_page
        if "start=100" in url:
            return ""
        if "start=90" in url:
            return last_page
        return first_page if "start=0" in url else second_page
    return get


def _check(get):
    return source_contract.check_source("linkedin", getter=get, pause=0)


def test_contract_passes_on_todays_linkedin():
    result = _check(_linkedin())
    assert result["status"] == "ok", source_contract.format_result(result)


def test_contract_fails_when_the_search_serves_no_cards():
    assert _check(_linkedin(first_page="<html>redesigned</html>"))["status"] == "broken"


def test_contract_fails_when_cards_stop_parsing():
    changed = "".join(f'<li><div class="jobCard">Dev {i}</div></li>' for i in range(10))
    result = _check(_linkedin(first_page=changed))
    assert result["status"] == "broken" and "cards parse" in result["detail"]


def test_contract_fails_when_the_date_filter_is_ignored():
    stale = "".join(_card(i, _OLD) for i in range(10))
    result = _check(_linkedin(first_page=stale))
    assert result["status"] == "broken" and "posted-within" in result["detail"]


def test_contract_fails_when_the_next_page_repeats_the_first():
    first = "".join(_card(i, _RECENT) for i in range(10))
    result = _check(_linkedin(first_page=first, second_page=first))
    assert result["status"] == "broken" and "next page" in result["detail"]


def test_contract_fails_when_a_vacancy_page_loses_its_description():
    result = _check(_linkedin(vacancy_page="<html>sign in to see more</html>"))
    assert result["status"] == "broken" and "description" in result["detail"]


def test_contract_fails_when_the_ceiling_drops_below_100():
    """The walk reads "empty at start=100" as the ceiling and splits the query.
    A lower ceiling would make cut-off lists look finished."""
    result = _check(_linkedin(last_page=""))
    assert result["status"] == "broken" and "first 100 results" in result["detail"]


def test_contract_fails_when_a_region_query_leaves_its_country():
    elsewhere = "".join(_card(i, _RECENT, where="London, Ontario, Canada") for i in range(10))
    result = _check(_linkedin(region_page=elsewhere))
    assert result["status"] == "broken" and "region" in result["detail"]
