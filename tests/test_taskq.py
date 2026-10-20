"""tools/taskq.py: the task queue in data/tasks.sqlite (task 0056) — tasks are
listed whoever asks, run one per slot, wait for what they need with the
reason shown, and never stay "running" for a dead process."""
import json
from datetime import timedelta
from pathlib import Path

import pytest

import taskq

BOTH = ("desktop", "ai")


@pytest.fixture
def conn(isolated_data_dir):
    with taskq.session() as c:
        yield c


def worker(conn, role="background", caps=("ai",), at=None):
    """A live worker row, as tools/taskd.py writes it."""
    conn.execute(
        "INSERT INTO workers (role, pid, capabilities, heartbeat_at) VALUES (?, 1, ?, ?) "
        "ON CONFLICT(role) DO UPDATE SET capabilities = excluded.capabilities, heartbeat_at = excluded.heartbeat_at",
        (role, ",".join(caps), taskq.iso(at)))


def claim(conn, role="background", caps=("ai",), **kw):
    return taskq.claim(conn, role, caps, pid=4242, **kw)


def test_the_queue_lives_beside_the_isolated_base(isolated_data_dir):
    assert taskq.path() == isolated_data_dir / "tasks.sqlite"


def test_a_task_is_listed_with_its_slot_needs_and_origin(conn):
    added = taskq.add(conn, "rest", "ftf", origin="agent")
    task = added["task"]
    assert added["added"] and task["state"] == "queued"
    assert (task["slot"], task["needs"], task["origin"]) == ("collect", ["ai"], "agent")
    assert task["log_path"].endswith(f"tasks\\{task['id']}.log") or task["log_path"].endswith(f"tasks/{task['id']}.log")
    assert [t["id"] for t in taskq.tasks(conn)] == [task["id"]]


def test_the_same_task_is_not_queued_twice_but_another_vacancy_is(conn):
    first = taskq.add(conn, "cv", "ftf", vacancy_id="v1", origin="app")
    again = taskq.add(conn, "cv", "ftf", vacancy_id="v1", origin="app")
    other = taskq.add(conn, "cv", "ftf", vacancy_id="v2", origin="app")
    assert again == {"added": False, "task": first["task"]}
    assert other["added"]


@pytest.mark.parametrize("kind,identity,origin", [
    ("dance", "ftf", "app"), ("rest", "../x", "app"), ("rest", "ftf", "cron")])
def test_an_unknown_kind_identity_or_origin_is_refused(conn, kind, identity, origin):
    with pytest.raises(ValueError):
        taskq.add(conn, kind, identity, origin=origin)


