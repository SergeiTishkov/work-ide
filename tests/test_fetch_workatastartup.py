"""
tools/fetch_workatastartup.py: Y Combinator's Work at a Startup, by keyword.

The search hits are trimmed from live answers of 2026-10-21, the location
strings exactly as served. The posting page is reduced to its data-page
attribute, HTML-escaped the way the site writes it.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import fetch_workatastartup as waas  # noqa: E402
import normalize  # noqa: E402

DILL = {"id": 113898, "title": "AI Engineer / Lead", "jobType": "Full-time", "location": "US / Remote (US)",
        "roleType": "AI engineer", "salary": "$160K - $200K", "companyName": "Dill", "companySlug": "dill",
        "companyBatch": "W23", "companyOneLiner": "Dill helps construction suppliers automate accounts receivable"}
PROJECTPRO = {"id": 76665, "title": " Looking for an LLM Developer with knowledge of Agentic AI Frameworks",
              "jobType": "Contract", "location": "Remote", "roleType": "Machine learning",
              "salary": "$500 - $1.4K", "companyName": "ProjectPro", "companyOneLiner": "Project-based learning"}
LIGHTDASH = {"id": 42246, "title": "Full Stack Software Engineer", "jobType": "Full-time",
             "location": "GB / ES / GE / US / Remote (GB; ES; PT; IT; DE; FR; GE; US)", "roleType": "Full stack",
             "salary": "$100K - $170K", "companyName": "Lightdash",
             "companyOneLiner": "The open source Looker alternative "}
OFFICE = {"id": 48056, "title": "Senior Software Engineer", "jobType": "Full-time",
          "location": "Redwood City, CA", "roleType": "Full stack", "salary": None,
          "companyName": "DreamCraft Entertainment, Inc.", "companyOneLiner": "Platform for video games."}
JOB = {"id": "76665", "title": PROJECTPRO["title"], "salaryRange": "$500 - $1.4K", "location": "Remote",
       "jobType": "Contract", "sponsorsVisa": "Will not sponsor", "minExperience": "3+ years",
       "descriptionHtml": "<p><strong>ProjectPro</strong> needs an LLM developer.</p>\n<ul><li>CrewAI</li></ul>"}


def page(job):
    data = {"component": "jobs/public/pages/JobDetailV2Page", "url": f"/jobs/{job['id']}",
            "props": {"job": job, "company": {"name": "ProjectPro"}}}
    return f'<html><body><div data-page="{html.escape(json.dumps(data))}"></div></body></html>'


def fake(results, pages=None, fail=()):
    """results: {keyword: [hits]}; pages: {id: html}; fail: keywords whose search raises."""
    asked = []

    def get(url, params=None):
        asked.append((url, dict(params or {})))
        if url == waas.SEARCH_URL:
            if params["q"] in fail:
                raise ConnectionError("down")
            return {"jobs": results[params["q"]]}
        job_id = int(url.rsplit("/", 1)[-1])
        if pages is None or job_id not in pages:
            raise TimeoutError("slow")
        return pages[job_id]
    return get, asked


def test_each_keyword_is_searched_and_a_posting_found_twice_is_kept_once():
    get, asked = fake({"llm": [PROJECTPRO, DILL], "remote": [PROJECTPRO, LIGHTDASH, OFFICE]})
    counts = {}
    records, note = waas.fetch(["llm", "remote"], ["GE"], details=False, get=get, pause=0, counts=counts)
    assert asked == [(waas.SEARCH_URL, {"q": "llm"}), (waas.SEARCH_URL, {"q": "remote"})]
    assert [r["external_id"] for r in records] == ["76665", "42246"]   # Remote (US) and the office out
    assert counts == {"found": 4, "kept": 2} and note is None


def test_the_default_keywords_are_searched_when_none_are_given():
    get, asked = fake({k: [] for k in waas.DEFAULT_KEYWORDS})
    assert waas.fetch(get=get, pause=0) == ([], None)
    assert [p["q"] for _, p in asked] == waas.DEFAULT_KEYWORDS


@pytest.mark.parametrize("location, countries, kept", [
    ("Remote", ["GE"], True),
    ("Chiyoda City, Tokyo, JP / San Francisco, CA, US / Remote", ["GE"], True),
    ("Atlanta, GA, US / Remote", ["GE"], True),        # bare Remote beside an office
    ("US / Remote (US)", ["GE"], False),
    ("KZ / Remote (KZ)", ["GE"], False),
    ("Remote (SK, CA; Saskatchewan, CA)", ["GE"], False),   # two entries, one country
    ("Remote (United States)", ["GE"], False),
    # the bracketed list decides over a plain part beside it
    ("Remote / Remote (US)", ["GE"], False),
    ("Remote - US / Remote (US)", ["GE"], False),
    ("Remote - United Kingdom", ["GE"], False),
    ("Remote - UK or Europe / Remote (US)", ["GE"], True),   # the employer's own words name no one country
    ("United States / Remote", ["GE"], True),
    ("Remote (GE)", ["GE"], True),
    ("Remote (GE)", ["Georgia"], True),
    ("PL / UA / Remote (PL; UA)", ["GE"], True),        # several countries: the scoring reads them
    ("Calgary, AB / Cape Town, WC, ZA / Remote (Calgary, AB, CA; Cape Town, WC, ZA)", ["GE"], True),
    ("US / Remote (US)", None, True),                    # no residency named: every remote posting
    ("Redwood City, CA", None, False),
    ("", ["GE"], False),
])
def test_the_location_rule(location, countries, kept):
    assert waas.wanted(location, countries) is kept


def test_a_record_carries_the_page_text_and_the_board_fields():
    get, asked = fake({"llm": [PROJECTPRO]}, pages={76665: page(JOB)})
    (record,), note = waas.fetch(["llm"], ["GE"], get=get, pause=0)
    assert note is None and asked[-1] == ("https://www.workatastartup.com/jobs/76665", {})
    assert record["title"] == "Looking for an LLM Developer with knowledge of Agentic AI Frameworks"
    assert record["company"] == "ProjectPro" and record["url"] == "https://www.workatastartup.com/jobs/76665"
    assert record["location_raw"] == "Remote" and record["remote"] is True and record["workplace_type"] == "remote"
    assert record["tags"] == ["Machine learning"] and record["salary_raw"] == "$500 - $1.4K"
    assert record["posted_at"] is None
    assert record["description_text"].startswith("ProjectPro needs an LLM developer.")
    assert "CrewAI" in record["description_text"]
    assert record["description_text"].endswith("Visa: Will not sponsor")
    canonical = normalize.normalize_record(record)
    assert canonical["employment_types"] == ["contract"]


def test_a_page_that_fails_leaves_the_one_liner_and_says_so():
    get, _ = fake({"remote": [LIGHTDASH, PROJECTPRO]}, pages={76665: "<html>no data</html>"})
    records, note = waas.fetch(["remote"], ["GE"], get=get, pause=0)
    assert [r["description_text"] for r in records] == ["The open source Looker alternative",
                                                        "Project-based learning"]
    assert note == "42246: TimeoutError; 76665: ValueError"


def test_a_failed_search_is_named_and_the_others_still_count():
    get, _ = fake({"llm": [PROJECTPRO]}, fail={"c#"})
    records, note = waas.fetch(["c#", "llm"], details=False, get=get, pause=0)
    assert [r["external_id"] for r in records] == ["76665"]
    assert note == "searches failed: c#: ConnectionError"


def test_every_search_failing_is_an_error_not_an_empty_success():
    get, _ = fake({}, fail={"c#", "llm"})
    records, note = waas.fetch(["c#", "llm"], get=get, pause=0)
    assert records == [] and note == "every search failed: c#: ConnectionError, llm: ConnectionError"


def test_an_answer_without_a_jobs_list_is_a_failed_search():
    def get(url, params=None):
        return {"error": "Not Acceptable"}
    records, note = waas.fetch(["llm"], get=get, pause=0)
    assert records == [] and note == "every search failed: llm: ValueError"


def test_malformed_hits_are_counted():
    nameless = {**PROJECTPRO, "id": 1, "companyName": ""}
    get, _ = fake({"remote": [PROJECTPRO, nameless, "rubbish", {"title": "no id"}]})
    records, note = waas.fetch(["remote"], details=False, get=get, pause=0)
    assert [r["external_id"] for r in records] == ["76665"] and note == "skipped 1 malformed"
