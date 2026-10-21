"""
tools/fetch_arcdev.py: Arc's own job requests through api.arc.dev.

The payloads are trimmed from live answers of 2026-10-21. Load-bearing
details in them: `company` is an object of nulls, posted_at is unix seconds,
the list spells the time-zone restriction client_time_zone_restriction and
the detail client_timezone_restriction, and a country list holds ISO codes.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import fetch_arcdev as arc  # noqa: E402
import normalize  # noqa: E402

NO_COMPANY = {"random_key": None, "url_string": None, "name": None, "logo": None, "internal_high_quality": None}
NET = {"random_key": "psx4zd2bui",
       "title": "Senior C#/.NET Engineer (Trading System) - Part-time - Overlap PST (3)",
       "job_type": "contract", "job_role": "engineering", "applied": None,
       "time_zone": "Pacific Time (US & Canada)", "time_zone_offset": "-07:00",
       "client_time_zone_restriction": "overlap", "required_countries": [],
       "min_annual_salary": None, "max_annual_salary": None, "overlap_hours": None,
       "experience_level": "senior",
       "url_string": "senior-c-net-engineer-trading-system-part-time-overlap-pst-3",
       "posted_at": 1792429712, "max_hourly_rate": 70, "min_hourly_rate": 40, "company": NO_COMPANY,
       "categories": [{"name": "C#", "url_string": "c_sharp"},
                      {"name": "Trading Systems", "url_string": "trading-systems"}]}
US_ONLY = {"random_key": "pt72fbno85", "title": "Freelance Developer US-FT ", "job_type": "contract",
           "job_role": "engineering", "time_zone": "Eastern Time (US & Canada)", "time_zone_offset": "-04:00",
           "client_time_zone_restriction": "strict", "required_countries": ["US"],
           "min_annual_salary": None, "max_annual_salary": None, "overlap_hours": None,
           "experience_level": "senior", "url_string": "freelance-developer-us-ft", "posted_at": 1792524692,
           "max_hourly_rate": 70, "min_hourly_rate": 40, "company": NO_COMPANY,
           "categories": [{"name": "MuleSoft", "url_string": "mulesoft"}]}
PERMANENT = {"random_key": "ptf98h8fw7", "title": "Mid-level Full-Stack Developer", "job_type": "permanent",
             "job_role": "engineering", "time_zone": "Central Time (US & Canada)", "time_zone_offset": "-05:00",
             "client_time_zone_restriction": "overlap", "required_countries": [],
             "min_annual_salary": 40000, "max_annual_salary": 60000, "overlap_hours": 4,
             "experience_level": "mid", "url_string": "mid-level-full-stack-developer", "posted_at": 1792603029,
             "max_hourly_rate": None, "min_hourly_rate": None, "company": NO_COMPANY,
             "categories": [{"name": "Python", "url_string": "python"}]}
DETAIL = {"random_key": "psx4zd2bui", "title": NET["title"], "job_type": "contract",
          "available_hours_per_week": 20,
          "description": "#### Project Overview\nThe client has a partially built automated futures trading "
                         "system in C#/.NET on Quantower.\n\n#### Required Experience\n"
                         "- Senior C#/.NET developer, 5+ years, production systems",
          "estimated_weeks": 4, "url_string": NET["url_string"], "required_countries": [],
          "required_locations": ["worldwide"], "discipline": "dot-net", "state": "opened",
          "timezone": "Pacific Time (US & Canada)", "timezone_offset": "-07:00",
          "client_timezone_restriction": "overlap", "closed": False, "public": True, "company": None,
          "max_hourly_rate": 70, "min_hourly_rate": 40}


def fake(pages, detail=DETAIL, fail_detail=False):
    asked = []

    def post(url, body):
        asked.append((url, dict(body)))
        return pages[body["page"] - 1]

    def get(url):
        asked.append((url, None))
        if fail_detail:
            raise TimeoutError("slow")
        return detail
    return post, get, asked


def test_every_page_is_read_with_the_header_body_and_the_country(monkeypatch):
    monkeypatch.setattr(arc, "PER_PAGE", 2)
    pages = [{"total_job_count": 3, "jobs": [NET, US_ONLY]}, {"total_job_count": 3, "jobs": [PERMANENT, NET]}]
    post, get, asked = fake(pages)
    records, note = arc.fetch("ge", details=False, post=post, get=get, pause=0)
    assert note is None
    assert [b for url, b in asked] == [
        {"page": 1, "per_page": 2, "sort_by": "latest", "country_code": "GE"},
        {"page": 2, "per_page": 2, "sort_by": "latest", "country_code": "GE"}]
    assert [r["external_id"] for r in records] == ["psx4zd2bui", "pt72fbno85", "ptf98h8fw7"]   # the repeat out
    assert arc.HEADERS["x-requested-from"] == "arc-next"


def test_a_full_page_that_reaches_the_total_is_the_last(monkeypatch):
    monkeypatch.setattr(arc, "PER_PAGE", 2)
    post, get, asked = fake([{"total_job_count": 2, "jobs": [NET, US_ONLY]}])
    records, note = arc.fetch(details=False, post=post, get=get, pause=0)
    assert len(records) == 2 and note is None
    assert asked == [(arc.LIST_URL, {"page": 1, "per_page": 2, "sort_by": "latest"})]   # no country: every request


def test_a_record_carries_the_page_link_the_terms_and_the_full_text():
    post, get, asked = fake([{"total_job_count": 1, "jobs": [NET]}])
    (record,), note = arc.fetch("GE", post=post, get=get, pause=0)
    assert note is None and asked[-1] == ("https://api.arc.dev/job-requests/psx4zd2bui", None)
    assert record["url"] == ("https://arc.dev/remote-jobs/details/"
                             "senior-c-net-engineer-trading-system-part-time-overlap-pst-3-psx4zd2bui")
    assert record["company"] == "Arc.dev client"
    assert record["location_raw"] == "Worldwide; overlap with Pacific Time (UTC-07:00)"
    assert record["remote"] is True and record["workplace_type"] == "remote"
    assert record["salary_raw"] == "$40-$70/hour"
    assert record["tags"] == ["C#", "Trading Systems"]
    text = record["description_text"]
    assert text.startswith("#### Project Overview")
    assert "Engagement: 20 hours a week, estimated 4 weeks" in text and text.endswith("Level: senior")
    canonical = normalize.normalize_record(record)
    assert canonical["employment_types"] == ["part-time", "contract"]
    assert canonical["posted_at"].startswith("2026-10-")


@pytest.mark.parametrize("item, location, salary, employment", [
    (US_ONLY, "United States only; working hours of Eastern Time (UTC-04:00)", "$40-$70/hour", ["contract"]),
    # "permanent" says nothing about hours (normalize.py)
    (PERMANENT, "Worldwide; overlap 4 h with Central Time (UTC-05:00)", "$40,000-$60,000/year", []),
    ({**PERMANENT, "required_countries": ["AM", "GE"], "time_zone": "Singapore", "time_zone_offset": "+08:00"},
     "Armenia, country of Georgia only; overlap 4 h with UTC+08:00", "$40,000-$60,000/year", []),
    ({**NET, "time_zone": "no-preference", "time_zone_offset": None, "min_hourly_rate": None},
     "Worldwide", "$70/hour", ["contract"]),
])
def test_location_salary_and_engagement_from_the_list_fields(item, location, salary, employment):
    record = arc.to_record(item)
    assert (record["location_raw"], record["salary_raw"], record["employment_types"]) == (location, salary, employment)


@pytest.mark.parametrize("codes, country_code, location", [
    # " only" is a refusal to score.py whoever reads it, so a list holding
    # the residency is written without it
    (["AM", "GE", "DE"], "ge", "3 countries including country of Georgia"),
    (["GE"], "GE", "country of Georgia"),
    (["US"], "GE", "United States only"),
    (["US", "CA", "MX", "BR", "AR", "CL", "PE"], None,
     "7 countries (United States, Canada, Mexico, Brazil, Argentina, ...) only"),
])
def test_a_country_list_names_the_residency_without_only(codes, country_code, location):
    item = {**NET, "required_countries": codes, "client_time_zone_restriction": None}
    assert arc.to_record(item, country_code=country_code)["location_raw"] == location


def test_the_residency_in_a_list_is_not_refused_by_the_structured_gate():
    import score

    criteria = {"remote_location_fit": {"structured_location_gate": {
        "worldwide_markers": ["worldwide"], "remote_without_country_tokens": ["remote"],
        "exclusivity_markers": [" only"], "continent_names": ["europe"], "continent_threshold": 3}}}
    listed = arc.to_record({**NET, "required_countries": ["AM", "GE"]}, country_code="GE")
    elsewhere = arc.to_record({**NET, "required_countries": ["US"]}, country_code="GE")
    assert score._check_structured_location(listed, criteria)[0] is False
    assert score._check_structured_location(elsewhere, criteria)[0] is True


@pytest.mark.parametrize("hours, employment", [
    (40, ["full-time"]), (25, ["part-time"]),
    (30, []),   # on a "WW - FT" and a "WW-PT" title alike (2026-10-22)
    (None, []),
])
def test_hours_a_week_on_the_detail_set_the_engagement(hours, employment):
    record = arc.to_record(PERMANENT, {**DETAIL, "available_hours_per_week": hours})
    assert record["employment_types"] == employment


def test_a_detail_that_fails_leaves_the_list_fields_and_says_so():
    post, get, _ = fake([{"total_job_count": 1, "jobs": [NET]}], fail_detail=True)
    (record,), note = arc.fetch(post=post, get=get, pause=0)
    assert record["description_text"] == "Skills: C#, Trading Systems\n\nLevel: senior"
    assert record["employment_types"] == ["contract"]
    assert note == "psx4zd2bui: TimeoutError"


def test_a_request_closed_on_its_detail_is_left_out():
    post, get, _ = fake([{"total_job_count": 1, "jobs": [NET]}], detail={**DETAIL, "closed": True})
    records, note = arc.fetch(post=post, get=get, pause=0)
    assert records == [] and note == "1 closed on their detail page"


def test_malformed_items_are_counted_and_a_short_read_is_said():
    broken = {**NET, "random_key": "pzzz", "url_string": ""}
    post, get, _ = fake([{"total_job_count": 5, "jobs": [NET, broken, "rubbish"]}])
    records, note = arc.fetch(details=False, post=post, get=get, pause=0)
    assert [r["external_id"] for r in records] == ["psx4zd2bui"]
    assert note == "skipped 2 malformed; read 3 of 5"


@pytest.mark.parametrize("failure", [ConnectionError("down"), ValueError("not JSON")])
def test_a_list_that_fails_is_an_error_not_an_empty_success(failure):
    def post(url, body):
        raise failure
    records, note = arc.fetch(post=post, get=None, pause=0)
    assert records == [] and note.startswith(type(failure).__name__)


def test_an_answer_without_a_jobs_list_is_an_error():
    post, get, _ = fake([{"error": "csrf check failed"}])
    records, note = arc.fetch(post=post, get=get, pause=0)
    assert records == [] and note == "ValueError: the answer has no `jobs` list"
