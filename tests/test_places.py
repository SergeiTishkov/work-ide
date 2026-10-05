"""
Which country a location names, and whether it names a place at all
(tools/places.py, config/derivation/countries.yaml).

2026-10-06: the owner saw SHARP's "Worldwide — no country tie" list hold 134
devitjobs vacancies with "New York" or "Denver" for a location — and 11 more in
the US list. The country index knew 35 countries, so "Bucharest, Romania"
named none either, and a vacancy naming no country was listed as worldwide.
"""
from __future__ import annotations

import pytest

import places
import report
import segments


@pytest.mark.parametrize("location, country", [
    ("Bucharest, Romania", "Romania"),
    ("Brazil only", "Brazil"),
    ("South Africa", "South Africa"),
    ("EMEA,  Portugal", "Portugal"),
    ("Remote - US", "United States"),
    ("Prague, Czech Republic", "Czechia"),       # the EU group spells it Czechia
    ("Austin, Texas, United States", "United States"),
    ("Albuquerque, New Mexico", "United States"),  # a state, not Mexico
    ("Seattle, WA", "United States"),
    ("Sydney, NSW", "Australia"),
    ("Berlin", "Germany"),
    ("Toronto", "Canada"),
    ("San Francisco, Seattle, New York", "United States"),
])
def test_a_named_country_state_or_city_is_found(location, country):
    assert places.country_in(location) == country
    assert report.hiring_country({"location_raw": location}) == (country, report.HIRING_OFFICE)


@pytest.mark.parametrize("location, country", [
    ("Remote, Romania", "Romania"),       # "oman" is inside it
    ("Remote, Nigeria", "Nigeria"),       # "niger"
    ("Remote, Russia", "Russia"),         # "us"
    ("Indianapolis", "United States"),    # "india"
])
def test_a_country_is_a_whole_word_not_a_piece_of_one(location, country):
    assert places.country_in(location) == country


def test_latin_america_is_not_the_united_states():
    """The alias "america" made every "Latin America" a US vacancy."""
    assert places.country_in("Remote, Latin America") is None


@pytest.mark.parametrize("location", ["Berlin, DE", "London, ON"])
def test_a_city_and_a_state_code_that_disagree_decide_nothing(location):
    assert places.country_in(location) is None


@pytest.mark.parametrize("location, group", [
    ("", "worldwide"),
    ("Remote", "worldwide"),
    ("Anywhere in the World", "worldwide"),
    ("Anywhere", "worldwide"),
    ("Time zone: CET (+/- 3 hours)", "worldwide"),
    ("REMOTE (Europe)", "worldwide"),
    ("LATAM", "worldwide"),
    ("N/A", "worldwide"),
    ("Denver, Colorado, United States", "united_states"),
    ("Calgary, Canada", "canada"),
    ("Bucharest, Romania", "european_union"),
    ("Berlin, DE", segments.OTHER_GROUP),       # a place, not resolved: not worldwide
    ("Ashreigney", segments.OTHER_GROUP),
    ("Multiple Locations", segments.OTHER_GROUP),
])
def test_worldwide_is_for_a_location_that_names_no_place(location, group):
    assert report.market_group({"location_raw": location}) == group


def test_a_board_code_is_a_country():
    assert places.country_of_code("PT") == "Portugal"
    assert places.country_of_code("no") == "Norway"
    assert places.country_of_code("ZZ") is None


def test_landing_jobs_locations_are_written_as_places():
    import fetch_landing_jobs

    item = {"title": "Backend Engineer", "company": {"name": "Acme"},
            "url": "https://landing.jobs/at/acme/backend-engineer",
            "locations": [{"city": "Lisbon", "country_code": "PT"},
                          {"city": "Munich", "country_code": "DE"}]}
    record = fetch_landing_jobs._to_common_schema(item)
    assert record["location_raw"] == "Lisbon, Portugal; Munich, Germany"
    assert report.market_group(record) == "european_union"


def test_every_country_of_the_market_tables_is_in_the_world_table():
    """market_groups.yaml and market_tiers.yaml spell countries the way
    countries.yaml does, or a vacancy found in one is lost to the other."""
    import markets

    named = {c.get("name") for spec in (markets.load_tiers() or {}).values()
             for c in spec.get("countries") or []}
    named |= {c for g in segments.load_groups().values() for c in g.get("countries") or []}
    assert {n for n in named if n and places.canonical(n) != n} == set()
