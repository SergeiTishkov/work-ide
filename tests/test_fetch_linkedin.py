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
    assert first["remote"] is True, "the query always carries the remote filter"


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
