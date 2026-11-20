"""
tools/availability.py (task 0127): is a listed vacancy still open. No
network: the session is a fake that answers per job number, the clock and
the sleep are the test's.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import availability
import db
import fetch_linkedin
import link_check

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
OPEN_PAGE = '<h1 class="topcard__title">Dev</h1><div class="description__text">Build things</div></section>'
CLOSED_PAGE = ('<figure class="closed-job"><figcaption>No longer accepting applications</figcaption></figure>'
               '<div class="description__text">Build things</div></section>')


class Answer:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


class FakeSession:
    """Answers the guest fragment by job number: a list of answers is
    given out one per request, the last one repeating."""

    def __init__(self, answers, other=None):
        self.answers = {k: list(v) if isinstance(v, list) else [v] for k, v in answers.items()}
        self.other = other or {}
        self.asked = []

    def get(self, url, timeout=None, allow_redirects=None, stream=None):
        self.asked.append(url)
        for job, queue in self.answers.items():
            if url == fetch_linkedin.GUEST_POSTING_URL.format(job_id=job):
                return queue.pop(0) if len(queue) > 1 else queue[0]
        if url in self.other:
            return self.other[url]
        raise ConnectionError("not in the fake")

    def head(self, url, timeout=None, allow_redirects=None):
        self.asked.append(("HEAD", url))
        if url in self.other:
            return self.other[url]
        raise ConnectionError("not in the fake")


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


def _li(vid, job, **extra):
    return {"id": vid, "url": f"https://www.linkedin.com/jobs/view/dev-at-acme-{job}", **extra}


def _run(vacancies, session, minutes=30, clock=None):
    clock = clock or Clock()
    return availability.check(vacancies, minutes=minutes, session=session, sleep=clock.sleep,
                              clock=clock, now=NOW)


# --- one LinkedIn posting --------------------------------------------------

def test_an_open_posting_a_closed_one_and_a_404_get_their_verdicts():
    session = FakeSession({"4000000001": Answer(200, OPEN_PAGE), "4000000002": Answer(200, CLOSED_PAGE),
                           "4000000003": Answer(404)})
    assert availability.linkedin_verdict("4000000001", session)["status"] == "ok"
    closed = availability.linkedin_verdict("4000000002", session)
    assert closed["status"] == "dead" and closed["reason"] == availability.CLOSED_MARKER
    assert availability.linkedin_verdict("4000000003", session)["status"] == "dead"


def test_a_429_an_empty_answer_and_a_dropped_connection_decide_nothing():
    session = FakeSession({"4000000001": Answer(429), "4000000002": Answer(200, "<html>sign in</html>")})
    assert availability.linkedin_verdict("4000000001", session)["status"] == "unknown"
    assert availability.linkedin_verdict("4000000002", session)["status"] == "unknown"
    assert availability.linkedin_verdict("4000000009", session)["status"] == "unknown"


def test_the_job_number_is_read_with_and_without_the_title_slug():
    assert fetch_linkedin.job_id("https://de.linkedin.com/jobs/view/senior-architect-net-at-cf-4472723959") \
        == "4472723959"
    assert fetch_linkedin.job_id("https://www.linkedin.com/jobs/view/4474971398/?refId=x") == "4474971398"
    assert fetch_linkedin.job_id("https://www.linkedin.com/company/acme") is None
    assert fetch_linkedin.job_id("") is None


# --- what is due -------------------------------------------------------------

def test_never_checked_and_old_verdicts_are_due_a_closed_one_and_a_fresh_one_are_not():
    old = (NOW - timedelta(hours=30)).isoformat()
    fresh = (NOW - timedelta(hours=2)).isoformat()
    assert availability.due({"url": "u"}, NOW)
    assert availability.due({"url": "u", "link_check": {"status": "unknown", "checked_at": old}}, NOW)
    assert not availability.due({"url": "u", "link_check": {"status": "ok", "checked_at": fresh}}, NOW)
    assert not availability.due({"url": "u", "link_check": {"status": "dead", "checked_at": old}}, NOW)
    assert not availability.due({"url": "u", "duplicate_of": "x"}, NOW)
    assert not availability.due({}, NOW)


def test_the_oldest_check_goes_first_and_the_budget_leaves_the_rest_for_the_next_run():
    vacancies = [
        _li("new", "4000000001", link_check={"status": "ok", "checked_at": (NOW - timedelta(hours=25)).isoformat()}),
        _li("never", "4000000002"),
        _li("old", "4000000003", link_check={"status": "unknown", "checked_at": "2026-11-01T00:00:00+00:00"}),
    ]
    session = FakeSession({j: Answer(200, OPEN_PAGE) for j in ("4000000001", "4000000002", "4000000003")})
    clock = Clock()
    # each page costs the pacer's pause (1.5 s); a budget of 2 s takes two
    stats = _run(vacancies, session, minutes=2 / 60, clock=clock)
    assert list(stats["changed"]) == ["never", "old"]
    assert stats["left_for_next_run"] == 1


# --- 429 ---------------------------------------------------------------------

def test_a_429_is_waited_out_and_the_same_posting_asked_again():
    session = FakeSession({"4000000001": [Answer(429), Answer(200, OPEN_PAGE)]})
    clock = Clock()
    stats = _run([_li("a", "4000000001")], session, clock=clock)
    assert stats["changed"]["a"]["status"] == "ok" and stats["rate_limited"] == 1
    assert clock.t >= fetch_linkedin.RATE_LIMIT_BACKOFF[0]


def test_429s_in_a_row_end_linkedin_for_the_run_and_leave_no_verdict():
    vacancies = [_li("a", "4000000001"), _li("b", "4000000002"),
                 {"id": "c", "url": "https://board.example/jobs/1"}]
    session = FakeSession({"4000000001": Answer(429), "4000000002": Answer(200, OPEN_PAGE)},
                          other={"https://board.example/jobs/1": Answer(404)})
    stats = _run(vacancies, session)
    assert stats["linkedin_stopped"] and stats["rate_limited"] == availability.LIMITED_IN_A_ROW
    assert "a" not in stats["changed"] and "b" not in stats["changed"]
    # the other board is still asked
    assert stats["changed"]["c"]["status"] == "dead"
    assert not any("4000000002" in str(u) for u in session.asked)


def test_a_linkedin_address_without_a_job_number_is_not_sent_a_head():
    session = FakeSession({})
    stats = _run([{"id": "a", "url": "https://www.linkedin.com/jobs/search?keywords=x"}], session)
    assert stats["changed"]["a"]["status"] == "unknown" and session.asked == []


# --- a closed verdict stays --------------------------------------------------

def test_an_unknown_answer_keeps_a_closed_verdict_and_an_open_one_replaces_it():
    before = {"status": "dead", "reason": "no longer accepting applications", "checked_at": "2026-11-01T00:00:00"}
    kept = link_check.merge(before, {"status": "unknown", "http_code": 429}, NOW)
    assert kept["status"] == "dead" and kept["reason"] == before["reason"]
    assert kept["checked_at"] == before["checked_at"] and kept["unknown_at"] == NOW.isoformat()
    reopened = link_check.merge(before, {"status": "ok", "http_code": 200}, NOW, by="availability")
    assert reopened == {"status": "ok", "http_code": 200, "checked_at": NOW.isoformat(), "by": "availability"}


# --- the base ----------------------------------------------------------------

def test_save_writes_only_link_check_into_the_row_as_it_is_now(isolated_data_dir):
    db.save_vacancies({"a": {"id": "a", "title": "Dev", "url": "https://x/1"}})
    # the row changed after this run read it (LinkedIn's merge beside it)
    db.save_vacancies({"a": {"id": "a", "title": "Dev (updated)", "url": "https://x/1"}})
    assert availability.save({"a": {"status": "dead", "checked_at": NOW.isoformat()},
                              "missing": {"status": "ok"}}) == 1
    record = db.load_vacancy("a")
    assert record["title"] == "Dev (updated)" and record["link_check"]["status"] == "dead"


def test_refresh_checks_one_vacancy_when_due_and_saves_it(isolated_data_dir):
    db.save_vacancies({"a": _li("a", "4000000001")})
    session = FakeSession({"4000000001": Answer(200, CLOSED_PAGE)})
    verdict = availability.refresh("a", session=session)
    assert verdict["status"] == "dead"
    assert db.load_vacancy("a")["link_check"]["status"] == "dead"
    # closed: not asked again
    assert availability.refresh("a", session=session)["status"] == "dead" and len(session.asked) == 1
    assert availability.refresh("nope", session=session) is None


# --- link_check leaves LinkedIn to this tool ---------------------------------

def test_link_check_does_not_send_linkedin_records_a_head():
    assert not link_check._should_check({"url": "https://uk.linkedin.com/jobs/view/x-4000000001"}, 12, NOW)
    assert not link_check._should_check({"url": "https://www.linkedin.com/jobs/view/4000000001/"}, 12, NOW)
    assert link_check._should_check({"url": "https://notlinkedin.com/jobs/1"}, 12, NOW)
