"""Stretch roles (criteria `stretch_roles`, the owner, 2026-10-20): "remote
outranks the technology". A remote role off the stack or level is read by the
screening model against the CV instead of being refused by keyword."""
import copy

import ai_screen
import score

CRITERIA = score.load_criteria()
PROFILE = score.load_profile()

REMOTE = "Fully remote, we hire worldwide as contractors. "
GO_TEXT = REMOTE + ("You will build backend services in Golang on PostgreSQL and Kubernetes, review code "
                    "with a team of eight engineers and own features end to end. ") * 4


def _vacancy(**fields):
    base = {"id": "x", "source": "remoteok", "title": "Senior Backend Engineer (Golang)",
            "company": "Acme", "url": "https://example.com/x", "location_raw": "Remote",
            "description_text": GO_TEXT, "tags": []}
    return {**base, **fields}


def _criteria(enabled=True, **extra):
    c = copy.deepcopy(CRITERIA)
    if enabled:
        c["stretch_roles"] = {"enabled": True, "stretch_points": -4}
    role = c["role_relevance_signal"]
    role["wrong_discipline_title_patterns"] = [
        p for p in role["wrong_discipline_title_patterns"] if "forward" not in p]
    role["stretch_discipline_title_patterns"] = ["forward[ -]deploy(ed|ment)"]
    c.update(extra)
    return c


def _read(record, **answer):
    """The record with a model answer for its current text."""
    return {**record, "_ai_screen": {"verdict": "keep", "reason": "r", **answer,
                                     "text_hash": ai_screen.text_hash(record)}}


def test_without_the_section_another_stack_is_refused_as_before():
    computed = score.score_vacancy(_vacancy(), _criteria(enabled=False), PROFILE)
    assert computed["classification"] == "rejected"
    assert any(d.startswith("stack: ") for d in computed["dealbreakers"])
    assert score.STRETCH_UNREAD not in computed["dealbreakers"]
    assert not computed["screen_wanted"]


def test_another_stack_waits_for_the_model_and_is_wanted_for_a_read():
    computed = score.score_vacancy(_vacancy(), _criteria(), PROFILE)
    assert computed["dealbreakers"] == [score.STRETCH_UNREAD]
    assert computed["classification"] == "rejected"
    assert computed["screen_wanted"]
    objections = computed["score_breakdown"]["stretch_roles"]["objections"]
    assert any(o.startswith("stack: ") for o in objections)


def test_the_models_stretch_lifts_the_objections_at_a_cost_and_fits_at_none():
    criteria = _criteria()
    stretch = score.score_vacancy(_read(_vacancy(), cv_fit="stretch", work_kind="software"), criteria, PROFILE)
    fits = score.score_vacancy(_read(_vacancy(), cv_fit="fits", work_kind="software"), criteria, PROFILE)
    assert stretch["dealbreakers"] == [] and fits["dealbreakers"] == []
    assert stretch["classification"] != "rejected"
    assert stretch["score_breakdown"]["stretch_roles"] == {
        "objections": stretch["score_breakdown"]["stretch_roles"]["objections"],
        "fit": "stretch", "points": -4, "work_kind": "software"}
    assert fits["score"] - stretch["score"] == 4
    assert [p for p in stretch["score_parts"] if p["key"] == "stretch"][0]["points"] == -4
    assert not stretch["screen_wanted"]


def test_the_models_no_rejects_and_is_asked_again_on_a_new_brief():
    computed = score.score_vacancy(
        _read(_vacancy(), verdict="reject", cv_fit="no", reason="ML research: trains models"), _criteria(), PROFILE)
    assert computed["dealbreakers"] == ["ai: ML research: trains models"]
    assert computed["score_breakdown"]["stretch_roles"]["fit"] == "no"
    # only the model stands in the way, so a new brief reads it again
    assert computed["screen_wanted"]


def test_an_answer_from_before_cv_fit_leaves_the_stretch_waiting():
    computed = score.score_vacancy(_read(_vacancy()), _criteria(), PROFILE)
    assert computed["dealbreakers"] == [score.STRETCH_UNREAD]


def test_remote_comes_first_an_unconfirmed_stretch_is_not_sent_to_the_model():
    office = ("You will build backend services in Golang on PostgreSQL and Kubernetes. ") * 3
    computed = score.score_vacancy(
        _vacancy(source="linkedin", description_text=office, location_raw="Berlin, Germany"), _criteria(), PROFILE)
    assert score.STRETCH_UNREAD in computed["dealbreakers"]
    assert not computed["screen_wanted"]


def test_a_discipline_a_developer_can_move_into_is_a_stretch_others_stay_refused():
    criteria = _criteria()
    fde = score.score_vacancy(_vacancy(title="Forward Deployed Engineer"), criteria, PROFILE)
    assert fde["dealbreakers"] == [score.STRETCH_UNREAD]
    assert any(o.startswith("role: ") for o in fde["score_breakdown"]["stretch_roles"]["objections"])
    security = score.score_vacancy(_vacancy(title="Senior Security Engineer"), criteria, PROFILE)
    assert any(d.startswith("role: ") for d in security["dealbreakers"])
    assert not security["screen_wanted"]


def test_a_junior_title_is_a_stretch_only_with_a_stretch_if_word():
    rules = [{"pattern": r"\bjunior\b", "label": "junior", "reject": True, "stretch_if": ["forward"]}]
    criteria = _criteria(title_role_penalty={"rules": rules})
    fde = score.score_vacancy(_vacancy(title="Junior Forward Deployed Engineer"), criteria, PROFILE)
    assert "title: junior" in fde["score_breakdown"]["stretch_roles"]["objections"]
    assert "title: junior" not in fde["dealbreakers"]
    developer = score.score_vacancy(_vacancy(title="Junior Golang Developer"), criteria, PROFILE)
    assert "title: junior" in developer["dealbreakers"]
    # with the section off, both are refusals
    off = _criteria(enabled=False, title_role_penalty={"rules": rules})
    assert "title: junior" in score.score_vacancy(
        _vacancy(title="Junior Forward Deployed Engineer"), off, PROFILE)["dealbreakers"]


def test_a_stretch_the_model_read_is_past_the_complexity_gate():
    criteria = _criteria()
    criteria["role_complexity_signal"]["title_red_flag_patterns"] = ["forward deployed"]
    waiting = score.score_vacancy(_vacancy(title="Forward Deployed Engineer"), criteria, PROFILE)
    assert waiting["score_breakdown"]["role_complexity_signal"]["gate_triggered"]
    record = _read(_vacancy(title="Forward Deployed Engineer"), cv_fit="stretch", work_kind="applied_ai")
    read = score.score_vacancy(record, criteria, PROFILE)
    without_gate = score.score_vacancy(record, _criteria(), PROFILE)
    assert read["classification"] == without_gate["classification"] != "rejected"
