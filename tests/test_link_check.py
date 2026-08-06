"""
Tests for tools/link_check.py. No network is used — requests.Session is
replaced with fake head/get so the tests are fast and deterministic.

"""
from datetime import datetime, timedelta, timezone

import requests

import link_check


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


def _iso(dt):
    return dt.isoformat()


def test_should_check_skips_duplicates():
    v = {"url": "https://x/1", "duplicate_of": "canonical-id"}
    assert link_check._should_check(v, 12, datetime.now(timezone.utc)) is False


def test_should_check_skips_missing_url():
    v = {}
    assert link_check._should_check(v, 12, datetime.now(timezone.utc)) is False


def test_should_check_true_when_never_checked():
    v = {"url": "https://x/1"}
    assert link_check._should_check(v, 12, datetime.now(timezone.utc)) is True


def test_should_check_false_when_recently_checked():
    now = datetime.now(timezone.utc)
    v = {"url": "https://x/1", "link_check": {"checked_at": _iso(now - timedelta(hours=1))}}
    assert link_check._should_check(v, 12, now) is False


def test_should_check_true_when_checked_long_ago():
    now = datetime.now(timezone.utc)
    v = {"url": "https://x/1", "link_check": {"checked_at": _iso(now - timedelta(hours=13))}}
    assert link_check._should_check(v, 12, now) is True


def test_check_links_classifies_dead_ok_and_unknown(monkeypatch):
    responses = {
        "https://x/dead": 404,
        "https://x/gone": 410,
        "https://x/ok": 200,
        "https://x/blocked": 403,  # anti-bot, but NOT a dead link
    }

    def fake_head(self, url, timeout=None, allow_redirects=None):
        if url not in responses:
            raise ConnectionError("simulated network failure")
        return FakeResponse(responses[url])

    def fake_get(self, url, timeout=None, allow_redirects=None, stream=None):
        if url not in responses:
            raise ConnectionError("simulated network failure")
        return FakeResponse(responses[url])

    monkeypatch.setattr(requests.Session, "head", fake_head)
    monkeypatch.setattr(requests.Session, "get", fake_get)

    vacancies = {
        "1": {"id": "1", "url": "https://x/dead"},
        "2": {"id": "2", "url": "https://x/gone"},
        "3": {"id": "3", "url": "https://x/ok"},
        "4": {"id": "4", "url": "https://x/blocked"},
        "5": {"id": "5", "url": "https://x/times-out"},  # not in map -> exception -> unknown
    }

    stats = link_check.check_links(vacancies, max_workers=3, timeout=1, recheck_after_hours=12)

    assert vacancies["1"]["link_check"]["status"] == "dead"
    assert vacancies["2"]["link_check"]["status"] == "dead"
    assert vacancies["3"]["link_check"]["status"] == "ok"
    assert vacancies["4"]["link_check"]["status"] == "unknown"  # 403 does not count as "dead"
    assert vacancies["5"]["link_check"]["status"] == "unknown"  # an exception does not count as "dead"
    assert stats["dead"] == 2
    assert stats["ok"] == 1
    assert stats["unknown"] == 2
    assert stats["checked"] == 5


def test_check_links_falls_back_to_get_when_head_not_allowed(monkeypatch):
    call_log = []

    def fake_head(self, url, timeout=None, allow_redirects=None):
        call_log.append("head")
        return FakeResponse(405)  # method not allowed

    def fake_get(self, url, timeout=None, allow_redirects=None, stream=None):
        call_log.append("get")
        return FakeResponse(200)

    monkeypatch.setattr(requests.Session, "head", fake_head)
    monkeypatch.setattr(requests.Session, "get", fake_get)

    vacancies = {"1": {"id": "1", "url": "https://x/only-get-allowed"}}
    link_check.check_links(vacancies, max_workers=1, timeout=1)

    assert vacancies["1"]["link_check"]["status"] == "ok"
    assert call_log == ["head", "get"]


def test_check_links_skips_duplicates_and_recently_checked(monkeypatch):
    call_count = {"n": 0}

    def fake_head(self, url, timeout=None, allow_redirects=None):
        call_count["n"] += 1
        return FakeResponse(200)

    monkeypatch.setattr(requests.Session, "head", fake_head)

    now_iso = datetime.now(timezone.utc).isoformat()
    vacancies = {
        "1": {"id": "1", "url": "https://x/1", "duplicate_of": "2"},
        "2": {"id": "2", "url": "https://x/2", "link_check": {"status": "ok", "checked_at": now_iso}},
        "3": {"id": "3", "url": "https://x/3"},  # the only one genuinely due for a check
    }
    stats = link_check.check_links(vacancies, max_workers=2, timeout=1, recheck_after_hours=12)

    assert call_count["n"] == 1  # only vac-3 actually reached the network
    assert stats["skipped_recent_or_duplicate"] == 2
    assert stats["checked"] == 1
