"""tools/runstate.py: whether a pipeline run is going, kept in the database,
and never stuck at "running" after the run is gone."""
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


def test_a_run_of_another_identity_blocks_this_one_too(isolated_data_dir, monkeypatch):
    """The base is shared: a run saves the facts it loaded an hour earlier, so
    a second run — whichever identity it is for — would undo the first one's
    merges. The refusal names whose run is going."""
    import common

    with runstate.PipelineRun():
        monkeypatch.setattr(common, "ACTIVE_IDENTITY", "other")
        with pytest.raises(runstate.AlreadyRunningError, match="identity ftf"):
            with runstate.PipelineRun():
                pass
        assert runstate.current()["identity"] == "ftf"


def test_a_rebuild_is_marked_as_a_run_and_refused_while_another_is_alive(isolated_data_dir, monkeypatch, tmp_path):
    """ingest_manual.py loads and saves the whole base like a pipeline run: the
    app must see it, and it must not overlap another run (2026-10-12)."""
    import sys as _sys

    import ingest_manual

    empty = tmp_path / "empty.json"
    empty.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(_sys, "argv", ["ingest_manual.py", "--file", str(empty)])
    monkeypatch.setattr("identity.activate_or_exit", lambda *_: None)
    seen = {}

    def fake_ingest(records, source_name="manual"):
        seen["live"] = runstate.current()
        return {}

    monkeypatch.setattr(ingest_manual, "ingest", fake_ingest)
    ingest_manual.main()
    assert seen["live"] is not None
    assert runstate.current() is None

    with runstate.PipelineRun():
        with pytest.raises(SystemExit) as stop:
            ingest_manual.main()
    assert stop.value.code == 2
