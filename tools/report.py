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
import i18n  # noqa: E402
import kb  # noqa: E402

# Английский текст — исходник, перевод берётся из словаря. Подробности и
# обоснование выбора «ключ = английская фраза» — в tools/i18n.py.
t = i18n.translate

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
            return f"{raw} _({t('source: stated in the vacancy')})_"
        periods = {"annual_amounts_found": t("year"),
                   "monthly_amounts_found": t("month"),
                   "hourly_amounts_found": t("hour")}
        parts = []
        for key, unit in periods.items():
            amounts = comp_bd.get(key) or []
            if not amounts:
                continue
            lo, hi = min(amounts), max(amounts)
            parts.append(f"{_fmt_amount(lo)}/{unit}" if lo == hi else f"{_fmt_amount(lo)}-{_fmt_amount(hi)}/{unit}")
        text = (", ".join(parts) if parts
                else t("amount mentioned in the description but not parsed reliably"))
        return f"{text} _({t('source: stated in the vacancy')})_"

    estimate = comp_bd.get("external_estimate")
    if estimate:
        period = {"year": t("year"), "month": t("month"),
                  "hour": t("hour")}.get(estimate.get("period"), estimate.get("period"))
        source = estimate.get("source", t("unknown third-party source"))
        note = estimate.get("note")
        note_str = f", {t('note')}: {note}" if note else ""
        return (
            f"{_fmt_amount(estimate['low'])}-{_fmt_amount(estimate['high'])}/{period} "
            f"_({t('source')}: {source}, {t('found manually on a third-party site')}{note_str})_"
        )

    return (t("not stated") + " _("
            + t("source: no data — neither in the vacancy nor found manually") + ")_")


def _fmt_reputation(rep_bd: dict, classification: str = "") -> str:
    """Строка про репутацию работодателя. Как и с зарплатой, всегда явно
    показываем источник и отличаем "нет данных" от "плохо"."""
    # Три состояния, а не два. Различие введено по прямой просьбе владельца
    # 2026-08-06 и закрывает настоящую двусмысленность: «не проверялась»
    # читалось как «данных нет», а означало «мы даже не пытались». Первое —
    # свойство компании, второе — дефект процесса, и человеку важно, какое
    # из двух он видит.
    if rep_bd.get("verdict") == "insufficient_sources":
        when = (rep_bd.get("checked_at") or "")[:10]
        where = rep_bd.get("searched") or "Glassdoor, Indeed, Trustpilot, web search"
        return (f"{t('checked')}{' ' + when if when else ''}, "
                f"{t('not determined — not enough sources')} "
                f"_({t('searched')}: {where}; "
                f"{t('usually the case for small, little-known companies')})_")

    if not rep_bd.get("has_data"):
        import reputation

        if classification in reputation.REQUIRED_CLASSES:
            return (
                "❗ " + t("not checked yet") + " _("
                + t("this is a gap in the process, not a property of the company")
                + ": `python tools/reputation.py worklist`)_"
            )
        # В хвосте выдачи проверка не делается сознательно — см. reputation.py.
        return (t("not checked") + " _("
                + t("tail of the shortlist: companies at worth_a_look and above are checked")
                + ")_")
    parts = []
    if rep_bd.get("overall_rating") is not None:
        parts.append(f"{t('overall')} {rep_bd['overall_rating']}/5")
    if rep_bd.get("work_life_balance") is not None:
        parts.append(f"{t('work-life balance')} {rep_bd['work_life_balance']}/5")
    text = ", ".join(parts) if parts else t("rating without numbers")
    source = rep_bd.get("source", "?")
    # Показываем не только ЧТО за источник, но и КАК данные получены:
    # цифры из поисковой выдачи — это вторая рука, сам первоисточник
    # (Glassdoor и т.п.) отдаёт 403 скриптам и агентом не открывался.
    retrieval_note = {
        "web_search": ", " + t("data from search results — the primary source was not opened"),
        "direct": ", " + t("the primary source page was read"),
        "owner": ", " + t("as told by the owner"),
    }.get(rep_bd.get("retrieval"), "")
    flags = rep_bd.get("red_flags") or []
    flag_str = f" ⚠ {t('red flags')}: {', '.join(flags)}" if flags else ""
    alarming = " 🚨 " + t("very low rating") if rep_bd.get("alarming_rating") else ""
    return f"{text} _({t('source')}: {source}{retrieval_note})_{alarming}{flag_str}"


