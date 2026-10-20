"""Schedules (tools/schedules.py, task 0061): the cron line, when a schedule
is due, a run missed while the computer was off (caught up or skipped), a
run skipped while the previous one goes. A fake clock; no task runs."""
import json
from datetime import datetime, timedelta, timezone

import pytest

import schedules
import taskd
import taskq


def local(*args):
    """A local wall-clock time, aware: the cron line is in local time."""
    return datetime(*args).astimezone()


def at_local(moment):
    return moment.astimezone().replace(tzinfo=None)


@pytest.fixture
def conn(isolated_data_dir):
    with taskq.session() as c:
        yield c


def due(conn, at, identities=("sharp", "part"), off=()):
    return schedules.run_due(conn, at, identities_of=lambda: list(identities), inactive_of=lambda: set(off))


# --- the cron line ------------------------------------------------------------------

@pytest.mark.parametrize("line, after, expected", [
    ("0 7 * * *", (2026, 10, 21, 6, 59), (2026, 10, 21, 7, 0)),
    ("0 7 * * *", (2026, 10, 21, 7, 0), (2026, 10, 22, 7, 0)),          # strictly after
    ("*/15 * * * *", (2026, 10, 21, 7, 1), (2026, 10, 21, 7, 15)),
    ("30 9-18/3 * * *", (2026, 10, 21, 13, 0), (2026, 10, 21, 15, 30)),
    ("0 9 * * 1-5", (2026, 10, 23, 10, 0), (2026, 10, 26, 9, 0)),        # Friday -> Monday
    ("0 9 * * sun", (2026, 10, 21, 0, 0), (2026, 10, 25, 9, 0)),
    ("0 9 * * 7", (2026, 10, 21, 0, 0), (2026, 10, 25, 9, 0)),           # 7 is Sunday too
    ("0 0 1 jan *", (2026, 10, 21, 0, 0), (2027, 1, 1, 0, 0)),
    ("0 0 13 * fri", (2026, 10, 21, 0, 0), (2026, 10, 23, 0, 0)),        # either day: Friday the 23rd
    ("@daily", (2026, 10, 21, 7, 0), (2026, 10, 22, 0, 0)),
    ("0 12 29 2 *", (2026, 10, 21, 0, 0), (2028, 2, 29, 12, 0)),         # the next leap year
])
def test_the_next_time_of_a_cron_line(line, after, expected):
    found = schedules.Cron(line).next_after(local(*after))
    assert found.tzinfo is not None
    assert at_local(found) == datetime(*expected)


def test_a_line_that_names_no_time_has_no_next_run():
    assert schedules.Cron("0 0 30 2 *").next_after(local(2026, 10, 21)) is None
    assert schedules.next_runs("0 0 31 4 *") == []


@pytest.mark.parametrize("line", [
    "0 7 * *", "60 * * * *", "* 24 * * *", "* * 0 * *", "* * * 13 *", "* * * * 8",
    "*/0 * * * *", "5-1 * * * *", "a b c d e", "0 7 * * * *", "",
])
def test_a_wrong_cron_line_is_refused_with_the_field(line):
    with pytest.raises(schedules.CronError):
        schedules.Cron(line)


def test_the_next_three_runs():
    runs = schedules.next_runs("0 7,19 * * *", 3, after=local(2026, 10, 21, 8, 0))
    assert [at_local(r) for r in runs] == [datetime(2026, 10, 21, 19, 0), datetime(2026, 10, 22, 7, 0),
                                           datetime(2026, 10, 22, 19, 0)]


# --- schedules ---------------------------------------------------------------------

def test_a_schedule_is_due_at_its_time_and_queues_a_collection_per_identity(conn):
    made = schedules.add(conn, "collect", "all", "0 7 * * *", at=local(2026, 10, 21, 6, 0))
    assert at_local(datetime.fromisoformat(made["next_at"])) == datetime(2026, 10, 21, 7, 0)
    assert due(conn, local(2026, 10, 21, 6, 59)) == []
    said = due(conn, local(2026, 10, 21, 7, 0, 20))
    assert len(said) == 1 and "queued #" in said[0] and "caught up" not in said[0]
    queued = taskq.tasks(conn)
    assert {t["identity"] for t in queued} == {"sharp", "part"}
    assert {t["origin"] for t in queued} == {"schedule"}
    assert {t["kind"] for t in queued} == {"collect", "linkedin", "rest", "cv_batch"}   # the group
    assert due(conn, local(2026, 10, 21, 7, 1)) == [], "a run time is queued once"
    again = schedules.get(conn, made["id"], local(2026, 10, 21, 7, 1))
    assert again["last_result"] == "queued"
    assert at_local(datetime.fromisoformat(again["next_at"])) == datetime(2026, 10, 22, 7, 0)
    assert sorted(again["last_tasks"]) == sorted(t["id"] for t in queued)


