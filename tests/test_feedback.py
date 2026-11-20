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
            "identity": db.identity(), "id": vid, "status": status,
            "rejected_reason": reason if status == "rejected" else None,
            "bugged_reason": reason if status == "bugged" else None,
            "applied_comment": reason if status == "applied" else None,
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
            "feedback_reviewed_at = feedback_at FROM vacancy_identity "
            "WHERE identity_id = 'ftf' AND vacancy_id = 'a'").fetchone()
    assert row == ("rejected", "on-site in Lyon, says the page", sel, 1)
    assert feedback.count() == {"bugged": 0, "rejected": 0}


def test_applications_come_with_what_was_written_and_stay_out_of_the_review(isolated_data_dir, capsys):
    """The applied comment (task 0131) is read back for the cover letter; it
    is not a reason about the vacancy, so no review package carries it."""
    sel = _setup({"a": "new", "b": "new", "c": "new", "r": "new"})
    _mark("a", "applied", sel, reason="Q: notice period? A: one month")
    _mark("b", "applied", sel, reason=None)
    _mark("r", "rejected", sel, reason="too far")
    with db.session() as conn:
        conn.execute("UPDATE vacancy_identity SET applied_at = '2026-01-01T00:00:00+00:00' "
                     "WHERE identity_id = 'ftf' AND vacancy_id = 'b'")

    items = feedback.applied_items()
    assert [(it["id"], it["applied_comment"]) for it in items] == [
        ("a", "Q: notice period? A: one month"), ("b", None)]
    assert items[0]["status"] == "applied" and items[0]["title"] == "Developer a"
    assert [it["id"] for it in feedback.applied_items(["b", "c"])] == ["b"]

    assert [it["id"] for it in feedback.pending_items()] == ["r"]
    assert "one month" not in yaml.safe_dump(feedback.build_package(feedback.pending_items()))

    args = feedback.build_parser().parse_args(["applied", "--id", "a"])
    args.func(args)
    printed = yaml.safe_load(capsys.readouterr().out)
    assert [it["applied_comment"] for it in printed["applied"]] == ["Q: notice period? A: one month"]


def test_a_text_counts_for_its_own_status_only(isolated_data_dir, capsys):
    """Task 0132: the texts outlive their status; a reading takes the text of
    the status the vacancy has now, and off-status texts only on request."""
    import ai_brief

    sel = _setup({"a": "new", "b": "new", "c": "new", "d": "new"})
    _mark("a", "applied", sel, reason="Q: notice? A: a month")            # counts
    _mark("b", "applied", sel, reason="Q: visa? A: none")
    _mark("b", "new", sel)                                                # undone: off-status
    _mark("c", "applied", sel, reason="Q: salary? A: 5000")
    _mark("c", "new", sel)
    _mark("c", "rejected", sel, reason="relocation")                      # now "not for me"
    _mark("d", "bugged", sel, reason="a Java role")
    _mark("d", "new", sel)
    _mark("d", "rejected", sel, reason=None)                              # the bugged text is off-status
    with db.session() as conn:
        kept = dict(conn.execute("SELECT vacancy_id, COALESCE(applied_comment, bugged_reason) "
                                 "FROM vacancy_identity WHERE identity_id = 'ftf'").fetchall())
    assert kept == {"a": "Q: notice? A: a month", "b": "Q: visa? A: none",
                    "c": "Q: salary? A: 5000", "d": "a Java role"}, "nothing was erased"

    assert [it["id"] for it in feedback.applied_items()] == ["a"]
    both = {it["id"]: it["off_status"] for it in feedback.applied_items(off_status="include")}
    assert both == {"a": False, "b": True, "c": True}
    assert sorted(it["id"] for it in feedback.applied_items(off_status="only")) == ["b", "c"]
    with pytest.raises(ValueError):
        feedback.applied_items(off_status="all")

    reasons = {it["id"]: it["reason"] for it in feedback.pending_items()}
    assert reasons == {"c": "relocation", "d": None}
    assert ai_brief.feedback_reasons("ftf") == ["Developer c | Company c | rejected: relocation"]

    args = feedback.build_parser().parse_args(["applied", "--off-status", "only"])
    args.func(args)
    printed = yaml.safe_load(capsys.readouterr().out)
    assert sorted(it["id"] for it in printed["applied"]) == ["b", "c"]


def test_the_agents_reject_keeps_the_other_texts(isolated_data_dir):
    sel = _setup({"a": "new"})
    _mark("a", "bugged", sel, reason="a Java role")
    _mark("a", "new", sel)
    assert feedback.reject("a", "onsite only")
    with db.session() as conn:
        row = conn.execute("SELECT feedback_status, rejected_reason, bugged_reason FROM vacancy_identity "
                           "WHERE identity_id = 'ftf' AND vacancy_id = 'a'").fetchone()
    assert tuple(row) == ("rejected", "onsite only", "a Java role")


def test_no_applications_without_a_base(isolated_data_dir):
    assert feedback.applied_items() == []
