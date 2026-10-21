"""
tools/fetch_justjoinit.py: justjoin.it's remote B2B offers through its API.

The items are trimmed from live answers of 2026-10-22. Load-bearing details
in them: for unit Hour and Day `from`/`to` hold a monthly figure and
fromPerUnit/toPerUnit the rate; the language code is "pl" on some offers and
"polish" on others; a b2b entry can have null figures; the board's own
conversion to USD sits beside the employer's figures.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import fetch_justjoinit as jj  # noqa: E402
import normalize  # noqa: E402


def b2b(lo, lo_unit, hi, hi_unit, currency, source, unit):
    return {"from": lo, "fromPerUnit": lo_unit, "to": hi, "toPerUnit": hi_unit, "currency": currency,
            "currencySource": source, "type": "b2b", "unit": unit, "gross": False}


CYCLAD = {"guid": "8e8a683b-854d-4b1d-8d6d-75cedf290c9e", "slug": "cyclad-sharepoint-administrator-0-5-fte--krakow-net",
          "title": "SharePoint Administrator (0.5 FTE)", "workplaceType": "remote", "workingTime": "part_time",
          "experienceLevel": "mid", "city": "Kraków", "companyName": "Cyclad",
          "publishedAt": "2026-10-21T16:05:08.8984955Z",
          "employmentTypes": [b2b(23520.0, 140.0, 28560.0, 170.0, "PLN", "original", "Hour"),
                              b2b(6013.0, 35.7909806728705, 7301.0, 43.46047653134275, "USD", "conversion", "Hour")],
          "requiredSkills": [{"name": "Scrum"}, {"name": "Waterfall"}, {"name": "PowerShell Scripting"}],
          "languages": [{"code": "en", "level": "B2"}],
          "applyUrl": "https://cyclad.recruitify.ai/job/767c2e0c-9326-49ec-a1f0-8934de6880ca?sourceId=37"}
ACT = {"guid": "8209a251-f2b5-4151-ac17-547a3bb4605f", "slug": "act-digital-fullstack-developer---net-angular-warszawa-net",
       "title": "Fullstack Developer - .Net + Angular", "workplaceType": "remote", "workingTime": "full_time",
       "experienceLevel": "mid", "city": "Warszawa", "companyName": "act digital",
       "publishedAt": "2026-10-21T14:05:05.9302424Z",
       "employmentTypes": [b2b(23520.0, 140.0, 26040.0, 155.0, "PLN", "original", "Hour"),
                           b2b(6098.0, 36.29764065335758, 6751.0, 40.18667358050303, "USD", "conversion", "Hour")],
       "requiredSkills": [{"name": "Angular"}, {"name": "C#"}, {"name": ".Net"}],
       "languages": [{"code": "pl", "level": "B2"}, {"code": "en", "level": "B2"}], "applyUrl": None}
IDEAMOTIVE = {"guid": "3be2e914-a1c9-4cf2-9a8e-a218813195c7", "slug": "ideamotive-senior-net-developer-warszawa-net",
              "title": "Senior .NET Developer", "workplaceType": "remote", "workingTime": "full_time",
              "experienceLevel": "senior", "city": "Warszawa", "companyName": "Ideamotive",
              "publishedAt": "2026-10-21T15:05:02.2004707Z",
              "employmentTypes": [b2b(16800.0, 100.0, 18480.0, 110.0, "PLN", "original", "Hour")],
              "requiredSkills": [{"name": ".Net"}], "languages": [{"code": "polish", "level": "C2"}]}
HOUSECALL = {"guid": "dd63f585-7c48-4f0e-bff3-72f93805c393", "slug": "housecall-pro-software-engineer-ii---poland-warszawa-net",
             "title": "Software Engineer II - Poland", "workplaceType": "remote", "workingTime": "full_time",
             "city": "Warszawa", "companyName": "Housecall Pro", "publishedAt": "2026-10-21T16:05:08.6917554Z",
             "employmentTypes": [b2b(5300.0, 5300.0, 6600.0, 6600.0, "USD", "original", "Month")],
             "requiredSkills": [{"name": "Go"}], "languages": []}
EMAGINE_DAY = {"guid": "12f972c5-b029-48b8-ab36-78209dd56177", "slug": "emagine-polska-senior-anaplan-model-builder-warszawa-net",
               "title": "Senior Anaplan Model Builder", "workplaceType": "remote", "workingTime": "full_time",
               "city": "Warszawa", "companyName": "emagine Polska", "publishedAt": "2026-10-21T15:05:03.5938571Z",
               "employmentTypes": [b2b(7793.0, 371.0853272207499, 8265.0, 393.5753470523105, "USD", "conversion", "Day"),
                                   b2b(6930.0, 330.0, 7350.0, 350.0, "EUR", "original", "Day")],
               "languages": [{"code": "en", "level": "B2"}]}
EMAGINE_BLANK = {"guid": "81088ecf-6c58-4153-a76c-147b617a31a1",
                 "slug": "emagine-polska-senior-net-backend-engineer-warszawa-net-12173fc9",
                 "title": "Senior .Net Backend Engineer", "workplaceType": "remote", "workingTime": "full_time",
                 "city": "Warszawa", "companyName": "emagine Polska", "publishedAt": "2026-10-21T15:05:03.273664Z",
                 "employmentTypes": [b2b(None, None, None, None, "USD", "conversion", "month"),
                                     b2b(None, None, None, None, "PLN", "original", "month")],
                 "languages": [{"code": "en", "level": "C1"}]}
CYCLAD_DETAIL = {"slug": CYCLAD["slug"], "countryCode": "PL", "companyUrl": "", "isActive": True, "city": "Kraków",
                 "languages": [{"code": "en", "level": "B2"}],
                 "body": "<p>At Cyclad, we work with top international IT companies.</p><ul>"
                         "<li><p>Office location: Kraków, Poland</p></li><li><p>Work mode: Remote</p></li>"
                         "<li><p>Only candidates with citizenship in the European Union and residence in Poland</p>"
                         "</li></ul>"}


def page(items, total, start, next_cursor):
    return {"data": items, "meta": {"from": start, "totalItems": total,
                                    "prev": {"cursor": None, "itemsCount": 100},
                                    "next": {"cursor": next_cursor, "itemsCount": 100}}}


def fake(pages, details=None, fail=()):
    """pages: {(category, from): payload}; details: {slug: detail}; fail: slugs or (category, from) that raise."""
    asked = []

    def get(url, params=None):
        asked.append((url, dict(params or {})))
        if url == jj.LIST_URL:
            key = (params["categories"], params["from"])
            if key in fail:
                raise ConnectionError("down")
            return pages[key]
        slug = url.rsplit("/", 1)[-1]
        if slug in fail or details is None or slug not in details:
            raise TimeoutError("slow")
        return details[slug]
    return get, asked


def test_pages_are_read_by_the_cursor_until_the_total_with_the_filters(monkeypatch):
    monkeypatch.setattr(jj, "ITEMS_COUNT", 2)
    get, asked = fake({("net", 0): page([CYCLAD, ACT], 3, 0, 2), ("net", 2): page([IDEAMOTIVE], 3, 2, None)})
    counts = {}
    records, note = jj.fetch(details=False, get=get, pause=0, counts=counts)
    assert note is None
    assert [p for _, p in asked] == [
        {"categories": "net", "remoteWorkOptions": "remote", "employmentTypes": "b2b", "itemsCount": 2, "from": 0},
        {"categories": "net", "remoteWorkOptions": "remote", "employmentTypes": "b2b", "itemsCount": 2, "from": 2}]
    assert [r["external_id"][:8] for r in records] == ["8e8a683b", "8209a251", "3be2e914"]
    assert counts == {"found": 3, "kept": 3, "polish": 2}


def test_a_page_that_reaches_the_total_is_the_last_even_with_a_cursor():
    get, asked = fake({("net", 0): page([CYCLAD, ACT], 2, 0, 100)})
    records, note = jj.fetch(details=False, get=get, pause=0)
    assert len(records) == 2 and len(asked) == 1 and note is None


def test_each_category_is_listed_and_an_offer_in_two_is_kept_once():
    get, asked = fake({("net", 0): page([CYCLAD, ACT], 2, 0, None), ("architecture", 0): page([ACT], 1, 0, None)})
    records, note = jj.fetch(["net", "architecture"], None, "b2b", details=False, get=get, pause=0)
    assert [p["categories"] for _, p in asked] == ["net", "architecture"]
    assert "remoteWorkOptions" not in asked[0][1]          # none: every work option
    assert len(records) == 2 and note is None


def test_a_record_carries_the_detail_text_the_rate_and_the_terms():
    get, asked = fake({("net", 0): page([CYCLAD], 1, 0, None)}, details={CYCLAD["slug"]: CYCLAD_DETAIL})
    (record,), note = jj.fetch(get=get, pause=0)
    assert note is None and asked[-1][0] == f"https://justjoin.it/api/candidate-api/offers/{CYCLAD['slug']}"
    assert record["url"] == "https://justjoin.it/job-offer/cyclad-sharepoint-administrator-0-5-fte--krakow-net"
    assert record["company"] == "Cyclad" and record["company_url"] is None
    assert record["location_raw"] == "Remote; office in Kraków, Poland"
    assert " only" not in record["location_raw"]
    assert record["remote"] is True and record["workplace_type"] == "remote"
    assert record["salary_raw"] == "140-170 PLN/hour net (B2B); justjoin.it's conversion: $36/hour to $43/hour"
    text = record["description_text"]
    assert text.startswith("Languages: English skills required (English B2).")
    assert "residence in Poland" in text and text.endswith("Level: mid")
    canonical = normalize.normalize_record(record)
    assert canonical["employment_types"] == ["part-time", "contract"]
    assert canonical["posted_at"] == "2026-10-21T16:05:08.8984955Z"


@pytest.mark.parametrize("item, line", [
    (ACT, "Languages: Polish and English skills required (Polish B2, English B2)."),
    (IDEAMOTIVE, "Languages: Polish skills required (Polish C2)."),     # "polish" as a code
    (HOUSECALL, ""),
])
def test_the_language_line(item, line):
    assert jj.language_line(item) == line
    assert jj.needs_polish(item) is ("Polish" in line)


@pytest.mark.parametrize("item, expected", [
    (ACT, "140-155 PLN/hour net (B2B); justjoin.it's conversion: $36/hour to $40/hour"),
    (IDEAMOTIVE, "100-110 PLN/hour net (B2B)"),                          # no conversion given
    (HOUSECALL, "$5,300/month to $6,600/month net (B2B)"),
    # a day rate's dollars as an hour: "/day" is not a unit the scoring reads
    (EMAGINE_DAY, "330-350 EUR/day net (B2B); justjoin.it's conversion: $46/hour to $49/hour at 8 hours a day"),
    (EMAGINE_BLANK, None),                                               # null figures
])
def test_the_rate(item, expected):
    assert jj.salary(item) == expected


def test_the_scoring_reads_the_dollars_of_a_rate():
    import score
    import common

    amounts = score._extract_amounts(common.normalize_for_matching(jj.salary(ACT)))
    assert sorted(h for _, h, _ in amounts if h) == [36.0, 40.0]
    monthly = score._extract_amounts(common.normalize_for_matching(jj.salary(HOUSECALL)))
    assert sorted(m for _, _, m in monthly if m) == [5300.0, 6600.0]


def test_a_detail_that_fails_leaves_the_list_fields_and_says_so():
    get, _ = fake({("net", 0): page([ACT], 1, 0, None)})
    (record,), note = jj.fetch(get=get, pause=0)
    assert note == f"{ACT['slug']}: TimeoutError"
    assert record["description_text"] == ("Languages: Polish and English skills required (Polish B2, English B2)."
                                          "\n\nRequired skills: Angular, C#, .Net\n\nLevel: mid")
    assert record["location_raw"] == "Remote; office in Warszawa"     # the country comes with the detail


def test_an_inactive_offer_is_left_out():
    get, _ = fake({("net", 0): page([CYCLAD], 1, 0, None)},
                  details={CYCLAD["slug"]: {**CYCLAD_DETAIL, "isActive": False}})
    assert jj.fetch(get=get, pause=0) == ([], "1 inactive on their detail page")


def test_a_failed_first_page_is_an_error_not_an_empty_success():
    get, _ = fake({}, fail={("net", 0)})
    assert jj.fetch(get=get, pause=0) == ([], "every listing failed: net: ConnectionError")


def test_an_answer_without_a_data_list_is_a_failed_listing():
    def get(url, params=None):
        return {"title": "Entity not found", "status": 404}
    assert jj.fetch(get=get, pause=0) == ([], "every listing failed: net: ValueError")


def test_a_later_page_that_fails_keeps_what_came_and_says_so(monkeypatch):
    monkeypatch.setattr(jj, "ITEMS_COUNT", 2)
    get, _ = fake({("net", 0): page([CYCLAD, ACT], 4, 0, 2)}, fail={("net", 2)})
    records, note = jj.fetch(details=False, get=get, pause=0)
    assert len(records) == 2 and note == "net from=2: ConnectionError"


def test_malformed_items_are_counted():
    nameless = {**ACT, "guid": "x", "companyName": ""}
    get, _ = fake({("net", 0): page([CYCLAD, nameless, "rubbish", {"title": "no guid"}], 4, 0, None)})
    records, note = jj.fetch(details=False, get=get, pause=0)
    assert [r["external_id"][:8] for r in records] == ["8e8a683b"] and note == "skipped 1 malformed"
