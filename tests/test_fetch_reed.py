"""
Reed — the largest UK board, and the two mistakes its markup invites.

Both were made while writing the fetcher and both were invisible: the parser
looked correct, ran without error, and produced nothing useful.

  1. **Attribute order.** Reed writes `title="..."` BEFORE
     `data-qa="job-card-title"`. A regex that expects the other order matches
     nothing, and the fetcher reported "markup changed" on markup that had not.

  2. **The window is smaller than the icon.** Every metadata item opens with an
     inline SVG of its own, and that icon alone runs past 200 characters. A
     capture window sized for the text ran out of budget before reaching it —
     117 records collected with not one salary among them, from a board that
     states pay on nearly every card.

The snapshot below is trimmed from a live page of 2026-09-08 and keeps both
hazards intact: the real attribute order, and a full-length icon before the
salary. Shortening it for readability would delete the thing it tests.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import fetch_reed as reed  # noqa: E402

SNAPSHOT = """
<main>
<article class="card index-module_jobCard__DaYuk" data-qa="job-card" data-id="job57178431">
  <div class="index-module_jobCard__body__vWzBf card-body">
    <header>
      <div data-qa="badges-container"><span class="badge" data-qa="badge-0-featured">Featured</span></div>
      <h2 class="index-module_jobResultHeading__title__r7Yqg"><a href="/jobs/net-developer/57178431?source=searchResults&amp;filter=%2Fjobs%2Fnet-developer-jobs" class="index-module_jobTitle__702ZU" color="link" data-id="57178431" title=".NET Developer" data-qa="job-card-title" data-page-component="job_card" data-element="job_title">.NET Developer</a></h2>
      <div data-qa="job-posted-by" class="index-module_postedBy__nBQbf">30 July<!-- --> by <a href="/jobs/anglian-home-improvements-102505/p102505" class="index-module_profileUrl__1BKrL">Anglian Home Improvements</a></div>
      <ul class="index-module_jobMetadata__Hmbnh list-group" role="list" data-qa="job-metadata">
        <li data-qa="job-metadata-salary" class="index-module_jobMetadata__item__xWXZK list-group-item" role="listitem "><svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Salary" class="index-module_icon__Lo-1u"><use xlink:href="#svg-salary" x="0" y="0"></use></svg>£45,000 - £48,000 per annum</li>
        <li data-qa="job-metadata-location" class="index-module_jobMetadata__item__xWXZK list-group-item" role="listitem "><svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Location" class="index-module_icon__Lo-1u"><use xlink:href="#svg-location" x="0" y="0"></use></svg>Norwich, Norfolk</li>
      </ul>
    </header>
  </div>
</article>
<article class="card" data-qa="job-card" data-id="job57281339">
  <header>
    <h2><a href="/jobs/senior-net-developer/57281339?source=searchResults" class="x" data-id="57281339" title="Senior .NET Developer" data-qa="job-card-title">Senior .NET Developer</a></h2>
    <div data-qa="job-posted-by">2 September<!-- --> by <a href="/p">Noir</a></div>
    <ul data-qa="job-metadata">
      <li data-qa="job-metadata-salary" role="listitem "><svg role="img" aria-label="Salary"><use xlink:href="#svg-salary"></use></svg>£65,000 - £80,000 per annum</li>
      <li data-qa="job-metadata-location" role="listitem "><svg role="img" aria-label="Location"><use xlink:href="#svg-location"></use></svg>London</li>
    </ul>
  </header>
