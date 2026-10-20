"""
A smoke test of the full pipeline WITHOUT network: every fetcher is replaced by
a fake function with data prepared in advance. What is checked is that the whole
fetch -> normalize -> score -> merge -> rescore -> companies -> report
cycle runs from end to end, does not fall over on one broken source, and really
does produce a report with meaningful content.
"""
import json

import pytest

import common
import kb
import pipeline


def fake_ok_source(records):
    def _fetch():
        return records, None

    return _fetch


def fake_crashing_source():
    def _fetch():
        raise RuntimeError("simulated network failure")

    return _fetch


def _disable_real_link_check(monkeypatch):
    """The pipeline smoke test has to work WITHOUT network — link_check.py makes
    real HTTP requests, so in tests it is replaced with a no-op."""
    import link_check

    def fake_check_links(vacancies, **kwargs):
        return {
            "checked": 0,
            "dead": 0,
            "ok": 0,
            "unknown": 0,
            "skipped_recent_or_duplicate": len(vacancies),
        }

    monkeypatch.setattr(link_check, "check_links", fake_check_links)


def test_full_pipeline_smoke(isolated_data_dir, monkeypatch):
    _disable_real_link_check(monkeypatch)
    good_records = [
        {
            "source": "arbeitnow",
            "external_id": "job-1",
            "title": "Senior .NET Developer - Legacy Insurance Platform",
            "company": "Old Reliable Insurance Co",
            "url": "https://example.com/jobs/1",
            "location_raw": "Remote - Anywhere",
            "remote": True,
            "tags": ["dotnet", "legacy"],
            "description_html": "<p>Maintain legacy ASP.NET WebForms system. Contractor via Deel, part-time, flexible hours, no on-call.</p>",
            "posted_at_epoch": 1700000000,
            "salary_raw": "$65/hour",
        },
        {
            "source": "arbeitnow",
            "external_id": "job-2",
            "title": "Junior Crypto Web3 Rockstar Ninja",
            "company": "Hypergrowth Startup Inc",
            "url": "https://example.com/jobs/2",
            "location_raw": "On-site required",
            "remote": False,
            "tags": ["crypto", "web3"],
            "description_html": "<p>Fast-paced startup, wear many hats, move fast, on-call rotation 24/7.</p>",
            "posted_at_epoch": 1700000000,
            "salary_raw": None,
        },
        {
            # a record without required fields — normalize should discard it
            "source": "arbeitnow",
            "title": "",
            "company": "",
            "url": "",
        },
    ]

    monkeypatch.setattr(pipeline, "FETCHERS", {
        "arbeitnow": fake_ok_source(good_records),
        "remoteok": fake_ok_source([]),
        "weworkremotely": fake_crashing_source(),  # simulate a source that died
        "hn_whoishiring": fake_ok_source([]),
    })

    result = pipeline.run_pipeline()

    assert result["new_vacancies"] == 2
    assert result["total_in_kb"] == 2

    vacancies = kb.load_vacancies()
    assert len(vacancies) == 2
    scores = {v["title"]: v["computed"]["classification"] for v in vacancies.values()}
    legacy_title = "Senior .NET Developer - Legacy Insurance Platform"
    startup_title = "Junior Crypto Web3 Rockstar Ninja"
    assert scores[legacy_title] in ("hot_lead", "worth_a_look")
    assert scores[startup_title] == "rejected"  # on-site required = hard dealbreaker

    state = common.load_json(common.STATE_PATH, default={})
    assert state["run_count"] == 1
    assert state["sources"]["weworkremotely"]["last_error"] is not None
    assert state["sources"]["weworkremotely"]["consecutive_failures"] == 1
    assert state["sources"]["arbeitnow"]["consecutive_failures"] == 0

    report_path = common.REPORTS_DIR / f"{common.FILE_PREFIX}latest.md"
    assert report_path.exists()
    report_text = report_path.read_text(encoding="utf-8")

    # The dated copy goes into the archive so that the root of reports/ does not
    # grow into a hundred files to search by eye for the latest one.
    # In the archive the file name is just a date: reports/archive/<prefix>/
    # already belongs to the identity, so repeating the prefix buys nothing.
    archived = list(common.REPORTS_ARCHIVE_DIR.glob("*.md"))
    assert len(archived) == 1, "the dated report should be in reports/archive/<prefix>/"
    assert archived[0].name[:2] == "20", f"an archived report is named by date, not {archived[0].name}"
    assert common.REPORTS_ARCHIVE_DIR.name == common.ACTIVE_IDENTITY
    assert not list(common.REPORTS_DIR.glob("2*.md")), (
        "there must be no dated reports at the root of reports/ — only latest"
    )
    assert legacy_title in report_text
    assert "Old Reliable Insurance Co" in report_text

    companies = kb.load_companies()
    assert any(c["name"] == "Old Reliable Insurance Co" for c in companies.values())


