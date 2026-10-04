"""
The order vacancies appear in, inside every section of the report.

The owner, 2026-09-13, opening his UK shortlist: the hot leads read "46, 40,
then 60" — "they must be sorted". They were sorted, by reachability first and
score second, and the grouping was invisible: nothing on the page said why a 46
came before a 60. An order a person cannot see the reason for reads as no order
at all.

So the score decides, and reachability only breaks a tie. It is still printed
on every vacancy, and the worldwide shortlist still comes first among the files.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import report  # noqa: E402


def _vacancy(vid, score, eligibility, classification="hot_lead"):
    return {
        "id": vid,
        "title": f"Senior .NET Developer {vid}",
        "company": f"Company {vid}",
        "url": f"https://example.test/{vid}",
        "location_raw": "Anywhere in the World",
        "description_text": "C# and SQL Server.",
        "tags": [],
        "computed": {
            "score": score,
            "classification": classification,
            "score_breakdown": {},
            "dealbreakers": [],
            "residency_eligibility": eligibility,
        },
        "manual": {"status": "new"},
    }


def _scores_in(markdown, heading):
    """The scores listed under one '### <class>' heading, in order."""
    section = markdown.split(f"### {heading}", 1)[1].split("\n### ", 1)[0]
    return [int(s) for s in re.findall(r"^- \*\*\[(\d+)\]", section, re.M)]


def _build(vacancies):
    return report.build_report_markdown(vacancies, {}, {}, criteria={})


def test_the_owners_case_46_40_60_comes_out_60_46_40():
    vacancies = {
        "a": _vacancy("a", 46, "likely"),
        "b": _vacancy("b", 40, "likely"),
        "c": _vacancy("c", 60, "unknown"),
    }
    assert _scores_in(_build(vacancies), "hot_lead") == [60, 46, 40]


def test_reachability_breaks_a_tie_and_nothing_more():
    vacancies = {
        "unknown": _vacancy("unknown", 50, "unknown"),
        "confirmed": _vacancy("confirmed", 50, "confirmed"),
        "likely": _vacancy("likely", 50, "likely"),
    }
    text = _build(vacancies)
    section = text.split("### hot_lead", 1)[1].split("\n### ", 1)[0]
    order = re.findall(r"Senior \.NET Developer (\w+)", section)
    assert order == ["confirmed", "likely", "unknown"]


def test_every_section_is_sorted_the_same_way():
    vacancies = {}
    for cls in ("worth_a_look", "long_shot", "remote_unconfirmed"):
        for n, (score, eligibility) in enumerate([(12, "confirmed"), (31, "unknown"), (25, "likely")]):
            vid = f"{cls}{n}"
            vacancies[vid] = _vacancy(vid, score, eligibility, cls)
    text = _build(vacancies)
    for cls in ("worth_a_look", "long_shot", "remote_unconfirmed"):
        assert _scores_in(text, cls) == [31, 25, 12], cls


def test_the_hours_section_appears_only_for_a_search_that_asks_about_hours():
    """A search with no engagement gate never sees an empty heading about it."""
    plain = report.build_report_markdown({"a": _vacancy("a", 40, "likely")}, {}, {},
                                         criteria={})
    assert "### engagement_unconfirmed" not in plain

    gated = report.build_report_markdown(
        {"a": _vacancy("a", 40, "likely"),
         "b": _vacancy("b", 55, "unknown", "engagement_unconfirmed"),
         "c": _vacancy("c", 70, "unknown", "engagement_unconfirmed")},
        {}, {}, criteria={"engagement_fit": {"confirming_types": ["part-time"]}})
    assert _scores_in(gated, "engagement_unconfirmed") == [70, 55]