_TECH_VOCABULARY_CACHE = {}


def _tech_vocabulary() -> dict:
    """Словарь технологий: каноническое имя -> формы написания.

    Общий для всех идентичностей: список того, что бывает в вакансиях, не
    зависит от того, кто ищет. Лежит в config/tech_vocabulary.yaml.
    """
    if not _TECH_VOCABULARY_CACHE:
        path = common.SHARED_CONFIG_DIR / "tech_vocabulary.yaml"
        data = (common.load_yaml(path) or {}).get("technologies") or {}
        _TECH_VOCABULARY_CACHE.update(data)
    return _TECH_VOCABULARY_CACHE


def expected_technologies(vacancy: dict, limit: int = 24) -> list:
    """Технологии, которых ждут на проекте — включая незнакомые человеку.

    Отдельно от stack_fit: тот показывает совпадения со стеком конкретного
    человека, а здесь нужен состав проекта как он есть. Увидеть в отчёте
    незнакомую технологию не менее полезно, чем знакомую: по ней сразу видно,
    подходит вакансия или нет, без открытия ссылки.
    """
    haystack = common.normalize_for_matching(chr(10).join([
        vacancy.get("title") or "",
        " ".join(vacancy.get("tags") or []),
        vacancy.get("description_text") or "",
    ]))
    if not haystack:
        return []

    found = []
    for canonical, forms in _tech_vocabulary().items():
        for form in (forms or []):
            if common.normalize_for_matching(form) in haystack:
                found.append(canonical)
                break
        if len(found) >= limit:
            break
    return found


# Страны в тех написаниях, которыми их называют площадки.
_COUNTRY_ALIASES = {
    "usa": "United States", "us": "United States", "u.s.": "United States",
    "united states of america": "United States", "america": "United States",
    "uk": "United Kingdom", "u.k.": "United Kingdom", "england": "United Kingdom",
    "scotland": "United Kingdom", "wales": "United Kingdom",
    "northern ireland": "United Kingdom", "great britain": "United Kingdom",
    "uae": "United Arab Emirates", "u.a.e.": "United Arab Emirates",
    "ksa": "Saudi Arabia", "holland": "Netherlands", "deutschland": "Germany",
    "schweiz": "Switzerland", "suisse": "Switzerland", "österreich": "Austria",
    "españa": "Spain", "italia": "Italy", "sverige": "Sweden", "norge": "Norway",
    "danmark": "Denmark", "suomi": "Finland", "éire": "Ireland",
    "czechia": "Czech Republic", "czech republic": "Czech Republic",
}

# Откуда узнали страну. Константы, а не строки на месте: их СРАВНИВАЮТ, и
# перевод сравниваемого значения — классический способ тихо сломать логику.
HIRING_OFFICE = "hiring office"
COMPANY_HOME = "company home country"

_COUNTRY_INDEX_CACHE = {}


def _country_index() -> dict:
    """Нормализованное название страны -> каноническое.

    Список стран берётся из общей таблицы рынков: она и так перечисляет всё,
    что проекту интересно, и поддерживать второй список незачем.
    """
    if "data" not in _COUNTRY_INDEX_CACHE:
        import markets

        index = {}
        for spec in (markets.load_tiers() or {}).values():
            for country in spec.get("countries") or []:
                name = country.get("name")
                if name:
                    index[common.normalize_for_matching(name)] = name
        for alias, canonical in _COUNTRY_ALIASES.items():
            index.setdefault(alias, canonical)
        _COUNTRY_INDEX_CACHE["data"] = index
    return _COUNTRY_INDEX_CACHE["data"]