def test_pipeline_is_idempotent_and_preserves_manual_status(isolated_data_dir, monkeypatch):
    _disable_real_link_check(monkeypatch)
    record = [{
        "source": "arbeitnow",
        "external_id": "job-1",
        "title": "Senior .NET Developer",
        "company": "Acme Corp",
        "url": "https://example.com/jobs/1",
        "location_raw": "Remote - Anywhere",
        "remote": True,
        "tags": [],
        "description_html": "Legacy enterprise system maintenance, contractor, Deel.",
        "posted_at_epoch": 1700000000,
        "salary_raw": None,
    }]
    monkeypatch.setattr(pipeline, "FETCHERS", {
        "arbeitnow": fake_ok_source(record),
        "remoteok": fake_ok_source([]),
        "weworkremotely": fake_ok_source([]),
        "hn_whoishiring": fake_ok_source([]),
    })

    pipeline.run_pipeline()
    vacancies = kb.load_vacancies()
    vid = list(vacancies.keys())[0]
    vacancies[vid]["external_signals"]["salary_estimate"] = {
        "low": 60000, "high": 80000, "period": "year", "source": "Glassdoor"}
    kb.save_vacancies(vacancies)
    import db

    with db.session() as conn:     # the person's answer, written by the app
        conn.execute("UPDATE vacancy_identity SET feedback_status = 'applied', "
                     "feedback_at = '2026-07-30T10:00:00+00:00' "
                     "WHERE identity_id = ? AND vacancy_id = ?", (db.identity(), vid))

    # a second run with the same data must not create duplicates and must not
    # lose what was recorded about the vacancy in between
    result2 = pipeline.run_pipeline()
    assert result2["new_vacancies"] == 0
    assert result2["updated_vacancies"] == 1
    assert result2["total_in_kb"] == 1

    v = kb.load_vacancies()[vid]
    assert v["external_signals"]["salary_estimate"]["source"] == "Glassdoor"
    with db.session() as conn:
        assert conn.execute("SELECT feedback_status FROM vacancy_identity "
                            "WHERE identity_id = ? AND vacancy_id = ?",
                            (db.identity(), vid)).fetchone()[0] == "applied"


def test_ingest_manual_merges_into_same_kb_and_reruns_report(isolated_data_dir, monkeypatch):
    _disable_real_link_check(monkeypatch)
    import ingest_manual

    monkeypatch.setattr(pipeline, "FETCHERS", {
        "arbeitnow": fake_ok_source([]),
        "remoteok": fake_ok_source([]),
        "weworkremotely": fake_ok_source([]),
        "hn_whoishiring": fake_ok_source([]),
    })
    pipeline.run_pipeline()  # the database is empty, but state and report are created

    manual_records = [{
        "title": "Legacy VB.NET Maintenance Engineer",
        "company": "Big Slow Bank",
        "url": "https://www.linkedin.com/jobs/view/999",
        "location_raw": "Remote worldwide",
        "remote": True,
        "description_text": (
            "Maintain legacy VB.NET banking system, C# ASP.NET SQL Server. "
            "Contractor, 1099, part-time."
        ),
        "tags": ["linkedin"],
        "salary_raw": "$70/hour",
    }]

    result = ingest_manual.ingest(manual_records, source_name="linkedin")
    assert result["new_vacancies"] == 1

    vacancies = kb.load_vacancies()
    assert len(vacancies) == 1
    v = list(vacancies.values())[0]
    assert v["source"] == "linkedin"
    assert v["computed"]["classification"] in ("hot_lead", "worth_a_look")

    report_text = (common.REPORTS_DIR / f"{common.FILE_PREFIX}latest.md").read_text(encoding="utf-8")
    assert "Big Slow Bank" in report_text


