"""
Where a board's statement of the engagement comes from, source by source.

The engagement gate (test_score_engagement.py) is only as good as what reaches
it. Before 2026-09-13 every source that states the type threw it into `tags` —
a bag of strings the gate does not read — or did not keep it at all: the
LinkedIn fetcher fetched the vacancy page and kept only its text, dropping
"Employment type: Part-time" printed a few lines below.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import enrich_descriptions  # noqa: E402
import fetch_himalayas  # noqa: E402
import fetch_linkedin  # noqa: E402
import fetch_remotive  # noqa: E402
import normalize  # noqa: E402

# Trimmed from a live guest vacancy page, 2026-09-13 (a Swiss insurer's
# "Full Stack Software Engineer C# / .NET / React (a) 80-100%").
LINKEDIN_PAGE = """
<section class="show-more-less-html">
  <div class="show-more-less-html__markup description__text">
    Build C# and React features for an insurance platform.
  </div>
</section>
<ul class="description__job-criteria-list">
  <li class="description__job-criteria-item">
    <h3 class="description__job-criteria-subheader">
      Seniority level
    </h3>
    <span class="description__job-criteria-text description__job-criteria-text--criteria">
      Mid-Senior level
    </span>
  </li>
  <li class="description__job-criteria-item">
    <h3 class="description__job-criteria-subheader">
      Employment type
    </h3>
    <span class="description__job-criteria-text description__job-criteria-text--criteria">
      Part-time
    </span>
  </li>
