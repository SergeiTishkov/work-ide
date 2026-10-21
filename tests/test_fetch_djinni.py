"""
tools/fetch_djinni.py: djinni.co's remote search, read from the JSON-LD
JobPosting list each results page carries.

The .NET postings are trimmed from the live page of
/jobs/?primary_keyword=.NET&employment=remote&country=GEO of 2026-10-22
(descriptions cut short); the Ukraine, Europe and filler postings follow the
shapes of the survey of 2026-10-21. Load-bearing details: countries come as
ISO alpha-3 ("GEO"), a region comes as addressRegion, and once the search's
own results run out the board pads the pages with postings of other
categories.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import fetch_djinni as dj  # noqa: E402
import normalize  # noqa: E402
import score  # noqa: E402


def _countries(*codes):
    return [{"@type": "AdministrativeArea", "address": {"@type": "PostalAddress", "addressCountry": c}}
            for c in codes]


def _posting(identifier, title, category, company="Example", countries=(), **extra):
    posting = {"@context": "https://schema.org/", "@type": "JobPosting", "identifier": identifier,
               "title": title, "category": category, "datePosted": "2026-10-06T12:41:29.041719",
               "description": "A posting.", "employmentType": "FULL_TIME",
               "hiringOrganization": {"@type": "Organization", "name": company},
               "jobLocationType": "TELECOMMUTE", "url": f"https://djinni.co/jobs/{identifier}-x/"}
    if countries:
        posting["applicantLocationRequirements"] = _countries(*countries)
    posting.update(extra)
    return posting


CODEHARBOR = _posting(
    851783, ".NET Developer", ".NET", "codeharbor.dev", ("ARM", "AZE", "GEO", "KAZ", "KGZ"),
    description="We're looking for an advanced Middle or Senior .Net engineer for a huge legacy project in the "
                "Healthcare domain.",
    hiringOrganization={"@type": "Organization", "name": "codeharbor.dev", "sameAs": "https://codeharbor.dev/"})
ADAPTIQ = _posting(
    851289, "Senior .NET / C# Software Engineer (Windows Systems)", ".NET", "Adaptiq", ("POL", "GEO", "ROU", "ARM"),
    datePosted="2026-10-02T12:48:33.645032",
    description="Adaptiq is looking for a Senior Windows Engineer to join an international product team.",
    baseSalary={"@type": "MonetaryAmount", "currency": "USD",
                "value": {"@type": "QuantitativeValue", "maxValue": 6500, "minValue": 6000, "unitText": "MONTH"}})
WINDOWS = _posting(851287, "Senior Windows Engineer (C#)", "Desktop", "Adaptiq")
UKRAINE = _posting(850100, "Middle .NET Developer", ".NET", "Kyiv Soft", ("UKR",))
EUROPE = _posting(850200, "Senior .NET Engineer", ".NET", "Euro Soft",
                  applicantLocationRequirements=[{"@type": "AdministrativeArea",
                                                  "address": {"@type": "PostalAddress", "addressRegion": "Europe"}}])
FULLSTACK = _posting(850300, "Fullstack Engineer", "Fullstack", "Mixed Soft",
                     description="Our backend is ASP.NET Core and the front end is React.")
SALES = _posting(840001, "Sales Manager", "Sales Manager", "Sales Co", description="Sell our services.")
DESIGN = _posting(840002, "Product Designer", "Design", "Design Co", description="Figma.")


def page(*items):
    """A results page with the JSON-LD list, as djinni writes it."""
    return ("<html><head><script type=\"application/ld+json\">" + json.dumps(list(items))
            + "</script></head><body></body></html>")


def fake(pages, fail=()):
    """pages: {(label, n): html}; label is the query's country, region or
    "plain". fail: (label, n) pairs that raise."""
    asked = []

    def get(url, params=None):
        params = dict(params or {})
        asked.append(params)
        key = (params.get("country") or params.get("region") or "plain", params["page"])
        if key in fail:
            raise ConnectionError("down")
        return pages.get(key, page(SALES, DESIGN))
    return get, asked


def test_the_searches_are_plain_then_the_country_then_worldwide():
    assert dj.searches() == [{"primary_keyword": ".NET", "employment": "remote"},
                             {"primary_keyword": ".NET", "employment": "remote", "region": "worldwide"}]
    assert dj.searches("C#", "geo", worldwide=False) == [
        {"primary_keyword": "C#", "employment": "remote"},
        {"primary_keyword": "C#", "employment": "remote", "country": "GEO"}]


def test_paging_stops_at_the_first_page_without_a_result_of_the_search():
    get, asked = fake({("plain", 1): page(CODEHARBOR, ADAPTIQ), ("plain", 2): page(WINDOWS, SALES),
                       ("plain", 3): page(FULLSTACK, SALES, DESIGN)})
    counts = {}
    records, note = dj.fetch(worldwide=False, get=get, pause=0, counts=counts)
    assert note is None
    assert [p["page"] for p in asked] == [1, 2, 3]
    # the filler page still gives up a posting whose text names the stack
    assert [r["external_id"] for r in records] == ["851783", "851289", "851287", "850300"]
    assert counts == {"kept": 4, "unrelated": 2}       # a posting seen on an earlier page counts once


def test_a_posting_already_seen_does_not_keep_the_paging_going():
    get, asked = fake({("plain", 1): page(CODEHARBOR), ("GEO", 1): page(CODEHARBOR, SALES)})
    records, note = dj.fetch(country="GEO", worldwide=False, get=get, pause=0)
    assert [(p.get("country"), p["page"]) for p in asked] == [(None, 1), (None, 2), ("GEO", 1)]
    assert [r["external_id"] for r in records] == ["851783"] and note is None


def test_the_title_or_the_category_decides_the_paging_and_the_text_what_is_kept():
    assert dj.in_results(WINDOWS) and dj.in_results(UKRAINE)
    assert not dj.in_results(FULLSTACK) and dj.on_stack(FULLSTACK)
    assert not dj.on_stack(SALES)
    assert not dj.on_stack(_posting(1, "Network Engineer", "Sysadmin", description="Cisco .network gear"))
    assert dj.on_stack(_posting(2, "Engineer", "Other", description="dotnet services"))


def test_a_record_carries_the_place_the_salary_and_the_contract():
    record = dj.to_record(ADAPTIQ, "GEO")
    assert record["external_id"] == "851289"
    assert record["url"] == "https://djinni.co/jobs/851289-x/"
    assert record["location_raw"] == "Remote; candidates in Poland, country of Georgia, Romania, Armenia"
    assert record["salary_raw"] == "$6,000/month to $6,500/month"
    assert record["remote"] is True and record["workplace_type"] == "remote"
    assert record["tags"] == [".NET"]
    canonical = normalize.normalize_record(record)
    assert canonical["employment_types"] == ["full-time"]
    assert canonical["posted_at"] == "2026-10-02T12:48:33.645032"
    assert dj.to_record(CODEHARBOR)["company_url"] == "https://codeharbor.dev/"


def test_the_monthly_salary_is_read_by_the_scoring():
    assert score._extract_amounts(dj.salary(ADAPTIQ))
    assert dj.salary({"baseSalary": {"currency": "EUR", "value": {"minValue": 4000, "maxValue": 5000,
                                                                   "unitText": "MONTH"}}}) == "4,000-5,000 EUR/month"
    assert dj.salary({"baseSalary": {"currency": "USD", "value": {"value": 90000, "unitText": "YEAR"}}}) == "$90,000/year"
    assert dj.salary({"baseSalary": {"currency": "USD", "value": {}}}) is None
    assert dj.salary(CODEHARBOR) is None


def test_a_country_list_without_the_residency_ends_in_only():
    assert dj.location(UKRAINE, "GEO") == "Remote; candidates in Ukraine only"
    assert dj.location(UKRAINE) == "Remote; candidates in Ukraine"
    assert dj.location(CODEHARBOR, "GEO") == ("Remote; candidates in Armenia, Azerbaijan, country of Georgia, "
                                              "Kazakhstan, Kyrgyzstan")
    assert dj.location(EUROPE, "GEO") == "Remote; candidates in Europe"
    assert dj.location(SALES, "GEO") == "Remote"
    assert dj.location(_posting(3, "x", ".NET", countries=("UA", "PL")), "GE") == "Remote; candidates in Ukraine, Poland only"


def test_the_scoring_reads_the_place_as_written():
    criteria, profile = score.load_criteria(), score.load_profile()

    def eligibility(posting):
        return score.score_vacancy(normalize.normalize_record(dj.to_record(posting, "GEO")),
                                   criteria, profile)["residency_eligibility"]
    assert eligibility(UKRAINE) == "no"
    assert eligibility(CODEHARBOR) == "confirmed"


def test_a_failed_later_page_ends_that_search_with_a_note():
    get, _ = fake({("plain", 1): page(CODEHARBOR), ("worldwide", 1): page(ADAPTIQ)}, fail={("plain", 2)})
    records, note = dj.fetch(get=get, pause=0)
    assert [r["external_id"] for r in records] == ["851783", "851289"]
    assert note == "plain page 2: ConnectionError"


def test_a_failed_search_is_named_and_the_others_still_count():
    get, _ = fake({("worldwide", 1): page(ADAPTIQ)}, fail={("plain", 1)})
    records, note = dj.fetch(get=get, pause=0)
    assert [r["external_id"] for r in records] == ["851289"]
    assert note == "searches failed: plain: ConnectionError"


def test_every_search_failing_is_an_error_not_an_empty_success():
    get, _ = fake({}, fail={("plain", 1), ("GEO", 1), ("worldwide", 1)})
    records, note = dj.fetch(country="GEO", get=get, pause=0)
    assert records == [] and note == ("every search failed: plain: ConnectionError, GEO: ConnectionError, "
                                      "worldwide: ConnectionError")


def test_the_paging_has_a_ceiling(monkeypatch):
    monkeypatch.setattr(dj, "MAX_PAGES", 2)
    get, _ = fake({("plain", 1): page(CODEHARBOR), ("plain", 2): page(ADAPTIQ)})
    records, note = dj.fetch(worldwide=False, get=get, pause=0)
    assert len(records) == 2 and note == "plain stopped after 2 pages"


def test_malformed_blocks_and_postings_are_skipped():
    html_text = ('<script type="application/ld+json">{not json</script>'
                 '<script type="application/ld+json">{"@graph": [' + json.dumps(CODEHARBOR) + ']}</script>'
                 '<script type="application/ld+json">' + json.dumps({"@type": "Organization"}) + '</script>')
    assert [p["identifier"] for p in dj.postings(html_text)] == [851783]
    broken = {**UKRAINE, "hiringOrganization": {}}
    get, _ = fake({("plain", 1): page(CODEHARBOR, broken)})
    records, note = dj.fetch(worldwide=False, get=get, pause=0)
    assert [r["external_id"] for r in records] == ["851783"] and note == "skipped 1 malformed"