def test_company_enrichment_runs_for_the_shortlist(isolated_data_dir, monkeypatch):
    """Audit 2026-08-04: company_intel was written, documented and mentioned in
    the report — and called from nowhere. Of 1083 companies, 22 had a known age,
    and all of them got there through manual runs. Meanwhile the trait
    "mature company, 10+ years" is written into ideal_company_traits outright:
    the system was asking for what it did not collect."""
    import company_intel
    import pipeline

    called = {}

    def fake_enrich(companies, only_names=None, **kwargs):
        called["names"] = set(only_names or [])
        return {"checked": len(called["names"]), "found": 0, "skipped": 0}

    monkeypatch.setattr(company_intel, "enrich_companies", fake_enrich)
    monkeypatch.setattr(pipeline.link_check, "check_links", lambda *_a, **_k: {})
    # Scoring is not exercised here: it would overwrite the manually set
    # classifications, and this test is precisely about WHOSE companies get enriched.
    monkeypatch.setattr(pipeline, "rescore_all", lambda *_a, **_k: None)

    vacancies = {
        "a": {"id": "a", "company": "Shortlisted Co", "title": "Senior C# Developer",
              "url": "https://example.com/a", "source": "test",
              "computed": {"classification": "worth_a_look", "score": 40,
                           "score_breakdown": {}, "dealbreakers": [],
                           "needs_manual_review": False}},
        "b": {"id": "b", "company": "Rejected Co", "title": "Chef",
              "url": "https://example.com/b", "source": "test",
              "computed": {"classification": "rejected", "score": 0,
                           "score_breakdown": {}, "dealbreakers": ["role: no"],
                           "needs_manual_review": False}},
    }
    pipeline.finalize_and_report(vacancies, {}, {})

    assert called["names"] == {"Shortlisted Co"}, (
        "only the visible part of the shortlist is enriched: the rest are filtered "
        "out anyway, and an external API does not deserve hundreds of pointless requests"
    )


def test_the_reputation_worklist_drops_a_company_once_it_has_a_result(tmp_path, monkeypatch):
    """The worklist for looking by hand (tools/reputation.py): the shortlist's
    companies with no result. Since 2026-10-17 the pipeline no longer records
    it; a lookup is the app's button (tools/reputation_lookup.py)."""
    import reputation

    vacancies = {
        "a": {"company": "Newco", "computed": {"classification": "hot_lead"}},
    }
    companies = {"newco": {"name": "Newco"}}

    todo = reputation.worklist(vacancies, companies)
    assert [item["company"] for item in todo] == ["Newco"]

    stats = reputation.coverage(vacancies, companies)
    assert stats == {"companies": 1, "found": 0, "insufficient": 0, "unchecked": 1}

    assert reputation.mark_insufficient(companies, "Newco", "Glassdoor")
    assert reputation.coverage(vacancies, companies)["insufficient"] == 1
    assert reputation.worklist(vacancies, companies) == [], (
        "once the result is recorded the company has to leave the worklist — "
        "otherwise every run searches again for reviews that do not exist"
    )


