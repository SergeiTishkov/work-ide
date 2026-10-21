"""
tools/fetch_dataart.py: DataArt's own vacancies through its site's JSON API.

The payloads are trimmed from live answers of 2026-10-21. Two details in them
are load-bearing: the banner card mixed into `items` (contentType 1, a GUID
id, no slug), and "Georgia" in the countries list, which is the country.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import fetch_dataart as dataart  # noqa: E402

FIELDS = {"totalVacancies": 117, "countries": [
    {"id": 4610, "parentId": None, "title": "Armenia", "total": 30},
    {"id": 5742, "parentId": None, "title": "Georgia", "total": 29},
    {"id": 17, "parentId": None, "title": "Bulgaria", "total": 40}]}

REMOTE = {"id": 44319, "fullUrl": "https://www.dataart.team/vacancies/dan00096", "slug": "DAN00096",
          "title": "Senior Data Analyst with Product Analytics, Learning Platform ",
          "text": "This project focuses on product analytics.",
          "locationTags": [{"id": 5770, "parentId": 5742, "title": "Remote.Georgia"},
                           {"id": 4611, "parentId": 4610, "title": "Remote.Armenia"}],
          "countriesTags": [{"id": 4610, "parentId": None, "title": "Armenia"},
                            {"id": 5742, "parentId": None, "title": "Georgia"}],
          "skillsTags": [{"id": 4668, "parentId": 4667, "title": "Data Analyst"}],
          "contentType": 0}
OFFICE = {"id": 44400, "fullUrl": "https://www.dataart.team/vacancies/hr00012", "slug": "HR00012",
          "title": "HR Administrator", "text": "Tbilisi office.",
          "locationTags": [{"id": 5743, "parentId": 5742, "title": "Tbilisi"},
                           {"id": 5780, "parentId": 17, "title": "Remote.Bulgaria"}],
          "countriesTags": [{"id": 5742, "parentId": None, "title": "Georgia"},
                            {"id": 17, "parentId": None, "title": "Bulgaria"}],
          "contentType": 0}
BANNER = {"id": "f0a4fffc-8e92-476c-80d6-ca1a4b9bb177", "title": "For Pros", "contentType": 1}
DETAIL = {"title": "Senior Data Analyst", "positionInfo": "<p>We are looking for a Senior Data Analyst.</p>",
          "projectInfo": "A learning platform.", "teamInfo": "", "technologiesStack": "Tableau, BigQuery",
          "responsibilities": ["Design experiments"], "requirements": ["5+ years of analytics", ""],
          "additionalRequirements": [], "countriesTags": REMOTE["countriesTags"]}


def fake(pages, detail=DETAIL, fail_detail=False):
    asked = []

    def get(url, params=None):
        asked.append((url, dict(params or {})))
        if url == dataart.FIELDS_URL:
            return FIELDS
        if url == dataart.LIST_URL:
            return pages[params["page"] - 1]
        if fail_detail:
            raise TimeoutError("slow")
        return detail
    return get, asked


def test_the_countries_named_are_asked_for_by_id_and_every_page_is_read():
    pages = [{"pagesTotal": 2, "page": 1, "items": [REMOTE, BANNER]},
             {"pagesTotal": 2, "page": 2, "items": [OFFICE, REMOTE]}]
    get, asked = fake(pages)
    records, note = dataart.fetch(["georgia"], get=get, pause=0)
    assert note is None
    lists = [p for url, p in asked if url == dataart.LIST_URL]
    assert lists == [{"pageSize": 200, "countries": "5742", "page": 1},
                     {"pageSize": 200, "countries": "5742", "page": 2}]
    assert [r["external_id"] for r in records] == ["dan00096", "hr00012"]   # the banner and the repeat out


def test_a_record_carries_the_countries_and_the_full_text():
    get, _ = fake([{"pagesTotal": 1, "items": [REMOTE]}])
    (record,), _ = dataart.fetch(["Georgia"], get=get, pause=0)
    assert record["title"] == "Senior Data Analyst with Product Analytics, Learning Platform"
    assert record["company"] == "DataArt" and record["url"].endswith("/dan00096")
    # "Georgia" alone reads as the US state in most vacancies
    assert record["location_raw"] == "Remote from: Armenia, country of Georgia"
    assert record["remote"] is True and record["workplace_type"] == "remote"
    assert record["tags"] == ["Data Analyst"] and record["salary_raw"] is None and record["posted_at"] is None
    text = record["description_text"]
    assert text.startswith("We are looking for a Senior Data Analyst.")
    assert "Technologies: Tableau, BigQuery" in text
    assert "Requirements:\n- 5+ years of analytics" in text and "Nice to have" not in text
    assert text.endswith("Hires from: Armenia, country of Georgia")


def test_remote_elsewhere_is_not_remote_from_the_country_asked_for():
    get, _ = fake([{"pagesTotal": 1, "items": [OFFICE]}])
    (record,), _ = dataart.fetch(["Georgia"], get=get, pause=0, details=False)
    assert record["remote"] is False and record["workplace_type"] is None
    assert record["location_raw"] == "country of Georgia, Bulgaria"
    assert record["description_text"] == "Tbilisi office."
    assert dataart.to_record(OFFICE)["remote"] is True   # no country asked for: any remote tag


def test_a_detail_that_fails_leaves_the_short_text_and_says_so():
    get, _ = fake([{"pagesTotal": 1, "items": [REMOTE]}], fail_detail=True)
    (record,), note = dataart.fetch(["Georgia"], get=get, pause=0)
    assert record["description_text"] == "This project focuses on product analytics."
    assert note == "dan00096: TimeoutError"


def test_a_country_the_site_does_not_list_fails_rather_than_fetching_everything():
    get, asked = fake([])
    records, note = dataart.fetch(["Sakartvelo"], get=get, pause=0)
    assert records == [] and "lists no country ['Sakartvelo']" in note
    assert all(url != dataart.LIST_URL for url, _ in asked)


def test_no_countries_fetches_every_vacancy_and_bad_items_are_counted():
    broken = {"contentType": 0, "title": "", "fullUrl": "x", "slug": "x1"}
    get, asked = fake([{"pagesTotal": 1, "items": [REMOTE, broken, "rubbish"]}])
    records, note = dataart.fetch(get=get, pause=0, details=False)
    assert [r["external_id"] for r in records] == ["dan00096"]
    assert note == "skipped 1 malformed"
    assert asked[0] == (dataart.LIST_URL, {"pageSize": 200, "page": 1})


@pytest.mark.parametrize("failure", [ConnectionError("down"), ValueError("not JSON")])
def test_a_list_that_fails_is_an_error_not_an_empty_success(failure):
    def get(url, params=None):
        raise failure
    records, note = dataart.fetch(get=get, pause=0)
    assert records == [] and note.startswith(type(failure).__name__)
