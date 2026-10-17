"""
score_parts: each part of the score with the least and most it can earn, for
the "Score" bars on the app's card (the owner, 2026-10-17: "the reasons for
the score, most positive first, one per row, earned points bright, the rest
faded").
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import report  # noqa: E402
import score  # noqa: E402

from test_score import CRITERIA, PROFILE, make_vacancy  # noqa: E402

GOOD = dict(title="Senior C# Developer", remote=True, location_raw="Anywhere in the World",
            description_text="Maintain a legacy ASP.NET and SQL Server platform in C#, "
                             "with .NET Core services and Entity Framework. Fully remote. "
                             "Contractors welcome. $90/hour.")


def _parts(**fields):
    return score.score_vacancy(make_vacancy(**{**GOOD, **fields}), CRITERIA, PROFILE)


def test_the_parts_add_up_to_the_raw_total():
    result = _parts()
    parts = result["score_parts"]
    assert sum(p["points"] for p in parts) == result["score_breakdown"]["raw_total_before_clamp"]


def test_every_part_sits_inside_its_range_and_the_range_holds_zero():
    for fields in ({}, {"title": "Frontend Developer (React)"},
                   {"description_text": "C# and .NET, crunch, on-call 24/7, $20/hour."}):
        for part in _parts(**fields)["score_parts"]:
            assert part["min"] <= min(0, part["points"]) and part["max"] >= max(0, part["points"]), part
            assert part["min"] < part["max"], part


def test_the_ranges_come_from_the_criteria_caps():
    parts = {p["key"]: p for p in _parts()["score_parts"]}
    assert parts["stack"]["max"] == CRITERIA["stack_fit"]["cap"]
    assert parts["stack"]["min"] == 0
    rep = CRITERIA["company_reputation_signal"]
    assert parts["reputation"]["max"] == (rep["overall_rating"]["excellent_points"]
                                          + rep["work_life_balance"]["excellent_points"])


def test_most_positive_first():
    points = [p["points"] for p in _parts(title="Frontend Developer")["score_parts"]]
    assert points == sorted(points, reverse=True)


def test_a_part_that_can_earn_nothing_is_left_out():
    criteria = {**CRITERIA, "contractor_friendliness": {**CRITERIA["contractor_friendliness"], "cap": 0}}
    parts = score.score_vacancy(make_vacancy(**GOOD), criteria, PROFILE)["score_parts"]
    assert "contractor" not in {p["key"] for p in parts}


def test_a_named_signal_carries_its_label():
    criteria = {**CRITERIA, "extra_signals": [
        {"name": "calm", "label": "calm domain", "points_per_keyword": 2, "cap": 6, "keywords": ["legacy"]}]}
    parts = {p["key"]: p for p in score.score_vacancy(make_vacancy(**GOOD), criteria, PROFILE)["score_parts"]}
    assert parts["extra:calm"] == {"key": "extra:calm", "label": "calm domain", "points": 2, "min": 0, "max": 6}


def test_the_card_view_carries_the_parts():
    computed = _parts()
    view = report.vacancy_view({"id": "a", "title": "t", "company": "c", "url": "u", "computed": computed})
    assert view["score_parts"] == computed["score_parts"]
    assert report.vacancy_view({"id": "b", "computed": {}})["score_parts"] == []
