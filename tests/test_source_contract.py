"""
The contract machinery itself, offline: how failures are sorted, and what a
contract that misbehaves comes out as. The sorting matters more than it looks —
`broken` sends an agent to rewrite a fetcher, so a rate limit or a closed door
must never be reported as `broken`.
"""
import types

import pytest
import requests

import source_contract


class _Response:
    def __init__(self, status, text="", url="https://example.org/search"):
        self.status_code = status
        self.text = text
        self.url = url


def _run_with(monkeypatch, response=None, error=None):
    def fake_get(url, headers=None, timeout=None):
        if error:
            raise error
        return response
    monkeypatch.setattr(requests, "get", fake_get)
    return source_contract.ContractRun("x", pause=0)


@pytest.mark.parametrize("status", [429, 500, 503])
def test_rate_limits_and_server_trouble_are_unreachable(monkeypatch, status):
    run = _run_with(monkeypatch, _Response(status))
    with pytest.raises(source_contract.Unreachable):
        run.get("https://example.org/search")


def test_a_network_error_is_unreachable(monkeypatch):
    run = _run_with(monkeypatch, error=requests.ConnectionError("down"))
    with pytest.raises(source_contract.Unreachable):
        run.get("https://example.org/search")


@pytest.mark.parametrize("status", [401, 403, 999])
def test_a_refusal_is_blocked(monkeypatch, status):
    run = _run_with(monkeypatch, _Response(status))
    with pytest.raises(source_contract.Blocked):
        run.get("https://example.org/search")


def test_a_login_wall_is_blocked_even_with_200(monkeypatch):
    run = _run_with(monkeypatch, _Response(200, "<html>sign in</html>",
                                           url="https://www.linkedin.com/authwall?trk=x"))
    with pytest.raises(source_contract.Blocked):
        run.get("https://www.linkedin.com/jobs/view/1")


def test_a_moved_endpoint_is_a_failed_expectation(monkeypatch):
    run = _run_with(monkeypatch, _Response(404))
    assert run.get("https://example.org/search") == ""
    assert run.checks == [{"name": "endpoint answers", "ok": False,
                           "detail": "HTTP 404 on https://example.org/search"}]


def _source_with(monkeypatch, contract):
    module = types.SimpleNamespace(contract=contract)
    monkeypatch.setattr(source_contract, "fetcher_modules", lambda: {"fake": "fake_module"})
    monkeypatch.setattr(source_contract.importlib, "import_module", lambda name: module)


def test_status_follows_what_the_contract_raised(monkeypatch):
    def unreachable(c):
        raise source_contract.Unreachable("HTTP 429")
    _source_with(monkeypatch, unreachable)
    assert source_contract.check_source("fake")["status"] == "unreachable"

    def blocked(c):
        raise source_contract.Blocked("HTTP 999")
    _source_with(monkeypatch, blocked)
    assert source_contract.check_source("fake")["status"] == "blocked"


def test_one_failed_expectation_makes_the_source_broken(monkeypatch):
    def contract(c):
        c.expect("cards", True)
        c.expect("paging", False, "the second page repeats the first")
        c.note("page size", "10")
    _source_with(monkeypatch, contract)
    result = source_contract.check_source("fake")
    assert result["status"] == "broken"
    assert result["detail"] == "paging: the second page repeats the first"
    assert "/source-doctor fake" in source_contract.format_result(result)


def test_a_crashing_contract_is_broken_not_an_exception(monkeypatch):
    def contract(c):
        raise KeyError("title")
    _source_with(monkeypatch, contract)
    result = source_contract.check_source("fake")
    assert result["status"] == "broken" and "crashed" in result["detail"]


def test_a_contract_that_checks_nothing_proves_nothing(monkeypatch):
    _source_with(monkeypatch, lambda c: None)
    assert source_contract.check_source("fake")["status"] == "broken"


def test_a_source_without_a_contract_says_so(monkeypatch):
    monkeypatch.setattr(source_contract, "fetcher_modules", lambda: {"fake": "fake_module"})
    monkeypatch.setattr(source_contract.importlib, "import_module",
                        lambda name: types.SimpleNamespace())
    assert source_contract.check_source("fake")["status"] == "no_contract"


def test_every_registered_source_is_known_to_the_contracts():
    """The registry comes from the pipeline, so a new source cannot be wired in
    without being visible here."""
    import pipeline

    assert set(source_contract.fetcher_modules()) == set(pipeline.FETCHERS)
    assert "linkedin" in source_contract.sources_with_contracts()
