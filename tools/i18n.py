"""
Report language.

WHY THIS EXISTS
---------------
The repository is written in English so that anyone can read it. The report is
different: it is the one file the owner opens by hand every morning, and it
should speak the language they speak to the agent in.

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


# Languages the report can be rendered in. A language absent here is not an
# error: the report falls back to English and says so nowhere, because English
# is the source text rather than a fallback locale.
CATALOGUES = {
    "ru": {
        # --- report skeleton ---------------------------------------------
        "Hot leads — look at these first": "Hot leads — смотреть в первую очередь",
        "Worth a look": "Worth a look",
        "Long shot (low priority, but not impossible)":
            "Long shot (низкий приоритет, но не исключено)",
        "National markets — strong vacancies tied to a country":
            "Национальные рынки — сильные вакансии, привязанные к стране",
        "eligibility: confirmed": "допуск подтверждён работодателем",
        "eligibility: likely": "допуск вероятен",
        "eligibility: not stated": "про допуск ничего не сказано",
        "eligibility: no": "допуск исключён",
        "Markets inside": "Рынки внутри",
        "This shortlist": "Эта выборка",
        "vacancies": "вакансий",
        "Other shortlists from this search":
            "Другие выборки этого поиска",
        "apply directly": "подать напрямую",
        "the company hires through": "компания нанимает через",
        "this vacancy is not on the board — possibly placed through an agency":
            "этой вакансии на доске нет — возможно, размещена через агентство",
        "address given in the vacancy": "адрес, указанный в вакансии",
        "no direct way to apply found — only through the board":
            "прямого способа подать заявку не нашлось — только через площадку",
        "Work arrangement not confirmed — check by hand":
            "Формат работы не подтверждён — проверить руками",
        "Nobody ever called these remote — neither the employer nor the "
        "board. That is not the same as knowing they are onsite, so they are "
        "not thrown away, and their score is NOT reduced: a 70 here is the "
        "same 70 it would have been above. What is missing is the "
        "confirmation, not the quality.":
            "Удалёнными их не назвал никто — ни работодатель, ни площадка. "
            "Это не то же самое, что знать, что они в офисе, поэтому они не "
            "выброшены, и оценка им НЕ снижена: 70 здесь — те же самые 70, "
            "что были бы выше. Не хватает подтверждения, а не качества.",
        "The reason this class exists: LinkedIn's guest search ignores its "
        "own remote filter, measured 2026-08-11 — the same vacancy comes back "
        "under 'on-site', 'remote' and 'hybrid' alike. Where an employer does "
        "say 'hybrid' or 'on-site', the vacancy is rejected outright and is "
        "not here.":
            "Откуда взялся этот класс: гостевой поиск LinkedIn игнорирует "
            "собственный фильтр удалёнки — замерено 11.08.2026, одна и та же "
            "вакансия возвращается и под «on-site», и под «remote», и под "
            "«hybrid». Там, где работодатель сам пишет «гибрид» или «в "
            "офисе», вакансия отклоняется совсем и сюда не попадает.",
        "Needs a manual check by the agent or the owner":
            "Требуют ручной проверки агентом/владельцем",
        "Company reputation checks": "Проверка репутации компаний",
        "Class statistics": "Статистика по классам",
        "Source health": "Здоровье источников",
        "Source usefulness": "Польза источников",
        "Link check": "Проверка ссылок",
        "How to read this report": "Как читать этот отчёт",
        "What next": "Дальше",
        "Empty for now.": "_Пока пусто._",
        "no data": "нет данных",

        # --- vacancy line ------------------------------------------------
        "status": "статус",
        "link": "ссылка",
        "salary": "ЗП",
        "technologies": "технологии",
        "reputation": "репутация",
        "hiring country": "страна найма",
        "company": "компания",
        "company site (apply directly)": "сайт компании (отклик напрямую)",
        "note": "заметка",
        "low intensity": "низкая нагрузка",
        "looks like a complex/R&D role, not a simple one":
            "похоже на сложную/R&D роль, не «простую»",
        "needs a manual check (see below)": "требует ручной проверки (см. ниже)",
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
        "not checked yet": "ещё не проверялась",
        "this is a gap in the process, not a property of the company":
            "это пробел в процессе, а не свойство компании",
        "not checked": "не проверялась",
        "tail of the shortlist: companies at worth_a_look and above are checked":
            "хвост выдачи: проверяются компании уровня worth_a_look и выше",
        "not determined": "не определена",
        "without a country": "без привязки к стране",
        "the board said": "площадка указала",
        "company home country": "штаб-квартира компании",

        # --- reputation coverage block -----------------------------------
        "Companies at the head of the shortlist (hot_lead + worth_a_look)":
            "Компаний в голове выдачи (hot_lead + worth_a_look)",
        "reputation found": "репутация найдена",
        "checked, no credible reviews exist": "проверено, достоверных отзывов нет",
        "not checked": "не проверено",
        "No gaps: every company at the head of the shortlist has a result.":
            "Пробелов нет: у каждой компании головы выдачи есть результат проверки.",
        "Still to check": "Осталось проверить",
        "and one more": "и ещё",
        "The shortlist has no hot_lead / worth_a_look companies yet.":
            "В выдаче пока нет компаний уровня hot_lead / worth_a_look.",
        'report of': 'отчёт от',
        'Search identity': 'Идентичность поиска',
        'Run': 'Запуск',
        'Vacancies shown': 'Показано вакансий',
        'collapsed': 'схлопнуто',
        'near-duplicates': 'почти-дублей',
        'removed': 'убрано',
        'with a confirmed dead link': 'с подтверждённо нерабочей ссылкой',
        'New on this run': 'Новых на этом запуске',
        'Companies in the database': 'Компаний в базе',
        'look at these first': 'смотреть в первую очередь',
        'Full score breakdown for any vacancy': 'Полная разбивка score по вакансии',
        'Showing': 'Показано',
        'best of': 'лучших из',
        'These vacancies have no objection against them except one: the board named a country. Almost always that means remote within that country, and then it is a miss. But not always: some employers happily sign a B2B contract with a contractor abroad, and the text of the vacancy does not show it.':
            'Здесь вакансии, к которым нет НИКАКИХ претензий, кроме одной: площадка указала страну. Почти всегда это значит «удалённо, но в пределах этой страны» — и тогда мимо. Но не всегда: часть работодателей спокойно оформляет контракт B2B с подрядчиком снаружи, и по тексту вакансии этого не видно.',
        'These are vacancies the automation is unsure about — most often ':
            'Это вакансии, где автоматика не уверена в оценке — чаще всего ',
        'or it is unclear whether the company will hire someone from your country. Worth re-checking with a web search and, if needed, updating the record through `tools/kb.py`.':
            'либо непонятно, готова ли компания нанять человека из вашей страны. Стоит перепроверить веб-поиском и, если нужно, обновить запись через `tools/kb.py`.',
        "Unchecked companies are a gap in the process, not a property of the companies. Until the check is done the report cannot tell 'no reviews exist' from 'we did not look', and for a decision those are different things.":
            'Непроверенные компании — это пробел в процессе, а не свойство компаний. Пока проверка не сделана, отчёт не может отличить «отзывов нет» от «мы не смотрели», а для решения это разные вещи.',
        'Volume and usefulness are different things. A source bringing thousands of records and zero candidates costs only run time.':
            'Объём и польза — разные вещи. Источник, приносящий тысячи записей и ноль кандидатов, стоит только времени прогона.',
        'Source': 'Источник',
        'Records': 'Записей',
        'In shortlist': 'В выдаче',
        'Per 100 records': 'На 100 записей',
        'records on the last run': 'записей на последнем запуске',
        'consecutive failures': 'подряд неудач',
        'checked on this run': 'Проверено на этом запуске',
        'skipped — recently checked or duplicates':
            'пропущено — недавно проверенные или дубли',
        'alive': 'живые',
        'removed as dead (404/410)': 'убраны как мёртвые (404/410)',
        'could not be verified conclusively (kept visible)':
            'не удалось однозначно проверить (не скрыты)',
        'first run after link checking was added':
            'первый запуск после добавления проверки ссылок',
        'an ambiguous place name': 'неоднозначная гео-локация',
        'for example': 'например',
        'source': 'источник',
        'found manually on a third-party site': 'найдено вручную на стороннем сайте',
        'unknown third-party source': 'неизвестный сторонний источник',
        'Accumulated market findings': 'Накопленные закономерности о рынке',
        'Full vacancy database': 'Полная база вакансий',
        'Archive of past reports': 'Архив прошлых отчётов',
        'Mark status after applying': 'Отметить статус после отклика',
    },
}


def language(profile: Optional[dict] = None) -> str:
    """Report language for the active identity.

    Falls back to English rather than guessing: a wrong guess would produce a
    report the owner cannot skim, which is the one thing the report must do.
    """
    if profile is None:
        try:
            profile = common.load_profile()
        except Exception:  # noqa: BLE001 — язык не повод ронять отчёт
            return DEFAULT_LANGUAGE
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
