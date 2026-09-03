"""
One identity, several shortlists.

Asked for by the owner 2026-08-12: a working identity should be able to produce
a separate shortlist per market, because a person reads one list at a time and
decides where to spend an evening — and a single file sorted by score mixes a
Singapore agency posting with a UK contract at four times the rate.

The three things this file is really guarding:

  1. **Nothing falls out of every file.** `rest` is COMPUTED from what the other
     segments claimed rather than listed by hand, so adding a segment can never
     silently orphan a market. A list maintained in two places drifts, and the
     drift here would be invisible: the vacancy simply would not be in any file.

  2. **"No country named" is a group, not a missing value.** For somebody
     contracting from outside every market in the table it is the only group
     where geography is not an obstacle at all, and treating it as absence
     would bury it in "everything else".

  3. **A typo fails loudly.** An unknown group key raises rather than producing
     an empty file, which would read exactly like "there is nothing in this
     market".
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import pytest  # noqa: E402

import segments  # noqa: E402


def _config(*entries):
    return {"segments": list(entries)}


def _vac(country):
    return {"country": country}


def country_of(v):
    return v["country"]


# --- the catalogue ---------------------------------------------------------

def test_countries_map_to_their_group():
    assert segments.group_of("Canada") == "canada"
    assert segments.group_of("United Kingdom") == "united_kingdom"
    # The EU is one group rather than 27 files: a contract with a Dutch or an
    # Irish company reaches the same kind of employer at the same kind of rate.
    assert segments.group_of("Germany") == "european_union"
    assert segments.group_of("Ireland") == "european_union"


def test_a_country_outside_the_catalogue_is_not_an_error():
    """The catalogue names the markets somebody wanted split out. The world is
    larger than that, and a vacancy in Brazil must still land somewhere."""
    assert segments.group_of("Brazil") == segments.OTHER_GROUP


def test_no_country_named_is_its_own_group():
    """Point 2 in the module docstring — the group that is not a place."""
    assert segments.group_of(None) == "worldwide"
    assert segments.group_of("") == "worldwide"


def test_country_matching_ignores_case_and_spacing():
    assert segments.group_of("  united kingdom ") == "united_kingdom"


# --- parsing ---------------------------------------------------------------

def test_an_unknown_group_key_fails_loudly():
    """Point 3. An empty file reads as "nothing in this market", which is the
    most misleading possible outcome of a typo."""
    with pytest.raises(ValueError) as excinfo:
        segments.parse_segments(_config({"slug": "uk", "groups": ["untied_kingdom"]}))
    assert "untied_kingdom" in str(excinfo.value)


def test_an_empty_configuration_produces_no_segments():
    """Which is how an identity that has said nothing about markets keeps
    getting exactly the one report it always got."""
    assert segments.parse_segments({}) == []
    assert segments.parse_segments({"segments": []}) == []


# --- splitting -------------------------------------------------------------

def test_each_vacancy_lands_in_its_market_and_in_the_full_file():
    parsed = segments.parse_segments(_config(
        {"slug": "uk", "groups": ["united_kingdom"]},
        {"slug": "canada", "groups": ["canada"]},
        {"slug": "full", "everything": True},
    ))
    buckets = segments.split(
        [_vac("United Kingdom"), _vac("Canada"), _vac("Canada")],
        parsed, country_of)

    assert len(buckets["uk"]) == 1
    assert len(buckets["canada"]) == 2
    assert len(buckets["full"]) == 3


def test_rest_is_whatever_no_other_segment_claimed():
    """Point 1, and the reason `rest` holds no list of its own."""
    parsed = segments.parse_segments(_config(
        {"slug": "uk", "groups": ["united_kingdom"]},
        {"slug": "rest", "rest": True},
    ))
    buckets = segments.split(
        [_vac("United Kingdom"), _vac("Canada"), _vac("Brazil"), _vac(None)],
        parsed, country_of)

    assert [v["country"] for v in buckets["uk"]] == ["United Kingdom"]
    assert sorted(str(v["country"]) for v in buckets["rest"]) == \
        ["Brazil", "Canada", "None"]


def test_adding_a_segment_shrinks_rest_by_itself():
    """The property that makes point 1 true rather than merely intended: the
    same vacancy set, one more segment, and nothing is orphaned or duplicated
    between the two files."""
    without = segments.parse_segments(_config(
        {"slug": "uk", "groups": ["united_kingdom"]},
        {"slug": "rest", "rest": True},
    ))
    with_canada = segments.parse_segments(_config(
        {"slug": "uk", "groups": ["united_kingdom"]},
        {"slug": "canada", "groups": ["canada"]},
        {"slug": "rest", "rest": True},
    ))
    vacancies = [_vac("United Kingdom"), _vac("Canada"), _vac("Brazil")]

    before = segments.split(vacancies, without, country_of)
    after = segments.split(vacancies, with_canada, country_of)

    assert len(before["rest"]) == 2
    assert len(after["rest"]) == 1
    assert len(after["canada"]) == 1
    # Nothing lost and nothing counted twice, in either arrangement.
    assert sum(len(b) for b in before.values()) == len(vacancies)
    assert sum(len(b) for b in after.values()) == len(vacancies)


def test_every_vacancy_reaches_at_least_one_file():
    """The invariant worth stating outright: splitting a report must never be
    a way of losing a vacancy."""
    parsed = segments.parse_segments(_config(
        {"slug": "worldwide", "groups": ["worldwide"]},
        {"slug": "uk", "groups": ["united_kingdom"]},
        {"slug": "rest", "rest": True},
    ))
    vacancies = [_vac(c) for c in
                 (None, "United Kingdom", "Canada", "Brazil", "Singapore", "Germany")]

    buckets = segments.split(vacancies, parsed, country_of)
    landed = sum(len(b) for b in buckets.values())

    assert landed == len(vacancies), buckets


def test_a_group_claimed_by_two_segments_appears_in_both():
    """Not a mistake — an identity may deliberately want a market both on its
    own and inside a wider file. It must not confuse `rest`, which is why
    `rest` is computed from every claim rather than from the first."""
    parsed = segments.parse_segments(_config(
        {"slug": "canada", "groups": ["canada"]},
        {"slug": "north_america", "groups": ["canada", "united_states"]},
        {"slug": "rest", "rest": True},
    ))
    buckets = segments.split([_vac("Canada")], parsed, country_of)

    assert len(buckets["canada"]) == 1
    assert len(buckets["north_america"]) == 1
    assert buckets["rest"] == []


# --- the configuration this repository actually ships ----------------------

def test_the_shipped_kisel_segmentation_is_valid_and_complete():
    """The template is configuration, and configuration breaks silently. This
    fails the moment somebody adds a segment naming a group that does not
    exist, or removes `rest` and orphans half the world."""
    import common

    path = (common.ROOT / "identity-templates" /
            "kisel-keep-it-simple-easy-legacy" / "kisel_reports.yaml")
    parsed = segments.parse_segments(common.load_yaml(path) or {})

    slugs = [s.slug for s in parsed]
    assert slugs[0] == "worldwide", (
        "the group where geography is not an obstacle is meant to be read first")
    assert sum(1 for s in parsed if s.rest) == 1, "exactly one catch-all"
    assert sum(1 for s in parsed if s.default) == 1, (
        "exactly one segment may claim <prefix>_latest.md")

    # Every group in the catalogue reaches a file.
    buckets = segments.split(
        [{"c": None}] + [{"c": g} for g in
                         ("United Kingdom", "Germany", "Canada", "United States",
                          "Australia", "Switzerland", "Israel", "Singapore",
                          "United Arab Emirates", "Brazil")],
        parsed, lambda v: v["c"])
    assert all(len(b) or s.slug in ("uk", "canada", "usa", "anz")
               for s, b in ((s, buckets[s.slug]) for s in parsed))


def test_the_default_configuration_is_a_single_undivided_report():
    """An identity that has said nothing about markets must be unaffected by
    any of this."""
    import common

    parsed = segments.parse_segments(
        common.load_yaml(common.ROOT / "config" / "defaults" / "reports.yaml") or {})

    assert len(parsed) == 1
    assert parsed[0].everything and parsed[0].default
    assert parsed[0].slug == "", "the single report keeps the historical filename"
