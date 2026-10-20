"""The AI usage limit (tools/ai_limit.py, task 0057): one refusal stops the
AI work, the tool says when the limit resets and exits with its own code,
and the task queue holds the AI tasks until then. No model is called."""
import json
import types
from datetime import datetime, timedelta, timezone

import pytest

import ai_limit
import ai_screen
import cv_batch
import db
import taskq

NOW = datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc)


def _done(stdout="", stderr="", code=0):
    return types.SimpleNamespace(stdout=stdout, stderr=stderr, returncode=code)


@pytest.mark.parametrize("text, resets", [
    ("Claude AI usage limit reached|1792540800", datetime.fromtimestamp(1792540800, timezone.utc)),
    ("5-hour limit reached ∙ resets in 2 hours", NOW + timedelta(hours=2)),
    ("You've hit your limit · resets 3pm (UTC)", None),   # the clock: checked below
    ("Claude usage limit reached. Your limit will reset at 5pm", None),
    ("Weekly limit reached", None),
])
def test_the_wordings_of_the_limit_are_recognised(text, resets):
    limit = ai_limit.recognise(text, now=NOW)
    assert isinstance(limit, ai_limit.UsageLimit)
    if resets is not None:
        assert limit.resets_at == resets


def test_a_reset_clock_time_is_the_next_one_ahead():
    later = ai_limit.reset_time("resets 3pm", now=NOW)
    assert later > NOW and later - NOW < timedelta(days=1)
    assert later.astimezone().hour == 15
    passed = ai_limit.reset_time("resets 1am", now=NOW)
    assert NOW < passed < NOW + timedelta(days=1)


@pytest.mark.parametrize("text", [
    "LinkedIn: 429, rate limit reached; pausing 60 s",
    "the posting says: no usage limits on our API",
    "",
])
def test_other_limits_are_not_the_ai_limit(text):
    assert ai_limit.recognise(text) is None


def test_only_a_refused_call_is_read_for_the_limit():
    ok = json.dumps({"type": "result", "is_error": False, "result": "the usage limit reached its peak"})
    ai_limit.check(_done(ok))   # an answer that mentions a limit is an answer
    refused = json.dumps({"type": "result", "is_error": True, "result": "Claude AI usage limit reached|1792540800"})
    with pytest.raises(ai_limit.UsageLimit) as caught:
        ai_limit.check(_done(refused, code=1))
    assert caught.value.resets_at.timestamp() == 1792540800
    with pytest.raises(ai_limit.UsageLimit):
        ai_limit.check(_done("", "Error: usage limit reached", code=1))
    ai_limit.check(_done(json.dumps({"is_error": True, "result": "Not logged in"}), code=1))   # another error


def test_the_line_a_tool_prints_is_read_back_by_the_worker():
    limit = ai_limit.UsageLimit("usage limit reached", datetime(2026, 10, 21, 18, 0, tzinfo=timezone.utc))
    back = ai_limit.from_line(f"  | [10:00:00] !! {ai_limit.mark(limit)}; the AI work stopped")
    assert back.resets_at == limit.resets_at
    assert ai_limit.from_line(json.dumps(limit.as_json())).resets_at == limit.resets_at
    unknown = ai_limit.from_line(ai_limit.mark(ai_limit.UsageLimit("x")))
    assert unknown is not None and unknown.resets_at is None
    event = json.dumps({"type": "result", "is_error": True, "result": "Claude AI usage limit reached|1792540800"})
    assert ai_limit.from_line(event) is not None
    assert ai_limit.from_line(json.dumps({"type": "result", "is_error": False, "result": "usage limit reached"})) is None
    assert ai_limit.from_line("ok fetch - 26:00 (900 new)") is None


def test_a_tool_that_meets_the_limit_holds_the_queue(isolated_data_dir):
    resets = datetime.now(timezone.utc) + timedelta(hours=3)
    ai_limit.record(ai_limit.UsageLimit("usage limit reached", resets))
    with taskq.session() as conn:
        assert taskq.ai_block(conn) == resets.replace(microsecond=0)
        top = taskq.add(conn, "collect", "ftf", origin="terminal")["task"]
        taskq.refresh_waiting(conn, taskq.plan(conn))
        assert taskq.get(conn, top["id"])["waiting_for"].startswith("the AI usage limit; tried again at")


