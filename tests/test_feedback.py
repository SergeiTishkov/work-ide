"""tools/feedback.py: gathering a person's feedback into a package the agent
can act on, and keeping track of what has been reviewed."""
import pytest
import yaml

import common
import db
import feedback
import kb
import segments
import selections


@pytest.fixture(autouse=True)
def _one_segment(monkeypatch):
    monkeypatch.setattr(segments, "load_segments", lambda prefix=None: segments.parse_segments(
        {"segments": [{"slug": "full", "name": "Everything", "everything": True}]}))


def _vacancy(vid, score=60, classification="hot_lead"):
    return {
        "id": vid, "title": f"Developer {vid}", "company": f"Company {vid}",
        "url": f"https://example.test/{vid}", "source": "wwr",
        "location_raw": "Anywhere in the World", "description_text": "C# " * 3000,
        "computed": {
            "score": score, "classification": classification, "dealbreakers": [],
            "score_breakdown": {"legacy_enterprise_signal": {"hits": ["insurance"]},
                                "stack_fit": {"core_hits": ["c#"]}},
        },
    }


def _setup(statuses: dict) -> int:
    vacancies = {vid: _vacancy(vid, score=50 + i) for i, vid in enumerate(statuses)}
    kb.save_vacancies(vacancies)
    sel = selections.record(vacancies, {"run_count": 1})
    for vid, status in statuses.items():
        if status != "new":
            _mark(vid, status, sel)
    return sel


def _mark(vid, status, selection_id=None, reason="because"):
    with db.session() as conn:
        conn.execute(selections.load_queries()["set_feedback"], {
            "id": vid, "status": status,
            "rejected_reason": reason if status == "rejected" else None,
            "bugged_reason": reason if status == "bugged" else None,
            "at": db.now_iso(), "selection_id": selection_id,
        })


def test_nothing_pending_writes_nothing(isolated_data_dir):
    _setup({"a": "new", "b": "applied"})
    assert feedback.count() == {"bugged": 0, "rejected": 0}
    assert feedback.collect() is None
    assert not (common.DATA_DIR / "feedback").exists()


def test_package_holds_only_pending_rejected_and_bugged_bugged_first(isolated_data_dir):
    _setup({"new": "new", "applied": "applied", "rej": "rejected", "bug": "bugged"})
    path = feedback.collect()
    package = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert [it["id"] for it in package["items"]] == ["bug", "rej"]
    bug = package["items"][0]
    assert bug["reason"] == "because"
    assert bug["score_breakdown"]["legacy_enterprise_signal"]["hits"] == ["insurance"]
    assert bug["then"]["class"] == "hot_lead" and bug["now"]["class"] == "hot_lead"
    assert bug["view"]["title"] == "Developer bug"
    assert len(bug["description"]) <= feedback.DESCRIPTION_LIMIT + 4
    assert package["summary"]["by_status"] == {"bugged": 1, "rejected": 1}
    assert {"signal": "legacy_enterprise_signal.hits: insurance", "items": 2} in \
        package["summary"]["most_common_signals"]
    assert feedback.count() == {"bugged": 1, "rejected": 1}


def test_reviewed_feedback_leaves_the_next_package(isolated_data_dir):
    _setup({"rej": "rejected", "bug": "bugged"})
    path = feedback.collect()
    assert feedback.mark_reviewed(["bug"], "role gate fixed") == 1

    assert [it["id"] for it in feedback.pending_items()] == ["rej"]
    assert feedback.count() == {"bugged": 0, "rejected": 1}
    recorded = yaml.safe_load(path.read_text(encoding="utf-8"))["reviewed"]
    assert recorded[0]["ids"] == ["bug"] and recorded[0]["outcome"] == "role gate fixed"


def test_feedback_changed_after_review_is_pending_again(isolated_data_dir, monkeypatch):
    sel = _setup({"bug": "bugged"})
    monkeypatch.setattr(db, "now_iso", lambda: "2099-01-01T10:00:00+00:00")
    feedback.mark_reviewed(["bug"], "looked")
    assert feedback.count()["bugged"] == 0

    monkeypatch.setattr(db, "now_iso", lambda: "2099-01-01T11:00:00+00:00")
    _mark("bug", "bugged", sel, reason="still wrong: onsite")
    assert feedback.count()["bugged"] == 1


def test_missing_database_counts_zero(isolated_data_dir):
    assert feedback.count() == {"bugged": 0, "rejected": 0}
    assert feedback.pending_items() == []


def test_expired_is_not_feedback_on_the_filter(isolated_data_dir):
    """A closed vacancy or a dead link says nothing about the pick."""
    _setup({"gone": "expired", "bug": "bugged"})
    assert feedback.count() == {"bugged": 1, "rejected": 0}
    assert [it["id"] for it in feedback.pending_items()] == ["bug"]


def test_the_agents_reject_is_a_reviewed_not_for_me(isolated_data_dir):
    """`feedback.py reject` replaced `kb.py set-status not_relevant`: the
    agent's verdict after the checklist is the same answer the person gives in
    the app, and reviewed at once — /feedback has nothing to learn from it."""
    sel = _setup({"a": "new", "b": "new"})
    assert feedback.reject("a", "on-site in Lyon, says the page")
    assert not feedback.reject("nope", "no such vacancy")
    with db.session() as conn:
        row = conn.execute(
            "SELECT feedback_status, rejected_reason, feedback_selection_id, "
            "feedback_reviewed_at = feedback_at FROM vacancies WHERE id = 'a'").fetchone()
    assert row == ("rejected", "on-site in Lyon, says the page", sel, 1)
    assert feedback.count() == {"bugged": 0, "rejected": 0}
