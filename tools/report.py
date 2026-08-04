"""
Генератор человекочитаемого Markdown-отчёта по текущей базе знаний.

Отчёт — главный интерфейс для владельца: он должен суметь за 10 минут
утреннего кофе просмотреть top-вакансии и понять, куда стоит откликнуться.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import kb  # noqa: E402

TOP_N_PER_SECTION = 15


def _fmt_amount(value: float) -> str:
    if value == int(value):
        return f"${int(value):,}"
    return f"${value:,.2f}"


def _fmt_salary_info(vacancy: dict, comp_bd: dict) -> str:
    """Всегда возвращает строку про ЗП с явным указанием источника —
    подтверждено владельцем явно (2026-07-30): указана ли зарплата прямо в
    вакансии, найдена агентом на стороннем сайте (Glassdoor и т.п.), или
    данных нет вообще — это должно быть видно прямо в отчёте, а не только
    влиять на score."""
    if comp_bd.get("explicit"):
        raw = vacancy.get("salary_raw")
        if raw:
            return f"{raw} _(источник: указано в вакансии)_"
        period_ru = {"annual_amounts_found": "год", "monthly_amounts_found": "мес", "hourly_amounts_found": "час"}
        parts = []
        for key, unit in period_ru.items():
            amounts = comp_bd.get(key) or []
            if not amounts:
                continue
            lo, hi = min(amounts), max(amounts)
            parts.append(f"{_fmt_amount(lo)}/{unit}" if lo == hi else f"{_fmt_amount(lo)}-{_fmt_amount(hi)}/{unit}")
        text = ", ".join(parts) if parts else "сумма упомянута в описании, но не распознана точно"
        return f"{text} _(источник: указано в вакансии)_"

    estimate = comp_bd.get("external_estimate")
    if estimate:
        period_ru = {"year": "год", "month": "мес", "hour": "час"}.get(estimate.get("period"), estimate.get("period"))
        source = estimate.get("source", "неизвестный сторонний источник")
        note = estimate.get("note")
        note_str = f", заметка: {note}" if note else ""
        return (
            f"{_fmt_amount(estimate['low'])}-{_fmt_amount(estimate['high'])}/{period_ru} "
            f"_(источник: {source}, найдено вручную на стороннем сайте{note_str})_"
        )

    return "не указана _(источник: нет данных — ни в вакансии, ни найдено вручную)_"


def _fmt_reputation(rep_bd: dict) -> str:
    """Строка про репутацию работодателя. Как и с зарплатой, всегда явно
    показываем источник и отличаем "нет данных" от "плохо"."""
    if not rep_bd.get("has_data"):
        return (
            "не проверялась _(нет данных — проверить через "
            "`tools/kb.py set-company-reputation`)_"
        )
    parts = []
    if rep_bd.get("overall_rating") is not None:
        parts.append(f"общий {rep_bd['overall_rating']}/5")
    if rep_bd.get("work_life_balance") is not None:
        parts.append(f"work-life balance {rep_bd['work_life_balance']}/5")
    text = ", ".join(parts) if parts else "оценка без цифр"
    source = rep_bd.get("source", "?")
    # Показываем не только ЧТО за источник, но и КАК данные получены:
    # цифры из поисковой выдачи — это вторая рука, сам первоисточник
    # (Glassdoor и т.п.) отдаёт 403 скриптам и агентом не открывался.
    retrieval_note = {
        "web_search": ", данные из поисковой выдачи — первоисточник не открывался",
        "direct": ", страница первоисточника прочитана",
        "owner": ", со слов владельца",
    }.get(rep_bd.get("retrieval"), "")
    flags = rep_bd.get("red_flags") or []
    flag_str = f" ⚠ красные флаги: {', '.join(flags)}" if flags else ""
    alarming = " 🚨 очень низкий рейтинг" if rep_bd.get("alarming_rating") else ""
    return f"{text} _(источник: {source}{retrieval_note})_{alarming}{flag_str}"


def _fmt_vacancy_line(v: dict) -> str:
    c = v.get("computed", {})
    score = c.get("score", 0)
    title = v.get("title", "?")
    company = v.get("company", "?")
    url = v.get("url", "")
    manual = v.get("manual", {})
    status = manual.get("status", "new")

    bd = c.get("score_breakdown", {})
    highlights = []
    legacy_hits = bd.get("legacy_enterprise_signal", {}).get("hits", [])
    if legacy_hits:
        highlights.append("legacy/enterprise: " + ", ".join(legacy_hits[:5]))
    rl = bd.get("remote_location_fit", {})
    if rl.get("worldwide_remote_hits"):
        highlights.append("worldwide remote")
    if rl.get("eor_or_contractor_hits"):
        highlights.append("EOR/contractor: " + ", ".join(rl["eor_or_contractor_hits"][:3]))
    if rl.get("acceptable_region_hits"):
        highlights.append("приемлемый регион найма: " + ", ".join(rl["acceptable_region_hits"][:3]))
    intensity = bd.get("low_intensity_signal", {})
    if intensity.get("positive_hits"):
        highlights.append("низкая нагрузка: " + ", ".join(intensity["positive_hits"][:4]))
    complexity = bd.get("role_complexity_signal", {})
    if complexity.get("gate_triggered"):
        highlights.append("⚠ похоже на сложную/R&D роль, не 'простую'")
    if c.get("needs_manual_review"):
        highlights.append("🔎 требует ручной проверки (см. ниже)")
    link_status = v.get("link_check", {}).get("status")
    if link_status == "unknown":
        highlights.append("🔗 ссылку не удалось однозначно проверить")

    highlight_str = f" — _{'; '.join(highlights)}_" if highlights else ""
    salary_line = _fmt_salary_info(v, bd.get("compensation_signal", {}))
    lines = [
        f"- **[{score}] {title}** @ {company} — [ссылка]({url}) — статус: `{status}`{highlight_str}",
        f"  - 💰 ЗП: {salary_line}",
    ]
    # Прямой сайт работодателя, если известен — чтобы можно было найти ту же
    # вакансию на карьерной странице и откликнуться без аккаунта на
    # джоб-борде (WWR держит воронку отклика у себя, см. docs/SOURCES.md).
    company_url = v.get("company_url")
    if company_url:
        lines.append(f"  - 🏢 сайт компании (отклик напрямую): {company_url}")
    lines.append(f"  - ⭐ репутация: {_fmt_reputation(bd.get('company_reputation_signal', {}))}")
    age_bd = bd.get("company_age_signal", {})
    if age_bd.get("has_data"):
        emp = f", ~{age_bd['employees']} сотрудников" if age_bd.get("employees") else ""
        lines.append(
            f"  - 🏛 компания: основана {age_bd['founded_year']} "
            f"({age_bd['age_years']} лет{emp}) _(Wikidata)_"
        )
    if manual.get("notes"):
        lines.append(f"  - заметка: {manual['notes']}")
    return "\n".join(lines)


def _section(title: str, items: list) -> str:
    if not items:
        return f"### {title}\n\n_Пока пусто._\n"
    body = "\n".join(_fmt_vacancy_line(v) for v in items[:TOP_N_PER_SECTION])
    extra = len(items) - TOP_N_PER_SECTION
    footer = f"\n\n_(ещё {extra} записей этого класса не показаны — см. `python tools/kb.py list`)_" if extra > 0 else ""
    return f"### {title} ({len(items)})\n\n{body}{footer}\n"


def _rel(path: Optional[Path]) -> str:
    """Путь относительно корня репозитория — так его удобнее копировать."""
    if path is None:
        return "?"
    try:
        return str(path.relative_to(common.ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


_DEFAULT_PHILOSOPHY = (
    "Чем выше score (0-100), тем больше вакансия соответствует профилю этой "
    "идентичности."
)


def _scoring_philosophy() -> str:
    """Объяснение шкалы score — своё у каждой идентичности.

    Раньше здесь стояла зашитая строка про «скучную, легаси, хорошо
    оплачиваемую» вакансию. Она печаталась в отчёт ЛЮБОЙ идентичности, включая
    ту, что ищет онсайт в стартапе, — то есть общая машинерия навязывала всем
    философию одного профиля поиска. Артефакт времён, когда профиль был один.
    """
    try:
        philosophy = ((common.load_profile().get("identity") or {})
                      .get("scoring_philosophy") or "").strip()
        return philosophy or _DEFAULT_PHILOSOPHY
    except Exception:  # noqa: BLE001 — подпись не должна ронять отчёт
        return _DEFAULT_PHILOSOPHY


def _identity_display_name() -> str:
    try:
        import identity as identity_mod

        return identity_mod.describe(common.ACTIVE_IDENTITY)
    except Exception:  # noqa: BLE001 - подпись не должна ронять отчёт
        return common.ACTIVE_IDENTITY or "не определена"


def _ambiguous_places_hint(criteria: Optional[dict]) -> str:
    """Подсказка про неоднозначные топонимы — из настроек активной идентичности,
    а не захардкоженная. У каждого человека своя ловушка: для одного это
    Georgia (страна vs штат), для другого Cambridge (UK vs Массачусетс)."""
    rules = ((criteria or {}).get("remote_location_fit") or {}).get("ambiguous_place_names") or []
    names = [r.get("name") for r in rules if r.get("name")]
    if not names:
        return "неоднозначная гео-локация"
    quoted = ", ".join(f'"{n}"' for n in names[:3])
    return f"неоднозначная гео-локация (например {quoted})"


def _format_link_check_stats(stats: Optional[dict]) -> str:
    if not stats:
        return "_нет данных (первый запуск после добавления проверки ссылок)_"
    return (
        f"Проверено на этом запуске: {stats.get('checked', 0)} "
        f"(пропущено — недавно проверенные или дубли: {stats.get('skipped_recent_or_duplicate', 0)}). "
        f"Живые: {stats.get('ok', 0)}, убраны как мёртвые (404/410): {stats.get('dead', 0)}, "
        f"не удалось однозначно проверить (не скрыты): {stats.get('unknown', 0)}."
    )


def build_report_markdown(vacancies: dict, companies: dict, state: dict,
                          criteria: Optional[dict] = None) -> str:
    import score

    now = datetime.now(timezone.utc)
    # Тексты отчёта, зависящие от настроек (например подсказка про
    # неоднозначные топонимы), берутся из активной идентичности.
    if criteria is None:
        try:
            criteria = score.load_criteria()
        except Exception:  # noqa: BLE001 - отчёт не должен падать из-за подсказки
            criteria = {}
    live = [v for v in vacancies.values() if not v.get("duplicate_of")]
    dead_link_count = sum(1 for v in live if v.get("link_check", {}).get("status") == "dead")
    items = [v for v in live if v.get("link_check", {}).get("status") != "dead"]
    duplicate_count = len(vacancies) - len(live)

    def by_class(cls):
        matching = [v for v in items if v.get("computed", {}).get("classification") == cls]
        matching.sort(key=lambda v: -v.get("computed", {}).get("score", 0))
        return matching

    hot = by_class("hot_lead")
    worth = by_class("worth_a_look")
    long_shot = by_class("long_shot")
    review_items = [v for v in items if v.get("computed", {}).get("needs_manual_review")]
    review_items.sort(key=lambda v: -v.get("computed", {}).get("score", 0))

    class_counts = {}
    for v in items:
        cls = v.get("computed", {}).get("classification", "unknown")
        class_counts[cls] = class_counts.get(cls, 0) + 1

    source_lines = []
    for name, info in sorted((state.get("sources") or {}).items()):
        status = "OK" if not info.get("last_error") else f"ERROR: {info['last_error']}"
        source_lines.append(
            f"- **{name}**: {info.get('fetched_count', 0)} записей на последнем запуске, "
            f"{status}, подряд неудач: {info.get('consecutive_failures', 0)}"
        )

    run_stats = state.get("last_run_stats", {})

    parts = [
        # Идентичность в заголовке: отчёт часто открывают отдельной вкладкой или
        # пересылают, и он обязан себя опознавать без контекста.
        f"# Work IDE [{common.ACTIVE_IDENTITY or '?'}] — отчёт от "
        f"{now.strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"_Идентичность поиска: {_identity_display_name()}_",
        "",
        f"Запуск №{state.get('run_count', '?')}. "
        f"Показано вакансий: {len(items)} "
        f"(схлопнуто {duplicate_count} почти-дублей, убрано {dead_link_count} с "
        f"подтверждённо нерабочей ссылкой — см. `python tools/kb.py stats`). "
        f"Новых на этом запуске: {run_stats.get('new_vacancies', '?')}. "
        f"Компаний в базе: {len(companies)}.",
        "",
        "## Как читать этот отчёт",
        "",
        f"{_scoring_philosophy()} "
        "`hot_lead` — смотреть в первую очередь. Полная разбивка score по каждой "
        "вакансии: `python tools/kb.py show --id <id>`.",
        "",
        "## 🔥 Hot leads — смотреть в первую очередь",
        "",
        _section("hot_lead", hot),
        "## 👀 Worth a look",
        "",
        _section("worth_a_look", worth),
        "## 🕰️ Long shot (низкий приоритет, но не исключено)",
        "",
        _section("long_shot", long_shot),
        "## 🔎 Требуют ручной проверки агентом/владельцем",
        "",
        "Это вакансии, где автоматика не уверена в оценке — чаще всего "
        f"{_ambiguous_places_hint(criteria)}, либо непонятно, готова ли компания "
        "нанять человека из вашей страны. Стоит явно перепроверить через "
        "веб-поиск и, если нужно, обновить запись через `tools/kb.py`.",
        "",
        _section("needs_manual_review", review_items),
        "## 📊 Статистика по классам",
        "",
        "\n".join(f"- {cls}: {n}" for cls, n in sorted(class_counts.items(), key=lambda kv: -kv[1])) or "_нет данных_",
        "",
        "## 📡 Здоровье источников",
        "",
        "\n".join(source_lines) or "_нет данных_",
        "",
        "## 🔗 Проверка ссылок",
        "",
        _format_link_check_stats(state.get("last_link_check")),
        "",
        "## Дальше",
        "",
        f"- Накопленные закономерности о рынке: `{_rel(common.INSIGHTS_PATH)}`",
        f"- Полная база вакансий: `{_rel(common.VACANCIES_PATH)}` "
        f"(или `python tools/kb.py list --identity {common.ACTIVE_IDENTITY}`)",
        f"- Архив прошлых отчётов: `{_rel(common.REPORTS_ARCHIVE_DIR)}`",
        "- Отметить статус после отклика: `python tools/kb.py set-status "
        f"--identity {common.ACTIVE_IDENTITY} --id <id> --status applied --notes \"...\"`",
        "",
    ]
    return "\n".join(parts)


def write_report(markdown_text: str, run_date: Optional[str] = None) -> Path:
    """Пишет свежий отчёт и кладёт датированную копию в архив.

    Раскладка (по прямой просьбе владельца, улучшение для всех пользователей):
        reports/<prefix>_latest.md        — свежие подборки всех идентичностей
        reports/archive/<prefix>/<дата>.md — история, разложенная по идентичностям

    Два отдельных решения, у каждого своя причина:
      * `reports/` лежит в КОРНЕ репозитория, а не внутри `data/<префикс>/`.
        Отчёт — единственный файл, который человек открывает руками; искать его
        в дереве накопленных данных неудобно.
      * latest отделён от датированных копий. Иначе через пару месяцев работы
        папка превращается в сотню файлов, среди которых глазами ищут свежий.
    """
    common.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    common.REPORTS_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    run_date = run_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prefix = common.FILE_PREFIX or ""

    latest_path = common.REPORTS_DIR / f"{prefix}latest.md"
    # В архиве префикс в имени не нужен: папка уже принадлежит идентичности.
    archived_path = common.REPORTS_ARCHIVE_DIR / f"{run_date}.md"

    latest_path.write_text(markdown_text, encoding="utf-8")
    archived_path.write_text(markdown_text, encoding="utf-8")
    return latest_path


def main() -> None:
    import identity as identity_mod

    parser = argparse.ArgumentParser(description="Пересобирает отчёт по текущей базе знаний")
    identity_mod.add_identity_arg(parser)
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)

    vacancies = kb.load_vacancies()
    companies = kb.load_companies()
    state = common.load_json(common.STATE_PATH, default={})
    md = build_report_markdown(vacancies, companies, state)
    path = write_report(md)
    print(f"Отчёт сохранён: {path}")


if __name__ == "__main__":
    main()