def test_the_origin_is_the_agent_inside_claude_code_and_the_terminal_otherwise(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    assert taskq.default_origin() == "agent"
    monkeypatch.delenv("CLAUDECODE")
    assert taskq.default_origin() == "terminal"


def test_one_task_per_slot_and_linkedin_beside_a_collection(conn):
    worker(conn)
    rest = taskq.add(conn, "rest", "ftf", origin="app")["task"]
    clean = taskq.add(conn, "clean", "ftf", origin="app")["task"]
    linkedin = taskq.add(conn, "linkedin", "ftf", origin="app")["task"]
    assert claim(conn)["id"] == rest["id"]
    assert claim(conn)["id"] == linkedin["id"]
    assert claim(conn) is None
    assert taskq.get(conn, clean["id"])["waiting_for"] == f"#{rest['id']} to end"
    taskq.finish(conn, rest["id"], "done")
    assert claim(conn)["id"] == clean["id"]


def test_a_task_waits_for_the_desktop_with_the_reason_and_the_desktop_worker_takes_it(conn):
    worker(conn)
    cv = taskq.add(conn, "cv", "ftf", vacancy_id="v1", origin="app")["task"]
    assert claim(conn) is None
    assert "sign-in" in taskq.get(conn, cv["id"])["waiting_for"]
    worker(conn, "desktop", BOTH)
    taken = claim(conn, "desktop", BOTH)
    assert taken["id"] == cv["id"] and taken["worker"] == "desktop" and taken["attempts"] == 1


def test_ai_work_waits_for_sign_in_when_the_background_worker_has_no_ai(conn):
    worker(conn, caps=())
    top = taskq.add(conn, "collect", "ftf", origin="app")["task"]
    assert claim(conn, caps=()) is None
    assert taskq.get(conn, top["id"])["waiting_for"] == "the owner's sign-in: AI does not run without it"
    worker(conn, "desktop", BOTH)
    assert claim(conn, "desktop", BOTH)["id"] == top["id"]


def test_the_desktop_worker_leaves_to_the_background_one_what_it_can_run(conn):
    worker(conn)
    worker(conn, "desktop", BOTH)
    rest = taskq.add(conn, "rest", "ftf", origin="app")["task"]
    assert claim(conn, "desktop", BOTH) is None
    assert claim(conn)["id"] == rest["id"]


def test_the_desktop_worker_runs_everything_while_no_background_worker_lives(conn):
    worker(conn, at=taskq.now() - timedelta(minutes=5))
    worker(conn, "desktop", BOTH)
    rest = taskq.add(conn, "rest", "ftf", origin="app")["task"]
    assert claim(conn, "desktop", BOTH)["id"] == rest["id"]


def test_no_live_worker_is_said_so(conn):
    task = taskq.add(conn, "rest", "ftf", origin="app")["task"]
    taskq.claim(conn, "background", ("ai",), pid=1)  # its own row is not written by claim
    assert taskq.get(conn, task["id"])["waiting_for"].startswith("no worker is running")


def test_ai_limit_holds_ai_work_and_lets_the_rest_go(conn):
    worker(conn)
    taskq.set_state_value(conn, "ai_blocked_until", taskq.iso(taskq.now() + timedelta(hours=2)))
    top = taskq.add(conn, "collect", "ftf", origin="app")["task"]
    linkedin = taskq.add(conn, "linkedin", "ftf", origin="app")["task"]
    assert claim(conn)["id"] == linkedin["id"]
    assert taskq.get(conn, top["id"])["waiting_for"].startswith("the AI usage limit")
    taskq.set_state_value(conn, "ai_blocked_until", taskq.iso(taskq.now() - timedelta(minutes=1)))
    assert claim(conn)["id"] == top["id"]


def test_a_collection_is_a_group_in_order(conn):
    worker(conn)
    worker(conn, "desktop", BOTH)
    made = taskq.collection(conn, "ftf", origin="agent")
    ids = made["ids"]
    kinds = [(t["kind"], t["group_id"]) for t in made["group"]]
    assert kinds == [("collect", ids["top"]), ("linkedin", ids["top"]), ("rest", ids["top"]),
                     ("cv_batch", ids["top"]), ("cv_batch", ids["top"])]
    assert claim(conn)["id"] == ids["top"]
    assert claim(conn)["id"] == ids["linkedin"]
    assert claim(conn) is None
    assert taskq.get(conn, ids["rest"])["waiting_for"] == f"#{ids['top']} to end"
    taskq.finish(conn, ids["top"], "done")
    # the CV/CL batch for what the top brought, beside LinkedIn
    assert claim(conn, "desktop", BOTH)["id"] == ids["cv_batch"]
    assert claim(conn) is None
    assert taskq.get(conn, ids["rest"])["waiting_for"] == f"#{ids['linkedin']} to end"
    taskq.finish(conn, ids["linkedin"], "failed", "429s")
    # the rest goes after a failed LinkedIn; LinkedIn's own batch does not
    assert claim(conn)["id"] == ids["rest"]
    assert taskq.get(conn, ids["cv_batch_linkedin"])["state"] == "skipped"


def test_a_failed_top_skips_the_rest_and_its_batch(conn):
    worker(conn)
    ids = taskq.collection(conn, "ftf", origin="app", linkedin=False)["ids"]
    claim(conn)
    taskq.finish(conn, ids["top"], "failed", "exit 1")
    assert claim(conn) is None
    assert taskq.get(conn, ids["rest"])["state"] == "skipped"
    assert taskq.get(conn, ids["rest"])["error"] == f"#{ids['top']} ended failed"
    assert taskq.get(conn, ids["cv_batch"])["state"] == "skipped"


def test_a_collection_already_going_is_not_queued_twice(conn):
    first = taskq.collection(conn, "ftf", origin="app")
    again = taskq.collection(conn, "ftf", origin="agent")
    assert not again["added"] and again["task"]["id"] == first["ids"]["top"]
    assert len(taskq.tasks(conn)) == len(first["group"])


def test_collections_of_two_identities_take_turns_in_the_slot(conn):
    worker(conn)
    a = taskq.add(conn, "collect", "ftf", origin="app")["task"]
    b = taskq.add(conn, "collect", "abc", origin="app")["task"]
    assert claim(conn)["id"] == a["id"]
    assert taskq.get(conn, b["id"])["waiting_for"] == f"#{a['id']} to end"


def test_a_task_waiting_for_another_lets_the_next_in_its_slot_go(conn):
    worker(conn)
    linkedin = taskq.add(conn, "linkedin", "ftf", origin="app")["task"]
    claim(conn)
    rest = taskq.add(conn, "rest", "ftf", origin="app", after=[(linkedin["id"], False)])["task"]
    clean = taskq.add(conn, "clean", "ftf", origin="app")["task"]
    assert claim(conn)["id"] == clean["id"]
    assert taskq.get(conn, rest["id"])["state"] == "queued"


def test_the_base_held_outside_the_queue_holds_a_collect_slot_task(conn):
    worker(conn)
    rest = taskq.add(conn, "rest", "ftf", origin="app")["task"]
    assert claim(conn, base_holder=lambda: "pid 7 (identity abc)") is None
    assert taskq.get(conn, rest["id"])["waiting_for"] == "the base: pid 7 (identity abc)"
    assert claim(conn, base_holder=lambda: None)["id"] == rest["id"]


def test_stop_ends_a_queued_task_at_once_and_asks_a_running_one(conn):
    worker(conn)
    running = taskq.add(conn, "rest", "ftf", origin="app")["task"]
    queued = taskq.add(conn, "clean", "ftf", origin="app")["task"]
    claim(conn)
    assert taskq.stop(conn, queued["id"])["task"]["state"] == "stopped"
    reply = taskq.stop(conn, running["id"])
    assert reply["ok"] and reply["task"]["state"] == "running" and taskq.stop_requested(conn, running["id"])
    taskq.finish(conn, running["id"], "stopped")
    assert not taskq.stop(conn, running["id"])["ok"]
    assert not taskq.stop(conn, 999)["ok"]


def test_a_task_whose_worker_died_is_queued_again_then_fails_after_three_starts(conn):
    worker(conn)
    task = taskq.add(conn, "rest", "ftf", origin="app")["task"]
    killed = []
    later = taskq.now() + timedelta(minutes=2)
    for attempt in range(1, taskq.MAX_ATTEMPTS + 1):
        worker(conn, at=later)
        assert claim(conn, at=later)["attempts"] == attempt
        later += timedelta(minutes=2)
        said = taskq.sweep(conn, at=later, kill=killed.append)
        assert len(said) == 1
    final = taskq.get(conn, task["id"])
    assert final["state"] == "failed" and final["error"] == "interrupted 3 times"
    assert killed == [4242] * 3


def test_a_live_task_is_not_swept(conn):
    worker(conn)
    taskq.add(conn, "rest", "ftf", origin="app")
    claim(conn)
    assert taskq.sweep(conn) == []


def test_requeue_keeps_the_task_and_its_attempts(conn):
    worker(conn)
    task = taskq.add(conn, "collect", "ftf", origin="app")["task"]
    claim(conn)
    taskq.requeue(conn, task["id"], "the AI usage limit")
    again = taskq.get(conn, task["id"])
    assert (again["state"], again["attempts"], again["worker"]) == ("queued", 1, None)


def test_cleared_tasks_stay_cleared_and_active_ones_cannot_be(conn):
    worker(conn)
    done = taskq.add(conn, "rest", "ftf", origin="app")["task"]
    claim(conn)
    taskq.finish(conn, done["id"], "done")
    queued = taskq.add(conn, "clean", "ftf", origin="app")["task"]
    assert taskq.hide(conn) == 1
    assert [t["id"] for t in taskq.tasks(conn)] == [queued["id"]]
    with taskq.session() as again:   # a new connection: the app after a restart
        assert [t["id"] for t in taskq.tasks(again)] == [queued["id"]]
    assert taskq.hide(conn, [queued["id"]]) == 0


def test_a_run_started_by_hand_registers_itself_and_ends_done(isolated_data_dir, monkeypatch):
    monkeypatch.delenv(taskq.TASK_ENV, raising=False)
    with taskq.Registered("rest", "ftf", log_path=isolated_data_dir / "p.log") as reg:
        with taskq.session() as conn:
            live = taskq.get(conn, reg.task_id)
        assert (live["state"], live["worker"], live["log_path"]) == ("running", "external", str(isolated_data_dir / "p.log"))
    with taskq.session() as conn:
        assert taskq.get(conn, reg.task_id)["state"] == "done"


@pytest.mark.parametrize("raised,state", [
    (RuntimeError("boom"), "failed"), (SystemExit(2), "failed"), (SystemExit(0), "done"),
    (KeyboardInterrupt(), "interrupted")])
def test_a_registered_run_ends_with_its_outcome(isolated_data_dir, monkeypatch, raised, state):
    monkeypatch.delenv(taskq.TASK_ENV, raising=False)
    with pytest.raises(type(raised)):
        with taskq.Registered("pipeline", "ftf") as reg:
            raise raised
    with taskq.session() as conn:
        assert taskq.get(conn, reg.task_id)["state"] == state


def test_under_a_worker_a_run_adds_no_second_row(isolated_data_dir, monkeypatch):
    monkeypatch.setenv(taskq.TASK_ENV, "12")
    with taskq.Registered("rest", "ftf") as reg:
        pass
    assert reg.task_id is None
    with taskq.session() as conn:
        assert taskq.tasks(conn, include_hidden=True) == []


def test_a_stop_asked_in_the_panel_interrupts_a_registered_run(isolated_data_dir, monkeypatch):
    monkeypatch.delenv(taskq.TASK_ENV, raising=False)
    monkeypatch.setattr(taskq, "HEARTBEAT_SECONDS", 0.05)
    asked = []
    with taskq.Registered("rest", "ftf", interrupt=lambda: asked.append(1)) as reg:
        with taskq.session() as conn:
            taskq.stop(conn, reg.task_id)
        import time
        for _ in range(100):
            if asked:
                break
            time.sleep(0.02)
    assert asked == [1]


def test_the_command_line_adds_lists_and_stops(isolated_data_dir, capsys):
    assert taskq.main(["add", "rest", "--identity", "ftf", "--origin", "agent"]) == 0
    added = capsys.readouterr().out
    assert '"added": true' in added
    assert taskq.main(["list"]) == 0
    assert "rest" in capsys.readouterr().out
    assert taskq.main(["collect", "ftf", "--origin", "agent", "--json"]) == 0
    capsys.readouterr()
    assert taskq.main(["stop", "1"]) == 0
    with pytest.raises(SystemExit):   # argparse refuses an unknown kind
        taskq.main(["add", "dance"])


def test_current_tells_a_task_the_worker_started_from_a_session_of_its_own(isolated_data_dir, capsys,
                                                                          monkeypatch):
    monkeypatch.delenv(taskq.TASK_ENV, raising=False)
    assert taskq.main(["current"]) == 0
    assert json.loads(capsys.readouterr().out)["task"] is None
    with taskq.session() as conn:
        task = taskq.add(conn, "collect", "ftf", origin="app")["task"]
    monkeypatch.setenv(taskq.TASK_ENV, str(task["id"]))
    assert taskq.main(["current"]) == 0
    assert json.loads(capsys.readouterr().out) == {"task": task["id"], "kind": "collect", "identity": "ftf"}


def test_the_log_command_prints_the_file(isolated_data_dir, capsys):
    with taskq.session() as conn:
        task = taskq.add(conn, "rest", "ftf", origin="app")["task"]
        taskq.append_log(task, "first\n\nsecond")
    assert taskq.main(["log", str(task["id"])]) == 0
    assert capsys.readouterr().out == "first\nsecond\n"


def _pipeline_main(monkeypatch, mode, run):
    import sys
    import identity
    import pipeline
    monkeypatch.delenv(taskq.TASK_ENV, raising=False)
    monkeypatch.setattr(sys, "argv", ["pipeline.py", "--identity", "ftf", mode])
    monkeypatch.setattr(identity, "activate_or_exit", lambda value=None, quiet=False: "ftf")
    monkeypatch.setattr(identity, "skip_if_inactive", lambda prefix: False)
    monkeypatch.setattr(pipeline, "run_rest", run)
    monkeypatch.setattr(pipeline, "run_top", lambda **_: run())
    pipeline.main()


def test_a_pipeline_run_from_a_terminal_is_listed_while_it_runs(isolated_data_dir, monkeypatch):
    seen = []

    def run():
        with taskq.session() as conn:
            seen.extend(taskq.tasks(conn, active_only=True))
        return {"collected": "nothing"}
    _pipeline_main(monkeypatch, "--rest", run)
    assert [(t["kind"], t["identity"], t["state"], t["worker"]) for t in seen] == [("rest", "ftf", "running", "external")]
    assert seen[0]["log_path"].endswith(".log") and "pipeline_" in seen[0]["log_path"]
    with taskq.session() as conn:
        assert taskq.get(conn, seen[0]["id"])["state"] == "done"


def test_a_failing_pipeline_run_from_a_terminal_is_listed_failed(isolated_data_dir, monkeypatch):
    def run():
        raise RuntimeError("network down")
    with pytest.raises(RuntimeError):
        _pipeline_main(monkeypatch, "--top", run)
    with taskq.session() as conn:
        (task,) = taskq.tasks(conn)
    assert (task["kind"], task["args"], task["state"], task["error"]) == (
        "pipeline", {"mode": "top"}, "failed", "RuntimeError: network down")
