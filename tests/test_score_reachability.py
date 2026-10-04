"""
Reachability from abroad weighs in the score (KISEL template V20).

The owner, 2026-10-05: the top of the list is full of vacancies that cannot be
taken from abroad. Measured on KISEL's 373 unanswered vacancies in view: the
location axis gave 0-8 points against ~37 for the stack, 50 hot leads offered
a 401(k) or RRSP, and "hybrid remote", "anywhere within the United States" or
"Must live in Houston" passed every existing pattern.

The rules are read from the KISEL template itself and laid over the frozen
fixture's criteria, so these tests check the template a person actually uses.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import score  # noqa: E402

from test_score import CRITERIA, PROFILE, make_vacancy  # noqa: E402

KISEL = yaml.safe_load(
    (Path(__file__).resolve().parent.parent / "identity-templates"
     / "kisel-keep-it-simple-easy-legacy" / "kisel_criteria.yaml").read_text(encoding="utf-8"))
KISEL_RL = KISEL["remote_location_fit"]

NEW_HARD = {"hybrid remote", "work mode field says hybrid", "hybrid as a separate item",
            "work in a hybrid environment", "remote within one country, said at length",
            "based in one country", "must live in a named place"}
PAYROLL = "US or Canadian payroll benefits (401(k), RRSP)"

STACK = (" Maintain a legacy ASP.NET and SQL Server platform in C#, with .NET Core"
         " services and Entity Framework.")


def _criteria(points=None, policy=None):
    rl = dict(CRITERIA["remote_location_fit"])
    wa = dict(rl["work_authorization"])
    wa["rules"] = list(wa["rules"]) + [r for r in KISEL_RL["work_authorization"]["rules"]
                                      if r["name"] == PAYROLL]
    wa["international_hiring_patterns"] = KISEL_RL["work_authorization"]["international_hiring_patterns"]
    rl["work_authorization"] = wa
    hard = dict(rl["hard_dealbreakers"])
    hard["patterns"] = list(hard.get("patterns") or []) + [
        p for p in KISEL_RL["hard_dealbreakers"]["patterns"] if p["name"] in NEW_HARD]
    rl["hard_dealbreakers"] = hard
    rl["residency_eligibility"] = {
        **(rl.get("residency_eligibility") or {}),
        "points": KISEL_RL["residency_eligibility"]["points"] if points is None else points}
    rl["restricted_location_policy"] = (KISEL_RL["restricted_location_policy"]
                                        if policy is None else policy)
    return {**CRITERIA, "remote_location_fit": rl}


def _score(description, criteria=None, **fields):
    fields = {"location_raw": "", **fields}
    return score.score_vacancy(make_vacancy(description_text=description + STACK, **fields),
                               criteria or _criteria(), PROFILE)


def test_the_template_carries_every_rule_these_tests_lay_over():
    names = {p["name"] for p in KISEL_RL["hard_dealbreakers"]["patterns"]}
    assert NEW_HARD <= names
    assert PAYROLL in {r["name"] for r in KISEL_RL["work_authorization"]["rules"]}


@pytest.mark.parametrize("benefits", [
    "Benefits include a 401(k) with company match, dental and vision.",
    "We offer medical, dental, HSA, FSA, 401K and life insurance.",
    "Employer RRSP contribution (3%) and comprehensive health benefits.",
])
def test_a_us_or_canadian_retirement_plan_rejects(benefits):
    result = _score("Fully remote role. " + benefits)
    assert result["classification"] == "rejected"
    assert f"location: {PAYROLL}" in result["dealbreakers"]


@pytest.mark.parametrize("text", [
    "Fully remote role. We hire contractors from any country. US employees get a 401(k).",
    "Fully remote role. A 401(k) plan for our US employees; elsewhere a local equivalent.",
])
def test_the_plan_does_not_reject_an_employer_that_engages_people_abroad(text):
    assert f"location: {PAYROLL}" not in _score(text)["dealbreakers"]


@pytest.mark.parametrize("text", [
    "This is a hybrid remote role based in Verdun, QC.",
    "Mode of work: Hybrid.",
    "C#, WPF, .NET Developer - Hybrid - Outside IR35 - 12 month contract.",
    "Work in a hybrid environment with opportunities for remote collaboration.",
    "Fully remote opportunity with the option to work anywhere within the United States.",
    "Location: Remote (UK-based). You MUST be UK based to be considered.",
    "Must live in Houston, TX (required).",
    "Remote. Must reside within the United States.",
])
def test_a_stated_place_or_hybrid_arrangement_rejects(text):
    result = _score(text)
    assert result["classification"] == "rejected"
    assert any(d[len("location: "):] in NEW_HARD for d in result["dealbreakers"]
               if d.startswith("location: ")), result["dealbreakers"]


@pytest.mark.parametrize("text", [
    "Remote. CSC offers hybrid or remote work schedules in alignment with local regulation.",
    "Remote. Hybrid / remote-friendly work environment.",
    "Remote. Experience with on-prem, hybrid, cloud deployments.",
    "Remote. Location: Hybrid, Remote.",
])
def test_hybrid_offered_beside_remote_or_as_technology_does_not(text):
    assert not any(d[len("location: "):] in NEW_HARD for d in _score(text)["dealbreakers"]
                   if d.startswith("location: "))


def test_a_board_saying_anywhere_makes_it_likely_and_adds_the_bonus():
    fields = dict(location_raw="Anywhere in the World", source="weworkremotely")
    with_bonus = _score("Fully remote.", **fields)
    without = _score("Fully remote.", criteria=_criteria(points={}), **fields)
    assert with_bonus["residency_eligibility"] == score.ELIGIBILITY_LIKELY
    bonus = KISEL_RL["residency_eligibility"]["points"]["likely"]
    assert bonus > 0
    assert with_bonus["score_breakdown"]["reachability_bonus"] == {
        "points": bonus, "eligibility": score.ELIGIBILITY_LIKELY}
    assert with_bonus["score"] == min(100, without["score"] + bonus)


def test_no_bonus_when_nothing_says_where_from():
    result = _score("Fully remote.", location_raw="Toronto, Ontario, Canada")
    assert result["residency_eligibility"] == score.ELIGIBILITY_UNKNOWN
    assert result["score_breakdown"]["reachability_bonus"]["points"] == 0


def test_a_contract_with_the_persons_own_business_counts_as_engaging_abroad():
    result = _score("Fully remote contract. You need to have an IE (individual entrepreneur), "
                    "or LLC registered to cooperate with us.")
    assert result["residency_eligibility"] == score.ELIGIBILITY_LIKELY


def test_a_board_saying_place_only_is_rejected_under_the_reject_policy():
    fields = dict(location_raw="United States only", source="himalayas")
    assert _score("Fully remote.", **fields)["classification"] == "rejected"
    kept = _score("Fully remote.", criteria=_criteria(policy="national_market"), **fields)
    assert kept["classification"] == "national_market"
