"""
A board the person cannot apply through is closed, whatever its vacancies say.

The owner's feedback of 2026-10-04 on a mycareersfuture vacancy:

    "https://www.mycareersfuture.gov.sg/ requires login, and login requires
    Singapore ID check. No chance for me. Remove this website from the jobs
    list completely"

Turning the board off in the sources file stops new vacancies, but 1 175 were
already in kisel's base, 14 of them as hot leads. `closed_sources` in the
criteria rejects them all, with the reason as the dealbreaker.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import score  # noqa: E402

from test_score import CRITERIA, PROFILE, make_vacancy  # noqa: E402

TEMPLATES = Path(__file__).resolve().parent.parent / "identity-templates"

# A vacancy every other gate lets through: remote, worldwide, .NET.
GOOD = dict(title="Senior C# Developer", remote=True, location_raw="Anywhere in the World",
            description_text="Maintain a legacy ASP.NET and SQL Server platform in C#, "
                             "with .NET Core services and Entity Framework. Fully remote.")


def _criteria(closed):
    return {**CRITERIA, "closed_sources": closed}


def test_a_vacancy_from_a_closed_board_is_rejected_with_the_reason():
    criteria = _criteria({"mycareersfuture": "applying needs a Singpass login"})
    result = score.score_vacancy(make_vacancy(source="mycareersfuture", **GOOD), criteria, PROFILE)
    assert result["classification"] == "rejected"
    assert "source: applying needs a Singpass login" in result["dealbreakers"]


def test_the_same_vacancy_from_another_board_is_untouched():
    criteria = _criteria({"mycareersfuture": "applying needs a Singpass login"})
    open_board = score.score_vacancy(make_vacancy(source="reed", **GOOD), criteria, PROFILE)
    no_rule = score.score_vacancy(make_vacancy(source="reed", **GOOD), _criteria({}), PROFILE)
    assert open_board["classification"] == no_rule["classification"] != "rejected"
    assert not any(d.startswith("source:") for d in open_board["dealbreakers"])


def test_both_templates_close_mycareersfuture_and_turn_it_off():
    for criteria_file in TEMPLATES.glob("*/*_criteria.yaml"):
        folder = criteria_file.parent
        if folder.name.startswith(("kisel-", "pjoice-")):
            criteria = yaml.safe_load(criteria_file.read_text(encoding="utf-8"))
            assert "mycareersfuture" in criteria["closed_sources"], folder.name
            sources = yaml.safe_load(
                next(folder.glob("*_sources.yaml")).read_text(encoding="utf-8"))
            entries = sources["sources"] if isinstance(sources, dict) else sources
            board = next(s for s in entries if s["name"] == "mycareersfuture")
            assert board["enabled"] is False, folder.name
