"""
Tests for tools/report.py — first of all for showing pay with its source named
explicitly (confirmed by the owner, 2026-07-30): whether it is stated in the
vacancy itself, was found by hand on an external site, or there is no data at
all.
"""
import common
import report


def test_salary_info_shows_raw_text_when_present():
    vacancy = {"salary_raw": "$65/hour"}
    comp_bd = {"explicit": True, "hourly_amounts_found": [65.0]}
    text = report._fmt_salary_info(vacancy, comp_bd)
    assert "$65/hour" in text
    assert "stated in the vacancy" in text


def test_salary_info_falls_back_to_extracted_amounts_when_no_raw_field():
    vacancy = {}
    comp_bd = {"explicit": True, "annual_amounts_found": [70000.0, 90000.0]}
    text = report._fmt_salary_info(vacancy, comp_bd)
    assert "70,000" in text or "$70,000" in text
    assert "90,000" in text
    assert "stated in the vacancy" in text


def test_salary_info_shows_external_estimate_with_source():
    vacancy = {}
    comp_bd = {
        "explicit": False,
        "external_estimate": {
            "low": 60000,
            "high": 80000,
            "period": "year",
            "source": "Glassdoor",
            "note": "average for similar roles",
        },
    }
    text = report._fmt_salary_info(vacancy, comp_bd)
    assert "Glassdoor" in text
    assert "found manually" in text
    assert "average for similar roles" in text
    assert "60,000" in text and "80,000" in text


def test_salary_info_shows_no_data_when_nothing_found():
    vacancy = {}
    comp_bd = {"explicit": False}
    text = report._fmt_salary_info(vacancy, comp_bd)
    assert "not stated" in text
    assert "no data" in text


def test_vacancy_line_always_includes_salary_sub_line():
    vacancy = {
        "title": "Senior .NET Developer",
        "company": "Acme Corp",
        "url": "https://example.com/1",
        "salary_raw": None,
        "manual": {"status": "new", "notes": ""},
        "computed": {
            "score": 50,
            "score_breakdown": {"compensation_signal": {"explicit": False}},
            "needs_manual_review": False,
        },
    }
    line = report._fmt_vacancy_line(vacancy)
    assert "💰 salary:" in line
    assert "not stated" in line


def test_scoring_philosophy_comes_from_the_identity_profile(monkeypatch):
    """The explanation of the scale used to be hard-coded into shared machinery
    and printed into every identity's report — including one looking for onsite
    work at a startup."""
    import report

    monkeypatch.setattr(
        common, "load_profile",
        lambda *a, **k: {"identity": {"scoring_philosophy": "This identity's own philosophy."}},
    )
    assert report._scoring_philosophy() == "This identity's own philosophy."


def test_scoring_philosophy_falls_back_to_a_neutral_line(monkeypatch):
    import report

    monkeypatch.setattr(common, "load_profile", lambda *a, **k: {"identity": {}})
    text = report._scoring_philosophy()
    assert "identity's profile" in text
    assert "legacy" not in text, (
        "a neutral default must not impose one profile's philosophy on every identity"
    )


def test_hiring_country_prefers_the_office_that_posted_over_company_hq():
    """The owner's request, 2026-08-05: for an international company what is
    wanted is the country of the OFFICE that posted the vacancy, not where the
    company was founded. Google's Swiss office hires in Switzerland — that is
    where the contract is, where the money comes from, which time zone applies."""
    swiss_office = {
        "title": "Software Engineer",
        "company": "Google",
        "location_raw": "Zurich, Zurich, Switzerland",
        "computed": {"score_breakdown": {"remote_location_fit": {
            "header_scope": {"header_lines": ["headquarters: united states"]}}}},
    }
    assert report.hiring_country(swiss_office) == ("Switzerland", report.HIRING_OFFICE)


def test_hiring_country_trusts_the_market_tag_over_the_location_string():
    """The `market:<country>` tag is written by the fetcher — it is the country
    the fetcher queried, that is, a fact rather than a parsed string."""
    v = {"tags": ["market:United Kingdom"], "location_raw": "Remote"}
    assert report.hiring_country(v) == ("United Kingdom", report.HIRING_OFFICE)


def test_hiring_country_falls_back_to_headquarters_and_says_so():
    """When the office is unknown, the head office beats nothing — but a person
    must see that it is a different thing."""
    v = {
        "location_raw": "Anywhere in the World",
        "computed": {"score_breakdown": {"remote_location_fit": {
            "header_scope": {"header_lines": ["headquarters: sweden"]}}}},
    }
    assert report.hiring_country(v) == ("Sweden", report.COMPANY_HOME)


def test_hiring_country_handles_common_platform_spellings():
    for raw, expected in [("USA", "United States"),
                          ("London, England, United Kingdom", "United Kingdom"),
                          ("Dubai, Dubai, United Arab Emirates", "United Arab Emirates"),
                          ("Remote, Israel", "Israel")]:
        assert report.hiring_country({"location_raw": raw})[0] == expected, raw


def test_reputation_has_three_states_not_two():
    """The owner's request, 2026-08-06. «Not checked» read as «no data exists»
    while it meant «we never even tried». The first is a property of the company,
    the second a defect in the process, and which of the two a person sees matters."""
    found = report._fmt_reputation(
        {"has_data": True, "overall_rating": 4.2, "work_life_balance": 4.4,
         "source": "Glassdoor", "retrieval": "web_search"}, "hot_lead")
    assert "4.2" in found and "4.4" in found

    checked_empty = report._fmt_reputation(
        {"has_data": False, "verdict": "insufficient_sources",
         "checked_at": "2026-08-06T10:00:00+00:00", "searched": "Glassdoor, Indeed"},
        "hot_lead")
    assert "not enough sources" in checked_empty
    assert "2026-08-06" in checked_empty
    assert "Glassdoor, Indeed" in checked_empty

    gap = report._fmt_reputation({"has_data": False}, "hot_lead")
    assert "❗" in gap, "a gap at the head of the shortlist has to be noticeable"

    tail = report._fmt_reputation({"has_data": False}, "long_shot")
    assert "❗" not in tail, "the tail is deliberately left unchecked — that is not a gap"


def test_reputation_coverage_block_names_what_is_left():
    """Work not done has to be visible in the report rather than in somebody's
    memory: a measurement on 2026-08-06 found 55 companies at the head of the
    shortlist and zero checks, and the report said nothing about it."""
    vacancies = {
        "a": {"company": "Known Co", "computed": {"classification": "hot_lead"}},
        "b": {"company": "Obscure Co", "computed": {"classification": "worth_a_look"}},
    }
    companies = {
        "known-co": {"name": "Known Co",
                      "reputation": {"overall_rating": 4.0,
                                     "checked_at": "2026-08-06T10:00:00+00:00"}},
        "obscure-co": {"name": "Obscure Co"},
    }
    block = report._reputation_coverage_block(vacancies, companies)
    assert "not checked: 1" in block
    assert "Obscure Co" in block
    assert "Known Co" not in block.split("Still to check")[-1]
