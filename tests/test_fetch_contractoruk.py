"""
ContractorUK: a UK board of contracts rather than staff jobs.

The snapshot below is trimmed from a live page of 2026-09-08, keeping every
element the parser reads and nothing else. It exists for the obligation this
project puts on any HTML source: when the markup changes, the fetcher must
return ZERO and say so, never a stream of half-filled records that quietly
poison the database.

What makes this source worth its own file:

  * the day RATE is on the card — most boards hide pay entirely;
  * the board states the arrangement as a badge, so `workplace_type` comes
    from the employer ticking a box rather than from a phrase in prose;
  * "Outside IR35" is stated too, which is what makes a contract takeable from
    outside the UK in the first place.

And what it does not give: a company name. The board never publishes the
recruiter — the field is empty on the detail page as well — so the record
carries an honest placeholder instead of a guess.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import fetch_contractoruk as cuk  # noqa: E402

SNAPSHOT = """
<div class="cuk-jobs-list">
  <article class="cuk-job-card">
    <div class="cuk-job-card__main">
      <div class="cuk-job-card__head">
        <div class="cuk-job-card__headtext">
          <h2 class="cuk-job-card__title">
            <a href="/job/430150-senior_net_developer">Senior .Net Developer</a>
          </h2>
          <p class="cuk-job-card__firm">
            <span class="cuk-job-card__loc">
              <svg viewBox="0 0 16 16"><path d="M8 16s6-5.686 6-10"/></svg>
              Nationwide
            </span>
          </p>
        </div>
      </div>
      <p class="cuk-job-card__summary">Senior .Net Developer My customer is looking for a
        Senior .Net Developer to join them on a 9 Month contract basis, Outside IR35 &amp;
        working fully remote.</p>
      <div class="cuk-job-card__meta">
        <span class="cuk-badge cuk-badge--outside">Outside IR35</span>
        <span class="cuk-badge cuk-badge--remote">Remote</span>
        <a class="cuk-badge cuk-badge--sector" href="/it_contract_jobs">IT</a>
        <span class="cuk-job-card__posted">24 days ago</span>
      </div>
    </div>
    <div class="cuk-job-card__side">
      <span class="cuk-job-card__rate">£500 – £550/day</span>
    </div>
  </article>

  <article class="cuk-job-card">
    <div class="cuk-job-card__main">
      <div class="cuk-job-card__head">
        <div class="cuk-job-card__headtext">
          <h2 class="cuk-job-card__title">
            <a href="/job/433992-full_stack_developer_net">Full Stack Developer - .NET</a>
          </h2>
          <p class="cuk-job-card__firm">
            <span class="cuk-job-card__loc">London</span>
          </p>
        </div>
      </div>
      <p class="cuk-job-card__summary">A financial services client needs a full stack
        developer across C#, .NET and Angular.</p>
      <div class="cuk-job-card__meta">
        <span class="cuk-badge cuk-badge--hybrid">Hybrid</span>
        <a class="cuk-badge cuk-badge--sector" href="/it_contract_jobs">IT</a>
        <span class="cuk-job-card__posted">Today</span>
      </div>
    </div>
    <div class="cuk-job-card__side">
      <span class="cuk-job-card__rate">Up to £540/day</span>
    </div>
  </article>
