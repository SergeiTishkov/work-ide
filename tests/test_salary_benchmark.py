"""
The UK market yardstick, and the two things it must never become.

IT Jobs Watch publishes no vacancies — only six-month rolling medians per
technology. What it fills is the middle of the three levels of trust in a
salary (CLAUDE.md section 5): a person reading "£55,000 - £60,000" cannot tell
whether that is generous or poor, and with the market median beside it they
can.

The prohibitions are what most of this file tests, because both would be easy
and both would be wrong:

  * it must not fill in a VACANCY's salary — a market median is not what this
    employer pays, and writing it onto a record invents a fact about a company;
  * it must not touch the SCORE — every UK .NET vacancy would gain the same
    points, changing no ordering and making the number less honest.

No network here: the fetch is replaced, as everywhere else in this suite.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import salary_benchmark as bench  # noqa: E402

PAGE = """
<html><body>
<h1>.NET Job Trends</h1>
<p>The table below provides summary statistics and salary benchmarking for jobs
requiring .NET skills. It covers permanent job vacancies from the 6 months
leading up to 7 September 2026.</p>
<table>
<tr><td>Median annual salary (50 th Percentile)</td><td>&#163;60,000</td></tr>
<tr><td>% change year-on-year</td><td>-4.00</td></tr>
</table>
</body></html>
"""


def test_a_median_and_its_year_on_year_change_are_read(monkeypatch):
    import requests

    class FakeResponse:
        status_code = 200
        text = PAGE

    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse())
    monkeypatch.setattr(bench.time, "sleep", lambda *_: None)

    result = bench._fetch_one("jobs", ".net", 10)

    assert result["median"] == "£60,000"
    assert result["year_on_year"] == "-4.00%"
    assert result["url"].endswith("/jobs/uk/.net.do")


def test_a_page_without_a_median_yields_nothing_rather_than_a_guess(monkeypatch):
    import requests

    class FakeResponse:
        status_code = 200
        text = "<html><body>No data for this technology.</body></html>"

    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse())

    assert bench._fetch_one("jobs", "nonsense", 10) is None


def test_a_failed_request_never_raises(monkeypatch):
    """A yardstick is a nicety. It must not be able to break a research cycle
    that has already collected, scored and enriched."""
    import requests

    def explode(*a, **k):
        raise RuntimeError("network")

    monkeypatch.setattr(requests, "get", explode)

    assert bench._fetch_one("jobs", ".net", 10) is None


# --- the slugs are measured, not guessed -----------------------------------

def test_only_verified_slugs_are_listed():
    """Measured 2026-09-08: "c%23", "sql-server", "angular" and
    "entity-framework" all answer 404. The site's own names are "csharp",
    "t-sql" and "angularjs". A benchmark silently covering half a stack is
    worse than none."""
    assert bench.SLUGS["C#"] == "csharp"
    assert bench.SLUGS["SQL Server"] == "t-sql"
    assert bench.SLUGS["Angular"] == "angularjs"
    assert "sql-server" not in bench.SLUGS.values()
    assert "c%23" not in bench.SLUGS.values()


def test_the_technologies_follow_the_identitys_own_stack():
    """No configuration of its own: the benchmark tracks whatever the person's
    core stack says, so a different identity gets a different table without
    anyone editing this file."""
    dotnet = bench.technologies_from_profile(
        {"tech_stack": {"core": [".NET", "C#", "COBOL"]}})

    assert dotnet == [".NET", "C#"], "COBOL is not on the site; .NET and C# are"

    # An identity whose core stack the site knows nothing about still gets
    # something rather than an empty table.
    assert bench.technologies_from_profile({"tech_stack": {"core": ["COBOL"]}})


# --- caching ---------------------------------------------------------------

def test_fresh_data_is_not_refetched(monkeypatch, tmp_path):
    """Six-month rolling statistics move slowly. Refetching them every run
    would be rude and would tell nobody anything new."""
    monkeypatch.setattr(bench, "_cache_path", lambda: tmp_path / "bench.json")
    fresh = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "technologies": {".NET": {"permanent": {"median": "£60,000"}}},
    }
    bench.save(fresh)

    def must_not_be_called(*a, **k):
        raise AssertionError("fresh data was refetched")

    monkeypatch.setattr(bench, "collect", must_not_be_called)

    assert bench.refresh_if_stale()["technologies"][".NET"]["permanent"]["median"] == "£60,000"


def test_stale_data_is_refreshed(monkeypatch, tmp_path):
    monkeypatch.setattr(bench, "_cache_path", lambda: tmp_path / "bench.json")
    old = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    bench.save({"collected_at": old, "technologies": {".NET": {}}})

    monkeypatch.setattr(bench, "collect", lambda *a, **k: {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "technologies": {".NET": {"permanent": {"median": "£61,000"}}},
    })

    result = bench.refresh_if_stale()

    assert result["technologies"][".NET"]["permanent"]["median"] == "£61,000"


def test_a_failed_refresh_keeps_the_old_numbers(monkeypatch, tmp_path):
    """A month-old median is still a useful yardstick. Losing the block
    entirely because the site was down is a worse outcome than showing a
    figure with its date on it."""
    monkeypatch.setattr(bench, "_cache_path", lambda: tmp_path / "bench.json")
    old = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    bench.save({"collected_at": old,
                "technologies": {".NET": {"permanent": {"median": "£58,000"}}}})

    monkeypatch.setattr(bench, "collect", lambda *a, **k: {"technologies": {}})

    result = bench.refresh_if_stale()

    assert result["technologies"][".NET"]["permanent"]["median"] == "£58,000"


def test_missing_or_corrupt_cache_reads_as_stale(monkeypatch, tmp_path):
    monkeypatch.setattr(bench, "_cache_path", lambda: tmp_path / "bench.json")

    assert bench.load() is None
    assert bench.is_stale(None)

    (tmp_path / "bench.json").write_text("{not json", encoding="utf-8")
    assert bench.load() is None
    assert bench.is_stale({"collected_at": "not a date", "technologies": {"x": {}}})


# --- the two prohibitions --------------------------------------------------

def test_the_benchmark_is_not_a_scoring_component():
    """Asserted against the scorer's own source, because the failure this
    guards against is silent: a market median folded into points would change
    every UK vacancy equally and be invisible in the result."""
    source = (Path(__file__).resolve().parent.parent / "tools" / "score.py"
              ).read_text(encoding="utf-8")

    assert "salary_benchmark" not in source, (
        "the scorer must not read the market yardstick")


def test_the_benchmark_never_writes_onto_a_vacancy():
    """A market median is not what THIS employer pays. Writing it onto a
    record would invent a fact about a company — the same confusion CLAUDE.md
    section 5 forbids in the other direction."""
    source = (Path(__file__).resolve().parent.parent / "tools" /
              "salary_benchmark.py").read_text(encoding="utf-8")

    for forbidden in ("salary_raw", "external_estimate", "vacancies["):
        assert forbidden not in source, (
            f"the benchmark touches {forbidden}, which is a vacancy's own field")
