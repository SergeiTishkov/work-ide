"""
tools/cv_batch.py: the batch outside the app — its status file, which the
app's task panel reads, its log, the stop file, requests that join a running
batch, and the app going first.
"""
from __future__ import annotations

import json
import os

import pytest

import cv_batch

ITEMS = {
    "sharp": [{"vacancy_id": "a1", "title": "Dev", "company": "Acme", "documents": ["cv", "letter"]},
              {"vacancy_id": "a2", "title": "Old", "company": "Gone", "documents": ["cv"]}],
    "partsharp": [{"vacancy_id": "b1", "title": "Part", "company": "Beta", "documents": ["letter"]}],
}


def _plan(prefix):
    return ITEMS[prefix]


def _ask(*prefixes):
    return [{"identity": p} for p in prefixes]


def _status(where):
    return json.loads(where["status"].read_text(encoding="utf-8"))


def test_the_status_follows_each_document_and_ends_finished(tmp_path):
    where = cv_batch.paths(tmp_path)
    seen = []

    def generate(prefix, item, kind):
        status = _status(where)
        seen.append((status["index"], status["total"], status["current"]["vacancy_id"], kind))
        if item["vacancy_id"] == "a2":
            return {"ok": False, "error": "Vacancy not found, possibly outdated: the link is dead."}
        if prefix == "partsharp":
            return {"ok": False, "error": "Word failed"}
        return {"ok": True, "pages": 2}

    status = cv_batch.Batch(where).run(_ask("sharp", "partsharp"), _plan, generate)
    assert seen == [(1, 4, "a1", "cv"), (2, 4, "a1", "letter"), (3, 4, "a2", "cv"), (4, 4, "b1", "letter")]
    assert (status["state"], status["made"], status["gone"], status["failed"]) == ("finished", 2, 1, 1)
    assert status["current"] is None and status["pid"] == os.getpid()
    assert status["identities"] == ["sharp", "partsharp"]
    assert _status(where)["state"] == "finished"
    log = where["log"].read_text(encoding="utf-8")
    assert "sharp: 2 vacancies, 3 documents" in log
    assert "gone    cv Vacancy not found" in log and "FAILED  letter" in log
    assert "finished: 2 made, 1 gone, 1 failed" in log


def test_each_identity_reaches_the_plan(tmp_path):
    asked = []
    cv_batch.Batch(cv_batch.paths(tmp_path)).run(
        _ask("sharp", "partsharp"), lambda p: asked.append(p) or [], lambda *a: {"ok": True})
    assert asked == ["sharp", "partsharp"]


def test_a_stop_file_ends_the_batch_before_the_next_document(tmp_path):
    where = cv_batch.paths(tmp_path)

    def generate(prefix, item, kind):
        where["stop"].touch()
        return {"ok": True}

    status = cv_batch.Batch(where).run(_ask("sharp"), _plan, generate)
    assert (status["state"], status["made"], status["index"]) == ("stopped", 1, 1)
    assert not where["stop"].exists()
    assert "stopped before 2/3" in where["log"].read_text(encoding="utf-8")


def test_a_request_made_while_it_runs_joins_the_batch(tmp_path):
    where = cv_batch.paths(tmp_path)
    done = []

    def generate(prefix, item, kind):
        if not done:
            cv_batch.request(where, ["partsharp"])
        done.append((prefix, item["vacancy_id"], kind))
        return {"ok": True}

    status = cv_batch.Batch(where).run(_ask("sharp"), _plan, generate)
    assert done[-1] == ("partsharp", "b1", "letter")
    assert (status["total"], status["made"], status["identities"]) == (4, 4, ["sharp", "partsharp"])
    assert not where["pending"].exists()


def test_the_batch_waits_between_documents_while_the_app_holds(tmp_path):
    where = cv_batch.paths(tmp_path)
    where["hold"].write_text(str(os.getpid()), encoding="utf-8")
    holding = []

    def sleep(_seconds):
        holding.append(_status(where)["holding"])
        where["hold"].unlink()   # the app has made its documents

    batch = cv_batch.Batch(where, sleep=sleep)
    status = batch.run(_ask("partsharp"), _plan, lambda *a: {"ok": True})
    assert holding == [True]
    assert (status["holding"], status["made"]) == (False, 1)
    assert "paused: the app is generating documents" in where["log"].read_text(encoding="utf-8")


def test_a_hold_of_a_process_that_ended_is_ignored(tmp_path):
    where = cv_batch.paths(tmp_path)
    where["hold"].write_text(str(2 ** 30), encoding="utf-8")
    status = cv_batch.Batch(where, sleep=lambda s: pytest.fail("waited")).run(
        _ask("partsharp"), _plan, lambda *a: {"ok": True})
    assert status["made"] == 1


def test_a_second_batch_starts_where_its_lines_begin_and_clears_an_old_stop(tmp_path):
    where = cv_batch.paths(tmp_path)
    cv_batch.Batch(where).run(_ask("partsharp"), _plan, lambda *a: {"ok": True})
    size = where["log"].stat().st_size
    where["stop"].touch()   # left from before: a new start means go
    status = cv_batch.Batch(where).run(_ask("partsharp"), _plan, lambda *a: {"ok": True})
    assert status["log_offset"] == size and status["state"] == "finished"
    assert where["log"].read_text(encoding="utf-8")[size:].split("  ", 1)[1].startswith("start: partsharp")


def test_a_running_batch_is_not_started_twice_and_a_crash_is_recorded(tmp_path, monkeypatch):
    where = cv_batch.paths(tmp_path)
    where["status"].write_text(json.dumps({"state": "running", "pid": 4242}), encoding="utf-8")
    monkeypatch.setattr(cv_batch, "pid_alive", lambda pid: True)
    with pytest.raises(RuntimeError, match="running already"):
        cv_batch.Batch(where).run(_ask("sharp"), _plan, lambda *a: {"ok": True})

    monkeypatch.setattr(cv_batch, "pid_alive", lambda pid: False)

    def broken(prefix):
        raise ValueError("no database")

    with pytest.raises(ValueError):
        cv_batch.Batch(where).run(_ask("sharp"), broken, lambda *a: {"ok": True})
    status = _status(where)
    assert (status["state"], status["error"]) == ("crashed", "no database")


def test_started_by_hand_while_one_runs_the_request_joins_it(tmp_path, monkeypatch, capsys):
    where = cv_batch.paths(tmp_path)
    monkeypatch.setattr(cv_batch, "paths", lambda: where)
    monkeypatch.setattr(cv_batch, "pid_alive", lambda pid: True)
    where["status"].write_text(json.dumps({"state": "running", "pid": 4242}), encoding="utf-8")
    assert cv_batch.main(["sharp"]) == 0
    assert "queued behind the running batch (pid 4242)" in capsys.readouterr().out
    assert cv_batch.take_pending(where) == [{"identity": "sharp"}]


def test_this_process_is_alive_and_a_made_up_pid_is_not():
    assert cv_batch.pid_alive(os.getpid())
    assert not cv_batch.pid_alive(None)
    assert not cv_batch.pid_alive(2 ** 30)
