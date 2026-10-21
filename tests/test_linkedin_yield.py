"""tools/linkedin_yield.py: what each LinkedIn search brings to the shortlist (task 0050)."""
import linkedin_yield


def vacancy(found_by, classification="hot_lead", source="linkedin", **extra):
    return {"source": source, "found_by": found_by, "computed": {"classification": classification}, **extra}


BASE = [
    vacancy(["C# @ France"]),                                   # shortlisted, France alone
    vacancy(["C# @ France", ".NET architect @ Austria"]),       # shortlisted, found twice
    vacancy([".NET architect @ Austria"], "not_a_fit"),
    vacancy([".NET architect @ Austria"], "not_a_fit"),
    vacancy(["C# developer @ Bavaria, Germany"], "long_shot"),  # a region of Germany
    vacancy(None),                                              # fetched before found_by
    vacancy(["C# @ France"], source="wwr"),                     # not LinkedIn
    vacancy(["C# @ France"], duplicate_of="x"),                 # a duplicate
]


def test_a_query_that_found_nothing_alone_is_listed_first():
    result = linkedin_yield.tally(BASE)
    rows = {r["group"]: r for r in result["rows"]}
    assert rows["C# @ France"] == {"group": "C# @ France", "served": 2, "shortlisted": 2, "alone": 1}
    assert rows[".NET architect @ Austria"] == {"group": ".NET architect @ Austria",
                                                "served": 3, "shortlisted": 1, "alone": 0}
    assert result["rows"][0]["group"] == ".NET architect @ Austria"
    assert result["unknown"] == 1


def test_by_keyword_and_by_country_with_regions_under_their_country():
    by_kw = {r["group"]: r["alone"] for r in linkedin_yield.tally(BASE, "keyword")["rows"]}
    assert by_kw == {"C#": 1, ".NET architect": 0, "C# developer": 1}
    by_country = {r["group"]: r["served"] for r in linkedin_yield.tally(BASE, "country")["rows"]}
    assert by_country == {"France": 2, "Austria": 3, "Germany": 1}