def test_the_pipeline_goes_on_without_ai_after_the_limit_and_remembers_it(isolated_data_dir, monkeypatch):
    import ai_brief
    import common
    import pipeline
    monkeypatch.setattr(common, "ACTIVE_IDENTITY", "ftf", raising=False)
    monkeypatch.setattr(pipeline, "AI_LIMIT", None)
    monkeypatch.setattr(ai_brief, "ensure", lambda prefix: {"written": False})
    monkeypatch.setattr(ai_brief, "load", lambda prefix: "brief")
    limit = ai_limit.UsageLimit("usage limit reached")
    limit.stats = {"screened": 2, "not_sent": 5}

    def screen(*args, **kwargs):
        raise limit

    monkeypatch.setattr(ai_screen, "screen", screen)
    state = {}
    assert pipeline.ai_check_stage({}, state) is True, "the answers given are rescored"
    assert pipeline.AI_LIMIT is limit
    assert state["last_ai_screen"]["not_sent"] == 5 and state["last_ai_screen"]["ai_limit"] == "unknown"
    # a second AI stage of the same run sends nothing
    monkeypatch.setattr(ai_screen, "screen", lambda *a, **k: pytest.fail("called after the limit"))
    assert pipeline.ai_check_stage({}, state) is False


def _record(vid):
    return {"id": vid, "title": "Senior .NET Engineer", "company": "Acme", "source": "arbeitnow",
            "url": f"https://example.com/{vid}", "location_raw": "Remote",
            "description_text": "Fully remote.", "computed": {"classification": "hot_lead", "score": 90 - int(vid[1:])}}


def test_the_first_refusal_stops_the_screen_and_keeps_the_answers_given(isolated_data_dir):
    with db.session():
        pass
    vacancies = {f"v{i}": _record(f"v{i}") for i in range(20)}
    calls = []

    def call(system_prompt, text, workdir=None):
        calls.append(text)
        if len(calls) == 3:
            raise ai_limit.UsageLimit("Claude AI usage limit reached|1792540800",
                                      datetime.fromtimestamp(1792540800, timezone.utc))
        return {"is_job_posting": True, "work_arrangement": "remote", "location_ok": "yes",
                "role_fit": "good", "verdict": "keep", "reason": "ok"}, 0.001

    with pytest.raises(ai_limit.UsageLimit) as caught:
        ai_screen.screen(vacancies, "ftf", "brief", workers=1, call=call)
    assert len(calls) == 3, "no call is sent after the refusal"
    stats = caught.value.stats
    assert (stats["screened"], stats["errors"], stats["not_sent"]) == (2, 0, 18)
    with db.session() as conn:
        assert len(ai_screen.load(conn, "ftf")) == 2, "the answers given are kept"
    # after the reset the screen goes on from where it stopped
    again = ai_screen.screen(vacancies, "ftf", "brief", workers=1, call=lambda *a, **k: call(*a, **k))
    assert again["considered"] == 18


def test_a_batch_stops_at_the_limit_and_says_so(isolated_data_dir, monkeypatch):
    where = {name: isolated_data_dir / f"cv_batch.{ext}" for name, ext in
             (("status", "json"), ("log", "log"), ("stop", "STOP"), ("pending", "pending"), ("hold", "HOLD"))}
    items = [{"vacancy_id": f"v{i}", "title": "Dev", "company": "Acme", "documents": ["cv"]} for i in range(5)]
    made = []

    def generate(prefix, item, kind):
        made.append(item["vacancy_id"])
        if item["vacancy_id"] == "v1":
            return ai_limit.UsageLimit("usage limit reached").as_json()
        return {"ok": True, "pages": 2}

    batch = cv_batch.Batch(where)
    monkeypatch.setattr(batch, "add", lambda work, requests, plan: work.extend(
        ("ftf", item, "cv") for r in requests for item in items))
    with pytest.raises(ai_limit.UsageLimit):
        batch.run([{"identity": "ftf", "all": False}], lambda prefix, everything: items, generate)
    assert made == ["v0", "v1"]
    status = json.loads(where["status"].read_text(encoding="utf-8"))
    assert status["state"] == "stopped" and status["made"] == 1
    assert ai_limit.MARK in where["log"].read_text(encoding="utf-8")