def test_a_source_closed_for_the_identity_is_not_fetched(monkeypatch):
    monkeypatch.setattr(pipeline, "FETCHERS", {"arbeitnow": object(), "contractoruk": object(),
                                               "reed": object()})
    sources_cfg = [{"name": "arbeitnow"}, {"name": "contractoruk"},
                   {"name": "reed", "enabled": False}, {"name": "manual", "kind": "manual_ingest"},
                   {"name": "no_fetcher"}]
    criteria = {"closed_sources": {"contractoruk": "applying is blocked",
                                   "devitjobs.uk": "a website, not a source"}}
    assert [s["name"] for s in pipeline.fetched_sources(sources_cfg, criteria)] == ["arbeitnow"]
    assert [s["name"] for s in pipeline.fetched_sources(sources_cfg, {})] == ["arbeitnow", "contractoruk"]


def test_linkedin_is_asked_for_the_days_since_the_last_collection_both_included():
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
    local = lambda days_ago, hour: (  # noqa: E731 — a local time `days_ago` days back
        datetime.combine(now.astimezone().date() - timedelta(days=days_ago),
                         datetime.min.time()).replace(hour=hour).astimezone().isoformat())
    base = {"v1": {"source": "linkedin"}}
    full = pipeline.LINKEDIN_FULL_DAYS

    # never collected, or the base holds no LinkedIn vacancy: the full window
    assert pipeline.linkedin_window({}, base, now) == full
    assert pipeline.linkedin_window({"linkedin_covered_to": local(1, 14)}, {"v1": {"source": "reed"}}, now) == full
    # collected today: today; yesterday afternoon: yesterday and today
    assert pipeline.linkedin_window({"linkedin_covered_to": local(0, 1)}, base, now) == 1
    assert pipeline.linkedin_window({"linkedin_covered_to": local(1, 14)}, base, now) == 2
    assert pipeline.linkedin_window({"linkedin_covered_to": local(1, 23)}, base, now) == 2
    # the last full run, four days back, as last_success: five days
    state = {"sources": {"linkedin": {"last_success": local(4, 6)}}}
    assert pipeline.linkedin_window(state, base, now) == 5
    # longer ago than the full window: the full window, a week
    assert full == 7
    assert pipeline.linkedin_window({"linkedin_covered_to": local(40, 6)}, base, now) == full

    # a fetch that went through moves the coverage and leaves no gap
    before = pipeline.linkedin_covered_to(state)
    state["sources"]["linkedin"]["last_success"] = now.isoformat()
    pipeline.note_linkedin_window(state, now, before)
    assert state["linkedin_covered_to"] == now.isoformat()
    assert state["linkedin_gap"] is False
    # a failed fetch keeps the old coverage (not last_success): the next run
    # asks for those days again
    failed = {"sources": {"linkedin": {"consecutive_failures": 1, "last_success": now.isoformat()}}}
    pipeline.note_linkedin_window(failed, now, local(3, 6))
    assert failed["linkedin_covered_to"] == local(3, 6)
    assert failed["linkedin_gap"] is True
    assert pipeline.linkedin_window(failed, base, now) == 4
    assert "the fetch failed" in pipeline.collected_text(failed, 4)
    # the LinkedIn run asks the base whether it holds LinkedIn, not for the base
    assert pipeline.linkedin_window_of(failed, True, now) == 4
    assert pipeline.linkedin_window_of(failed, False, now) == full


def test_the_top_subset_is_the_top_classes_and_what_this_run_brought():
    vacancies = {
        "hot": {"computed": {"classification": "hot_lead"}},
        "unconfirmed_old": {"computed": {"classification": "remote_unconfirmed"}},
        "unconfirmed_new": {"computed": {"classification": "remote_unconfirmed"}},
        "rejected": {"computed": {"classification": "rejected"}},
    }
    assert set(pipeline.top_subset(vacancies)) == {"hot"}
    assert set(pipeline.top_subset(vacancies, {"unconfirmed_new"})) == {"hot", "unconfirmed_new"}
    assert pipeline.top_subset(vacancies)["hot"] is vacancies["hot"], "the records are shared"


