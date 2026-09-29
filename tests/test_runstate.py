"""tools/runstate.py: whether a pipeline run is going, kept in the database,
and never stuck at "running" after the run is gone."""
import sqlite3
import time

import pytest

import db
import kb
import progress
import runstate


def _rows():
    with db.session() as conn:
        return conn.execute(
            "SELECT status, stage, error FROM pipeline_runs ORDER BY id").fetchall()


def test_a_run_is_marked_while_going_and_cleared_after(isolated_data_dir):
    with runstate.PipelineRun():
        with progress.stage("check links"):
            live = runstate.current()
    assert live is not None and live["pid"]
    assert runstate.current() is None
    assert _rows() == [("finished", "check links", None)]


def test_a_failing_run_is_rolled_back_to_failed_and_the_error_kept(isolated_data_dir):
    with pytest.raises(RuntimeError):
        with runstate.PipelineRun():
            raise RuntimeError("network down")
    assert runstate.current() is None
    assert _rows() == [("failed", None, "RuntimeError: network down")]


def test_a_second_run_of_the_same_identity_is_refused(isolated_data_dir):
    with runstate.PipelineRun():
        with pytest.raises(runstate.AlreadyRunningError):
            with runstate.PipelineRun():
                pass
    assert [r[0] for r in _rows()] == ["finished"]


def test_a_killed_run_goes_stale_and_the_next_run_marks_it_interrupted(isolated_data_dir):
    """A hard kill skips `finally`: the row stays 'running' but stops beating."""
    kb.save_vacancies({})
    with db.session() as conn:
        conn.execute("INSERT INTO pipeline_runs (started_at, heartbeat_at, status, pid) "
                     "VALUES ('2026-09-29T10:00:00+00:00', '2026-09-29T10:00:00+00:00', "
                     "'running', 999999)")
    assert runstate.current() is None, "a silent run is not shown as going"
    with runstate.PipelineRun():
        pass
    assert [r[0] for r in _rows()] == ["interrupted", "finished"]


def test_the_heartbeat_records_the_current_stage(isolated_data_dir, monkeypatch):
    monkeypatch.setattr(runstate, "HEARTBEAT_SECONDS", 0.05)
    with runstate.PipelineRun():
        with progress.stage("rescore the base"):
            time.sleep(0.3)
            with db.session() as conn:
                (stage,) = conn.execute("SELECT stage FROM pipeline_runs").fetchone()
    assert stage == "rescore the base"


def test_staleness_threshold():
    assert runstate.is_stale("2026-09-29T10:00:00+00:00")
    assert runstate.is_stale("not a date")
    assert not runstate.is_stale(runstate._iso(runstate._now()))


def test_a_version_1_database_is_upgraded_in_place(isolated_data_dir):
    kb.save_vacancies({"a": {"id": "a"}})
    raw = sqlite3.connect(str(db.db_path()))
    raw.execute("DROP TABLE pipeline_runs")
    raw.execute("UPDATE meta SET value = '1' WHERE key = 'schema_version'")
    raw.commit()
    raw.close()

    assert kb.load_vacancies() == {"a": {"id": "a"}}
    with db.session() as conn:
        assert conn.execute("SELECT value FROM meta WHERE key = 'schema_version'"
                            ).fetchone()[0] == str(db.SCHEMA_VERSION)
        conn.execute("SELECT COUNT(*) FROM pipeline_runs").fetchone()
