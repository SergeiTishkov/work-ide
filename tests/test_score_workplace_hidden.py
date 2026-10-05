"""
A board that hides the work arrangement confirms remote only on an explicit word.

LinkedIn shows Remote/Hybrid/On-site to logged-in visitors only. Measured
2026-10-04 on SHARP's base: 14 LinkedIn vacancies sat in the confident tiers
with no "remote" anywhere, on phrases that mean something else there — "WFH 3
Days per week" (hybrid), "an allowance when you work from home" (a perk), "a
distributed team", "work from any location in Belarus ... or our offices", a
named EOR platform on a Rome posting with three office days a week. The owner:
everything from LinkedIn where remote is not stated goes to "remote not
confirmed".
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import score  # noqa: E402

from test_score import CRITERIA, PROFILE, make_vacancy  # noqa: E402

STACK = (" Maintain a legacy ASP.NET and SQL Server platform in C#, with .NET Core"
         " services and Entity Framework.")


@pytest.fixture(autouse=True)
def linkedin_hides_the_arrangement(monkeypatch):
    monkeypatch.setattr(score, "_workplace_hidden_sources", lambda: {"linkedin"})


def _linkedin(description, **fields):
    fields = {"workplace_type": None,
              "location_raw": "Rotterdam, South Holland, Netherlands", **fields}
    return make_vacancy(source="linkedin", remote=None,
                        description_text=description + STACK, **fields)


def _criteria():
    rl = {**CRITERIA["remote_location_fit"],
          "explicit_remote_keywords": ["remote", "telecommute", "telework"]}
    return {**CRITERIA, "remote_location_fit": rl}


@pytest.mark.parametrize("description", [
    "An allowance when you work from home.",
    "Collaborate closely with distributed team members.",
    "You can work from any location in Belarus, whether it's your home or our offices.",
    "Payroll through Deel.",
])
def test_a_phrase_that_is_not_remote_leaves_a_linkedin_vacancy_unconfirmed(description):
    result = score.score_vacancy(_linkedin(description), _criteria(), PROFILE)
    assert result["classification"] == "remote_unconfirmed"
    assert score.REMOTE_UNCONFIRMED in result["dealbreakers"]
    assert result["score_breakdown"]["remote_location_fit"]["workplace_hidden_by_source"] == "linkedin"


def test_the_title_saying_wfh_three_days_is_not_remote_either():
    vacancy = _linkedin("", title="ASP.NET Core Developer (WFH 3 Days per week)")
    assert score.score_vacancy(vacancy, _criteria(), PROFILE)["classification"] == "remote_unconfirmed"


@pytest.mark.parametrize("fields", [
    {"title": "Remote Senior C# Developer"},
    {"description": "This is a fully remote position."},
    {"workplace_type": "remote"},
])
def test_an_explicit_remote_confirms_it(fields):
    description = fields.pop("description", "")
    vacancy = _linkedin(description, **fields)
    result = score.score_vacancy(vacancy, _criteria(), PROFILE)
    assert score.REMOTE_UNCONFIRMED not in result["dealbreakers"]
    assert result["classification"] != "remote_unconfirmed"


def test_another_board_keeps_the_wider_synonyms():
    vacancy = make_vacancy(source="reed", remote=None, location_raw="Rotterdam",
                           description_text="An allowance when you work from home." + STACK)
    result = score.score_vacancy(vacancy, _criteria(), PROFILE)
    assert score.REMOTE_UNCONFIRMED not in result["dealbreakers"]


def test_the_scores_are_not_touched_only_the_class():
    """The objection is about what we know, not about the job (see the gate)."""
    hidden = score.score_vacancy(_linkedin("Payroll through Deel."), _criteria(), PROFILE)
    criteria = _criteria()
    criteria["remote_location_fit"] = {**criteria["remote_location_fit"],
                                       "explicit_remote_keywords": ["deel"]}
    confirmed = score.score_vacancy(_linkedin("Payroll through Deel."), criteria, PROFILE)
    assert hidden["score"] == confirmed["score"]
    assert confirmed["classification"] != "remote_unconfirmed"


def test_the_catalogue_marks_linkedin_and_both_templates_name_the_words():
    import yaml

    root = Path(__file__).resolve().parent.parent
    catalog = yaml.safe_load((root / "config" / "sources.catalog.yaml").read_text(encoding="utf-8"))
    hidden = {s["name"] for s in catalog["sources"] if s.get("workplace_hidden")}
    assert hidden == {"linkedin"}
    for name in ("sharp", "pjoice"):
        path = next((root / "identity-templates").glob(f"{name}-*/{name}_criteria.yaml"))
        criteria = yaml.safe_load(path.read_text(encoding="utf-8"))
        words = criteria["remote_location_fit"]["explicit_remote_keywords"]
        assert "remote" in words and "work from home" not in words