</div>
"""


def test_the_snapshot_parses_into_complete_records():
    records, note = cuk.parse_page(SNAPSHOT)

    assert note is None
    assert len(records) == 2

    first = records[0]
    assert first["title"] == "Senior .Net Developer"
    assert first["external_id"] == "contractoruk:430150"
    assert first["url"] == "https://www.contractoruk.com/job/430150-senior_net_developer"
    assert first["location_raw"] == "Nationwide"
    assert first["source"] == "contractoruk"


def test_the_day_rate_is_kept_verbatim():
    """Most boards say "competitive". This one states a number, and a stated
    rate is the highest of the three levels of trust in pay (CLAUDE.md 5).
    The board separates the range with a non-breaking space and an en dash."""
    records, _ = cuk.parse_page(SNAPSHOT)

    assert records[0]["salary_raw"] == "£500 – £550/day"
    assert records[1]["salary_raw"] == "Up to £540/day"


def test_the_badge_becomes_the_workplace_type():
    """The heart of why this source is good. The badge is the board's own
    structured statement of where the work happens, so it feeds the field that
    already decides the arrangement gate — no inference from prose."""
    records, _ = cuk.parse_page(SNAPSHOT)

    assert records[0]["workplace_type"] == "remote"
    assert records[1]["workplace_type"] == "hybrid"


def test_remote_is_never_invented():
    """The mistake that cost this project every LinkedIn vacancy in the base:
    a fetcher that stamps remote=True because of how it searched. The flag
    stays None; only the badge speaks."""
    records, _ = cuk.parse_page(SNAPSHOT)

    assert all(r["remote"] is None for r in records)


def test_the_ir35_status_survives_as_a_tag():
    """Outside IR35 is what makes a UK contract takeable from abroad at all."""
    records, _ = cuk.parse_page(SNAPSHOT)

    assert "Outside IR35" in records[0]["tags"]
    assert "market:United Kingdom" in records[0]["tags"]
    assert "Outside IR35" not in records[1]["tags"]


def test_the_missing_company_is_named_honestly():
    """The board genuinely never publishes the recruiter. A placeholder that
    says so beats a guess, and beats an empty string that normalize would
    throw the record away for."""
    records, _ = cuk.parse_page(SNAPSHOT)

    assert all(r["company"] == cuk.UNDISCLOSED_COMPANY for r in records)
    assert "ContractorUK" in cuk.UNDISCLOSED_COMPANY


def test_a_relative_posting_date_becomes_a_real_one():
    from datetime import datetime, timedelta, timezone

    today = datetime.now(timezone.utc).date()
    assert cuk._posted_at("Today") == today.isoformat()
    assert cuk._posted_at("Yesterday") == (today - timedelta(days=1)).isoformat()
    assert cuk._posted_at("24 days ago") == (today - timedelta(days=24)).isoformat()
    assert cuk._posted_at("3 weeks ago") == (today - timedelta(days=21)).isoformat()
    assert cuk._posted_at("nonsense") is None
    assert cuk._posted_at("") is None


# --- the obligation every HTML parser in this project carries --------------

def test_changed_markup_returns_zero_and_an_explicit_error():
    """Cards present, none parseable. The fetcher must say the markup changed
    rather than hand back rubbish — a source silently returning nothing is
    visible in the report, a source returning nonsense is not."""
    broken = SNAPSHOT.replace('cuk-job-card__title', 'cuk-job-card__heading')

    records, note = cuk.parse_page(broken)

    assert records == []
    assert note and "markup changed" in note
    assert "2 cards" in note


def test_a_page_with_no_cards_at_all_is_not_an_error():
    """An empty result page is an ordinary thing — the last page of a search,
    or a keyword nothing matches. It must not read as breakage."""
    records, note = cuk.parse_page("<div class='cuk-jobs-list'></div>")

    assert records == []
    assert note is None


def test_one_unparseable_card_among_good_ones_is_skipped():
    records, note = cuk.parse_page(
        SNAPSHOT + '<article class="cuk-job-card"><p>nothing here</p></article>')

    assert len(records) == 2
    assert note is None


# --- pagination, the way this board really does it -------------------------

def test_the_first_page_carries_no_page_parameter(monkeypatch):
    """The pager is zero-based, and the link it labels "next page" is page=1.
    A loop starting at 1 silently skips the best-matching page — which on a
    relevance sort is the one that matters most."""
    asked = []

    def fake_page(query, page, timeout):
        asked.append((query, page))
        return SNAPSHOT if page == cuk.FIRST_PAGE else ""

    monkeypatch.setattr(cuk, "_fetch_page", fake_page)
    monkeypatch.setattr(cuk.time, "sleep", lambda *_: None)

    records, note = cuk.fetch(queries=["x"], max_pages=2)

    assert asked[0] == ("x", 0)
    assert len(records) == 2


def test_a_repeated_page_stops_the_paging(monkeypatch):
    """The board answers 200 for any page number and repeats the last one.
    Without this the fetcher would walk to max_pages every time, spending
    requests on vacancies it already has."""
    calls = []

    def fake_page(query, page, timeout):
        calls.append(page)
        return SNAPSHOT

    monkeypatch.setattr(cuk, "_fetch_page", fake_page)
    monkeypatch.setattr(cuk.time, "sleep", lambda *_: None)

    records, _ = cuk.fetch(queries=["x"], max_pages=5)

    assert len(records) == 2, "the same two vacancies, however many pages"
    assert len(calls) == 2, "one page beyond the repeat is enough to notice"


def test_one_failing_query_does_not_stop_the_others(monkeypatch):
    def fake_page(query, page, timeout):
        if query == "boom":
            raise RuntimeError("network")
        return SNAPSHOT

    monkeypatch.setattr(cuk, "_fetch_page", fake_page)
    monkeypatch.setattr(cuk.time, "sleep", lambda *_: None)

    records, note = cuk.fetch(queries=["boom", "fine"], max_pages=1)

    assert len(records) == 2
    assert note and "boom" in note


def test_the_default_queries_avoid_the_hash(monkeypatch):
    """"c#" returns zero results on this board however it is encoded, and so do
    "csharp" and "dotnet". Measured 2026-09-08 — a default query that finds
    nothing is a silent hole."""
    assert not any("#" in q for q in cuk.DEFAULT_QUERIES)
    assert ".net" in cuk.DEFAULT_QUERIES