</ul>
"""


class _Response:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


# --- LinkedIn ------------------------------------------------------------------

def test_the_linkedin_page_states_the_employment_type(monkeypatch):
    import requests

    monkeypatch.setattr(requests, "get", lambda *a, **k: _Response(LINKEDIN_PAGE))
    facts = fetch_linkedin.fetch_page_facts("https://www.linkedin.com/jobs/view/1", 10)
    assert facts["employment_types"] == ["part-time"]


def test_a_page_without_the_criteria_list_says_nothing(monkeypatch):
    import requests

    page = LINKEDIN_PAGE.split("<ul")[0]
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Response(page))
    assert fetch_linkedin.fetch_page_facts("https://x/1", 10)["employment_types"] == []


def test_the_seniority_line_is_not_mistaken_for_the_employment_type(monkeypatch):
    import requests

    page = LINKEDIN_PAGE.replace("Employment type", "Job function").replace("Part-time", "Engineering")
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Response(page))
    assert fetch_linkedin.fetch_page_facts("https://x/1", 10)["employment_types"] == []


def test_a_country_page_without_the_list_falls_back_to_the_guest_fragment(monkeypatch):
    """ae., nl. and il.linkedin.com serve a full page with no criteria list;
    the guest fragment for the same posting has it."""
    import requests

    asked = []

    def fake_get(url, *a, **k):
        asked.append(url)
        if "jobs-guest/jobs/api/jobPosting/4444319037" in url:
            return _Response(LINKEDIN_PAGE.replace("Part-time", "Full-time"))
        return _Response(LINKEDIN_PAGE.split("<ul")[0])

    monkeypatch.setattr(requests, "get", fake_get)
    facts = fetch_linkedin.fetch_page_facts(
        "https://ae.linkedin.com/jobs/view/senior-fullstack-developer-at-tat-4444319037", 10)

    assert facts["employment_types"] == ["full-time"]
    assert len(asked) == 2


def test_a_page_that_states_the_type_costs_no_second_request(monkeypatch):
    import requests

    asked = []
    monkeypatch.setattr(requests, "get", lambda url, *a, **k: asked.append(url) or _Response(LINKEDIN_PAGE))
    fetch_linkedin.fetch_page_facts("https://www.linkedin.com/jobs/view/4448425639", 10)
    assert len(asked) == 1


def test_a_url_without_a_posting_id_asks_nothing_more(monkeypatch):
    import requests

    asked = []
    monkeypatch.setattr(requests, "get",
                        lambda url, *a, **k: asked.append(url) or _Response(LINKEDIN_PAGE.split("<ul")[0]))
    facts = fetch_linkedin.fetch_page_facts("https://www.linkedin.com/jobs/view/no-id-here", 10)
    assert facts["employment_types"] == [] and len(asked) == 1


def test_a_described_vacancy_without_a_type_is_read_only_when_hours_matter():
    vacancies = {"v": {"source": "linkedin", "url": "https://x/1", "description_text": "C# work.",
                       "employment_types": [],
                       "computed": {"score": 45, "classification": "remote_unconfirmed"}},
                 "typed": {"source": "linkedin", "url": "https://x/2", "description_text": "C# work.",
                           "employment_types": ["full-time"],
                           "computed": {"score": 50, "classification": "remote_unconfirmed"}}}
    assert enrich_descriptions.worklist(vacancies) == []
    assert enrich_descriptions.worklist(vacancies, need_employment_types=True) == ["v"]


def test_the_linkedin_fetcher_keeps_what_the_page_states(monkeypatch):
    """Its own enrichment used to keep the text and throw away the rest."""
    card = ('<li><h3 class="base-search-card__title">Full Stack Engineer C#</h3>'
            '<h4 class="base-search-card__subtitle">Insurer AG</h4>'
            '<span class="job-search-card__location">Zurich</span>'
            '<a href="https://ch.linkedin.com/jobs/view/4448425639"></a></li>')
    monkeypatch.setattr(fetch_linkedin, "_fetch_page", lambda *a: card)
    monkeypatch.setattr(fetch_linkedin.time, "sleep", lambda *_: None)
    monkeypatch.setattr(fetch_linkedin, "fetch_page_facts", lambda url, timeout: {
        "description": "C# and React.", "employment_types": ["part-time"],
        "workplace_type": "remote", "salary_raw": "CHF 100000-120000 YEAR", "closed": False})

    records, _ = fetch_linkedin.fetch(keywords=["C#"], locations=["Switzerland"], max_pages=1)

    rec = normalize.normalize_record(records[0])
    assert rec["employment_types"] == ["part-time"]
    assert rec["workplace_type"] == "remote"
    assert rec["salary_raw"] == "CHF 100000-120000 YEAR"
    assert rec["description_text"] == "C# and React."


# --- boards with a type field ------------------------------------------------------

def test_remotive_states_the_type_as_a_field():
    rec = normalize.normalize_record(fetch_remotive._to_common_schema({
        "id": 1, "title": "Senior Independent Software Developer", "company_name": "A.Team",
        "url": "https://remotive.com/1", "job_type": "contract",
        "candidate_required_location": "Americas, Europe, Israel"}))
    assert rec["employment_types"] == ["contract"]


def test_himalayas_states_the_type_as_a_field():
    rec = normalize.normalize_record(fetch_himalayas._to_common_schema({
        "title": "Backend Developer (Node) Part-time", "companyName": "Zoftify",
        "applicationLink": "https://himalayas.app/1", "guid": "g1",
        "employmentType": "Part Time", "locationRestrictions": []}))
    assert rec["employment_types"] == ["part-time"]


# --- Himalayas search mode ------------------------------------------------------------

def _item(guid, employment="Part Time"):
    return {"title": f"Developer {guid}", "companyName": "Acme",
            "applicationLink": f"https://himalayas.app/{guid}", "guid": guid,
            "employmentType": employment}


def test_search_mode_multiplies_queries_by_types_and_walks_pages(monkeypatch):
    calls = []

    def fake_get(url, timeout, params=None):
        calls.append((url, dict(params or {})))
        page = params["page"]
        query, kind = params["q"], params.get("employment_type")
        size = fetch_himalayas.PAGE_SIZE if page == 1 else 3
        return [_item(f"{query}-{kind}-{page}-{i}", kind) for i in range(size)]

    monkeypatch.setattr(fetch_himalayas, "_get_jobs", fake_get)
    monkeypatch.setattr(fetch_himalayas.time, "sleep", lambda *_: None)

    records, note = fetch_himalayas.fetch(queries=[".net", "c#"],
                                          employment_types=["Part Time", "Contractor"],
                                          max_pages=5)

    assert note is None
    assert all(url == fetch_himalayas.SEARCH_URL for url, _ in calls)
    # a short second page ends the walk: 2 pages x 2 queries x 2 types
    assert len(calls) == 8
    assert {(p["q"], p["employment_type"]) for _, p in calls} == {
        (".net", "Part Time"), (".net", "Contractor"), ("c#", "Part Time"), ("c#", "Contractor")}
    assert len(records) == 4 * (fetch_himalayas.PAGE_SIZE + 3)


def test_search_mode_collapses_a_vacancy_found_twice(monkeypatch):
    monkeypatch.setattr(fetch_himalayas, "_get_jobs", lambda url, timeout, params=None: [_item("same")])
    monkeypatch.setattr(fetch_himalayas.time, "sleep", lambda *_: None)

    records, _ = fetch_himalayas.fetch(queries=["developer", ".net"], employment_types=["Part Time"])

    assert len(records) == 1


def test_search_mode_reports_a_failure_and_carries_on(monkeypatch):
    def flaky(url, timeout, params=None):
        if params["q"] == "broken":
            raise ValueError("unexpected payload shape")
        return [_item("ok")]

    monkeypatch.setattr(fetch_himalayas, "_get_jobs", flaky)
    monkeypatch.setattr(fetch_himalayas.time, "sleep", lambda *_: None)

    records, note = fetch_himalayas.fetch(queries=["broken", "fine"], employment_types=["Part Time"])

    assert len(records) == 1
    assert "broken/Part Time p1: ValueError" in note


def test_without_queries_the_plain_feed_is_unchanged(monkeypatch):
    seen = []
    monkeypatch.setattr(fetch_himalayas, "_get_jobs",
                        lambda url, timeout, params=None: seen.append((url, params)) or [_item("a")])

    records, note = fetch_himalayas.fetch()

    assert seen == [(fetch_himalayas.API_URL, None)]
    assert len(records) == 1 and note is None


# --- enrichment merges rather than replaces --------------------------------------------

def test_enrichment_adds_the_pages_statement_to_the_cards(monkeypatch):
    """A card that said "contract" and a page that says "part-time" are both
    true; the second does not cancel the first."""
    vacancies = {"v": {"source": "remoterocketship", "url": "https://x/1", "description_text": "",
                       "employment_types": ["contract"],
                       "computed": {"score": 50, "classification": "engagement_unconfirmed"}}}
    monkeypatch.setattr(enrich_descriptions, "_reader_for", lambda source: (
        lambda url, timeout: {"description": "Twenty hours a week.", "workplace_type": None,
                              "salary_raw": None, "closed": False,
                              "employment_types": ["part-time"]}))

    stats = enrich_descriptions.enrich(vacancies)

    assert vacancies["v"]["employment_types"] == ["part-time", "contract"]
    assert stats["employment_type_found"] == 1


def test_the_schema_org_reader_reads_employment_type(monkeypatch):
    import requests

    page = ('<script type="application/ld+json">{"@type": "JobPosting", '
            '"description": "C# work", "employmentType": ["PART_TIME", "CONTRACTOR"]}</script>')
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Response(page))

    facts = enrich_descriptions._json_ld_facts("https://x/1", 10)

    assert facts["employment_types"] == ["part-time", "contract"]
