"""tools/taskd.py: the workers that run the queue (task 0056) — with fake
processes for the queue rules, and real ones for the process handling."""
import json
import os
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

import pytest

import cv_batch
import taskd
import taskq

BOTH = ("desktop", "ai")


class FakeHandle:
    """A task's process: ends when told to, with the code it is given."""

    def __init__(self, task, on_line):
        self.task, self.on_line, self.pid = task, on_line, 5000 + task["id"]
        self.code = None
        self.stopped = self.forced = False
        on_line(f"fake {task['kind']}")

    def poll(self):
        return self.code

    def stop(self):
        self.stopped = True

    def force(self):
        self.forced = True

    def outcome(self, code):
        if self.stopped:
            return "stopped", "stopped", None
        return ("done", None, {"ok": True}) if code == 0 else ("failed", f"exit {code}", None)


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture
def made(isolated_data_dir, monkeypatch):
    monkeypatch.setattr(cv_batch, "paths", lambda data_root=None: {
        name: isolated_data_dir / f"cv_batch.{ext}" for name, ext in
        (("status", "json"), ("log", "log"), ("stop", "STOP"), ("pending", "pending"), ("hold", "HOLD"))})
    handles = {}
    said = []

    def worker(role="background", caps=("ai",), **kw):
        def start(task, on_line):
            handles[task["id"]] = FakeHandle(task, on_line)
            return handles[task["id"]]
        w = taskd.Worker(role, caps, start=start, kill=lambda pid: said.append(f"kill {pid}"),
                         awake=lambda on: said.append(f"awake {on}"), holder=lambda: None,
                         alive=lambda pid: True, say=said.append, **kw)
        w.pid = 100 if role == "background" else 200
        w.register()
        return w
    return worker, handles, said


def state(task_id):
    with taskq.session() as conn:
        return taskq.get(conn, task_id)


def add(kind, **kw):
    with taskq.session() as conn:
        return taskq.add(conn, kind, kw.pop("identity", "ftf"), origin="app", **kw)["task"]["id"]


def test_a_worker_runs_a_task_to_done_with_its_log(made):
    worker, handles, said = made
    w = worker()
    task_id = add("rest")
    w.tick()
    assert state(task_id)["state"] == "running" and state(task_id)["pid"] == handles[task_id].pid
    assert "awake True" in said
    handles[task_id].code = 0
    w.tick()
    done = state(task_id)
    assert (done["state"], done["result"]) == ("done", {"ok": True})
    log = Path(done["log_path"]).read_text(encoding="utf-8")
    assert "started by the background worker" in log and "fake rest" in log and "ended: done" in log
    assert said[-1] == "awake False"


def test_a_failed_process_fails_its_task_and_the_slot_goes_on(made):
    worker, handles, _ = made
    w = worker()
    first, second = add("rest"), add("clean", args={"ages": ["older"]})
    w.tick()
    assert second not in handles
    handles[first].code = 3
    w.tick()
    assert (state(first)["state"], state(first)["error"]) == ("failed", "exit 3")
    assert state(second)["state"] == "running"


def test_a_stop_from_the_panel_reaches_the_process(made):
    worker, handles, _ = made
    w = worker()
    task_id = add("linkedin")
    w.tick()
    with taskq.session() as conn:
        taskq.stop(conn, task_id)
    w.tick()
    assert handles[task_id].stopped
    handles[task_id].code = 1
    w.tick()
    assert state(task_id)["state"] == "stopped"


def test_a_task_that_cannot_start_fails_alone(made, monkeypatch):
    worker, _, said = made
    w = worker()
    w.start = lambda task, on_line: taskd.Process(task, taskd.command(task), on_line)
    with taskq.session() as conn:
        bad = taskq.add(conn, "clean", "ftf", origin="app", args={"ages": []})["task"]["id"]
    w.tick()
    assert state(bad)["state"] == "failed"
    assert state(bad)["error"] == "not started: a clean-up names at least one filter"


def test_one_worker_per_role(made):
    worker, _, _ = made
    worker()
    with pytest.raises(taskd.AnotherWorker):
        w = taskd.Worker("background", ("ai",), start=None, alive=lambda pid: True, say=lambda s: None)
        w.pid = 101
        w.register()


