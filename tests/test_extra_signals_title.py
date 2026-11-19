"""extra_signals' title_patterns (task 0124): a role name counts in the title
only, the description's mention of it does not."""
import copy

import pytest

import score

CRITERIA = score.load_criteria()
PROFILE = score.load_profile()
SIGNAL = {"name": "fde_like", "label": "forward deployed or similar", "points_per_keyword": 20,
          "cap": 20, "keywords": ["forward deployed"],
          "title_patterns": [r"\bai engineer\b", r"\bapplied ai engineer\b"]}


def _points(title, text=""):
    detail = score._score_extra_signals(text.lower(), {"extra_signals": [SIGNAL]}, title)[1]
    return detail["fde_like"]["points"], detail["fde_like"]["hits"]


@pytest.mark.parametrize("title,expected", [
    ("Senior AI Engineer", 20),
    ("Senior  AI   Engineer (LLM)", 20),
    ("Applied AI Engineer", 20),          # two patterns, one cap
    ("OpenAI Engineer Advocate", 0),
    ("AI Engineering Manager", 0),
    ("Machine Learning Engineer", 0),
    ("", 0),
])
def test_title_patterns(title, expected):
    assert _points(title)[0] == expected


def test_the_description_does_not_trigger_a_title_pattern():
    assert _points("Backend Engineer", "you will work with our ai engineers")[0] == 0


def test_text_keywords_still_count():
    points, hits = _points("Software Engineer", "join us as a forward deployed engineer")
    assert points == 20 and hits == ["forward deployed"]


def test_hits_name_the_title_pattern():
    assert _points("Senior AI Engineer")[1] == [r"title: \bai engineer\b"]


def test_score_vacancy_passes_the_title():
    criteria = copy.deepcopy(CRITERIA)
    criteria["extra_signals"] = [SIGNAL]
    vacancy = {"id": "t", "title": "Senior AI Engineer", "company": "Acme", "location_raw": "",
               "remote": True, "tags": [], "description_text": "C# and Azure OpenAI.", "salary_raw": None}
    result = score.score_vacancy(vacancy, criteria, PROFILE)
    assert result["score_breakdown"]["extra_signals"]["fde_like"]["points"] == 20
    part = next(p for p in result["score_parts"] if p["key"] == "extra:fde_like")
    assert (part["points"], part["max"]) == (20, 20)
