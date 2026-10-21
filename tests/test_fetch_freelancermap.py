"""
tools/fetch_freelancermap.py: freelancermap.de's project search.

The projects are trimmed from the live answer of /project/search/ajax of
2026-10-22 (descriptions cut short). Load-bearing details in them: `company`
and `poster.company` can both be null, `city` can be "Remote/Oldenburg",
`budget` is null, and the answer's currentPage stays 1 whatever page is
asked.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import fetch_freelancermap as fm  # noqa: E402
import normalize  # noqa: E402

GERMANY = {"id": 1, "iso2": "DE", "nameEn": "Germany"}
REMOTE_CONTRACT = {"type": "contracting", "remoteInPercent": 100}
KEIL = {"id": 3057517, "slug": "c-net-developer-m-f-d-november-6-months",
        "title": "C# / .NET Developer  (m/f/d) – November – 6 months",
        "company": "Keil Business Solutions GmbH", "poster": {"company": "Keil Business Solutions GmbH"},
        "city": "frankfurt", "country": GERMANY, "created": "2026-10-06T22:30:43+02:00",
        "description": '<div class="ql-editor"><div><span style="color: rgb(0, 0, 0);">Keil Business Solutions '
                       'GmbH is an innovative IT services provider.</span></div><div><br></div><div><strong>'
                       'Tasks /Requirements:</strong></div><div><span> -Strong development &amp; programming '
                       'experience (at least 5-10 years) with deep C# and Microsoft .NET Framework knowledge'
                       '</span></div></div>',
        "beginningText": None, "durationText": None, "budget": None, "contractType": "CONTRACT",
        "projectContractType": REMOTE_CONTRACT,
        "skills": [{"de": "Banking", "en": "Banking", "url": "/projekte/banking"}]}
NAMELESS = {"id": 3060374, "slug": "senior-windows-net-aws-devops-und-platform-engineer-windows-server-migration",
            "title": "Senior Windows / .NET / AWS DevOps & Platform Engineer – Windows Server Migration",
            "company": None, "poster": {"company": None}, "city": "Bei Nürnberg", "country": GERMANY,
            "created": "2026-10-13T19:09:41+02:00",
            "description": "<div><strong>Projektbeschreibung</strong></div><div>Für eine etablierte deutsche "
                           "B2B-SaaS-Plattform suchen wir einen erfahrenen Senior DevOps / Platform Engineer.</div>",
            "beginningText": "ab sofort", "durationText": None, "budget": None, "contractType": "CONTRACT",
            "projectContractType": REMOTE_CONTRACT, "skills": []}
SOLCOM = {"id": 3061148, "slug": "1084432-d365-crm-entwickler", "title": "1084432 D365 CRM Entwickler",
          "company": "SOLCOM GmbH", "poster": {"company": "SOLCOM GmbH"}, "city": "Remote/Oldenburg",
          "country": GERMANY, "created": "2026-10-15T11:41:05+02:00",
          "description": "<strong>Aufgaben:</strong><br /><p>Aktuell sind wir auf der Suche nach einem D365 CRM "
                         "Entwickler.</p>",
          "beginningText": "09.11.2026", "durationText": "3 MM+", "budget": [], "contractType": None,
          "projectContractType": REMOTE_CONTRACT, "skills": []}


def answer(projects, count=96):
    return {"searchMetaBag": {}, "projects": projects, "topProjects": [], "currentPage": 1,
            "pagination": {"content": "<div class='paginator'></div>"}, "count": count, "countWithHidden": count}


def fake(results, fail=()):
    """results: {(query, sort): [projects]}; fail: (query, sort) pairs that raise."""
    asked = []

    def get(url, params=None):
        asked.append((url, dict(params or {})))
        key = (params["query"], params["sort"])
        if key in fail:
            raise ConnectionError("down")
        return answer(results.get(key, []))
    return get, asked


def test_each_query_is_asked_newest_and_most_relevant_and_merged_on_id():
    get, asked = fake({(".net", 1): [KEIL, NAMELESS], (".net", 2): [SOLCOM, KEIL], ("c#", 1): [KEIL]})
    counts = {}
    records, note = fm.fetch([".net", "c#"], get=get, pause=0, counts=counts)
    assert note is None
    assert [(p["query"], p["sort"]) for _, p in asked] == [(".net", 1), (".net", 2), ("c#", 1), ("c#", 2)]
    assert asked[0] == (fm.SEARCH_URL, {"query": ".net", "sort": 1, "countries": "",
                                        "remoteInPercent[0]": 100, "projectContractTypes[0]": "contracting"})
    assert [r["external_id"] for r in records] == ["3057517", "3060374", "3061148"]
    assert counts == {"found": 3, "kept": 3, "totals": {".net": 96, "c#": 96}}


def test_the_default_queries_are_asked_when_none_are_given():
    get, asked = fake({})
    assert fm.fetch(get=get, pause=0) == ([], None)
    assert [p["query"] for _, p in asked][::2] == fm.DEFAULT_QUERIES


def test_filters_can_be_dropped():
    params = fm.search_params("blazor", 2, None, None)
    assert params == {"query": "blazor", "sort": 2, "countries": ""}


def test_a_record_carries_the_text_the_place_and_the_contract():
    get, _ = fake({(".net", 1): [KEIL]})
    (record,), note = fm.fetch([".net"], get=get, pause=0)
    assert note is None
    assert record["url"] == "https://www.freelancermap.de/projekt/c-net-developer-m-f-d-november-6-months"
    assert record["company"] == "Keil Business Solutions GmbH"
    assert record["location_raw"] == "100% remote; client in frankfurt, Germany"
    assert " only" not in record["location_raw"]
    assert record["remote"] is True and record["workplace_type"] == "remote"
    assert record["tags"] == ["Banking"] and record["salary_raw"] is None
    assert record["description_text"].startswith("Keil Business Solutions GmbH is an innovative IT services provider.")
    assert "programming experience" in record["description_text"]
    canonical = normalize.normalize_record(record)
    assert canonical["employment_types"] == ["contract"]
    assert canonical["posted_at"] == "2026-10-06T22:30:43+02:00"


def test_start_and_duration_follow_the_text_and_a_bare_remote_city_is_dropped():
    record = fm.to_record(SOLCOM)
    assert record["description_text"].endswith("Start: 09.11.2026\n\nDuration: 3 MM+")
    assert record["location_raw"] == "100% remote; client in Remote/Oldenburg, Germany"
    assert record["salary_raw"] is None                                   # an empty budget list
    assert fm.location({**SOLCOM, "city": "Remote"}) == "100% remote; client in Germany"
    assert fm.location({"projectContractType": {"type": "contracting", "remoteInPercent": 80}}) == "80% remote"


def test_a_project_without_a_company_gets_the_fallback():
    assert fm.to_record(NAMELESS)["company"] == "freelancermap client"
    assert fm.to_record({**NAMELESS, "poster": {"company": "Poster GmbH"}})["company"] == "Poster GmbH"


def test_a_partly_remote_project_is_hybrid():
    record = fm.to_record({**KEIL, "projectContractType": {"type": "contracting", "remoteInPercent": 60}})
    assert record["remote"] is False and record["workplace_type"] == "hybrid"
    assert record["location_raw"] == "60% remote; client in frankfurt, Germany"


def test_a_failed_search_is_named_and_the_others_still_count():
    get, _ = fake({(".net", 2): [KEIL]}, fail={(".net", 1)})
    records, note = fm.fetch([".net"], get=get, pause=0)
    assert [r["external_id"] for r in records] == ["3057517"]
    assert note == "searches failed: .net sort=1: ConnectionError"


def test_every_search_failing_is_an_error_not_an_empty_success():
    get, _ = fake({}, fail={(".net", 1), (".net", 2)})
    records, note = fm.fetch([".net"], get=get, pause=0)
    assert records == [] and note == ("every search failed: .net sort=1: ConnectionError, "
                                      ".net sort=2: ConnectionError")


def test_an_answer_without_a_projects_list_is_a_failed_search():
    def get(url, params=None):
        return {"__error": {"status": 500}}
    records, note = fm.fetch([".net"], get=get, pause=0)
    assert records == [] and note.startswith("every search failed: .net sort=1: ValueError")


def test_malformed_projects_are_counted():
    get, _ = fake({(".net", 1): [KEIL, {"id": 5, "title": "no slug"}, "rubbish", {"title": "no id"}]})
    records, note = fm.fetch([".net"], get=get, pause=0)
    assert [r["external_id"] for r in records] == ["3057517"] and note == "skipped 1 malformed"