def test_a_worker_that_restarts_queues_its_last_tasks_again(made):
    worker, handles, said = made
    w = worker()
    task_id = add("rest")
    w.tick()
    with taskq.session() as conn:
        conn.execute("UPDATE workers SET heartbeat_at = ?", (taskq.iso(taskq.now() - timedelta(minutes=5)),))
    again = worker()
    assert f"kill {handles[task_id].pid}" in said
    assert state(task_id)["state"] == "queued"
    again.tick()
    assert state(task_id)["state"] == "running" and state(task_id)["attempts"] == 2


def test_the_desktop_worker_takes_the_cv_while_the_background_one_runs_the_collection(made):
    worker, handles, _ = made
    back, desk = worker(), worker("desktop", BOTH)
    rest, cv = add("rest"), add("cv", vacancy_id="v1")
    desk.tick()
    back.tick()
    assert state(rest)["worker"] == "background" and state(cv)["worker"] == "desktop"


def test_after_a_sleep_no_task_of_another_worker_is_declared_dead_at_once(made):
    worker, handles, said = made
    clock = Clock()
    back = worker(wall=clock)
    desk = worker("desktop", BOTH, wall=clock)
    rest = add("rest")
    back.tick()
    desk.tick()
    # the machine sleeps an hour: every beat is old
    with taskq.session() as conn:
        old = taskq.iso(taskq.now() - timedelta(hours=1))
        conn.execute("UPDATE tasks SET heartbeat_at = ?", (old,))
        conn.execute("UPDATE workers SET heartbeat_at = ?", (old,))
    clock.t += 3600
    desk.tick()
    assert state(rest)["state"] == "running"
    assert any("sleep?" in line for line in said)
    back.tick()
    assert not taskq.is_stale(state(rest)["heartbeat_at"])


def test_a_dead_worker_task_is_swept_by_the_other_worker(made):
    worker, handles, said = made
    back, desk = worker(), worker("desktop", BOTH)
    rest = add("rest")
    back.tick()
    with taskq.session() as conn:
        conn.execute("UPDATE tasks SET heartbeat_at = ?", (taskq.iso(taskq.now() - timedelta(minutes=5)),))
        conn.execute("UPDATE workers SET heartbeat_at = ? WHERE role = 'background'",
                     (taskq.iso(taskq.now() - timedelta(minutes=5)),))
    desk.tick()
    # queued again, and the desktop worker took it, the background one being gone
    assert state(rest)["state"] == "running" and state(rest)["worker"] == "desktop"
    assert f"kill {handles[rest].pid}" in said


def test_a_cv_asked_in_the_app_goes_while_the_batch_pauses(made, isolated_data_dir):
    worker, handles, _ = made
    desk = worker("desktop", BOTH)
    batch = add("cv_batch")
    desk.tick()
    cv = add("cv", vacancy_id="v1")
    desk.tick()
    hold = isolated_data_dir / "cv_batch.HOLD"
    assert hold.read_text(encoding="utf-8") == "200"
    assert state(cv)["state"] == "queued"
    (isolated_data_dir / "cv_batch.json").write_text(json.dumps({"state": "running", "holding": True}),
                                                     encoding="utf-8")
    desk.tick()
    desk.tick()
    assert state(cv)["state"] == "running" and state(batch)["state"] == "running"
    handles[cv].code = 0
    desk.tick()
    (isolated_data_dir / "cv_batch.json").write_text(json.dumps({"state": "running", "holding": False}),
                                                     encoding="utf-8")
    desk.tick()
    assert not hold.exists()


def test_stopping_the_worker_queues_its_tasks_again(made):
    worker, handles, said = made
    w = worker()
    rest = add("rest")
    w.tick()
    w.stop_all("its background worker was stopped; queued again")
    assert handles[rest].forced and state(rest)["state"] == "queued"
    assert said[-1] == "awake False"


# --- commands ---------------------------------------------------------------------

def task(kind, **fields):
    return {"id": 7, "kind": kind, "identity": "ftf", "vacancy_id": None, "args": {}, **fields}


