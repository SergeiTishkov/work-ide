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
    # Settled under the old process: not pending review in the new one.
    assert feedback["a1"]["reviewed_at"] == feedback["a1"]["at"]
    import feedback as feedback_mod
    assert feedback_mod.count() == {"bugged": 0, "rejected": 0}
    assert not common.VACANCIES_PATH.exists()
    assert common.VACANCIES_PATH.with_name(common.VACANCIES_PATH.name + ".bak").exists()
    assert common.COMPANIES_PATH.with_name(common.COMPANIES_PATH.name + ".bak").exists()


def test_migration_refuses_to_run_twice(isolated_data_dir):
    _write_legacy_json({"a1": _vacancy("a1")}, {})
    db.migrate_from_json()
    with pytest.raises(RuntimeError):
        db.migrate_from_json()


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


# The vacancies table exactly as schema version 2 defined it.
VERSION_2_VACANCIES = """CREATE TABLE vacancies_v2 (
  id                    TEXT PRIMARY KEY,
  data                  TEXT NOT NULL,
  view                  TEXT,
  feedback_status       TEXT NOT NULL DEFAULT 'new'
                        CHECK (feedback_status IN ('new', 'applied', 'rejected', 'bugged')),
  rejected_reason       TEXT,
  bugged_reason         TEXT,
  feedback_at           TEXT,
  feedback_selection_id INTEGER REFERENCES selections(id),
  feedback_reviewed_at  TEXT
)"""


def _downgrade_to_version_2(path):
    """Rebuilds the vacancies table the way schema 2 defined it (the rename
    leaves its stored definition quoted, as a real rename would)."""
    raw = sqlite3.connect(str(path))
    raw.execute("PRAGMA foreign_keys = OFF")
    raw.execute(VERSION_2_VACANCIES)
    columns = ("id, data, view, feedback_status, rejected_reason, bugged_reason, "
               "feedback_at, feedback_selection_id, feedback_reviewed_at")
    raw.execute(f"INSERT INTO vacancies_v2 ({columns}) SELECT {columns} FROM vacancies")
    raw.execute("DROP TABLE vacancies")
    raw.execute("ALTER TABLE vacancies_v2 RENAME TO vacancies")
    raw.execute("UPDATE meta SET value = '2' WHERE key = 'schema_version'")
    raw.commit()
    raw.close()


def test_version_2_is_migrated_to_the_current_table_keeping_everything(isolated_data_dir):
    import selections

    listed = {"score": 60, "classification": "hot_lead", "score_breakdown": {}, "dealbreakers": []}
    vacancies = {"a": _vacancy("a", computed=listed), "b": _vacancy("b", computed=listed)}
    kb.save_vacancies(vacancies)
    sel = selections.record(vacancies, {"run_count": 1})
    _set_feedback("a", "rejected", "too much travel")
    _downgrade_to_version_2(db.db_path())

    raw = sqlite3.connect(str(db.db_path()))
    with pytest.raises(sqlite3.IntegrityError):
        raw.execute("UPDATE vacancies SET feedback_status = 'expired' WHERE id = 'b'")
    raw.close()

    assert kb.load_vacancies() == vacancies          # any access migrates
    with db.session() as conn:
        assert conn.execute("SELECT value FROM meta WHERE key = 'schema_version'"
                            ).fetchone()[0] == str(db.SCHEMA_VERSION)
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        items = conn.execute("SELECT COUNT(*) FROM selection_items WHERE selection_id = ?",
                             (sel,)).fetchone()[0]
    assert items == 2, "the selection's rows still point at the vacancies"
    assert db.load_feedback()["a"]["rejected_reason"] == "too much travel"
    _set_feedback("b", "expired")
    assert db.load_feedback()["b"]["status"] == "expired"
    with db.session() as conn:
        conn.execute("UPDATE vacancies SET feedback_status = 'interview', "
                     "interview_comments = '[\"\"]' WHERE id = 'b'")   # the funnel columns exist


def test_migration_runs_once(isolated_data_dir):
    kb.save_vacancies({"a": _vacancy("a")})
    _downgrade_to_version_2(db.db_path())
    kb.load_vacancies()
    kb.load_vacancies()          # already at the latest version: nothing to redo
    with db.session() as conn:
        assert conn.execute("SELECT COUNT(*) FROM vacancies").fetchone()[0] == 1


def test_version_3_gains_the_funnel_keeping_expired_marks(isolated_data_dir):
    kb.save_vacancies({"a": _vacancy("a"), "b": _vacancy("b")})
    _set_feedback("a", "expired")
    raw = sqlite3.connect(str(db.db_path()))
    version_3 = VERSION_2_VACANCIES.replace("'bugged')", "'bugged', 'expired')").replace(
        "vacancies_v2", "vacancies_v3")
    raw.execute("PRAGMA foreign_keys = OFF")
    raw.execute(version_3)
    columns = ("id, data, view, feedback_status, rejected_reason, bugged_reason, "
               "feedback_at, feedback_selection_id, feedback_reviewed_at")
    raw.execute(f"INSERT INTO vacancies_v3 ({columns}) SELECT {columns} FROM vacancies")
    raw.execute("DROP TABLE vacancies")
    raw.execute("ALTER TABLE vacancies_v3 RENAME TO vacancies")
    raw.execute("UPDATE meta SET value = '3' WHERE key = 'schema_version'")
    raw.commit()
    raw.close()

    assert db.load_feedback()["a"]["status"] == "expired"
    with db.session() as conn:
        conn.execute("UPDATE vacancies SET feedback_status = 'awaiting_final', "
                     "final_comment = '' WHERE id = 'b'")
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_version_4_gains_views_in_every_language_keeping_the_rest(isolated_data_dir):
    import re

    kb.save_vacancies({"a": _vacancy("a")})
    _set_feedback("a", "rejected", "far too senior")
    schema = db.SCHEMA_PATH.read_text(encoding="utf-8")
    table = re.search(r"CREATE TABLE IF NOT EXISTS vacancies (\(.*?\n\));", schema, re.S).group(1)
    version_4 = "CREATE TABLE vacancies_v4 " + re.sub(r"\n\s*views\s+TEXT,", "", table)
    assert "views" not in re.sub(r"--[^\n]*", "", version_4)
    raw = sqlite3.connect(str(db.db_path()))
    raw.execute("PRAGMA foreign_keys = OFF")
    raw.execute(version_4)
    columns = ", ".join(row[1] for row in raw.execute("PRAGMA table_info(vacancies)")
                        if row[1] != "views")
    raw.execute(f"INSERT INTO vacancies_v4 ({columns}) SELECT {columns} FROM vacancies")
    raw.execute("DROP TABLE vacancies")
    raw.execute("ALTER TABLE vacancies_v4 RENAME TO vacancies")
    raw.execute("UPDATE meta SET value = '4' WHERE key = 'schema_version'")
    raw.commit()
    raw.close()

    assert db.load_feedback()["a"]["rejected_reason"] == "far too senior"
    with db.session() as conn:
        assert "views" in {row[1] for row in conn.execute("PRAGMA table_info(vacancies)")}
        assert conn.execute("SELECT value FROM meta WHERE key = 'schema_version'"
                            ).fetchone()[0] == str(db.SCHEMA_VERSION)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(vacancies)")}
        assert {"awaiting_offer_comment", "declined_at"} <= columns, "version 6 too"
        assert {"offered_comment", "started_at"} <= columns, "version 7 too"
        conn.execute("UPDATE vacancies SET feedback_status = 'declined', "
                     "declined_comment = '' WHERE id = 'a'")
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