</article>
</main>
"""


def test_the_snapshot_parses_into_complete_records():
    records, note = reed.parse_page(SNAPSHOT)

    assert note is None
    assert len(records) == 2

    first = records[0]
    assert first["title"] == ".NET Developer"
    assert first["external_id"] == "reed:57178431"
    assert first["url"] == "https://www.reed.co.uk/jobs/net-developer/57178431"
    assert first["source"] == "reed"


def test_the_title_is_found_whatever_the_attribute_order():
    """Mistake 1. Reed writes title= before data-qa=, and a fetcher that
    assumes otherwise reports a markup change on markup that never changed."""
    records, note = reed.parse_page(SNAPSHOT)

    assert note is None, "the real attribute order must not read as breakage"
    assert [r["title"] for r in records] == [".NET Developer", "Senior .NET Developer"]


def test_the_salary_survives_the_icon_in_front_of_it():
    """Mistake 2, and the reason the snapshot keeps a full-length SVG. A stated
    salary is the highest of the three levels of trust in pay (CLAUDE.md 5) and
    this board states one on nearly every card — losing them all to a capture
    window was the most expensive silent bug in this file."""
    records, _ = reed.parse_page(SNAPSHOT)

    assert records[0]["salary_raw"] == "£45,000 - £48,000 per annum"
    assert records[1]["salary_raw"] == "£65,000 - £80,000 per annum"


def test_the_location_survives_it_too():
    records, _ = reed.parse_page(SNAPSHOT)

    assert records[0]["location_raw"] == "Norwich, Norfolk"
    assert records[1]["location_raw"] == "London"


def test_the_company_comes_out_of_the_posted_by_line():
    """"30 July by Anglian Home Improvements" — one field holding two facts."""
    records, _ = reed.parse_page(SNAPSHOT)

    assert records[0]["company"] == "Anglian Home Improvements"
    assert records[1]["company"] == "Noir"


def test_a_date_with_no_year_is_read_as_the_most_recent_one():
    """Reed omits the year. A day that has not arrived yet belongs to last
    year: a posting dated 30 December, read in January, is days old rather
    than eleven months in the future."""
    from datetime import datetime, timedelta, timezone

    today = datetime.now(timezone.utc).date()
    tomorrow = today + timedelta(days=1)
    month_name = tomorrow.strftime("%B")

    posted, _ = reed._posted_and_company(f"{tomorrow.day} {month_name} by Someone")

    assert posted is not None
    assert posted < today.isoformat(), "a future date must fall back a year"


def test_remote_is_never_invented_but_reeds_filter_is_recorded():
    """Reed's filters were tested the way LinkedIn's should have been: the
    remote slug shares only 15 of 25 results with the plain search, and the
    contract slug shares none. They work — so the slug may set workplace_type,
    and a tag keeps it distinguishable from an employer's own words."""
    plain, _ = reed.parse_page(SNAPSHOT)
    from_remote, _ = reed.parse_page(SNAPSHOT, workplace="remote", variant="remote-")

    assert all(r["remote"] is None for r in plain + from_remote)
    assert all(r["workplace_type"] is None for r in plain)
    assert all(r["workplace_type"] == "remote" for r in from_remote)
    assert "reed-filter:remote" in from_remote[0]["tags"]


def test_the_three_variants_are_all_fetched(monkeypatch):
    """The contract slug shares zero results with the plain search — skipping
    it would leave a whole body of work uncollected."""
    asked = []

    def fake_page(keyword, variant, page, timeout):
        asked.append((keyword, variant, page))
        return SNAPSHOT if page == 1 else ""

    monkeypatch.setattr(reed, "_fetch_page", fake_page)
    monkeypatch.setattr(reed.time, "sleep", lambda *_: None)

    reed.fetch(keywords=["net-developer"], max_pages=1)

    assert {v for _, v, _ in asked} == {"", "remote-", "contract-"}


# --- the obligation every HTML parser in this project carries --------------

def test_changed_markup_returns_zero_and_an_explicit_error():
    broken = SNAPSHOT.replace('data-qa="job-card-title"', 'data-qa="job-heading"')

    records, note = reed.parse_page(broken)

    assert records == []
    assert note and "markup changed" in note and "2 cards" in note


def test_a_page_with_no_cards_is_not_an_error():
    records, note = reed.parse_page("<main></main>")

    assert records == [] and note is None


def test_class_hashes_are_not_relied_on():
    """Reed's class names are build hashes and change on every deploy. A parser
    that reads one breaks on somebody else's release, silently — which is a
    failure that would otherwise only show up in production.

    The PATTERNS are inspected rather than the module text: the docstring
    explains this rule by quoting a hash, and a test that fails on its own
    explanation teaches the next person to weaken it.
    """
    import re as _re

    patterns = [value.pattern for value in vars(reed).values()
                if isinstance(value, _re.Pattern)]
    assert patterns, "the fetcher should compile its regexes at module level"

    for pattern in patterns:
        assert "index-module_" not in pattern, (
            f"a build-hash class name reached a parser regex: {pattern}")

    joined = " ".join(patterns)
    for hook in ('data-qa="job-card"', 'data-qa="job-card-title"',
                 'data-qa="job-metadata-salary"'):
        assert hook in joined, f"the stable hook {hook} should be what is parsed"


def test_one_failing_keyword_does_not_stop_the_others(monkeypatch):
    def fake_page(keyword, variant, page, timeout):
        if keyword == "boom":
            raise RuntimeError("network")
        return SNAPSHOT

    monkeypatch.setattr(reed, "_fetch_page", fake_page)
    monkeypatch.setattr(reed.time, "sleep", lambda *_: None)

    records, note = reed.fetch(keywords=["boom", "net-developer"], max_pages=1)

    assert len(records) == 2
    assert note and "boom" in note
