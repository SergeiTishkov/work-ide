"""
Remote Rocketship — the board that filters by engagement for real.

Its listing page carries the whole result set as Next.js page data, and the
parser reads that rather than the markup. The records below are trimmed from
live pages of 2026-09-13; the shapes that matter are kept exactly:

  * `employmentType` as a field ("part-time", "contract") — the reason the
    source exists in this project;
  * `salaryRange` with amounts already converted to US dollars, and periods
    the scoring does not know ("per day", "per week") — converted here, or
    "$80 per day" would read as eighty dollars an hour;
  * `url` pointing at the EMPLOYER's own posting, while the record's link is
    the Remote Rocketship page the description reader can work with.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import fetch_remoterocketship as rr  # noqa: E402
import normalize  # noqa: E402

JOB_NET_CONTRACT = {
    "id": 20170001,
    "created_at": "2026-09-11T10:00:00.000+00:00",
    "roleTitle": "Senior .NET Developer",
    "slug": "senior-net-developer-lithuania-remote",
    "url": "https://scale3c.recruitee.com/o/net-developer",
    "company": {"name": "Scale3C", "slug": "scale3c", "homePageURL": "https://scale3c.com"},
    "employmentType": "contract",
    "locationType": "remote",
    "location": "Lithuania",
    "locationCountries": None,
    "salaryRange": {"min": 30, "max": 40, "salaryType": "per hour", "currencyCode": "EUR",
                    "minSalaryAsUSD": 35, "maxSalaryAsUSD": 46,
                    "salaryHumanReadableText": "€30 - €40 per hour"},
    "techStack": ["Azure", "Kubernetes", "Microservices", ".NET"],
    "twoLineJobDescriptionSummary": "Build .NET microservices on Azure for a logistics platform.",
    "jobDescriptionSummary": "Contract .NET developer",
}

JOB_PART_TIME_DAILY = {
    "id": 20170002,
    "created_at": "2026-09-12T10:00:00.000+00:00",
    "roleTitle": "Open Source Software Engineer",
    "slug": "open-source-software-engineer-new-york-remote",
    "url": "https://24mag.example/jobs/1",
    "company": {"name": "24-MAG", "slug": "24-mag"},
    "employmentType": "part-time",
    "locationType": "remote",
    "location": "United States",
    "locationCountries": ["United States", "Canada"],
    "salaryRange": {"salaryType": "per day", "minSalaryAsUSD": 480, "maxSalaryAsUSD": 640},
    "techStack": [],
    "twoLineJobDescriptionSummary": "Maintain open-source TypeScript tooling.",
}


def _page(jobs, total=None):
    data = {"props": {"pageProps": {"initialJobOpenings": jobs,
                                    "initialTotalJobCount": total or len(jobs)}}}
    return ('<html><head></head><body><div id="__next"></div>'
            '<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(data) + "</script></body></html>")


# --- parsing the page ---------------------------------------------------------

def test_the_page_data_is_read():
    jobs, note = rr.parse_listing(_page([JOB_NET_CONTRACT, JOB_PART_TIME_DAILY]))
    assert note is None
    assert [j["id"] for j in jobs] == [20170001, 20170002]


def test_a_page_without_page_data_is_zero_records_and_a_note():
    """The markup-change obligation: nothing half-parsed, and a reason."""
    jobs, note = rr.parse_listing("<html><body>Remote jobs</body></html>")
    assert jobs == []
    assert "format changed" in note


def test_broken_page_data_is_zero_records_and_a_note():
    body = '<script id="__NEXT_DATA__" type="application/json">{not json</script>'
    jobs, note = rr.parse_listing(body)
    assert jobs == [] and "not JSON" in note


def test_page_data_without_the_list_is_zero_records_and_a_note():
    body = '<script id="__NEXT_DATA__" type="application/json">{"props": {"pageProps": {}}}</script>'
    jobs, note = rr.parse_listing(body)
    assert jobs == [] and "initialJobOpenings" in note


def test_empty_and_none_bodies_do_not_raise():
    for body in ("", None):
        jobs, note = rr.parse_listing(body)
        assert jobs == [] and note


# --- one record -------------------------------------------------------------------

def test_a_record_carries_the_engagement_as_a_field():
    rec = normalize.normalize_record(rr._to_common_schema(JOB_NET_CONTRACT))
    assert rec["employment_types"] == ["contract"]
    assert rec["workplace_type"] == "remote"
    assert rec["remote"] is True


def test_the_link_is_the_boards_page_and_the_employers_posting_is_kept():
    rec = rr._to_common_schema(JOB_NET_CONTRACT)
    assert rec["url"] == ("https://www.remoterocketship.com/company/scale3c/jobs/"
                          "senior-net-developer-lithuania-remote/")
    assert rec["company_url"] == "https://scale3c.recruitee.com/o/net-developer"
    assert rec["external_id"] == "remoterocketship:20170001"


def test_pay_is_written_in_us_dollars_in_a_unit_the_scoring_reads():
    assert rr._to_common_schema(JOB_NET_CONTRACT)["salary_raw"] == "$35 - $46 per hour"


def test_a_day_rate_becomes_an_hourly_rate():
    """"$480-640 per day" must not reach the amount extractor as it is: it
    knows hours, months and years, and would take 480 for an hourly rate."""
    assert rr._to_common_schema(JOB_PART_TIME_DAILY)["salary_raw"] == "$60 - $80 per hour"


def test_a_weekly_rate_becomes_an_annual_one():
    job = dict(JOB_PART_TIME_DAILY, salaryRange={"salaryType": "per week",
                                                 "minSalaryAsUSD": 1500, "maxSalaryAsUSD": 1500})
    assert rr._to_common_schema(job)["salary_raw"] == "$78,000 per year"


def test_no_salary_is_none_not_a_zero():
    for salary in (None, {}, {"salaryType": "per hour"}):
        assert rr._to_common_schema(dict(JOB_NET_CONTRACT, salaryRange=salary))["salary_raw"] is None


def test_a_list_of_countries_wins_over_the_single_location():
    assert rr._to_common_schema(JOB_PART_TIME_DAILY)["location_raw"] == "United States, Canada only"


def test_the_location_is_written_as_the_applicant_requirement_it_is():
    """The job page publishes it as schema.org applicantLocationRequirements.
    "X only" is the phrase the structured-location gate reads as a restriction,
    the same one fetch_himalayas writes."""
    assert rr._to_common_schema(JOB_NET_CONTRACT)["location_raw"] == "Lithuania only"


def test_no_country_is_worldwide_not_an_empty_restriction():
    for location in ("Worldwide", "", None, "Anywhere"):
        job = dict(JOB_NET_CONTRACT, location=location, locationCountries=None)
        assert rr._to_common_schema(job)["location_raw"] == "Worldwide", location


def test_a_restricted_remote_record_is_rejected():
    """End to end through the scoring: a Brazil-only contract must not wait in
    a section asking a person to check its hours."""
    import score
    from test_score import CRITERIA, PROFILE

    job = dict(JOB_NET_CONTRACT, location="Brazil", employmentType="part-time",
               twoLineJobDescriptionSummary="Maintain an ASP.NET Core and SQL Server platform in C#.")
    rec = normalize.normalize_record(rr._to_common_schema(job))
    result = score.score_vacancy(rec, CRITERIA, PROFILE)
    assert any(d.startswith("location: source restricts hiring to") for d in result["dealbreakers"])
    assert result["classification"] == "rejected"


def test_the_tech_stack_and_summary_reach_the_text_the_gates_read():
    rec = rr._to_common_schema(JOB_NET_CONTRACT)
    assert "Tech stack: Azure, Kubernetes, Microservices, .NET" in rec["description_text"]
    assert "Build .NET microservices" in rec["description_text"]
    assert "Pay as posted: €30 - €40 per hour" in rec["description_text"]


def test_records_missing_what_identifies_them_are_dropped():
    for broken in ({}, None, "text",
                   dict(JOB_NET_CONTRACT, roleTitle=""),
                   dict(JOB_NET_CONTRACT, company={"name": "X"}),
                   dict(JOB_NET_CONTRACT, company="Scale3C"),
                   dict(JOB_NET_CONTRACT, slug=""),
                   dict(JOB_NET_CONTRACT, id=None)):
        assert rr._to_common_schema(broken) is None, broken


# --- the walk over listings -----------------------------------------------------

def test_every_listing_is_walked_and_repeats_are_collapsed(monkeypatch):
    asked = []

    def fake_page(slug, employment, timeout):
        asked.append((slug, employment))
        return _page([JOB_NET_CONTRACT, JOB_PART_TIME_DAILY])

    monkeypatch.setattr(rr, "_fetch_page", fake_page)
    monkeypatch.setattr(rr.time, "sleep", lambda *_: None)

    records, note = rr.fetch(slugs=["net", "developer"], employment_types=["part-time", "contract"])

    assert asked == [("net", "part-time"), ("net", "contract"),
                     ("developer", "part-time"), ("developer", "contract")]
    assert len(records) == 2
    assert note is None


def test_an_unknown_slug_is_reported_as_a_configuration_mistake(monkeypatch):
    monkeypatch.setattr(rr, "_fetch_page",
                        lambda slug, employment, timeout: None if slug == "dotnet" else _page([JOB_NET_CONTRACT]))
    monkeypatch.setattr(rr.time, "sleep", lambda *_: None)

    records, note = rr.fetch(slugs=["dotnet", "net"], employment_types=["contract"])

    assert len(records) == 1
    assert "dotnet/contract" in note and "404" in note


def test_one_failing_listing_does_not_stop_the_rest(monkeypatch):
    def flaky(slug, employment, timeout):
        if slug == "net":
            raise ConnectionError("reset")
        return _page([JOB_PART_TIME_DAILY])

    monkeypatch.setattr(rr, "_fetch_page", flaky)
    monkeypatch.setattr(rr.time, "sleep", lambda *_: None)

    records, note = rr.fetch(slugs=["net", "developer"], employment_types=["part-time"])

    assert [r["external_id"] for r in records] == ["remoterocketship:20170002"]
    assert "net/part-time: ConnectionError" in note


def test_a_changed_page_is_named_in_the_note(monkeypatch):
    monkeypatch.setattr(rr, "_fetch_page", lambda *a: "<html>redesigned</html>")
    monkeypatch.setattr(rr.time, "sleep", lambda *_: None)

    records, note = rr.fetch(slugs=["net"], employment_types=["contract"])

    assert records == []
    assert "format changed" in note
