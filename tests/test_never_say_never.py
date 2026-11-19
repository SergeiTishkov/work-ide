"""The class under long_shot that is still listed (task 0124): opt-in by a
`never_say_never` threshold, never sent to the screening model, listed in a
section of its own."""
import copy

import pytest

import ai_screen
import db
import kb
import report
import score
import segments
import selections

CRITERIA = score.load_criteria()
PROFILE = score.load_profile()


def _vacancy():
    return {"id": "nsn", "title": "Senior C# Developer", "company": "Acme Corp", "location_raw": "",
            "remote": True, "tags": [], "description_text": "C# and SQL Server.", "salary_raw": None}


def _criteria(**thresholds):
    criteria = copy.deepcopy(CRITERIA)
    criteria["classification_thresholds"].update(thresholds)
    return criteria


@pytest.fixture(scope="module")
def total():
    """The test vacancy's score; the thresholds below are set around it."""
    result = score.score_vacancy(_vacancy(), CRITERIA, PROFILE)
    assert result["classification"] != "rejected"
    return result["score"]


def _class(criteria):
    return score.score_vacancy(_vacancy(), criteria, PROFILE)["classification"]


def test_without_the_threshold_the_band_stays_low_priority(total):
    criteria = _criteria(hot_lead=total + 3, worth_a_look=total + 2, long_shot=total + 1)
    criteria["classification_thresholds"].pop(score.NEVER_SAY_NEVER, None)
    assert _class(criteria) == "low_priority"


@pytest.mark.parametrize("offset,expected", [(0, score.NEVER_SAY_NEVER), (-1, score.NEVER_SAY_NEVER),
                                             (1, "low_priority")])
def test_the_band_from_the_threshold_to_long_shot(total, offset, expected):
    criteria = _criteria(hot_lead=total + 3, worth_a_look=total + 2, long_shot=total + 1,
                         never_say_never=total + offset)
    assert _class(criteria) == expected


def test_long_shot_still_wins_above_its_own_threshold(total):
    assert _class(_criteria(hot_lead=total + 2, worth_a_look=total + 1, long_shot=total,
                            never_say_never=total - 1)) in ("long_shot", ai_screen.UNSCREENED)


def test_the_band_is_not_held_for_the_screening_model(total):
    criteria = _criteria(hot_lead=total + 3, worth_a_look=total + 2, long_shot=total + 1,
                         never_say_never=total, ai_screen={"required": True})
    result = score.score_vacancy(_vacancy(), criteria, PROFILE)
    assert result["classification"] == score.NEVER_SAY_NEVER
    assert result["script_class"] is None
    assert score.NEVER_SAY_NEVER not in ai_screen.TOP_CLASSES


def test_the_band_is_listed_last(isolated_data_dir, monkeypatch):
    monkeypatch.setattr(segments, "load_segments", lambda prefix=None: segments.parse_segments(
        {"segments": [{"slug": "full", "name": "Everything", "everything": True, "default": True}]}))
    vacancies = {}
    for vid, cls, points in (("a", "long_shot", 12), ("b", score.NEVER_SAY_NEVER, 7), ("c", "low_priority", 4)):
        vacancies[vid] = {**_vacancy(), "id": vid, "url": f"https://example.test/{vid}",
                          "computed": {"score": points, "classification": cls,
                                       "score_breakdown": {}, "dealbreakers": []}}
    kb.save_vacancies(vacancies)
    selection_id = selections.record(vacancies, {"run_count": 1})
    with db.session() as conn:
        rows = selections.listing(conn, selection_id, selections.view(["full"]))
    assert [(r["vacancy_id"], r["class"]) for r in rows] == [("a", "long_shot"), ("b", score.NEVER_SAY_NEVER)]
    assert report.LISTED_CLASSES[-1] == score.NEVER_SAY_NEVER
