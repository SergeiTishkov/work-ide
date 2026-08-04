"""
Оркестратор исследовательского цикла Work IDE.

python tools/pipeline.py            -> полный цикл: fetch всех enabled
                                        источников -> normalize -> merge в
                                        базу знаний -> rescoring ВСЕЙ базы
                                        (не только новых записей — так
                                        улучшения в criteria.yaml применяются
                                        ретроактивно) -> перестройка
                                        companies.json -> отчёт.

Никогда не падает целиком из-за одного упавшего источника: каждый источник
обёрнут в try/except, ошибка попадает в data/state.json и в отчёт, пайплайн
идёт дальше.
"""
from __future__ import annotations

import argparse
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import fetch_arbeitnow  # noqa: E402
import fetch_ats  # noqa: E402
import fetch_himalayas  # noqa: E402
import fetch_hn_whoishiring  # noqa: E402
import fetch_jobicy  # noqa: E402
import fetch_linkedin  # noqa: E402
import fetch_devitjobs  # noqa: E402
import fetch_jobs_ch  # noqa: E402
import fetch_landing_jobs  # noqa: E402
import fetch_mycareersfuture  # noqa: E402
import fetch_rss_boards  # noqa: E402
import fetch_workingnomads  # noqa: E402
import fetch_remoteok  # noqa: E402
import fetch_remotive  # noqa: E402
import fetch_wwr  # noqa: E402
import kb  # noqa: E402
import company_intel  # noqa: E402
import link_check  # noqa: E402
import normalize  # noqa: E402
import report  # noqa: E402
import score  # noqa: E402

FETCHERS = {
    "arbeitnow": fetch_arbeitnow.fetch,
    "remoteok": fetch_remoteok.fetch,
    "weworkremotely": fetch_wwr.fetch,
    "hn_whoishiring": fetch_hn_whoishiring.fetch,
    "remotive": fetch_remotive.fetch,
    "jobicy": fetch_jobicy.fetch,
    "himalayas": fetch_himalayas.fetch,
    "ats": fetch_ats.fetch,
    "linkedin": fetch_linkedin.fetch,
    "devitjobs": fetch_devitjobs.fetch,
    "jobs_ch": fetch_jobs_ch.fetch,
    "mycareersfuture": fetch_mycareersfuture.fetch,
    "landing_jobs": fetch_landing_jobs.fetch,
    "workingnomads": fetch_workingnomads.fetch,
    "rss_boards": fetch_rss_boards.fetch,
}


def _archive_raw_records(source_name: str, raw_records: list) -> None:
    """Аудиторский след: сырые данные с источника, как они были на момент
    запуска, до какой-либо нормализации/скоринга. Не критично для работы
    пайплайна — ошибка записи не должна его останавливать."""
    if not raw_records:
        return
    try:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = common.RAW_DIR / source_name / f"{date_str}.jsonl"
        common.append_jsonl(path, raw_records)
    except Exception as exc:  # noqa: BLE001 - аудит необязателен для успеха пайплайна
        common.eprint(f"[pipeline] failed to archive raw records for '{source_name}': {exc}")


def load_sources_config() -> list:
    return common.load_sources()


def fetch_params(src: dict) -> dict:
    """Аргументы, которые получит фетчер: эндпоинт из общего каталога плюс
    параметры идентичности.

    До разделения конфигов поле `url` в конфигурации источников было мёртвым:
    каждый фетчер хардкодил свой API_URL, а пайплайн звал `fetch_fn()` вообще
    без аргументов. Теперь конфигурация действительно управляет запросом.
    """
    params = dict(src.get("params") or {})
    # url/urls берём из каталога, но только если фетчер их принимает и
    # идентичность не задала своё значение.
    for key in ("url", "urls"):
        if key in src and key not in params:
            params[key] = src[key]
    return params


def fetch_source_safely(name: str, fetch_fn, params: Optional[dict] = None):
    """Никогда не бросает исключение — сетевые/парсинговые баги одного
    источника не должны валить весь исследовательский цикл.

    Неизвестный фетчеру параметр — не повод падать: конфиг мог уйти вперёд кода
    (или наоборот). Такой параметр отбрасывается с записью в лог, а сбор
    продолжается тем, что фетчер понимает.
    """
    params = params or {}
    try:
        try:
            records, note = fetch_fn(**params)
        except TypeError as exc:
            if params and "unexpected keyword argument" in str(exc):
                common.eprint(
                    f"[pipeline] источник '{name}' не принимает часть параметров "
                    f"({exc}); вызываю без них"
                )
                records, note = fetch_fn()
            else:
                raise
        return records or [], note
    except Exception as exc:  # noqa: BLE001 - намеренно широкий catch на границе источника
        tb = traceback.format_exc(limit=3)
        common.eprint(f"[pipeline] source '{name}' crashed:\n{tb}")
        return [], f"CRASHED: {type(exc).__name__}: {exc}"


def rescore_all(vacancies: dict, criteria: dict, profile: dict, companies: Optional[dict] = None) -> None:
    """Ретроактивный rescoring ВСЕЙ базы — если criteria.yaml/profile.yaml
    стали умнее со времени прошлого запуска, старые вакансии тоже должны
    получить актуальную оценку, а не только новые. Используется и полным
    пайплайном, и tools/ingest_manual.py.

    companies нужен, чтобы прокинуть в скоринг репутацию работодателя —
    она хранится на уровне компании, а score считается на уровне вакансии."""
    if companies:
        kb.attach_company_reputation(vacancies, companies)
    for v in vacancies.values():
        vacancy_view = {k: val for k, val in v.items() if k not in ("computed", "manual")}
        v["computed"] = score.score_vacancy(vacancy_view, criteria, profile)


