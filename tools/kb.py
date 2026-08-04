"""
База знаний (Knowledge Base): вакансии, компании, рекрутеры.

Хранится как человекочитаемый JSON в data/knowledge/*.json. Здесь же —
CLI для ручного управления записями (agent/owner отмечает статус вакансии,
добавляет заметку, смотрит статистику), которым можно пользоваться из
интерактивной сессии без необходимости лезть в JSON руками.

Важный инвариант: повторный запуск пайплайна НИКОГДА не должен затирать
поле "manual" (status/notes), которое мог отредактировать человек/агент.
Оно создаётся один раз при первом обнаружении вакансии со значением по
умолчанию и дальше трогается только через merge_vacancy(..., manual_patch=)
или CLI-команды этого файла.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import score  # noqa: E402

VALID_STATUSES = (
    "new",
    "shortlisted",
    "applied",
    "interviewing",
    "offer",
    "rejected_by_owner",
    "dead_link",
    "not_relevant",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Загрузка / сохранение ------------------------------------------------
#
# Каждая функция начинается с require_identity(). Это code-level реализация
# правила №0: без активной идентичности любое касание данных должно падать с
# понятным объяснением, а не с "NoneType has no attribute 'exists'". Формально
# activate_identity() и так вызывается раньше — но именно эти шесть функций
# являются входной дверью к данным, и дешевле проверить здесь, чем однажды
# записать вакансии одного человека в базу другого.

def load_vacancies() -> dict:
    common.require_identity()
    return common.load_json(common.VACANCIES_PATH, default={})


def save_vacancies(vacancies: dict) -> None:
    common.require_identity()
    common.save_json_atomic(common.VACANCIES_PATH, vacancies)


def load_companies() -> dict:
    common.require_identity()
    return common.load_json(common.COMPANIES_PATH, default={})


def save_companies(companies: dict) -> None:
    common.require_identity()
    common.save_json_atomic(common.COMPANIES_PATH, companies)


def load_recruiters() -> list:
    common.require_identity()
    return common.load_json(common.RECRUITERS_PATH, default=[])


def save_recruiters(recruiters: list) -> None:
    common.require_identity()
    common.save_json_atomic(common.RECRUITERS_PATH, recruiters)


# --- Слияние вакансий -----------------------------------------------------

def merge_vacancy(kb: dict, normalized: dict, computed: dict) -> str:
    """Вставляет/обновляет вакансию в kb (dict, ключ = id). Возвращает
    "new" или "updated". Поля "manual" и "external_signals" создаются один
    раз и больше не трогаются автоматикой — это данные, которые заносит
    человек/агент (статус отклика, вручную найденная вилка ЗП с Glassdoor и
    т.п. через `tools/kb.py set-salary-estimate`), и следующий прогон
    пайплайна не имеет права их стереть, пересобирая запись с нуля."""
    vid = normalized["id"]
    ts = now_iso()
    existing = kb.get(vid)

    if existing is None:
        kb[vid] = {
            **normalized,
            "first_seen": ts,
            "last_seen": ts,
            "fetched_at": ts,
            "computed": computed,
            "manual": {"status": "new", "notes": ""},
            "external_signals": {},
        }
        return "new"

    manual = existing.get("manual", {"status": "new", "notes": ""})
    external_signals = existing.get("external_signals", {})
    kb[vid] = {
        **normalized,
        "first_seen": existing.get("first_seen", ts),
        "last_seen": ts,
        "fetched_at": ts,
        "computed": computed,
        "manual": manual,
        "external_signals": external_signals,
    }
    return "updated"


def mark_duplicates(vacancies: dict) -> int:
    """Помечает почти-дубли (одна и та же вакансия, опубликованная дважды —
    например, замечено на практике: We Work Remotely иногда отдаёт один и тот
    же пост под двумя разными URL). Дублями считаются записи с ТОЧНЫМ
    совпадением нормализованной пары (компания, заголовок). Каноническая
    запись — с лучшим score (при равенстве — самая ранняя по first_seen);
    остальные получают top-level поле "duplicate_of" и исключаются из отчёта.

    Важно: сознательно НЕ используется fuzzy-сравнение заголовков. На
    реальных данных это давало серьёзные false positives — например,
    "Software Engineer - Manchester" и "Software Engineer - Newcastle" (одна
    компания массово нанимает на одну роль в разных городах) или
    "(Native Danish) Support Consultant" / "(Native Finnish) Support
    Consultant" (разные вакансии под разные языки) fuzzy-совпадали на >90% и
    ошибочно схлопывались в одну, пряча от владельца реально разные открытые
    позиции. Спрятать настоящую вакансию — куда хуже, чем изредка показать
    безобидный точный повтор, поэтому порог сознательно строгий (exact match).

    Пересчитывается с нуля на каждом запуске (иначе при исчезновении дубля
    из выдачи источника пометка осталась бы навсегда)."""
    for v in vacancies.values():
        v.pop("duplicate_of", None)

    by_key: dict = {}
    for vid, v in vacancies.items():
        key = (
            common.normalize_company_name(v.get("company")),
            common.normalize_for_matching(v.get("title")),
        )
        by_key.setdefault(key, []).append(vid)

    marked = 0
    for ids in by_key.values():
        if len(ids) < 2:
            continue
        ids.sort(
            key=lambda vid: (
                -(vacancies[vid].get("computed", {}).get("score", 0)),
                vacancies[vid].get("first_seen") or "",
            )
        )
        canonical = ids[0]
        for vid in ids[1:]:
            vacancies[vid]["duplicate_of"] = canonical
            marked += 1
    return marked


def build_companies_from_vacancies(vacancies: dict, previous_companies: Optional[dict] = None) -> dict:
    """companies.json — производное представление от vacancies.json (плюс
    ручные заметки per-company). Пересобирается целиком на каждом запуске,
    чтобы счётчики (vacancy_ids, signals) никогда не расходились с реальным
    состоянием базы вакансий. first_seen и notes переносятся из предыдущей
    версии, чтобы не терять историю."""
    companies: dict = {}
    for slug, old in (previous_companies or {}).items():
        carried = {
            "name": old.get("name", slug),
            "first_seen": old.get("first_seen"),
            "last_seen": old.get("last_seen"),
            "vacancy_ids": [],
            "signals": {
                "legacy_enterprise_hits": 0,
                "eor_or_contractor_mentioned": False,
                "worldwide_remote_seen": False,
            },
            "notes": old.get("notes", ""),
        }
        # Репутация собрана вручную агентом (дорогая, требует веб-поиска) —
        # переносим, как notes и first_seen, иначе она терялась бы при
        # каждой пересборке companies.json.
        if old.get("reputation"):
            carried["reputation"] = old["reputation"]
        if old.get("intel"):
            carried["intel"] = old["intel"]
        companies[slug] = carried
    for v in vacancies.values():
        upsert_company(companies, v.get("company", "Unknown"), v)
    return companies


def upsert_company(companies: dict, company_name: str, vacancy: dict) -> None:
    slug = common.normalize_company_name(company_name)
    ts = now_iso()
    entry = companies.get(slug)
    computed = vacancy.get("computed", {})
    breakdown = computed.get("score_breakdown", {})

    eor_hits = breakdown.get("remote_location_fit", {}).get("eor_or_contractor_hits", [])
    worldwide_hits = breakdown.get("remote_location_fit", {}).get("worldwide_remote_hits", [])
    legacy_hits = breakdown.get("legacy_enterprise_signal", {}).get("hits", [])

    if entry is None:
        entry = {
            "name": company_name,
            "first_seen": ts,
            "last_seen": ts,
            "vacancy_ids": [],
            "signals": {
                "legacy_enterprise_hits": 0,
                "eor_or_contractor_mentioned": False,
                "worldwide_remote_seen": False,
            },
            "notes": "",
        }
        companies[slug] = entry

    entry["last_seen"] = ts
    if vacancy["id"] not in entry["vacancy_ids"]:
        entry["vacancy_ids"].append(vacancy["id"])
    entry["signals"]["legacy_enterprise_hits"] = max(
        entry["signals"]["legacy_enterprise_hits"], len(legacy_hits)
    )
    entry["signals"]["eor_or_contractor_mentioned"] = (
        entry["signals"]["eor_or_contractor_mentioned"] or bool(eor_hits)
    )
    entry["signals"]["worldwide_remote_seen"] = (
        entry["signals"]["worldwide_remote_seen"] or bool(worldwide_hits)
    )


# --- CLI --------------------------------------------------------------

def cmd_stats(_args) -> None:
    vacancies = load_vacancies()
    if not vacancies:
        print("База знаний пуста. Запустите tools/pipeline.py.")
        return
    by_class = {}
    for v in vacancies.values():
        cls = v.get("computed", {}).get("classification", "unknown")
        by_class[cls] = by_class.get(cls, 0) + 1
    print(f"Всего вакансий в базе: {len(vacancies)}")
    for cls, n in sorted(by_class.items(), key=lambda kv: -kv[1]):
        print(f"  {cls}: {n}")
    review = sum(1 for v in vacancies.values() if v.get("computed", {}).get("needs_manual_review"))
    print(f"  требуют ручной проверки: {review}")
    dupes = sum(1 for v in vacancies.values() if v.get("duplicate_of"))
    print(f"  почти-дублей (скрыты в отчёте): {dupes}")
    dead = sum(1 for v in vacancies.values() if v.get("link_check", {}).get("status") == "dead")
    print(f"  мёртвых ссылок (скрыты в отчёте): {dead}")


def cmd_list(args) -> None:
    vacancies = load_vacancies()
    items = [v for v in vacancies.values() if not v.get("duplicate_of") or args.include_duplicates]
    if args.classification:
        items = [v for v in items if v.get("computed", {}).get("classification") == args.classification]
    items.sort(key=lambda v: -v.get("computed", {}).get("score", 0))
    for v in items[: args.limit]:
        c = v.get("computed", {})
        print(f"[{c.get('score'):>3}] {c.get('classification'):14} {v['company'][:30]:30} | {v['title'][:60]}")
        print(f"       id={v['id']} status={v.get('manual', {}).get('status')} url={v['url']}")


def cmd_show(args) -> None:
    vacancies = load_vacancies()
    v = vacancies.get(args.id)
    if not v:
        print(f"Вакансия с id={args.id} не найдена.")
        sys.exit(1)
    import json

    print(json.dumps(v, ensure_ascii=False, indent=2))


def cmd_set_status(args) -> None:
    if args.status not in VALID_STATUSES:
        print(f"Недопустимый статус. Допустимые: {', '.join(VALID_STATUSES)}")
        sys.exit(1)
    vacancies = load_vacancies()
    v = vacancies.get(args.id)
    if not v:
        print(f"Вакансия с id={args.id} не найдена.")
        sys.exit(1)
    v.setdefault("manual", {"status": "new", "notes": ""})
    v["manual"]["status"] = args.status
    if args.notes is not None:
        v["manual"]["notes"] = args.notes
    save_vacancies(vacancies)
    print(f"OK: {args.id} -> status={args.status}")


def cmd_set_salary_estimate(args) -> None:
    """Заносит вручную найденную (например, через Glassdoor) вилку ЗП для
    вакансии, которая сама зарплату не указывает. Подтверждено владельцем
    явно (2026-07-30): такая оценка даёт маленький плюс — меньше, чем явно
    указанная в вакансии ставка, но больше, чем полное отсутствие данных.
    Хранится в vacancy.external_signals (не в manual!) — именно поэтому
    участвует в скоринге, а не только в отображении."""
    vacancies = load_vacancies()
    v = vacancies.get(args.id)
    if not v:
        print(f"Вакансия с id={args.id} не найдена.")
        sys.exit(1)

    v.setdefault("external_signals", {})
    v["external_signals"]["salary_estimate"] = {
        "low": args.low,
        "high": args.high,
        "period": args.period,
        "source": args.source,
        "note": args.note or "",
    }

    # Пересчитываем score сразу, чтобы изменение было видно немедленно, не
    # дожидаясь следующего запуска tools/pipeline.py.
    criteria = score.load_criteria()
    profile = score.load_profile()
    vacancy_view = {k: val for k, val in v.items() if k not in ("computed", "manual")}
    v["computed"] = score.score_vacancy(vacancy_view, criteria, profile)
    save_vacancies(vacancies)
    print(
        f"OK: {args.id} -> external salary estimate "
        f"{args.low}-{args.high}/{args.period} (источник: {args.source}). "
        f"Новый score: {v['computed']['score']} ({v['computed']['classification']})"
    )


def cmd_set_company_reputation(args) -> None:
    """Заносит репутацию работодателя, найденную агентом во внешних
    источниках (Glassdoor/Indeed/Trustpilot). Хранится на уровне КОМПАНИИ,
    поэтому применяется сразу ко всем её вакансиям.

    Автоматически скрейпить эти площадки нельзя (ToS), поэтому данные
    собирает агент обычным веб-поиском и заносит сюда — тот же принцип, что
    и с `set-salary-estimate`."""
    companies = load_companies()
    slug = common.normalize_company_name(args.company)
    entry = companies.get(slug)
    if entry is None:
        matches = [s for s in companies if args.company.lower().replace(" ", "-") in s]
        hint = f" Похожие: {', '.join(matches[:5])}" if matches else ""
        print(f"Компания '{args.company}' (slug={slug}) не найдена в базе.{hint}")
        sys.exit(1)

    reputation = {
        "overall_rating": args.rating,
        "work_life_balance": args.wlb,
        "source": args.source,
        # КАК именно получены цифры. Важное различие, всплывшее по вопросу
        # владельца (2026-07-31): "источник: Glassdoor" читается как "агент
        # открыл страницу Glassdoor и посмотрел", тогда как на деле сам
        # Glassdoor отдаёт 403 любому скрипту, и цифры взяты из СНИППЕТОВ
        # поисковой выдачи. Это второисточник: если сниппет устарел или
        # поисковик выдернул число из другого контекста, агент этого не
        # заметит. Данные обязаны честно показывать свою достоверность.
        #   web_search  - из поисковой выдачи, первоисточник НЕ открывался
        #   direct      - страница первоисточника реально прочитана
        #   owner       - владелец сообщил лично
        "retrieval": args.retrieval,
        "review_count": args.reviews,
        "red_flags": [f.strip() for f in (args.red_flags or "").split(",") if f.strip()],
        "notes": args.notes or "",
        "checked_at": now_iso(),
    }
    entry["reputation"] = reputation
    save_companies(companies)

    # Пересчитываем score всех вакансий этой компании сразу, чтобы эффект
    # был виден немедленно, не дожидаясь следующего pipeline.py.
    vacancies = load_vacancies()
    criteria = score.load_criteria()
    profile = score.load_profile()
    updated = 0
    for vid in entry.get("vacancy_ids", []):
        v = vacancies.get(vid)
        if not v:
            continue
        vacancy_view = {k: val for k, val in v.items() if k not in ("computed", "manual")}
        vacancy_view["_company_reputation"] = reputation
        v["computed"] = score.score_vacancy(vacancy_view, criteria, profile)
        updated += 1
    save_vacancies(vacancies)

    print(
        f"OK: {entry['name']} -> rating={args.rating} wlb={args.wlb} "
        f"(источник: {args.source}). Пересчитано вакансий: {updated}"
    )


def attach_company_reputation(vacancies: dict, companies: dict) -> None:
    """Прокидывает репутацию компании в каждую её вакансию перед скорингом.
    Вызывается пайплайном: репутация живёт на уровне компании, а score
    считается на уровне вакансии."""
    by_slug = {}
    for slug, entry in companies.items():
        payload = {}
        if entry.get("reputation"):
            payload["reputation"] = entry["reputation"]
        if entry.get("intel"):
            payload["intel"] = entry["intel"]
        if payload:
            by_slug[slug] = payload
    for v in vacancies.values():
        payload = by_slug.get(common.normalize_company_name(v.get("company")), {})
        if payload.get("reputation"):
            v["_company_reputation"] = payload["reputation"]
        else:
            v.pop("_company_reputation", None)
        if payload.get("intel"):
            v["_company_intel"] = payload["intel"]
        else:
            v.pop("_company_intel", None)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Управление базой знаний Work IDE")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("stats", help="Сводная статистика по базе знаний").set_defaults(func=cmd_stats)

    p_list = sub.add_parser("list", help="Список вакансий, отсортированный по score")
    p_list.add_argument("--classification", default=None, choices=[
        "hot_lead", "worth_a_look", "long_shot", "low_priority", "rejected"
    ])
    p_list.add_argument("--limit", type=int, default=20)
    p_list.add_argument("--include-duplicates", action="store_true", help="Не скрывать помеченные дубли")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="Полная запись вакансии по id")
    p_show.add_argument("--id", required=True)
    p_show.set_defaults(func=cmd_show)

    p_status = sub.add_parser("set-status", help="Изменить manual.status/notes вакансии")
    p_status.add_argument("--id", required=True)
    p_status.add_argument("--status", required=True)
    p_status.add_argument("--notes", default=None)
    p_status.set_defaults(func=cmd_set_status)

    p_salary = sub.add_parser(
        "set-salary-estimate",
        help="Указать вручную найденную (напр. Glassdoor) вилку ЗП для вакансии без явной ставки",
    )
    p_salary.add_argument("--id", required=True)
    p_salary.add_argument("--low", type=float, required=True)
    p_salary.add_argument("--high", type=float, required=True)
    p_salary.add_argument("--period", choices=["year", "month", "hour"], default="year")
    p_salary.add_argument("--source", required=True, help="Например: Glassdoor")
    p_salary.add_argument("--note", default=None)
    p_salary.set_defaults(func=cmd_set_salary_estimate)

    p_rep = sub.add_parser(
        "set-company-reputation",
        help="Занести репутацию компании из внешних источников (Glassdoor и т.п.)",
    )
    p_rep.add_argument("--company", required=True, help="Название компании как в базе")
    p_rep.add_argument("--rating", type=float, default=None, help="Общий рейтинг 1..5")
    p_rep.add_argument("--wlb", type=float, default=None, help="Work-life balance 1..5")
    p_rep.add_argument("--source", required=True, help="Первоисточник данных, например: Glassdoor")
    p_rep.add_argument(
        "--retrieval",
        choices=["web_search", "direct", "owner"],
        default="web_search",
        help="КАК получены цифры: web_search — из поисковой выдачи (первоисточник не "
             "открывался, данные второй руки); direct — страница реально прочитана; "
             "owner — со слов владельца",
    )
    p_rep.add_argument("--reviews", type=int, default=None, help="Количество отзывов")
    p_rep.add_argument("--red-flags", default=None, help="Через запятую: layoffs,toxic,...")
    p_rep.add_argument("--notes", default=None)
    p_rep.set_defaults(func=cmd_set_company_reputation)

    return p


def main(argv: Optional[list] = None) -> None:
    import identity as identity_mod

    parser = build_parser()
    identity_mod.add_identity_arg(parser)
    args = parser.parse_args(argv)
    identity_mod.activate_or_exit(getattr(args, "identity", None))
    args.func(args)


if __name__ == "__main__":
    main()