def hiring_country(vacancy: dict):
    """(страна, откуда узнали) — или (None, None).

    Нужна СТРАНА НАЙМА, а не родина компании. У международной компании это
    разные вещи: швейцарский офис Google нанимает в Швейцарии, и человеку
    важна именно Швейцария — там оформляют договор, оттуда платят, тот
    часовой пояс. Поэтому порядок источников такой:

      1. тег площадки `market:<страна>` — страна, по которой фетчер делал
         запрос, то есть офис, разместивший вакансию. Это факт, а не догадка;
      2. последний элемент поля локации ("Barendrecht, South Holland,
         Netherlands");
      3. любое упоминание страны в поле локации ("Remote, Israel");
      4. заголовок "Headquarters:" из описания — уже штаб-квартира, а не
         офис найма, поэтому идёт последним и помечается явно.
    """
    index = _country_index()

    for tag in vacancy.get("tags") or []:
        tag = str(tag)
        if tag.startswith("market:"):
            name = index.get(common.normalize_for_matching(tag[7:]), tag[7:])
            return name, HIRING_OFFICE

    location = (vacancy.get("location_raw") or "").strip()
    if location:
        parts = [p.strip() for p in location.split(",") if p.strip()]
        if parts:
            direct = index.get(common.normalize_for_matching(parts[-1]))
            if direct:
                return direct, HIRING_OFFICE
        normalized = common.normalize_for_matching(location)
        for needle, canonical in index.items():
            if needle and needle in normalized:
                return canonical, HIRING_OFFICE

    header = (vacancy.get("computed", {}).get("score_breakdown", {})
              .get("remote_location_fit", {}).get("header_scope", {}))
    for line in header.get("header_lines") or []:
        if not line.startswith("headquarters:"):
            continue
        for needle, canonical in index.items():
            if needle and needle in line:
                return canonical, COMPANY_HOME

    return None, None


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
    intensity = bd.get("low_intensity_signal", {})
    if intensity.get("positive_hits"):
        highlights.append(t("low intensity") + ": " + ", ".join(intensity["positive_hits"][:4]))
    complexity = bd.get("role_complexity_signal", {})
    if complexity.get("gate_triggered"):
        highlights.append("⚠ " + t("looks like a complex/R&D role, not a simple one"))
    if c.get("needs_manual_review"):
        highlights.append("🔎 " + t("needs a manual check (see below)"))
    link_status = v.get("link_check", {}).get("status")
    if link_status == "unknown":
        highlights.append("🔗 " + t("the link could not be verified conclusively"))

    highlight_str = f" — _{'; '.join(highlights)}_" if highlights else ""
    salary_line = _fmt_salary_info(v, bd.get("compensation_signal", {}))
    lines = [
        f"- **[{score}] {title}** @ {company} — [{t('link')}]({url}) — "
        f"{t('status')}: `{status}`{highlight_str}",
        f"  - 💰 {t('salary')}: {salary_line}",
    ]
    # Прямой сайт работодателя, если известен — чтобы можно было найти ту же
    # вакансию на карьерной странице и откликнуться без аккаунта на
    # джоб-борде (WWR держит воронку отклика у себя, см. docs/SOURCES.md).
    company_url = v.get("company_url")
    if company_url:
        lines.append(f"  - 🏢 {t('company site (apply directly)')}: {company_url}")
    techs = expected_technologies(v)
    if techs:
        lines.append(f"  - 🧰 {t('technologies')}: {', '.join(techs)}")
    lines.append("  - ⭐ " + t("reputation") + ": " + _fmt_reputation(
        bd.get("company_reputation_signal", {}), c.get("classification", "")))
    country, country_source = hiring_country(v)
    if country:
        suffix = "" if country_source == HIRING_OFFICE else f" _({t(country_source)})_"
        lines.append(f"  - 🌍 {t('hiring country')}: {country}{suffix}")
    else:
        # Отсутствие страны бывает двух разных видов, и путать их не стоит:
        # либо вакансия сознательно без географии, либо площадка не сказала.
        verdict = (bd.get("remote_location_fit", {})
                   .get("structured_location", {}).get("verdict"))
        location = (v.get("location_raw") or "").strip()
        if verdict in ("worldwide", "worldwide_by_continents", "remote_without_country"):
            lines.append(f"  - 🌍 {t('hiring country')}: {t('without a country')}")
        else:
            lines.append(f"  - 🌍 {t('hiring country')}: {t('not determined')}"
                         + (f" _({t('the board said')}: «{location}»)_" if location else ""))
    age_bd = bd.get("company_age_signal", {})
    if age_bd.get("has_data"):
        emp = f", ~{age_bd['employees']} {t('employees')}" if age_bd.get("employees") else ""
        lines.append(
            f"  - 🏛 {t('company')}: {t('founded')} {age_bd['founded_year']} "
            f"({age_bd['age_years']} {t('years old')}{emp}) _(Wikidata)_"
        )
    if manual.get("notes"):
        lines.append(f"  - {t('note')}: {manual['notes']}")
    return "\n".join(lines)