def test_the_top_run_end_to_end(isolated_data_dir, monkeypatch):
    import apply_channels
    import company_intel
    import enrich_descriptions

    asked = {}

    def linkedin(**params):
        asked.update(params)
        return [], None

    record = {
        "source": "arbeitnow", "external_id": "job-1",
        "title": "Senior .NET Developer", "company": "Old Reliable Insurance Co",
        "url": "https://example.com/jobs/1", "location_raw": "Remote - Anywhere", "remote": True,
        "tags": ["dotnet"], "description_html": "<p>C# and .NET, fully remote, contractor via Deel.</p>",
        "posted_at_epoch": 1700000000,
    }
    monkeypatch.setattr(pipeline, "FETCHERS", {"arbeitnow": fake_ok_source([record]), "linkedin": linkedin})
    monkeypatch.setattr(pipeline, "load_sources_config",
                        lambda: [{"name": "arbeitnow"}, {"name": "linkedin", "params": {"posted_within_days": 7}}])
    described = {}

    def fake_enrich(vacancies, **kwargs):
        described["ids"] = set(vacancies)
        described["limit"] = kwargs.get("limit")
        return {"considered": 0}

    checked = {}

    def fake_links(vacancies, **kwargs):
        checked["ids"] = set(vacancies)
        return {"checked": 0}

    monkeypatch.setattr(enrich_descriptions, "enrich", fake_enrich)
    monkeypatch.setattr(pipeline.link_check, "check_links", fake_links)
    monkeypatch.setattr(apply_channels, "collect", lambda *_a, **_k: {"considered": 0})
    monkeypatch.setattr(company_intel, "enrich_companies", lambda *_a, **_k: {"checked": 0})

    result = pipeline.run_top()

    assert asked == {}, "LinkedIn is its own run (--linkedin), beside the top run"
    assert "LinkedIn is not in this run" in result["collected"]
    assert result["new_vacancies"] == 1
    (vid,) = kb.load_vacancies()
    assert described["ids"] == {vid} and described["limit"] == pipeline.TOP_DESCRIPTION_LIMIT
    state = common.load_json(common.STATE_PATH, default={})
    assert state["last_run_stats"]["mode"] == "top"
    assert state["last_top_run_at"]
    assert "linkedin_covered_to" not in state, "the top run leaves LinkedIn's window alone"
    assert state["last_run_stats"]["linkedin_days"] is None
    assert "error" in state["last_ai_screen"], "no model in tests: the AI check is skipped, the run goes on"
    assert (common.REPORTS_DIR / f"{common.FILE_PREFIX}latest.md").exists()


def _linkedin_card(n):
    return {"source": "linkedin", "external_id": f"https://www.linkedin.com/jobs/view/{n}",
            "title": "Senior .NET Developer", "company": f"Company {n}",
            "url": f"https://www.linkedin.com/jobs/view/{n}", "location_raw": "United Kingdom",
            "remote": None, "tags": ["market:United Kingdom"], "description_text": "",
            "posted_at": "2026-10-19"}


def _quiet_top(monkeypatch):
    import apply_channels
    import company_intel
    import enrich_descriptions

    seen = {}

    def fake_enrich(vacancies, **kwargs):
        seen["described"] = set(vacancies)
        return {"considered": 0}
    monkeypatch.setattr(enrich_descriptions, "enrich", fake_enrich)
    monkeypatch.setattr(pipeline.link_check, "check_links", lambda *_a, **_k: {"checked": 0})
    monkeypatch.setattr(apply_channels, "collect", lambda *_a, **_k: {"considered": 0})
    monkeypatch.setattr(company_intel, "enrich_companies", lambda *_a, **_k: {"checked": 0})
    return seen