def test_a_run_waits_for_nothing_while_the_previous_one_goes(conn):
    made = schedules.add(conn, "rest", "sharp", "0 * * * *", at=local(2026, 10, 21, 6, 30))
    due(conn, local(2026, 10, 21, 7, 0, 5))
    first = schedules.get(conn, made["id"])["last_tasks"]
    said = due(conn, local(2026, 10, 21, 8, 0, 5))
    assert "skipped, the previous run is still queued" in said[0]
    assert len(taskq.tasks(conn)) == 1
    assert schedules.get(conn, made["id"])["last_note"] == said[0]
    taskq.stop(conn, first[0])
    said = due(conn, local(2026, 10, 21, 9, 0, 5))
    assert "queued #" in said[0]
    assert schedules.get(conn, made["id"])["last_result"] == "queued"


def test_runs_missed_while_off_are_caught_up_once(conn):
    made = schedules.add(conn, "linkedin", "sharp", "0 * * * *", missed="catch_up", at=local(2026, 10, 21, 6, 30))
    # the laptop slept from 06:40 to 11:20: four run times passed
    said = due(conn, local(2026, 10, 21, 11, 20))
    assert len(said) == 1 and "the run of 2026-10-21 11:00: caught up, queued #" in said[0]
    assert len(taskq.tasks(conn)) == 1
    assert at_local(datetime.fromisoformat(schedules.get(conn, made["id"], local(2026, 10, 21, 11, 20))["next_at"])) \
        == datetime(2026, 10, 21, 12, 0)


def test_runs_missed_while_off_are_skipped_when_the_schedule_says_so(conn):
    made = schedules.add(conn, "linkedin", "sharp", "0 * * * *", missed="skip", at=local(2026, 10, 21, 6, 30))
    said = due(conn, local(2026, 10, 21, 11, 20))
    assert "missed (the computer was off or asleep); skipped" in said[0]
    assert taskq.tasks(conn) == []
    assert due(conn, local(2026, 10, 21, 11, 21)) == []
    # on time, it runs
    assert "queued #" in due(conn, local(2026, 10, 21, 12, 0, 30))[0]
    assert schedules.get(conn, made["id"])["missed"] == "skip"


def test_a_run_a_few_minutes_late_is_on_time(conn):
    schedules.add(conn, "linkedin", "sharp", "0 7 * * *", missed="skip", at=local(2026, 10, 21, 6, 0))
    assert "queued #" in due(conn, local(2026, 10, 21, 7, 9))[0]


def test_a_schedule_turned_off_is_not_due_and_turned_on_counts_from_then(conn):
    made = schedules.add(conn, "rest", "sharp", "0 * * * *", at=local(2026, 10, 21, 6, 30))
    schedules.update(conn, made["id"], enabled=False, at=local(2026, 10, 21, 6, 31))
    assert due(conn, local(2026, 10, 21, 9, 0, 5)) == []
    assert schedules.get(conn, made["id"])["next_at"] is None
    schedules.update(conn, made["id"], enabled=True, at=local(2026, 10, 21, 9, 30))
    assert due(conn, local(2026, 10, 21, 9, 31)) == [], "the runs while off were not missed"
    assert "queued #" in due(conn, local(2026, 10, 21, 10, 0, 5))[0]


def test_a_new_timetable_counts_from_the_change(conn):
    made = schedules.add(conn, "rest", "sharp", "0 7 * * *", at=local(2026, 10, 21, 6, 0))
    changed = schedules.update(conn, made["id"], cron="0 12 * * *", at=local(2026, 10, 21, 10, 0))
    assert changed["cron"] == "0 12 * * *"
    assert due(conn, local(2026, 10, 21, 10, 1)) == []
    assert "queued #" in due(conn, local(2026, 10, 21, 12, 0, 5))[0]


def test_an_identity_turned_off_is_not_collected(conn):
    schedules.add(conn, "collect", "sharp,part", "0 7 * * *", at=local(2026, 10, 21, 6, 0))
    due(conn, local(2026, 10, 21, 7, 0, 5), off={"part"})
    assert {t["identity"] for t in taskq.tasks(conn)} == {"sharp"}


def test_a_clean_up_keeps_its_filters_and_needs_one(conn):
    with pytest.raises(ValueError, match="at least one filter"):
        schedules.add(conn, "clean", "sharp", "0 9 * * 0", args={})
    with pytest.raises(ValueError, match="invalid ages"):
        schedules.add(conn, "clean", "sharp", "0 9 * * 0", args={"ages": ["older; rm"]})
    made = schedules.add(conn, "clean", "sharp", "0 9 * * 0", args={"ages": ["older"], "junk": [1]},
                         at=local(2026, 10, 21, 0, 0))
    assert made["args"] == {"ages": ["older"]}
    due(conn, local(2026, 10, 25, 9, 0, 5))
    task = taskq.tasks(conn)[0]
    assert (task["kind"], task["args"]) == ("clean", {"ages": ["older"]})
    taskd.command(task, python="python")   # the worker accepts what the schedule queued


