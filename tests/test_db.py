"""The shared SQLite knowledge base (tools/db.py): the dict contract the rest
of the code relies on, the split between what a vacancy is and what one
identity thinks of it, and column ownership between the pipeline and the app."""
import json
import sqlite3
import threading
import time

import pytest

import common
import db
import kb


def _vacancy(vid, title="Senior .NET Developer", **extra):
    return {"id": vid, "title": title, "company": "Acme",
            "computed": {"score": 50, "classification": "worth_a_look"}, **extra}


def _set_feedback(vid, status, reason=None, identity="ftf"):
    """What the app does — the only other writer of vacancy_identity."""
    column = {"rejected": "rejected_reason", "bugged": "bugged_reason"}.get(status)
    with db.session() as conn:
        conn.execute("UPDATE vacancy_identity SET feedback_status = ?, "
                     "feedback_at = '2026-09-29' WHERE identity_id = ? AND vacancy_id = ?",
                     (status, identity, vid))
        if column:
            conn.execute(f"UPDATE vacancy_identity SET {column} = ? "
                         "WHERE identity_id = ? AND vacancy_id = ?", (reason, identity, vid))


def _feedback(vid, identity="ftf"):
    """The feedback columns of one vacancy, or None when it has none."""
    if not db.exists():
        return None
    with db.session() as conn:
        row = conn.execute(
            "SELECT feedback_status, rejected_reason, bugged_reason FROM vacancy_identity "
            "WHERE identity_id = ? AND vacancy_id = ? AND feedback_status <> 'new'",
            (identity, vid)).fetchone()
    return dict(zip(("status", "rejected_reason", "bugged_reason"), row)) if row else None


def _as(monkeypatch, prefix):
    """Another identity looking at the same base. Only the prefix matters to
    the storage layer; activating a real second identity is what
    test_identity_isolation.py does."""
    monkeypatch.setattr(common, "ACTIVE_IDENTITY", prefix)


def test_vacancies_round_trip_unchanged(isolated_data_dir):
    vacancies = {
        "a1": _vacancy("a1", title="\u0420\u0430\u0437\u0440\u0430\u0431\u043e\u0442\u0447\u0438\u043a .NET", tags=["market:uk"]),
        "b2": _vacancy("b2", salary_raw=None, remote=True, duplicate_of="a1"),
    }
    kb.save_vacancies(vacancies)
    assert kb.load_vacancies() == vacancies


def test_the_vacancy_is_stored_once_and_the_verdict_per_identity(isolated_data_dir):
    kb.save_vacancies({"a1": _vacancy("a1", _company_reputation={"overall_rating": 4})})
    with db.session() as conn:
        data = json.loads(conn.execute("SELECT data FROM vacancies").fetchone()[0])
        verdict = conn.execute(
            "SELECT identity_id, score, class, json_extract(computed, '$.score') "
            "FROM vacancy_identity").fetchall()
    assert "computed" not in data, "the score belongs to the identity, not the vacancy"
    assert "_company_reputation" not in data, "copied for scoring, kept in companies"
    assert verdict == [("ftf", 50, "worth_a_look", 50)]


def test_another_identity_sees_the_vacancy_but_not_the_verdict(isolated_data_dir, monkeypatch):
    """The owner, 2026-10-05: a vacancy is one entity, its score one per
    identity. A vacancy one identity fetched is there for the next one to
    score; the first one's score and the person's answer are not."""
    kb.save_vacancies({"a1": _vacancy("a1", duplicate_of="zz")})
    _set_feedback("a1", "rejected", "too much travel")

    _as(monkeypatch, "other")
    seen = kb.load_vacancies()
    assert seen["a1"]["title"] == "Senior .NET Developer"
    assert "computed" not in seen["a1"] and "duplicate_of" not in seen["a1"]

    kb.save_vacancies({"a1": {**seen["a1"], "computed": {"score": 80,
                                                         "classification": "hot_lead"}}})
    assert _feedback("a1", identity="other") is None

    _as(monkeypatch, "ftf")
    mine = kb.load_vacancies()["a1"]
    assert mine["computed"]["score"] == 50 and mine["duplicate_of"] == "zz"
    assert _feedback("a1")["rejected_reason"] == "too much travel"


def test_a_fact_learned_under_one_identity_is_there_for_the_other(isolated_data_dir, monkeypatch):
    kb.save_vacancies({"a1": _vacancy("a1")})
    _as(monkeypatch, "other")
    record = kb.load_vacancies()["a1"]
    record["description_text"] = "The page, read once."
    kb.save_vacancies({"a1": record})
    _as(monkeypatch, "ftf")
    assert kb.load_vacancies()["a1"]["description_text"] == "The page, read once."