# Сколько вакансий национальных рынков показывать. Их сотни; смысл раздела —
# дать человеку увидеть, что рынок есть, а не пролистать его целиком.
NATIONAL_MARKET_LIMIT = 25


def _section(title: str, items: list) -> str:
    if not items:
        return f"### {title}\n\n_{t('Empty for now.')}_\n"
    body = "\n".join(_fmt_vacancy_line(v) for v in items[:TOP_N_PER_SECTION])
    extra = len(items) - TOP_N_PER_SECTION
    footer = (f"\n\n_({t('and one more')} {extra} — `python tools/kb.py list`)_"
              if extra > 0 else "")
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
    "The higher the score (0-100), the closer the vacancy is to this "
    "identity's profile."
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
        return common.ACTIVE_IDENTITY or t("not determined")


def _ambiguous_places_hint(criteria: Optional[dict]) -> str:
    """Подсказка про неоднозначные топонимы — из настроек активной идентичности,
    а не захардкоженная. У каждого человека своя ловушка: для одного это
    Georgia (страна vs штат), для другого Cambridge (UK vs Массачусетс)."""
    rules = ((criteria or {}).get("remote_location_fit") or {}).get("ambiguous_place_names") or []
    names = [r.get("name") for r in rules if r.get("name")]
    if not names:
        return t("an ambiguous place name")
    quoted = ", ".join(f'"{n}"' for n in names[:3])
    return f"{t('an ambiguous place name')} ({t('for example')} {quoted})"


def _format_link_check_stats(stats: Optional[dict]) -> str:
    if not stats:
        return f"_{t('no data')} ({t('first run after link checking was added')})_"
    return (
        f"{t('checked on this run')}: {stats.get('checked', 0)} "
        f"({t('skipped — recently checked or duplicates')}: "
        f"{stats.get('skipped_recent_or_duplicate', 0)}). "
        f"{t('alive')}: {stats.get('ok', 0)}, "
        f"{t('removed as dead (404/410)')}: {stats.get('dead', 0)}, "
        f"{t('could not be verified conclusively (kept visible)')}: "
        f"{stats.get('unknown', 0)}."
    )


def _source_usefulness(vacancies: dict) -> str:
    """Сколько вакансий источник принёс и сколько из них дошло до выдачи.

    ЗАЧЕМ. Реестр источников хранит ОБЪЁМ, и по нему источники выглядят
    совершенно иначе, чем они есть. Замер 2026-08-05: devitjobs дал 4033
    записи и НОЛЬ в выдаче, а weworkremotely с его 251 записью дал больше
    половины всех кандидатов. Объём без пользы — это только время прогона и
    раздутая база.

    Поэтому считаем «выход на 100 записей». Источник с нулём в выдаче не
    отключается автоматически: у редких источников выдача появляется рывками,
    и одно решение по одному прогону было бы поспешным. Но цифра должна быть
    перед глазами.
    """
    stats = {}
    for v in vacancies.values():
        if v.get("duplicate_of"):
            continue
        src = v.get("source") or "?"
        entry = stats.setdefault(src, {"total": 0, "shortlist": 0})
        entry["total"] += 1
        if (v.get("computed") or {}).get("classification") in (
                "hot_lead", "worth_a_look", "long_shot"):
            entry["shortlist"] += 1

    if not stats:
        return f"_{t('no data')}_"

    rows = sorted(stats.items(), key=lambda kv: -kv[1]["shortlist"])
    lines = [f"| {t('Source')} | {t('Records')} | {t('In shortlist')} | "
             f"{t('Per 100 records')} |", "|---|---:|---:|---:|"]
    for name, s in rows:
        rate = (100.0 * s["shortlist"] / s["total"]) if s["total"] else 0.0
        lines.append(f"| {name} | {s['total']} | {s['shortlist']} | {rate:.1f} |")
    return chr(10).join(lines)


