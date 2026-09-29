"""The SQLite knowledge base (tools/db.py): the dict contract the rest of the
code relies on, column ownership between the pipeline and the app, and the
one-off migration from the JSON files."""
import json
import sqlite3
import threading
import time

import pytest

import common
import db
import kb


def _vacancy(vid, title="Senior .NET Developer", **extra):
    return {"id": vid, "title": title, "company": "Acme", "computed": {"score": 50}, **extra}


def _set_feedback(vid, status, reason=None):
    """What the app does — the only other writer of the vacancies table."""
    column = {"rejected": "rejected_reason", "bugged": "bugged_reason"}.get(status)
    with db.session() as conn:
        conn.execute("UPDATE vacancies SET feedback_status = ?, feedback_at = '2026-09-29' "
                     "WHERE id = ?", (status, vid))
        if column:
            conn.execute(f"UPDATE vacancies SET {column} = ? WHERE id = ?", (reason, vid))


def test_vacancies_round_trip_unchanged(isolated_data_dir):
    vacancies = {
        "a1": _vacancy("a1", title="\u0420\u0430\u0437\u0440\u0430\u0431\u043e\u0442\u0447\u0438\u043a .NET", tags=["market:uk"], manual={"status": "new"}),
        "b2": _vacancy("b2", salary_raw=None, remote=True),
    }
    kb.save_vacancies(vacancies)
    assert kb.load_vacancies() == vacancies


def test_companies_round_trip_and_are_replaced_whole(isolated_data_dir):
    kb.save_companies({"acme": {"name": "Acme"}, "old": {"name": "Old"}})
    kb.save_companies({"acme": {"name": "Acme", "notes": "x"}})
    assert kb.load_companies() == {"acme": {"name": "Acme", "notes": "x"}}


def test_missing_database_reads_as_empty_without_creating_it(isolated_data_dir):
    assert kb.load_vacancies() == {}
    assert kb.load_companies() == {}
    assert db.load_feedback() == {}
    assert not common.DB_PATH.exists()


def test_save_does_not_overwrite_feedback(isolated_data_dir):
    kb.save_vacancies({"a1": _vacancy("a1")})
    _set_feedback("a1", "bugged", "Java, not .NET")

    kb.save_vacancies({"a1": _vacancy("a1", title="Senior .NET Developer (updated)")})

    assert kb.load_vacancies()["a1"]["title"] == "Senior .NET Developer (updated)"
    feedback = db.load_feedback()["a1"]
    assert feedback["status"] == "bugged"
    assert feedback["bugged_reason"] == "Java, not .NET"


def test_feedback_stays_out_of_vacancy_records(isolated_data_dir):
    """Vacancy records feed the scorer; feedback must not leak into them."""
    kb.save_vacancies({"a1": _vacancy("a1"), "b2": _vacancy("b2")})
    _set_feedback("a1", "rejected", "too much travel")
    assert "feedback" not in kb.load_vacancies()["a1"]
    assert set(db.load_feedback()) == {"a1"}


def test_feedback_written_during_a_pipeline_save_is_not_lost(isolated_data_dir):
    kb.save_vacancies({"a1": _vacancy("a1"), "b2": _vacancy("b2")})

    pipeline = db.connect()
    pipeline.execute("BEGIN IMMEDIATE")
    pipeline.execute("UPDATE vacancies SET data = ? WHERE id = 'b2'",
                     (json.dumps(_vacancy("b2", title="changed")),))

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
    assert db.load_feedback()["a1"]["status"] == "applied"
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


# --- Migration ---------------------------------------------------------------

def _write_legacy_json(vacancies, companies):
    common.KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    common.VACANCIES_PATH.write_text(json.dumps(vacancies), encoding="utf-8")
    common.COMPANIES_PATH.write_text(json.dumps(companies), encoding="utf-8")


def test_unmigrated_identity_refuses_instead_of_starting_empty(isolated_data_dir):
    _write_legacy_json({"a1": _vacancy("a1")}, {})
    with pytest.raises(db.NotMigratedError):
        kb.load_vacancies()
    with pytest.raises(db.NotMigratedError):
        kb.save_vacancies({})
    assert not common.DB_PATH.exists()


def test_migration_moves_everything_and_keeps_a_backup(isolated_data_dir):
    vacancies = {
        "a1": _vacancy("a1", manual={"status": "not_relevant", "notes": "Java shop"}),
        "b2": _vacancy("b2", manual={"status": "not_relevant", "notes": "  "}),
        "c3": _vacancy("c3", manual={"status": "shortlisted", "notes": "looks good"}),
        "d4": _vacancy("d4"),
    }
    companies = {"acme": {"name": "Acme"}}
    _write_legacy_json(vacancies, companies)

    result = db.migrate_from_json()

    assert result == {"vacancies": 4, "companies": 1, "rejected": 2}
    assert kb.load_vacancies() == vacancies          # manual stays in the record as is
    assert kb.load_companies() == companies
    feedback = db.load_feedback()
    assert set(feedback) == {"a1", "b2"}
    assert feedback["a1"]["status"] == "rejected"
    assert feedback["a1"]["rejected_reason"] == "Java shop"
    assert feedback["b2"]["rejected_reason"] is None  # a blank note is no reason
    assert not common.VACANCIES_PATH.exists()
    assert common.VACANCIES_PATH.with_name(common.VACANCIES_PATH.name + ".bak").exists()
    assert common.COMPANIES_PATH.with_name(common.COMPANIES_PATH.name + ".bak").exists()


def test_migration_refuses_to_run_twice(isolated_data_dir):
    _write_legacy_json({"a1": _vacancy("a1")}, {})
    db.migrate_from_json()
    with pytest.raises(RuntimeError):
        db.migrate_from_json()