def test_the_commands_of_each_kind():
    py = "py"
    tools = lambda name: str(Path("tools") / name)  # noqa: E731
    collect = taskd.command(task("collect"), python=py, claude="claude")
    assert collect.argv[:3] == ["claude", "-p", "/top ftf"] and "stream-json" in collect.argv
    assert collect.follow_dir.parts[-3:] == ("identities", "ftf", "runs")
    assert taskd.command(task("rest"), python=py).argv == [py, tools("pipeline.py"), "--identity", "ftf", "--rest"]
    assert taskd.command(task("linkedin"), python=py).argv[-1] == "--linkedin"
    assert taskd.command(task("pipeline", args={"mode": "top"}), python=py).argv[-1] == "--top"
    clean = taskd.command(task("clean", args={"ages": ["older"], "statuses": ["expired"]}), python=py)
    assert clean.argv[2:] == ["--identity", "ftf", "--json", "--ages", "older", "--statuses", "expired"]
    cv = taskd.command(task("cv", vacancy_id="abc123", args={"instructions": " shorter "}), python=py)
    assert cv.argv == [py, tools("cv_tailor.py"), "--identity", "ftf", "--vacancy", "abc123", "--json",
                       "--instructions", "shorter"] and cv.result_json
    assert taskd.command(task("letter", vacancy_id="abc"), python=py).argv[1] == tools("cover_letter.py")
    batch = taskd.command(task("cv_batch", args={"all": True}), python=py)
    assert batch.argv == [py, tools("cv_batch.py"), "ftf", "--all"] and batch.graceful_stop
    assert taskd.command(task("reputation", vacancy_id="v1"), python=py).argv[1] == tools("reputation_lookup.py")


@pytest.mark.parametrize("bad", [
    task("rest", identity="../x"), task("cv", vacancy_id="a b"), task("cv", vacancy_id=None),
    task("clean", args={"ages": ["older; rm"]}), task("clean"), task("dance"),
    task("cv", vacancy_id="v", args={"instructions": "x" * 9000})])
def test_a_task_that_does_not_fit_has_no_command(bad):
    with pytest.raises(ValueError):
        taskd.command(bad, python="py", claude="claude")


def test_a_collection_without_claude_says_so(monkeypatch):
    monkeypatch.setattr(taskd, "claude_executable", lambda: None)
    with pytest.raises(RuntimeError, match="claude"):
        taskd.command(task("collect"), python="py")


def test_agent_events_read_as_log_lines():
    text = json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": " Collecting. "},
        {"type": "tool_use", "name": "Bash", "input": {"command": "python   tools/pipeline.py --top"}}]}})
    assert taskd.describe_event(text) == "Collecting.\n> Bash: python tools/pipeline.py --top"
    result = json.dumps({"type": "result", "subtype": "success", "total_cost_usd": 1.234, "result": "ok"})
    assert taskd.describe_event(result) == "= success ($1.23)\nok"
    assert taskd.describe_event(json.dumps({"type": "system"})) is None
    assert taskd.describe_event("plain") == "plain"
    assert taskd.describe_event("[1, 2]") is None


def test_pipeline_progress_lines_are_prefixed_for_the_step_list():
    assert taskd.pipeline_line("[04:14:11] >> check links") == "  | [04:14:11] >> check links"
    assert taskd.pipeline_line("Pipeline finished:") == "Pipeline finished:"


# --- real processes -----------------------------------------------------------------

def run_until_ended(handle, limit=20):
    since = time.monotonic()
    while handle.poll() is None:
        assert time.monotonic() - since < limit
        time.sleep(0.05)
    return handle.poll()


def test_a_real_process_logs_its_lines_and_its_result(isolated_data_dir):
    lines = []
    script = "import sys; print('[10:00:00] >> fetch'); print('note', file=sys.stderr); print('{\"ok\": true, \"path\": \"x\"}')"
    cmd = taskd.Command([sys.executable, "-c", script], map_line=taskd.pipeline_line, result_json=True)
    handle = taskd.Process(task("rest"), cmd, lines.append)
    code = run_until_ended(handle)
    assert handle.outcome(code) == ("done", None, {"ok": True, "path": "x"})
    assert "  | [10:00:00] >> fetch" in lines and "note" in lines


def test_a_real_process_gets_the_task_id_in_its_environment(isolated_data_dir):
    lines = []
    cmd = taskd.Command([sys.executable, "-c", f"import os; print(os.environ['{taskq.TASK_ENV}'])"])
    run_until_ended(taskd.Process(task("rest"), cmd, lines.append))
    assert lines == ["7"]


def test_a_tool_that_answers_ok_false_fails_its_task(isolated_data_dir):
    cmd = taskd.Command([sys.executable, "-c", "print('{\"ok\": false, \"error\": \"Vacancy not found\"}')"],
                        result_json=True)
    handle = taskd.Process(task("cv"), cmd, lambda s: None)
    assert handle.outcome(run_until_ended(handle))[:2] == ("failed", "Vacancy not found")