def _reputation_coverage_block(vacancies: dict, companies: dict) -> str:
    """Сколько компаний головы выдачи проверено — и кто остался.

    Раздел существует потому, что невыполненная работа обязана быть видна.
    Замер 2026-08-06: в hot_lead и worth_a_look было 55 компаний, репутация
    была известна у нуля, и отчёт про это молчал — писал у каждой «не
    проверялась», что читается как свойство компании, а не как пробел.
    """
    import reputation

    stats = reputation.coverage(vacancies, companies)
    if not stats["companies"]:
        return f'_{t("The shortlist has no hot_lead / worth_a_look companies yet.")}_'

    lines = [
        f"{t('Companies at the head of the shortlist (hot_lead + worth_a_look)')}: "
        f"**{stats['companies']}**",
        "",
        f"- {t('reputation found')}: **{stats['found']}**",
        f"- {t('checked, no credible reviews exist')}: **{stats['insufficient']}** "
        f"_({t('usually the case for small, little-known companies')})_",
        f"- **{t('not checked')}: {stats['unchecked']}**",
    ]
    if stats["unchecked"]:
        todo = reputation.worklist(vacancies, companies, limit=12)
        lines += [
            "",
            "> ⚠ " + t("Unchecked companies are a gap in the process, not a property "
            "of the companies. Until the check is done the report cannot tell "
            "'no reviews exist' from 'we did not look', and for a decision "
                       "those are different things."),
            "",
            t('Still to check') + ':',
            "",
        ] + [f"- {item['classification']}: {item['company']}" for item in todo]
        if stats["unchecked"] > len(todo):
            lines.append(f"- _…{t('and one more')} {stats['unchecked'] - len(todo)}_")
        lines += [
            "",
            "```bash",
            "python tools/reputation.py worklist          # полный список",
            "python tools/kb.py set-company-reputation \\",
            "    --company \"<имя>\" --rating 4.2 --wlb 4.4 --source Glassdoor",
            "python tools/reputation.py mark-insufficient --company \"<имя>\"",
            "```",
        ]
    else:
        lines += ['', t('No gaps: every company at the head of the shortlist has a result.')]
    return "\n".join(lines)


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
    # Вакансии, у которых единственное возражение — страна в поле локации.
    # Не в основной выдаче (их сотни, они утопят десяток живых кандидатов),
    # но и не выброшены: догадка "вакансия в стране N значит для резидентов
    # N" верна не всегда, а решение писать или не писать — человека, не
    # системы. Показываем верхушку по score, сгруппированную по стране.
    national = by_class("national_market")[:NATIONAL_MARKET_LIMIT]
    # Ручной проверки требуют только те вакансии, судьба которых ещё не решена.
    #
    # Реальная жалоба человека 2026-08-05: в этой секции лежали Sales Manager,
    # Business Partner Analyst, Patient Outreach Specialist и Data Entry — все
    # ОТКЛОНЁННЫЕ. Флаг «нужна проверка» ставится независимо от классификации,
    # и секция собирала отсеянное вместе с сомнительным. Проверять в
    # отклонённой вакансии нечего: гейт уже принял решение, а человек тратит
    # внимание на мусор в единственном месте, куда смотрит.
    visible = {"hot_lead", "worth_a_look", "long_shot"}
    review_items = [v for v in items
                    if v.get("computed", {}).get("needs_manual_review")
                    and v.get("computed", {}).get("classification") in visible]
    review_items.sort(key=lambda v: -v.get("computed", {}).get("score", 0))

    class_counts = {}
    for v in items:
        cls = v.get("computed", {}).get("classification", "unknown")
        class_counts[cls] = class_counts.get(cls, 0) + 1

    source_lines = []
    for name, info in sorted((state.get("sources") or {}).items()):
        status = "OK" if not info.get("last_error") else f"ERROR: {info['last_error']}"
        source_lines.append(
            f"- **{name}**: {info.get('fetched_count', 0)} "
            f"{t('records on the last run')}, "
            f"{status}, {t('consecutive failures')}: "
            f"{info.get('consecutive_failures', 0)}"
        )

    run_stats = state.get("last_run_stats", {})

    parts = [
        # Идентичность в заголовке: отчёт часто открывают отдельной вкладкой или
        # пересылают, и он обязан себя опознавать без контекста.
        f"# Work IDE [{common.ACTIVE_IDENTITY or '?'}] — {t('report of')} "
        f"{now.strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"_{t('Search identity')}: {_identity_display_name()}_",
        "",
        f"{t('Run')} #{state.get('run_count', '?')}. "
        f"{t('Vacancies shown')}: {len(items)} "
        f"({t('collapsed')} {duplicate_count} {t('near-duplicates')}, "
        f"{t('removed')} {dead_link_count} "
        f"{t('with a confirmed dead link')} — `python tools/kb.py stats`). "
        f"{t('New on this run')}: {run_stats.get('new_vacancies', '?')}. "
        f"{t('Companies in the database')}: {len(companies)}.",
        "",
        f"## {t('How to read this report')}",
        "",
        f"{_scoring_philosophy()} "
        f"`hot_lead` — {t('look at these first')}. "
        f"{t('Full score breakdown for any vacancy')}: "
        "`python tools/kb.py show --id <id>`.",
        "",
        f"## 🔥 {t('Hot leads — look at these first')}",
        "",
        _section("hot_lead", hot),
        f"## 👀 {t('Worth a look')}",
        "",
        _section("worth_a_look", worth),
        f"## 🕰️ {t('Long shot (low priority, but not impossible)')}",
        "",
        _section("long_shot", long_shot),
        f"## 🌍 {t('National markets — strong vacancies tied to a country')}",
        "",
        t("These vacancies have no objection against them except one: the "
        "board named a country. Almost always that means remote within that "
        "country, and then it is a miss. But not always: some employers "
        "happily sign a B2B contract with a contractor abroad, and the text "
        "of the vacancy does not show it.") + " " +
        f"{t('Showing')} {len(national)} {t('best of')} "
        f"{class_counts.get('national_market', 0)}.",
        "",
        _section("national_market", national),
        f"## 🔎 {t('Needs a manual check by the agent or the owner')}",
        "",
        t("These are vacancies the automation is unsure about — most often ") +
        f"{_ambiguous_places_hint(criteria)}, " +
        t("or it is unclear whether the company will hire someone from your "
        "country. Worth re-checking with a web search and, if needed, "
        "updating the record through `tools/kb.py`."),
        "",
        _section("needs_manual_review", review_items),
        f"## ⭐ {t('Company reputation checks')}",
        "",
        _reputation_coverage_block(vacancies, companies),
        "",
        f"## 📊 {t('Class statistics')}",
        "",
        "\n".join(f"- {cls}: {n}" for cls, n in sorted(class_counts.items(), key=lambda kv: -kv[1])) or f"_{t('no data')}_",
        "",
        f"## 📡 {t('Source health')}",
        "",
        "\n".join(source_lines) or "_нет данных_",
        "",
        f"## 📈 {t('Source usefulness')}",
        "",
        t("Volume and usefulness are different things. A source bringing "
        "thousands of records and zero candidates costs only run time."),
        "",
        _source_usefulness(vacancies),
        "",
        f"## 🔗 {t('Link check')}",
        "",
        _format_link_check_stats(state.get("last_link_check")),
        "",
        f"## {t('What next')}",
        "",
        f"- {t('Accumulated market findings')}: `{_rel(common.INSIGHTS_PATH)}`",
        f"- {t('Full vacancy database')}: `{_rel(common.VACANCIES_PATH)}` "
        f"(или `python tools/kb.py list --identity {common.ACTIVE_IDENTITY}`)",
        f"- {t('Archive of past reports')}: `{_rel(common.REPORTS_ARCHIVE_DIR)}`",
        f"- {t('Mark status after applying')}: `python tools/kb.py set-status "
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

    parser = argparse.ArgumentParser(
        description="Rebuild the report from the current knowledge base")
    identity_mod.add_identity_arg(parser)
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)

    vacancies = kb.load_vacancies()
    companies = kb.load_companies()
    state = common.load_json(common.STATE_PATH, default={})
    md = build_report_markdown(vacancies, companies, state)
    path = write_report(md)
    print(f"Report saved: {path}")


if __name__ == "__main__":
    main()
