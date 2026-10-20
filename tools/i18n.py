"""
The language of a vacancy's lines (tools/report.vacancy_view).

WHY THIS EXISTS
---------------
The repository is written in English so that anyone can read it. The lines a
person reads on a vacancy are different: they should speak the language the
person picked (the app renders every language it offers, report.vacancy_views).

So the language is a property of the person, not of the project. It lives in
the local identity (`preferences.language`), outside git, and defaults to the
language the owner actually uses. Everything else — code, comments, docs — is
English regardless.

HOW IT WORKS
------------
Message keys ARE the English text. That choice is deliberate:

  * a missing translation degrades to readable English rather than to a bare
    key like `report.section.hot_leads`, which is what a human sees when a
    catalogue drifts out of sync with the code;
  * the code stays readable — `t("Hot leads")` says what it renders;
  * adding a language means adding a dictionary, touching nothing else.

The cost is that editing an English string silently drops its translation.
That is caught by a test which walks the catalogue and reports keys no longer
present in the sources, rather than by hoping someone remembers.
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

DEFAULT_LANGUAGE = "en"

# Ключи, которые передаются в translate() ПЕРЕМЕННОЙ, а не литералом.
#
# Их не находит статический разбор, поэтому проверка «нет мёртвых записей»
# считала бы их лишними и требовала удалить — а удаление сломало бы отчёт.
# Список короткий и должен таким остаться: динамический ключ всегда стоит
# лишней осторожности при чтении кода.
DYNAMIC_KEYS = {
    # report.HIRING_OFFICE / report.COMPANY_HOME — откуда узнали страну найма
    "hiring office",
    "company home country",
}


# Languages the vacancy lines can be rendered in. A language absent here is not
# an error: the lines fall back to English and say so nowhere, because English
# is the source text rather than a fallback locale.
CATALOGUES = {
    "ru": {
        # --- eligibility, application, confirmation ------------------------
        "eligibility: confirmed": "допуск подтверждён работодателем",
        "eligibility: likely": "допуск вероятен",
        "eligibility: not stated": "про допуск ничего не сказано",
        "eligibility: no": "допуск исключён",
        "apply directly": "подать напрямую",
        "the company hires through": "компания нанимает через",
        "this vacancy is not on the board — possibly placed through an agency":
            "этой вакансии на доске нет — возможно, размещена через агентство",
        "address given in the vacancy": "адрес, указанный в вакансии",
        "the board sends applications to": "площадка отправляет отклик на",
        "no direct way to apply found — only through the board":
            "прямого способа подать заявку не нашлось — только через площадку",
        "engagement confirmed": "занятость подтверждена",
        "the core stack is required": "основной стек обязателен",
        "that it is remote": "что это удалёнка",
        "the hours (part-time, freelance)": "занятость (part-time, фриланс)",

        # --- vacancy line ------------------------------------------------
        "note": "заметка",
        "low intensity": "низкая нагрузка",
        "looks like a complex/R&D role, not a simple one":
            "похоже на сложную/R&D роль, не «простую»",
        "needs a manual check": "требует ручной проверки",
        "the link could not be verified conclusively":
            "ссылку не удалось однозначно проверить",
        "employees": "сотрудников",
        "founded": "основана",
        "years old": "лет",
        "hiring office": "офис найма",

        # --- salary ------------------------------------------------------
        "not stated": "не указана",
        "source: stated in the vacancy": "источник: указано в вакансии",
        "source: no data — neither in the vacancy nor found manually":
            "источник: нет данных — ни в вакансии, ни найдено вручную",
        "amount mentioned in the description but not parsed reliably":
            "сумма упомянута в описании, но не распознана точно",
        "year": "год",
        "month": "мес",
        "hour": "час",

        # --- reputation --------------------------------------------------
        "overall": "общий",
        "work-life balance": "work-life balance",
        "rating without numbers": "оценка без цифр",
        "data from search results — the primary source was not opened":
            "данные из поисковой выдачи — первоисточник не открывался",
        "the primary source page was read": "страница первоисточника прочитана",
        "as told by the owner": "со слов владельца",
        "red flags": "красные флаги",
        "very low rating": "очень низкий рейтинг",
        "checked": "проверялась",
        "not determined — not enough sources":
            "не определена — недостаточно источников",
        "searched": "искали",
        "usually the case for small, little-known companies":
            "обычно так у небольших и малоизвестных компаний",
        "not collected": "не собрана",
        "the vacancy's “Collect reputation” button in the app":
            "кнопка «Собрать репутацию» на вакансии в приложении",
        "not determined": "не определена",
        "without a country": "без привязки к стране",
        "the board said": "площадка указала",
        "company home country": "штаб-квартира компании",

        'source': 'источник',
        'found manually on a third-party site': 'найдено вручную на стороннем сайте',
        'unknown third-party source': 'неизвестный сторонний источник',
    },
}


# Every language a text can be rendered in: English, the source, and each
# catalogue. The app offers the same ones in its interface and shows each
# vacancy's lines in whichever the person picked, so the pipeline renders them
# in all of these (report.vacancy_views).
LANGUAGES = (DEFAULT_LANGUAGE, *CATALOGUES)

# Set while rendering in a language other than the identity's (speaking()).
_SPOKEN = None


@contextmanager
def speaking(lang: str):
    """Within the block, translate() speaks `lang` instead of the identity's
    language. For rendering one text in several languages; the report itself
    keeps the identity's."""
    global _SPOKEN
    if lang not in LANGUAGES:
        raise ValueError(f"no such language: {lang!r} (known: {', '.join(LANGUAGES)})")
    previous, _SPOKEN = _SPOKEN, lang
    try:
        yield
    finally:
        _SPOKEN = previous


# The active identity's language, resolved once. Resolving the profile parses
# three YAML files, and translate() runs for every phrase of every vacancy:
# uncached, rendering one vacancy took half a second (measured 2026-09-29),
# and listing a whole shortlist took minutes. Keyed by the profile loader as
# well, so a test that swaps the loader is not served a stale answer.
_LANGUAGE_CACHE = {}


def _reset_language_cache() -> None:
    _LANGUAGE_CACHE.clear()


common.register_identity_hook(_reset_language_cache)


def language(profile: Optional[dict] = None) -> str:
    """Report language for the active identity.

    Falls back to English rather than guessing: a wrong guess would produce a
    report the owner cannot skim, which is the one thing the report must do.
    """
    if profile is None:
        if _SPOKEN is not None:
            return _SPOKEN
        key = (common.ACTIVE_IDENTITY, common.load_profile)
        if key not in _LANGUAGE_CACHE:
            try:
                _LANGUAGE_CACHE[key] = language(common.load_profile())
            except Exception:  # noqa: BLE001 — a language is no reason to fail a report
                return DEFAULT_LANGUAGE
        return _LANGUAGE_CACHE[key]
    value = ((profile or {}).get("preferences") or {}).get("language")
    if not value:
        return DEFAULT_LANGUAGE
    return str(value).strip().lower()[:2] or DEFAULT_LANGUAGE


def translate(text: str, lang: Optional[str] = None) -> str:
    """English source text -> the report language. Unknown text passes through."""
    if lang is None:
        lang = language()
    if lang == DEFAULT_LANGUAGE:
        return text
    return CATALOGUES.get(lang, {}).get(text, text)


def catalogue_keys(lang: str) -> set:
    return set(CATALOGUES.get(lang, {}))