def test_a_real_process_is_killed_with_its_children_on_stop(isolated_data_dir):
    cmd = taskd.Command([sys.executable, "-c", "import time; time.sleep(60)"])
    handle = taskd.Process(task("rest"), cmd, lambda s: None)
    handle.stop()
    assert handle.outcome(run_until_ended(handle))[0] == "stopped"


def test_the_pipeline_log_is_followed_during_a_collection(isolated_data_dir, tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "pipeline_old.log").write_text("[09:00:00] >> old run\n", encoding="utf-8")
    old = time.time() - 3600
    import os
    os.utime(runs / "pipeline_old.log", (old, old))
    script = ("import time, pathlib; time.sleep(0.3); "
              f"pathlib.Path(r'{runs / 'pipeline_new.log'}').write_text('[10:00:00] >> fetch\\n'); time.sleep(1.5)")
    lines = []
    cmd = taskd.Command([sys.executable, "-c", script], follow_dir=runs)
    run_until_ended(taskd.Process(task("collect"), cmd, lines.append))
    assert lines == ["  | [10:00:00] >> fetch"]


# --- the machine and Task Scheduler --------------------------------------------------

def test_a_worker_started_for_the_app_returns_at_once_and_holds_no_pipe_of_its_caller(tmp_path):
    """`taskd.py start` returns while the worker it started goes on: had the
    worker inherited the caller's stdout, `subprocess.run` would wait for it."""
    env = {**os.environ, "WORK_IDE_DATA_ROOT": str(tmp_path), "WORK_IDE_FAKE_RUNNER": "1",
           "PYTHONIOENCODING": "utf-8"}
    env.pop(taskq.TASK_ENV, None)
    since = time.monotonic()
    done = subprocess.run([sys.executable, str(Path(taskd.__file__)), "start", "--role", "desktop",
                           "--idle-exit", "60"], capture_output=True, text=True, env=env, timeout=50)
    assert done.returncode == 0, done.stderr
    assert time.monotonic() - since < 30
    pid = json.loads(done.stdout)["pid"]
    log = tmp_path / "tasks" / "worker_desktop.log"
    try:
        while "desktop worker started" not in (log.read_text(encoding="utf-8") if log.exists() else ""):
            assert time.monotonic() - since < 40, "the worker did not start"
            time.sleep(0.2)
    finally:
        taskd.kill_tree(pid)


def test_the_scheduled_tasks_store_no_password_and_restart():
    root, py = Path("C:/repo"), "C:/repo/.venv/Scripts/python.exe"
    back = taskd.task_xml("background", root=root, python=py, user="PC\\me")
    desk = taskd.task_xml("desktop", root=root, python=py, user="PC\\me")
    assert "<LogonType>S4U</LogonType>" in back and "<BootTrigger>" in back
    assert "<LogonType>InteractiveToken</LogonType>" in desk and "<LogonTrigger>" in desk
    for xml in (back, desk):
        assert "Password" not in xml
        assert "<RestartOnFailure><Interval>PT1M</Interval>" in xml
        assert "<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>" in xml
        assert "<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>" in xml
        assert "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>" in xml


def test_install_without_elevation_says_how(capsys):
    calls = []

    def run(argv, **kw):
        calls.append(argv)
        if argv[1] == "/Create" and "background" in argv[3]:
            return subprocess.CompletedProcess(argv, 1, "", "ERROR: Access is denied.")
        return subprocess.CompletedProcess(argv, 0, "SUCCESS", "")
    assert taskd.install(["background", "desktop"], run=run) == 1
    out = capsys.readouterr().out
    assert "background: not registered: ERROR: Access is denied." in out and "Run as administrator" in out
    assert "desktop: registered" in out
    assert ["schtasks", "/Run", "/TN", taskd.TASK_NAMES["desktop"]] in calls


@pytest.mark.parametrize("stdout,stderr,expected", [
    ('{"type":"result","is_error":false,"result":"OK"}', "", True),
    ('{"type":"result","is_error":true,"result":"Not logged in"}', "", False),
    ("", "Claude usage limit reached. Your limit will reset at 5pm", True),
    ("", "Invalid API key", False)])
def test_the_ai_probe(stdout, stderr, expected):
    run = lambda argv, **kw: subprocess.CompletedProcess(argv, 0, stdout, stderr)  # noqa: E731
    assert taskd.probe_ai("claude", run=run)[0] is expected


def test_the_ai_probe_without_claude():
    def run(argv, **kw):
        raise FileNotFoundError("claude")
    assert taskd.probe_ai("claude", run=run)[0] is False