def test_the_linkedin_run_fetches_apart_then_merges_like_the_top_run(isolated_data_dir, monkeypatch):
    import db
    import runstate

    asked = {}

    def linkedin(**params):
        asked.update(params)
        # the fetch holds LinkedIn, not the base: another run may hold the base
        assert runstate.LinkedInFetch(wait=False).path.exists()
        assert runstate.current() is None
        return [_linkedin_card(1), _linkedin_card(2)], "queries 1, pages 1"

    monkeypatch.setattr(pipeline, "FETCHERS", {"linkedin": linkedin})
    monkeypatch.setattr(pipeline, "load_sources_config",
                        lambda: [{"name": "linkedin", "params": {"keywords": [".NET"]}}])
    seen = _quiet_top(monkeypatch)

    staged = pipeline.fetch_linkedin_apart()
    assert asked["posted_within_days"] == pipeline.LINKEDIN_FULL_DAYS, "no collection known: the full window"
    assert asked["keywords"] == [".NET"]
    assert str(asked["query_stats_to"]).startswith(str(common.DATA_DIR / "runs"))
    assert pipeline.linkedin_staged_path().exists(), "kept until it is merged"
    assert kb.load_vacancies() == {}, "the fetch writes nothing into the base"
    assert not runstate.LinkedInFetch(wait=False).path.exists(), "LinkedIn is free again"

    with runstate.PipelineRun(wait=True):
        result = pipeline.merge_linkedin(staged)
    assert result["new_vacancies"] == 2
    assert "the full window" in result["collected"]
    assert len(kb.load_vacancies()) == 2
    assert seen["described"] == set(kb.load_vacancies()), "the top run's steps, on what LinkedIn brought"
    assert not pipeline.linkedin_staged_path().exists()
    state = common.load_json(common.STATE_PATH, default={})
    assert state["linkedin_covered_to"] == staged["started_at"]
    assert state["last_linkedin_stats"]["new_vacancies"] == 2
    with db.session() as conn:
        assert conn.execute("SELECT kind FROM selections").fetchall() == [("rebuild",)], \
            "a rebuild: the top run's vacancies stay fresh, LinkedIn's new ones too"

    # the next run asks for the days since this one, both included
    asked.clear()
    pipeline.fetch_linkedin_apart()
    assert asked["posted_within_days"] == 1


def test_a_failed_linkedin_fetch_records_the_failure_without_loading_the_base(isolated_data_dir, monkeypatch):
    monkeypatch.setattr(pipeline, "FETCHERS", {"linkedin": lambda **_: ([], "errors: C#/UK: HTTPError")})
    monkeypatch.setattr(pipeline, "load_sources_config", lambda: [{"name": "linkedin"}])
    common.save_json_atomic(common.STATE_PATH, {"sources": {}, "linkedin_covered_to": "2026-10-15T06:00:00+00:00"})
    monkeypatch.setattr(kb, "load_vacancies", lambda: pytest.fail("the base was loaded for nothing"))

    result = pipeline.merge_linkedin(pipeline.fetch_linkedin_apart())
    state = common.load_json(common.STATE_PATH, default={})
    assert state["sources"]["linkedin"]["consecutive_failures"] == 1
    assert state["linkedin_covered_to"] == "2026-10-15T06:00:00+00:00", "the next run asks for those days again"
    assert "the fetch failed" in result["collected"]
    assert not pipeline.linkedin_staged_path().exists()


def test_an_identity_without_linkedin_has_nothing_to_fetch_apart(isolated_data_dir, monkeypatch):
    monkeypatch.setattr(pipeline, "FETCHERS", {"linkedin": lambda **_: pytest.fail("fetched")})
    monkeypatch.setattr(pipeline, "load_sources_config", lambda: [{"name": "linkedin", "enabled": False}])
    assert pipeline.fetch_linkedin_apart() is None


def test_the_rest_run_fetches_nothing(isolated_data_dir, monkeypatch):
    monkeypatch.setattr(pipeline, "FETCHERS", {"linkedin": lambda **_: pytest.fail("fetched")})
    monkeypatch.setattr(pipeline, "load_sources_config", lambda: [{"name": "linkedin"}])
    common.save_json_atomic(common.STATE_PATH, {"sources": {}, "linkedin_gap": True})
    monkeypatch.setattr(pipeline, "finalize_and_report", lambda *_a, **_k: "report.md")
    assert pipeline.run_rest()["new_vacancies"] == 0