def finalize_and_report(vacancies: dict, prev_companies: dict, state: dict) -> str:
    """Общий хвост цикла: пересчёт компаний, сохранение KB/state, генерация
    отчёта. Возвращает путь к отчёту."""
    criteria = score.load_criteria()
    profile = score.load_profile()
    # prev_companies содержит уже накопленную репутацию — передаём её в
    # скоринг до пересборки companies.json.
    rescore_all(vacancies, criteria, profile, prev_companies)
    kb.mark_duplicates(vacancies)
    link_stats = link_check.check_links(vacancies)
    state["last_link_check"] = link_stats
    companies = kb.build_companies_from_vacancies(vacancies, prev_companies)

    # Обогащение компаний из выдачи фактами из Wikidata (год основания, размер).
    #
    # Раньше этот модуль существовал, был задокументирован и упоминался в
    # отчёте — но не вызывался ниоткуда. Ревизия 2026-08-04: из 1083 компаний
    # возраст был известен у 22, и все они попали туда ручными запусками.
    # Признак "зрелая компания 10+ лет" при этом прямо записан в
    # ideal_company_traits, то есть система просила то, чего не собирала.
    #
    # Обогащаем ТОЛЬКО компании из видимой части выдачи: остальные всё равно
    # отсеяны, а Wikidata не заслуживает сотен запросов впустую. Кэш на 30
    # дней — по тому же принципу, что и в link_check.
    shortlist_companies = {
        v.get("company")
        for v in vacancies.values()
        if (v.get("computed") or {}).get("classification") in
           ("hot_lead", "worth_a_look", "long_shot")
        and not v.get("duplicate_of") and v.get("company")
    }
    if shortlist_companies:
        try:
            state["last_company_intel"] = company_intel.enrich_companies(
                companies, only_names=shortlist_companies, limit=60
            )
        except Exception as exc:  # noqa: BLE001 — обогащение не должно ронять цикл
            state["last_company_intel"] = {"error": f"{type(exc).__name__}: {exc}"}
        # Пересчёт после обогащения: возраст компании участвует в score.
        rescore_all(vacancies, criteria, profile, companies)

    kb.save_vacancies(vacancies)
    kb.save_companies(companies)
    common.save_json_atomic(common.STATE_PATH, state)

    if not (common.KNOWLEDGE_DIR / "insights.md").exists():
        (common.KNOWLEDGE_DIR / "insights.md").write_text(
            "# Insights — накопленные закономерности о рынке\n\n"
            "_Этот файл ведётся вручную агентом/владельцем по итогам анализа "
            "отчётов. Пайплайн его не перезаписывает._\n",
            encoding="utf-8",
        )

    md = report.build_report_markdown(vacancies, companies, state)
    report_path = report.write_report(md)
    return str(report_path)


def run_pipeline(include_manual_placeholder_note: bool = True) -> dict:
    common.ensure_dirs()
    sources_cfg = load_sources_config()
    criteria = score.load_criteria()
    profile = score.load_profile()

    vacancies = kb.load_vacancies()
    prev_companies = kb.load_companies()
    state = common.load_json(common.STATE_PATH, default={"run_count": 0, "sources": {}})
    state.setdefault("sources", {})

    new_count = 0
    updated_count = 0
    total_fetched = 0
    total_skipped = 0

    for src in sources_cfg:
        name = src.get("name")
        if not src.get("enabled", True) or src.get("kind") == "manual_ingest":
            continue
        fetch_fn = FETCHERS.get(name)
        if fetch_fn is None:
            continue

        raw_records, err = fetch_source_safely(name, fetch_fn, fetch_params(src))
        _archive_raw_records(name, raw_records)
        normalized, skipped = normalize.normalize_batch(raw_records)
        total_fetched += len(normalized)
        total_skipped += skipped

        src_state = state["sources"].setdefault(name, {"consecutive_failures": 0})
        fetch_failed = bool(err) and not normalized
        src_state["consecutive_failures"] = (
            src_state.get("consecutive_failures", 0) + 1 if fetch_failed else 0
        )
        src_state["last_error"] = err
        src_state["fetched_count"] = len(normalized)
        src_state["skipped_count"] = skipped
        src_state["last_attempt_at"] = kb.now_iso()
        if not fetch_failed:
            src_state["last_success"] = kb.now_iso()

        for rec in normalized:
            computed = score.score_vacancy(rec, criteria, profile)
            action = kb.merge_vacancy(vacancies, rec, computed)
            if action == "new":
                new_count += 1
            else:
                updated_count += 1

    state["run_count"] = state.get("run_count", 0) + 1
    state["last_run_at"] = kb.now_iso()
    state["last_run_stats"] = {
        "new_vacancies": new_count,
        "updated_vacancies": updated_count,
        "total_fetched_this_run": total_fetched,
        "total_skipped_this_run": total_skipped,
    }

    report_path = finalize_and_report(vacancies, prev_companies, state)

    return {
        "new_vacancies": new_count,
        "updated_vacancies": updated_count,
        "total_in_kb": len(vacancies),
        "report_path": report_path,
    }


def main() -> None:
    import identity as identity_mod

    parser = argparse.ArgumentParser(description="Полный исследовательский цикл Work IDE")
    identity_mod.add_identity_arg(parser)
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)

    result = run_pipeline()
    print("Пайплайн завершён:")
    for k, v in result.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
