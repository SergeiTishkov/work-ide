"""
devitjobs after 2026-10-04: the UK board closed, and the US records are read
by the fields they actually carry.

The owner opened a devitjobs.uk vacancy and landed on
https://devitjobs.jobcopilot.com/signup?utm_source=dot_uk_old — every
devitjobs.uk address does that now, the API too. The US list
(devitjobs.com/api/jobsLight, 2 918 records that day) has no `url`: the page is
/jobs/<jobUrl>, the detail API takes `_id`, `workplace` states office / remote /
hybrid, and `redirectJobUrl` is where "Apply" goes.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import enrich_descriptions  # noqa: E402
import fetch_devitjobs  # noqa: E402
import normalize  # noqa: E402
import report  # noqa: E402
import score  # noqa: E402

from test_score import CRITERIA, PROFILE  # noqa: E402

# One record as the US API served it on 2026-10-04, trimmed to what is read.
ITEM = {
    "_id": "6abd7df4bb1ee58c947b149b",
    "jobUrl": "Acme-Senior-C-Developer",
    "name": "Senior C# Developer",
    "company": "Acme",
    "actualCity": "Austin",
    "cityCategory": "Austin",
    "expLevel": "Senior",
    "jobType": "Full-Time",
    "workplace": "office",
    "redirectJobUrl": "https://www.jobg8.com/Traffic.aspx?abc",
    "annualSalaryFrom": 120000,
    "annualSalaryTo": 150000,
    "currency": "USD",
}


def _record(**changes):
    return normalize.normalize_record(fetch_devitjobs._to_common_schema({**ITEM, **changes}, "us"))


def test_the_link_is_the_page_a_person_opens_and_the_id_is_kept_for_reading():
    record = _record()
    assert record["url"] == "https://devitjobs.com/jobs/Acme-Senior-C-Developer"
    assert record["read_url"] == "https://devitjobs.com/jobs/6abd7df4bb1ee58c947b149b"
    assert record["external_id"] == "us:6abd7df4bb1ee58c947b149b", "the id, so no vacancy is new again"


def test_the_boards_workplace_is_the_arrangement():
    assert _record()["workplace_type"] == "on-site"
    assert _record(workplace="hybrid")["workplace_type"] == "hybrid"
    remote = _record(workplace="remote")
    assert remote["workplace_type"] == "remote" and remote["remote"] is True
    assert _record(workplace=None)["workplace_type"] is None


def test_an_office_job_is_rejected_on_the_boards_word():
    vacancy = {**_record(), "description_text": "C#, ASP.NET, SQL Server. A legacy platform."}
    result = score.score_vacancy(vacancy, CRITERIA, PROFILE)
    assert result["classification"] == "rejected"
    assert any('states the work is "on-site"' in d for d in result["dealbreakers"])


def test_the_apply_target_is_shown_and_never_requested():
    record = _record()
    assert record["apply_url"] == "https://www.jobg8.com/Traffic.aspx?abc"
    items = report._apply_channel_items(record)
    assert any("jobg8.com: https://www.jobg8.com/Traffic.aspx?abc" in i for i in items)
    assert _record(redirectJobUrl=None)["apply_url"] is None


def test_the_closed_uk_board_is_reported_not_requested(monkeypatch):
    asked = []
    monkeypatch.setattr("requests.get", lambda url, **kw: asked.append(url))
    records, note = fetch_devitjobs.fetch(["uk"])
    assert records == [] and asked == []
    assert "uk: closed 2026-10-04" in note


def test_a_board_that_redirects_elsewhere_is_said_to(monkeypatch):
    class Moved:
        url = "https://devitjobs.jobcopilot.com/signup?utm_source=dot_us_old"

        def raise_for_status(self):
            pass

        def json(self):
            raise ValueError("an HTML page")

    monkeypatch.setattr("requests.get", lambda url, **kw: Moved())
    records, note = fetch_devitjobs.fetch(["us"])
    assert records == []
    assert note == "us: redirected to https://devitjobs.jobcopilot.com/signup?utm_source=dot_us_old"


def test_the_description_is_read_from_the_id_link(monkeypatch):
    asked = []

    def reader(url, timeout):
        asked.append(url)
        return {"description": "C# and ASP.NET", "workplace_type": None,
                "salary_raw": None, "closed": False}

    monkeypatch.setattr(enrich_descriptions, "_devitjobs_facts", reader)
    monkeypatch.setattr(enrich_descriptions.time, "sleep", lambda s: None)
    record = {**_record(), "computed": {"score": 50, "classification": "hot_lead"}}
    enrich_descriptions.enrich({"a": record})
    assert asked == ["https://devitjobs.com/jobs/6abd7df4bb1ee58c947b149b"]


def test_a_closed_site_rejects_its_vacancies_and_spares_its_sibling():
    criteria = {**CRITERIA, "closed_sources": {"devitjobs.uk": "the board closed"}}
    uk = {**_record(workplace="remote"), "url": "https://devitjobs.uk/jobs/6ab43e4a59a9dc5c1ffe09f7",
          "description_text": "C#, ASP.NET, SQL Server."}
    us = {**uk, "url": "https://devitjobs.com/jobs/Acme-Senior-C-Developer"}
    assert "source: the board closed" in score.score_vacancy(uk, criteria, PROFILE)["dealbreakers"]
    assert not any(d.startswith("source:") for d in score.score_vacancy(us, criteria, PROFILE)["dealbreakers"])