def test_companies_round_trip_and_are_replaced_whole(isolated_data_dir):
    kb.save_companies({"acme": {"name": "Acme"}, "old": {"name": "Old"}})
    kb.save_companies({"acme": {"name": "Acme", "notes": "x"}})
    assert kb.load_companies() == {"acme": {"name": "Acme", "notes": "x"}}


def test_missing_database_reads_as_empty_without_creating_it(isolated_data_dir):
    assert kb.load_vacancies() == {}
    assert kb.load_companies() == {}
    assert _feedback("a1") is None
    assert not common.DB_PATH.exists()


def test_save_does_not_overwrite_feedback(isolated_data_dir):
    kb.save_vacancies({"a1": _vacancy("a1")})
    _set_feedback("a1", "bugged", "Java, not .NET")

    kb.save_vacancies({"a1": _vacancy("a1", title="Senior .NET Developer (updated)")})

    assert kb.load_vacancies()["a1"]["title"] == "Senior .NET Developer (updated)"
    feedback = _feedback("a1")
    assert feedback["status"] == "bugged"
    assert feedback["bugged_reason"] == "Java, not .NET"


def test_feedback_stays_out_of_vacancy_records(isolated_data_dir):
    """Vacancy records feed the scorer; feedback must not leak into them."""
    kb.save_vacancies({"a1": _vacancy("a1"), "b2": _vacancy("b2")})
    _set_feedback("a1", "rejected", "too much travel")
    assert "feedback" not in kb.load_vacancies()["a1"]
    assert _feedback("a1")["status"] == "rejected" and _feedback("b2") is None


def test_feedback_written_during_a_pipeline_save_is_not_lost(isolated_data_dir):
    kb.save_vacancies({"a1": _vacancy("a1"), "b2": _vacancy("b2")})

    pipeline = db.connect()
    pipeline.execute("BEGIN IMMEDIATE")
    pipeline.execute("UPDATE vacancies SET data = ? WHERE id = 'b2'",
                     (json.dumps({"id": "b2", "title": "changed"}),))

    errors = []

    def app_click():
        try:
            _set_feedback("a1", "applied")
        except Exception as exc:  # noqa: BLE001 — reported through the assert below
            errors.append(exc)

    app = threading.Thread(target=app_click)
    app.start()
    time.sleep(0.3)          # the app is now waiting on the pipeline's lock
    pipeline.commit()
    pipeline.close()
    app.join(timeout=10)

    assert not errors
    assert _feedback("a1")["status"] == "applied"
    assert kb.load_vacancies()["b2"]["title"] == "changed"


def test_schema_rejects_unknown_feedback_status(isolated_data_dir):
    kb.save_vacancies({"a1": _vacancy("a1")})
    with pytest.raises(sqlite3.IntegrityError):
        _set_feedback("a1", "maybe")


def test_schema_version_mismatch_is_refused(isolated_data_dir):
    kb.save_vacancies({"a1": _vacancy("a1")})
    with db.session() as conn:
        conn.execute("UPDATE meta SET value = '999' WHERE key = 'schema_version'")
    with pytest.raises(db.SchemaVersionError):
        kb.load_vacancies()


def test_a_base_from_before_the_shared_one_is_refused_with_the_way_out(isolated_data_dir):
    """Versions 1-7 were one file per identity; they were merged once by a
    script, never upgraded in place — an upgrade could not know which
    identity the rows belong to."""
    kb.save_vacancies({"a1": _vacancy("a1")})
    with db.session() as conn:
        conn.execute("UPDATE meta SET value = '7' WHERE key = 'schema_version'")
    with pytest.raises(db.SchemaVersionError, match="merge_shared_base"):
        kb.load_vacancies()


def test_dump_gives_the_shortlist_with_full_descriptions(isolated_data_dir, capsys):
    """RUNBOOK step 1.5 reads full descriptions; the base is no longer a file
    one can open, so `kb.py dump` is the way in."""
    import argparse

    import yaml

    def shortlisted(vid, cls, score):
        return _vacancy(vid, computed={"score": score, "classification": cls},
                        description_text=f"Full text of {vid}")

    kb.save_vacancies({
        "h": shortlisted("h", "hot_lead", 70),
        "l": shortlisted("l", "long_shot", 30),
        "r": shortlisted("r", "rejected", 0),
        "d": {**shortlisted("d", "hot_lead", 90), "duplicate_of": "h"},
    })
    kb.cmd_dump(argparse.Namespace(id=None, min_class="long_shot"))
    records = yaml.safe_load(capsys.readouterr().out)
    assert [r["id"] for r in records] == ["h", "l"]
    assert records[0]["description_text"] == "Full text of h"

    kb.cmd_dump(argparse.Namespace(id=None, min_class="hot_lead"))
    assert [r["id"] for r in yaml.safe_load(capsys.readouterr().out)] == ["h"]