@pytest.mark.parametrize("what, identities, cron, missed, error", [
    ("dance", "all", "0 7 * * *", "skip", "unknown schedule kind"),
    ("rest", "Bad Prefix", "0 7 * * *", "skip", "invalid identity"),
    ("rest", "all", "0 7 * *", "skip", "5 fields"),
    ("rest", "all", "0 7 * * *", "sometimes", "missed runs"),
])
def test_a_wrong_schedule_is_refused(conn, what, identities, cron, missed, error):
    with pytest.raises(ValueError, match=error):
        schedules.add(conn, what, identities, cron, missed=missed)


def test_the_links_task_rechecks_the_shortlist(conn):
    schedules.add(conn, "links", "sharp", "0 */6 * * *", at=local(2026, 10, 21, 5, 0))
    due(conn, local(2026, 10, 21, 6, 0, 5))
    task = taskq.tasks(conn)[0]
    assert task["kind"] == "links" and task["slot"] == "collect"
    assert taskd.command(task, python="python").argv[-3:] == ["--identity", "sharp", "--links"]


def test_removing_a_schedule_keeps_its_tasks(conn):
    made = schedules.add(conn, "rest", "sharp", "0 7 * * *", at=local(2026, 10, 21, 6, 0))
    due(conn, local(2026, 10, 21, 7, 0, 5))
    assert schedules.remove(conn, made["id"]) is True
    assert schedules.listing(conn) == []
    assert len(taskq.tasks(conn)) == 1
    assert schedules.remove(conn, made["id"]) is False


def test_the_worker_queues_what_is_due_every_few_seconds(isolated_data_dir, monkeypatch):
    calls = []
    monkeypatch.setattr(schedules, "run_due", lambda conn: calls.append(1) or ["schedule #1: queued #5"])
    said = []
    worker = taskd.Worker("background", ("ai",), start=lambda task, on_line: None, kill=lambda pid: None,
                          awake=lambda on: None, holder=lambda: None, alive=lambda pid: True, say=said.append,
                          wall=lambda: clock[0])
    clock = [1000.0]
    worker.register()
    worker.tick()
    clock[0] += 5
    worker.tick()
    assert calls == [1], "not more often than CHECK_EVERY_SECONDS"
    clock[0] += schedules.CHECK_EVERY_SECONDS
    worker.tick()
    assert calls == [1, 1]
    assert "schedule #1: queued #5" in said


def test_a_broken_schedule_does_not_stop_the_worker(isolated_data_dir, monkeypatch):
    def broken(conn):
        raise RuntimeError("boom")

    monkeypatch.setattr(schedules, "run_due", broken)
    said = []
    worker = taskd.Worker("background", ("ai",), start=lambda task, on_line: None, kill=lambda pid: None,
                          awake=lambda on: None, holder=lambda: None, alive=lambda pid: True, say=said.append)
    worker.register()
    worker.tick()
    assert "schedules: RuntimeError: boom" in said


def test_the_command_line(isolated_data_dir, capsys):
    assert taskq.main(["schedule", "add", "collect", "--identities", "sharp", "--cron", "0 7 * * *",
                       "--missed", "skip"]) == 0
    made = json.loads(capsys.readouterr().out)
    assert (made["what"], made["identities"], made["missed"], made["enabled"]) == ("collect", ["sharp"], "skip", True)
    assert taskq.main(["schedule", "set", str(made["id"]), "--cron", "30 6 * * 1-5", "--name", "mornings"]) == 0
    assert json.loads(capsys.readouterr().out)["name"] == "mornings"
    assert taskq.main(["schedule", "off", str(made["id"])]) == 0
    assert json.loads(capsys.readouterr().out)["enabled"] is False
    assert taskq.main(["schedule", "list", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["cron"] == "30 6 * * 1-5"
    assert taskq.main(["schedule", "next", "0 7 * * *", "-n", "2"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 2
    assert taskq.main(["schedule", "add", "rest", "--cron", "61 * * * *"]) == 2
    assert "minute" in capsys.readouterr().err
    assert taskq.main(["schedule", "remove", str(made["id"])]) == 0
    assert taskq.main(["schedule", "remove", str(made["id"])]) == 1


def test_end_to_end_a_schedule_queues_its_task_the_worker_runs_it_and_the_schedule_shows_the_result(
        isolated_data_dir):
    with taskq.session() as c:
        made = schedules.add(c, "rest", "ftf", "* * * * *", at=taskq.now() - timedelta(minutes=2))
    said = []
    worker = taskd.Worker("background", ("ai",), start=taskd.FakeRun, kill=lambda pid: None,
                          awake=lambda on: None, holder=lambda: None, alive=lambda pid: True, say=said.append)
    worker.register()
    worker.tick()       # due: queued, claimed, started
    worker.tick()       # ended
    with taskq.session() as c:
        task = taskq.tasks(c)[0]
        assert (task["kind"], task["identity"], task["origin"], task["state"]) == ("rest", "ftf", "schedule", "done")
        shown = schedules.get(c, made["id"])
        assert shown["last_tasks"] == [task["id"]] and shown["last_result"] == "done"
        assert shown["last_note"].endswith(f"queued #{task['id']}")
    assert any(line.startswith(f"schedule #{made['id']}") for line in said)
