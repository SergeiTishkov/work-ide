"""
Smoke-тест полного пайплайна БЕЗ сети: все фетчеры подменены на фейковые
функции с заранее подготовленными данными. Проверяем, что весь цикл
fetch -> normalize -> score -> merge -> rescore -> companies -> report
отрабатывает от начала до конца, не падает на одном сломанном источнике и
реально производит отчёт с осмысленным содержимым.
"""
import json

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
    """Смоук-тест пайплайна должен работать БЕЗ сети - link_check.py делает
    настоящие HTTP-запросы, поэтому в тестах подменяем его на no-op."""
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
            # запись без обязательных полей - должна быть отброшена normalize'ом
            "source": "arbeitnow",
            "title": "",
            "company": "",
            "url": "",
        },
    ]

    monkeypatch.setattr(pipeline, "FETCHERS", {
        "arbeitnow": fake_ok_source(good_records),
        "remoteok": fake_ok_source([]),
        "weworkremotely": fake_crashing_source(),  # симулируем упавший источник
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

    # Датированная копия уходит в архив, чтобы корень reports/ не зарастал
    # сотней файлов, среди которых глазами ищут latest.
    # В архиве имя файла — просто дата: папка reports/archive/<префикс>/ уже
    # принадлежит идентичности, повторять префикс в каждом имени незачем.
    archived = list(common.REPORTS_ARCHIVE_DIR.glob("*.md"))
    assert len(archived) == 1, "датированный отчёт должен лежать в reports/archive/<префикс>/"
    assert archived[0].name[:2] == "20", f"имя архивного отчёта — дата, а не {archived[0].name}"
    assert common.REPORTS_ARCHIVE_DIR.name == common.ACTIVE_IDENTITY
    assert not list(common.REPORTS_DIR.glob("2*.md")), (
        "в корне reports/ не должно быть датированных отчётов — только latest"
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
    vacancies[vid]["manual"]["status"] = "applied"
    vacancies[vid]["manual"]["notes"] = "Sent CV on 2026-07-30"
    kb.save_vacancies(vacancies)

    # второй запуск с теми же данными не должен создавать дублей и не должен
    # затирать manual.status/notes
    result2 = pipeline.run_pipeline()
    assert result2["new_vacancies"] == 0
    assert result2["updated_vacancies"] == 1
    assert result2["total_in_kb"] == 1

    vacancies_after = kb.load_vacancies()
    v = vacancies_after[vid]
    assert v["manual"]["status"] == "applied"
    assert v["manual"]["notes"] == "Sent CV on 2026-07-30"


def test_ingest_manual_merges_into_same_kb_and_reruns_report(isolated_data_dir, monkeypatch):
    _disable_real_link_check(monkeypatch)
    import ingest_manual

    monkeypatch.setattr(pipeline, "FETCHERS", {
        "arbeitnow": fake_ok_source([]),
        "remoteok": fake_ok_source([]),
        "weworkremotely": fake_ok_source([]),
        "hn_whoishiring": fake_ok_source([]),
    })
    pipeline.run_pipeline()  # база пустая, но state/report создаются

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
    """Ревизия 2026-08-04: company_intel был написан, задокументирован и
    упомянут в отчёте — но не вызывался ниоткуда. Из 1083 компаний возраст
    знали у 22, и все они попали туда ручными запусками. При этом признак
    «зрелая компания 10+ лет» прямо записан в ideal_company_traits: система
    просила то, чего не собирала."""
    import company_intel
    import pipeline

    called = {}

    def fake_enrich(companies, only_names=None, **kwargs):
        called["names"] = set(only_names or [])
        return {"checked": len(called["names"]), "found": 0, "skipped": 0}

    monkeypatch.setattr(company_intel, "enrich_companies", fake_enrich)
    monkeypatch.setattr(pipeline.link_check, "check_links", lambda *_a, **_k: {})
    # Скоринг здесь не проверяется: он перезаписал бы выставленные вручную
    # классификации, а тест ровно про то, ЧЬИ компании попадают в обогащение.
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
        "обогащаем только видимую часть выдачи: остальные компании всё равно "
        "отсеяны, а внешний API не заслуживает сотен запросов впустую"
    )
