"""
Скоринг вакансий по рубрике config/criteria.yaml + config/profile.yaml.

Философия (см. CLAUDE.md): обычный джоб-серч штрафует "legacy"/"boring"/
"bureaucracy" — здесь наоборот, это плюс. Итоговый score — 0..100,
раскладывается на прозрачные компоненты в score_breakdown, плюс отдельно
список dealbreakers и флаг needs_manual_review.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import textclean  # noqa: E402

_AMOUNT_RE = re.compile(
    r"\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*"
    r"(k\b|m\b|mm\b|bn\b|million\b|billion\b"
    r"|/\s?(?:hour|hr)\b|per\s?hour|/\s?(?:month|mo)\b|per\s?month)?",
    re.IGNORECASE,
)

# Суффиксы порядка величины, после которых сумма заведомо НЕ является
# зарплатой: миллионы и миллиарды в тексте вакансии — это оборот компании,
# объём инвестиций или (реальный найденный случай) сумма выплат площадки
# фрилансерам. Реальный баг 2026-07-31, замеченный на ручном чек-листе:
# Lemon.io пишет "We've already paid out over $11M to our engineers", а
# отчёт показывал владельцу "ЗП: $11/час" — прямая дезинформация в самом
# важном для решения поле. Мы не просто игнорируем такую сумму: раньше
# число 11 попадало в ветку "меньше 500 — значит почасовая ставка".
_MAGNITUDE_SUFFIXES = {"m", "mm", "bn", "million", "billion"}

# Суммы в таком контексте — не ставка кандидата.
_NON_SALARY_CONTEXT_WORDS = (
    "bonus",
    "signing",
    "stipend",
    "budget",
    "allowance",
    "raised",
    "funding",
    "revenue",
    "arr ",
    "valuation",
    "paid out",
    "referral",
)


# Кэш ОБЯЗАН быть ключеван по идентичности. Раньше это был один глобальный
# набор, заполняемый при первом вызове: после перехода на мультиидентичность
# такой кэш стал бы межидентичностной утечкой — список remote-only источников
# идентичности A управлял бы remote-гейтом идентичности B, а этот гейт решает
# "дисквалифицировать вакансию или дать ей +4 балла". Отказ был бы тихим.
#
# Кэш нужен: функция вызывается на КАЖДУЮ вакансию внутри рескоринга, а база
# — тысячи записей; чтение YAML каждый раз превратило бы прогон в парсинг.
_REMOTE_ONLY_SOURCES_CACHE: dict = {}


def _reset_caches() -> None:
    """Вызывается при активации идентичности (см. common.register_identity_hook).
    Страховка на случай, если ключевание когда-нибудь сломают."""
    _REMOTE_ONLY_SOURCES_CACHE.clear()


common.register_identity_hook(_reset_caches)


def _remote_only_sources() -> set:
    """Имена источников, помеченных remote_only — площадки, публикующие
    исключительно удалённые вакансии (их флаг достаточен как подтверждение
    удалёнки, см. docs/SOURCES.md)."""
    common.require_identity()
    key = common.ACTIVE_IDENTITY
    if key not in _REMOTE_ONLY_SOURCES_CACHE:
        _REMOTE_ONLY_SOURCES_CACHE[key] = {
            s.get("name")
            for s in common.load_sources()
            if s.get("remote_only") and s.get("enabled", True) and s.get("name")
        }
    return _REMOTE_ONLY_SOURCES_CACHE[key]


def load_criteria() -> dict:
    """Критерии со всеми слоями, наложенными в фиксированном порядке.

    До 2026-08-05 читался ровно один файл — файл идентичности. Из-за этого
    Малая Конституция могла влиять только на профиль (через сентинел `local`)
    и не могла тронуть ни одного порога или списка в критериях, хотя ровно
    там живёт большая часть решений. Порядок и правила слияния — settings.py.
    """
    import settings

    merged, _ = settings.resolve("criteria", common.ACTIVE_IDENTITY)
    return merged


def load_profile() -> dict:
    # Через common.load_profile, а не напрямую: личные поля профиля помечены
    # сентинелом `local` и живут в Малой Конституции. Прямое чтение файла
    # вернуло бы скорингу строку "local" вместо, например, списка языков.
    return common.load_profile()


def _vacancy_text(vacancy: dict) -> str:
    # Почта и ссылки вырезаются ДО поиска ключевых слов: домен внутри адреса
    # неотличим от названия технологии (".net" в "harnly.net"), а внутри
    # ссылки — от чего угодно ("react-native" в пути к вакансии).
    # См. tools/textclean.py: там же объяснено, почему это не валидация
    # адреса и почему библиотека-валидатор здесь не подходит.
    parts = [
        vacancy.get("title") or "",
        vacancy.get("company") or "",
        vacancy.get("location_raw") or "",
        " ".join(vacancy.get("tags") or []),
        vacancy.get("description_text") or "",
        vacancy.get("salary_raw") or "",
    ]
    return common.normalize_for_matching(
        textclean.strip_contact_noise(" \n ".join(parts))
    )


_TECH_PATTERNS_CACHE = {}


def tech_matching_patterns() -> dict:
    """Общий словарь "как найти технологию в тексте" (config/tech_vocabulary.yaml).

    Знание ГЛОБАЛЬНОЕ: как пишется ".NET", одинаково для всех пользователей
    проекта, поэтому живёт в config/, а не в идентичности (CLAUDE.md §13).
    Идентичность называет технологию каноническим именем в своём tech_stack —
    и получает правильный поиск бесплатно.
    """
    if "data" not in _TECH_PATTERNS_CACHE:
        path = common.ROOT / "config" / "tech_vocabulary.yaml"
        data = common.load_yaml(path) if path.exists() else {}
        _TECH_PATTERNS_CACHE["data"] = (data or {}).get("matching_patterns") or {}
    return _TECH_PATTERNS_CACHE["data"]


def _substring_unsafe_names() -> set:
    """Технологии, которые НЕЛЬЗЯ искать подстрокой ни в каком списке."""
    return {name for name, spec in tech_matching_patterns().items()
            if spec.get("substring_unsafe")}


def _pattern_specs_for(names: list) -> list:
    """Записи глобального словаря для технологий, названных идентичностью."""
    vocabulary = tech_matching_patterns()
    specs = []
    for name in names or []:
        spec = vocabulary.get(name)
        if not spec:
            continue
        for pattern in spec.get("patterns") or []:
            specs.append({"name": name, "pattern": pattern,
                          "redundant_if": spec.get("redundant_if")})
    return specs


def _matches_patterns(text: str, patterns: list, already_found: list = ()) -> list:
    """Совпадение по регулярному выражению, а не по подстроке.

    Нужно там, где название технологии невозможно записать безопасной
    подстрокой. Канонический случай — ".NET": подстрока ".net" есть в любом
    почтовом домене ("(firstname)@harnly.net" — реальная запись с Hacker
    News), поэтому её нельзя просто добавить в список ключей. А без неё
    заголовок "Senior .NET Backend Developer" не совпадает НИ С ОДНИМ ключом
    ядра, потому что все они длиннее (".NET Core", "ASP.NET", "C#").

    Цена ошибки измерена 2026-08-05: 754 вакансии с .NET в заголовке,
    отклонены все до единой, 325 из них — с формулировкой "не .NET/JS роль".

    Формат записи — {name, pattern, redundant_if}: в отчёт попадает `name`
    (человекочитаемое ".NET", а не сырая регулярка), а `redundant_if`
    перечисляет ключи, при наличии которых совпадение не засчитывается.
    Последнее обязательно: ".NET" совпадает и внутри "ASP.NET", и без этой
    оговорки одна и та же технология считалась бы дважды.
    """
    found = []
    for spec in patterns or []:
        if isinstance(spec, str):  # краткая форма: сама регулярка и есть имя
            spec = {"name": spec, "pattern": spec}
        name, pattern = spec.get("name"), spec.get("pattern")
        if not pattern or name in found or name in already_found:
            continue
        if any(key in already_found for key in spec.get("redundant_if") or []):
            continue
        if re.search(pattern, text, re.IGNORECASE):
            found.append(name)
    return found


def _matches(text: str, keywords: list) -> list:
    """Поиск подстрокой. Технологии, помеченные в общем словаре как
    `substring_unsafe`, пропускаются: их ищет только _matches_patterns.

    Без этой оговорки ".NET" в списке ключей снова начинает ловиться внутри
    "asp.net" — то есть ровно та ошибка, ради которой словарь и заведён.
    """
    unsafe = _substring_unsafe_names()
    found = []
    for kw in keywords or []:
        if kw in unsafe:
            continue
        needle = common.normalize_for_matching(kw)
        if needle and needle in text and kw not in found:
            found.append(kw)
    return found


def _check_structured_location(vacancy: dict, criteria: dict, profile: dict = None):
    """Проверяет СТРУКТУРНОЕ поле локации (location_raw), которое источники
    отдают отдельно от текста описания. Возвращает (is_restricted, detail).

    Правило: непустое поле локации без явного маркера "весь мир" — это
    гео-ограничение. Владелец в Грузии, поэтому "USA"/"Canada only"/
    "Brazil"/"Europe" одинаково недоступны (реальный найденный баг
    2026-07-30: ~20 из 32 кандидатов имели именно такое ограничение и
    проходили фильтр, потому что проверялся только текст описания)."""
    cfg = criteria["remote_location_fit"].get("structured_location_gate")
    if not cfg:
        return False, None

    loc_raw = (vacancy.get("location_raw") or "").strip()
    if not loc_raw:
        return False, None  # поле не заполнено — судить не по чему, решает текстовая логика

    loc = common.normalize_for_matching(loc_raw)

    worldwide_marker_hits = [m for m in cfg["worldwide_markers"] if m in loc]
    # "USA Only" содержит "only", но это НЕ маркер свободы; сначала явные маркеры.
    if worldwide_marker_hits:
        # Оговорка: "Europe only"/"US only" тоже могут содержать слово из
        # списка континентов, но не маркер "весь мир" — сюда попадают только
        # действительно свободные формулировки ("Anywhere in the World",
        # "100% Remote (Global)").
        return False, {"verdict": "worldwide", "matched_markers": worldwide_marker_hits, "value": loc_raw}

    # "Remote job" / "Distributed" / "Remote" — это указание формата работы,
    # а не страны. Если после вычёркивания таких слов ничего не остаётся,
    # значит источник просто не назвал страну — это не ограничение.
    residual = loc
    for token in cfg.get("remote_without_country_tokens", []):
        residual = residual.replace(token, " ")
    residual = re.sub(r"[^a-z]+", "", residual)
    if not residual:
        return False, {"verdict": "remote_without_country", "value": loc_raw}

    # Регион, который идентичность САМА назвала приемлемым, не является
    # ограничением. Реальная находка 2026-08-05: профиль kisel перечисляет
    # Израиль и ОАЭ целевыми рынками, а структурный гейт отбрасывал ".NET
    # Back End Developer @ Abu Dhabi" и "Backend Developer @ Israel" как
    # "вакансия привязана к стране". Одна часть настроек противоречила
    # другой, и побеждала та, что срабатывает раньше.
    # Явная исключительность перебивает всё, что ниже. Реальная находка
    # 2026-08-05: поле локации "United States only" содержит "United States",
    # то есть целевой рынок, и вакансия проходила по правилу целевого рынка.
    # Слово работодателя сильнее совпадения по названию страны.
    exclusivity_hits = [m for m in cfg.get("exclusivity_markers", []) if m in loc]
    if exclusivity_hits:
        return True, {"verdict": "restricted_explicitly", "matched": exclusivity_hits,
                      "value": loc_raw}

    continent_hits = [c for c in cfg["continent_names"] if c in loc]
    if len(continent_hits) >= cfg["continent_threshold"]:
        # Перечислены почти все континенты — фактически "весь мир"
        # (Remotive: "Americas, Europe, Asia, Africa, Oceania").
        return False, {"verdict": "worldwide_by_continents", "continents": continent_hits, "value": loc_raw}

    # СТРАНА САМА ПО СЕБЕ БОЛЬШЕ НЕ ЯВЛЯЕТСЯ ОГРАНИЧЕНИЕМ.
    #
    # Пересмотрено 2026-08-05 по прямому указанию владельца: «целевой регион —
    # да пофиг, что мне даст регион? важна не география, а сама работа».
    #
    # История вопроса стоит того, чтобы её тут держать. Сначала любая страна в
    # поле локации была полным отсевом — из 3281 европейской вакансии в выдачу
    # попадала одна. Потом появилось исключение для «целевых рынков», и мир
    # разделился на страны, дающие плюс, и страны, дающие отказ. Обе редакции
    # решали за человека одно и то же: куда ему можно, а куда нельзя.
    #
    # Теперь география не даёт НИЧЕГО. Ранжируют признаки самой работы: стек,
    # деньги, устаревшие технологии, отзывы про work-life balance. Страна
    # влияет ровно в одном месте — нетто-экспортёры разработки получают штраф
    # (_score_market_penalty), потому что там ставки конкурируют вниз. Это не
    # запрет: вакансия из такой страны просто должна быть лучше по существу.
    #
    # Отказ остаётся только там, где работодатель САМ говорит «нельзя»:
    # exclusivity_markers выше, absolute_residency_phrases и hard_dealbreakers.
    return False, {"verdict": "country_named", "value": loc_raw}


_AVOIDED_MARKETS_CACHE = {}


def _score_market_penalty(vacancy: dict, criteria: dict, profile: dict):
    """Штраф за нетто-экспортёров разработки — единственное место, где
    география вообще влияет на балл.

    Владелец 2026-08-05: «есть понятие НЕцелевого региона — Индия, Пакистан,
    Филиппины, им минус. Целевой регион — да пофиг».

    Почему штраф, а не отсев: в такой стране тоже бывает подходящая вакансия,
    просто большинство будет не в том стиле. Штраф ровно это и выражает —
    вакансия оттуда должна быть лучше по существу, чтобы попасть наверх.

    Список стран — общий (config/derivation/market_tiers.yaml, ярусы
    exporter_avoid и excluded_practical): направление потока работы описывает
    рынок, а не человека.
    """
    cfg = (criteria.get("remote_location_fit") or {}).get("net_exporter_penalty")
    if not cfg:
        return 0, {}

    key = id(profile)
    if key not in _AVOIDED_MARKETS_CACHE:
        import markets as markets_mod

        names = markets_mod.avoided_countries(profile)
        _AVOIDED_MARKETS_CACHE[key] = {
            common.normalize_for_matching(n): n for n in names
        }
    avoided = _AVOIDED_MARKETS_CACHE[key]
    if not avoided:
        return 0, {}

    for tag in vacancy.get("tags") or []:
        tag = str(tag)
        if tag.startswith("market:"):
            name = tag[7:]
            if common.normalize_for_matching(name) in avoided:
                return cfg.get("points", -10), {"country": name, "source": "тег площадки",
                                                "points": cfg.get("points", -10)}

    loc = common.normalize_for_matching(vacancy.get("location_raw") or "")
    for needle, name in avoided.items():
        if needle and needle in loc:
            return cfg.get("points", -10), {"country": name, "source": "поле локации",
                                            "points": cfg.get("points", -10)}
    return 0, {}


_TARGET_MARKETS_CACHE = {}


def _target_market_of(vacancy: dict, profile: dict):
    """Целевой рынок вакансии, если он есть, иначе None.

    Сначала по тегу площадки (`market:United Kingdom` — фетчер LinkedIn
    записывает страну, по которой делался запрос: это факт, а не догадка),
    затем по названию страны в поле локации.
    """
    if not profile:
        return None
    key = id(profile)
    if key not in _TARGET_MARKETS_CACHE:
        import markets as markets_mod

        names = markets_mod.target_locations(profile)
        _TARGET_MARKETS_CACHE[key] = (
            set(names),
            {common.normalize_for_matching(n): n for n in names},
        )
    names, normalized = _TARGET_MARKETS_CACHE[key]
    if not names:
        return None

    for tag in vacancy.get("tags") or []:
        tag = str(tag)
        if tag.startswith("market:") and tag[7:] in names:
            return tag[7:]

    loc = common.normalize_for_matching(vacancy.get("location_raw") or "")
    for needle, name in normalized.items():
        if needle and needle in loc:
            return name
    return None


def _check_header_hiring_scope(vacancy: dict, criteria: dict):
    """Структурный заголовок ВНУТРИ описания (WWR добавляет в начало текста
    блок "Headquarters: … / URL: …"). Возвращает (is_restricted, detail).

    Зачем отдельная проверка. Реальный найденный баг 2026-07-31 (ручной
    чек-лист, два кандидата в топе выдачи):
      * Stripe — поле region от площадки: "Anywhere in the World",
        а первая строка описания: "Headquarters: US Remote";
      * Airtable — то же поле "Anywhere in the World", заголовок:
        "Headquarters: San Francisco, CA; New York, NY; Remote - US".
    Обе — вакансии только для резидентов США, обе стояли в hot_lead.

    Категорийный фид WWR ("Programming") не различает страну найма, поэтому
    его region-поле заполняется размашисто; строка Headquarters приходит от
    самого работодателя и потому точнее. Смотрим ТОЛЬКО заголовочные строки,
    а не весь текст: "our US remote team" в теле описания — рассказ о
    компании, а не требование к кандидату.

    Обычный "Headquarters: Saudi Arabia" ограничением НЕ считается: это
    адрес компании. Ограничение — только связка "remote + страна/регион",
    то есть явное заявление о том, ГДЕ компания нанимает удалённо.
    """
    cfg = (criteria.get("remote_location_fit") or {}).get("header_scope_gate")
    if not cfg:
        return False, None

    description = vacancy.get("description_text") or ""
    header_lines = []
    for line in description.splitlines()[: cfg.get("scan_first_lines", 6)]:
        line_norm = common.normalize_for_matching(line)
        if any(re.search(p, line_norm) for p in cfg.get("header_line_patterns", [])):
            header_lines.append(line_norm)
    if not header_lines:
        return False, None

    for line in header_lines:
        for pattern in cfg.get("restriction_patterns", []):
            m = re.search(pattern, line)
            if m:
                return True, {
                    "verdict": "restricted_by_header",
                    "header_line": line,
                    "matched": m.group(0),
                }
    return False, {"verdict": "header_without_restriction", "header_lines": header_lines}


def _check_infrastructure_role(text: str, title: str, criteria: dict):
    """DevOps/платформенная роль, замаскированная нейтральным заголовком.

    Владелец исключил DevOps явно ("выкинь девопсов, это не моя вакансия"),
    и в hard_wrong_profession_title_patterns есть devops/sre/platform
    engineer — но это проверка ЗАГОЛОВКА. Реальный найденный случай
    2026-07-31: "Software Engineer, Compute (8+ YOE)" @ Airtable — заголовок
    абсолютно нейтральный, а тело целиком про Kubernetes-платформу (~70
    кластеров, CNI-плагин, операторы, Terraform, ArgoCD, SLO). Score 45,
    второе место в выдаче.

    Порог обязателен. Одно-два упоминания Kubernetes/Docker/CI-CD есть
    почти в любой современной вакансии прикладного разработчика — по ним
    судить нельзя. Отсекаем только плотную концентрацию инфраструктурных
    признаков, которая означает, что роль ИМЕННО про эксплуатацию.
    """
    cfg = (criteria.get("role_relevance_signal") or {}).get("infrastructure_role_gate")
    if not cfg:
        return False, {}

    hits = _matches(text, cfg.get("description_keywords", []))
    title_norm = common.normalize_for_matching(title)
    exempt = [p for p in cfg.get("title_exemption_patterns", []) if re.search(p, title_norm)]
    threshold = cfg.get("threshold_hits", 4)
    triggered = len(hits) >= threshold and not exempt
    return triggered, {
        "gate_triggered": triggered,
        "hits": hits,
        "threshold": threshold,
        "title_exemptions": exempt,
    }


_TZ_WINDOW_RE = re.compile(
    r"\b(?P<tz>[a-z]{2,9})\s*(?:time\s?zone|timezone|time)?\s*"
    r"\(?\s*(?:\+/-|±|\+\s?/\s?-)\s*(?P<hours>\d{1,2})\s*(?:hours?|hrs?)?\s*\)?"
)

# Вторая форма того же требования, словами. Реальная находка 2026-07-31:
# "We need a developer located within three hours of Pacific timezone"
# (RedLine Solutions, HN) — единственная C#/.NET вакансия в выдаче, и она
# для владельца (UTC+4) недостижима: Pacific ±3 = UTC-11..-5.
_TZ_WITHIN_RE = re.compile(
    r"within\s+(?P<hours>\d{1,2}|one|two|three|four|five|six)\s*(?:hours?|hrs?)"
    r"\s*(?:of|from)\s*(?:the\s+)?(?P<tz>[a-z]{2,9})"
)

_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}

# Третья форма требования к поясу: явный ДИАПАЗОН смещений.
# Реальная находка 2026-08-04: SuperPlane пишет "We currently work across
# GMT+2 to GMT-3 and welcome candidates in that range". Ни "±N часов", ни
# "within N hours of X" — а кандидат в UTC+4 в этот диапазон не попадает.
_TZ_RANGE_RE = re.compile(
    r"(?:gmt|utc)\s*(?P<a>[+-]\s*\d{1,2})\s*(?:to|through|\.\.|-)\s*"
    r"(?:gmt|utc)?\s*(?P<b>[+-]\s*\d{1,2})"
)



def _check_timezone_requirement(text: str, criteria: dict, profile: dict):
    """Требование к часовому поясу кандидата.

    Не покрывалось ничем: гео-гейты смотрят страну, а формулировка
    "Located in CET timezone (+/- 3 hours), we are unable to consider
    applications from candidates in other time zones" (Proxify, 5 вакансий
    в выдаче 2026-07-31) — это отдельная ось. Для владельца в UTC+4 такое
    окно как раз проходит, но узнали мы это чтением глазами, а не проверкой.

    Возвращает (is_dealbreaker, needs_review, detail).
    Осознанное ограничение: разбираем только явную форму "<TZ> +/- N часов".
    Более вольные формулировки ("significant overlap with PST") дают
    needs_review, а не отказ — скрыть настоящую вакансию хуже, чем показать
    сомнительную (принцип из Большой Конституции).
    """
    cfg = (criteria.get("remote_location_fit") or {}).get("timezone_gate")
    if not cfg:
        return False, False, None

    # Профиль хранит локацию внутри owner; верхний уровень поддержан на
    # случай другой раскладки у чужой идентичности.
    my_offset = ((profile.get("owner") or {}).get("location") or {}).get("utc_offset")
    if my_offset is None:
        my_offset = (profile.get("location") or {}).get("utc_offset")
    exclusive_hits = _matches(text, cfg.get("exclusive_phrases", []))
    # Форма "within N hours of <TZ>" сама по себе является требованием —
    # отдельной запретительной фразы рядом с ней не бывает.
    within_matches = list(_TZ_WITHIN_RE.finditer(text))
    range_matches = list(_TZ_RANGE_RE.finditer(text))
    if not exclusive_hits and not within_matches and not range_matches:
        return False, False, None
    if my_offset is None:
        return False, True, {"verdict": "no_utc_offset_in_profile", "phrases": exclusive_hits}

    # Диапазон разбираем первым: он однозначнее любых окон вокруг названия.
    for m in range_matches:
        lo, hi = sorted(int(m.group(g).replace(" ", "")) for g in ("a", "b"))
        detail = {
            "verdict": "fits" if lo <= my_offset <= hi else "outside",
            "range_utc": [lo, hi],
            "my_utc_offset": my_offset,
            "phrases": exclusive_hits,
        }
        return (detail["verdict"] == "outside"), False, detail

    zones = {common.normalize_for_matching(k): v for k, v in (cfg.get("zone_offsets") or {}).items()}
    matches = list(_TZ_WINDOW_RE.finditer(text)) + within_matches
    for m in matches:
        tz = m.group("tz")
        if tz not in zones:
            continue
        raw_hours = m.group("hours")
        window = _NUMBER_WORDS.get(raw_hours, None)
        if window is None:
            window = int(raw_hours)
        base = zones[tz]
        # Летнее время сдвигает зону на час; принимаем кандидата, если он
        # попадает в окно хотя бы при одном из двух вариантов — иначе
        # отсекли бы по формальности того, кто фактически подходит полгода.
        fits = any(
            base + shift - window <= my_offset <= base + shift + window
            for shift in (0, 1)
        )
        detail = {
            "verdict": "fits" if fits else "outside",
            "zone": tz.upper(),
            "zone_utc_offset": base,
            "window_hours": window,
            "my_utc_offset": my_offset,
            "phrases": exclusive_hits,
        }
        return (not fits), False, detail

    return False, True, {"verdict": "unparsed_requirement", "phrases": exclusive_hits}


def _strip_stack_noise_sections(text: str, criteria: dict):
    """Отрезает "стековый спам" — блоки, перечисляющие все технологии мира.

    Реальный найденный случай 2026-07-31: у Lemon.io в конце каждого
    объявления идёт абзац "NOT YOUR TECH STACK?" со списком ~60 технологий
    (включая ".NET & C#", Angular, Scala). Из-за него ЛЮБАЯ их вакансия,
    вплоть до "Senior Graphic Designer", получала core_hits ["C#",
    "Angular"] и проходила гейт релевантности стека с максимальным баллом.

    Это не про одну площадку: тот же приём (перечислить все стеки, чтобы
    попасть в любой поиск) используют агрегаторы и аутстаф-компании. Текст
    отрезается ТОЛЬКО для оценки стека — гео и язык по-прежнему смотрят
    описание целиком (там же перечень стран найма).
    """
    markers = (criteria.get("stack_fit") or {}).get("noise_section_markers") or []
    cut_at = len(text)
    matched = []
    for marker in markers:
        needle = common.normalize_for_matching(marker)
        pos = text.find(needle) if needle else -1
        if pos != -1:
            matched.append(marker)
            cut_at = min(cut_at, pos)
    return text[:cut_at], matched


def _score_ambiguous_places(text: str, criteria: dict):
    """Неоднозначные топонимы: одно название, два разных места.

    Обобщение прежней захардкоженной проверки на "georgia". Ловушка не уникальна
    для одной идентичности: Cambridge (UK / Массачусетс), Washington (штат /
    столица), Ontario (Канада / Калифорния), Odessa (Украина / Техас),
    Birmingham (Англия / Алабама) — тот же класс ошибки для других людей.

    Логика сохранена дословно: помечаем, только если сработал контекст ОБОИХ
    значений или НИ ОДНОГО. Одно ясное значение — не повод дёргать человека.
    """
    rules = (criteria.get("remote_location_fit") or {}).get("ambiguous_place_names") or []
    flagged = False
    detail = []

    for rule in rules:
        triggers = rule.get("trigger_keywords") or []
        if not any(common.normalize_for_matching(k) in text for k in triggers):
            continue

        a = _matches(text, (rule.get("meaning_a") or {}).get("context_keywords") or [])
        b = _matches(text, (rule.get("meaning_b") or {}).get("context_keywords") or [])

        if bool(a) == bool(b):  # оба контекста или ни одного — непонятно
            flagged = True
            detail.append({
                "name": rule.get("name"),
                "verdict": "ambiguous",
                "meaning_a_hits": a,
                "meaning_b_hits": b,
            })
        else:
            detail.append({
                "name": rule.get("name"),
                "verdict": "meaning_a" if a else "meaning_b",
                "resolved_as": (rule.get("meaning_a") if a else rule.get("meaning_b")).get("label"),
            })

    return flagged, detail


def _score_remote_location(text: str, vacancy: dict, criteria: dict, profile: dict):
    rl = criteria["remote_location_fit"]
    breakdown = {}
    dealbreakers = []
    needs_review = False

    hard_hits = _matches(text, rl["hard_dealbreakers"]["keywords"])
    if hard_hits:
        dealbreakers.extend(f"location: {h}" for h in hard_hits)

    worldwide_hits = _matches(text, rl["worldwide_remote"]["keywords"])
    # ПРИМЕЧАНИЕ: голого "eor" здесь намеренно нет. Реальный найденный баг
    # (2026-07-30): "eor" - подстрока внутри обычных английских слов
    # ("th-EOR-etical", "th-EOR-y") - ложно совпадало и обходило гейт
    # "не подтверждено как remote" для вакансии, которая была Hybrid/Munich
    # без единого слова "remote" в тексте. Тот же класс бага, что "LESS"/
    # ".NET" внутри "VB.NET" - короткие акронимы слишком легко совпадают
    # как подстрока.
    eor_keywords = list(profile.get("eor_platforms_signal") or []) + [
        "contractor",
        "1099",
        "freelance",
    ]
    eor_hits = _matches(text, eor_keywords)
    region_hits = _matches(text, rl["acceptable_region_signal"]["keywords"])

    # Жёсткая привязка к конкретному региону (LATAM/APAC/UK-only/US-only/...)
    # — dealbreaker, ЕСЛИ нет worldwide/EOR-сигнала, который бы это
    # перевешивал (подтверждено человеком явно 2026-07-30: вакансия
    # "remote LATAM" физически недоступна человеку из Грузии, убирать её
    # надо, а не просто занижать приоритет).
    # Прямое требование резидентства от работодателя не перебивается ничем —
    # ни маркетинговым "worldwide" в тексте, ни размашистой подписью площадки.
    absolute_hits = _matches(text, rl["restrictive_region_signal"].get("absolute_residency_phrases", []))
    if absolute_hits:
        dealbreakers.extend(f"location: explicit residency requirement ('{h}')" for h in absolute_hits)
        breakdown["absolute_residency_hits"] = absolute_hits

    restrictive_hits = _matches(text, rl["restrictive_region_signal"]["keywords"])
    if restrictive_hits and not (worldwide_hits or eor_hits):
        dealbreakers.extend(f"location: restricted to '{h}'" for h in restrictive_hits)
        breakdown["restrictive_region_hits"] = restrictive_hits

    # Структурное поле локации от источника (WWR region / Remotive
    # candidate_required_location / Jobicy jobGeo / Himalayas
    # locationRestrictions) — более надёжный сигнал, чем фразы в тексте.
    structured_restricted, structured_detail = _check_structured_location(vacancy, criteria, profile)
    if structured_detail:
        breakdown["structured_location"] = structured_detail
    # ВАЖНО: структурное ограничение НЕ снимается ничем из текста описания —
    # ни упоминанием EOR/contractor, ни маркетинговыми worldwide-фразами.
    # Поле локации от площадки — авторитетное утверждение о том, ГДЕ
    # компания готова нанимать; фразы в описании таковыми не являются.
    # Два реальных найденных бага (2026-07-30):
    #  * LawnStarter: location = "Brazil"/"Uruguay"/"Mexico" + упоминание
    #    Multiplier (EOR) — 11 латиноамериканских вакансий проходили.
    #    EOR говорит, КАК оформляют сотрудника, а не ГДЕ его наймут.
    #  * Prima: location = "London" + фраза "work from anywhere" в описании
    #    бенефитов (типичное "работай откуда хочешь N недель в году") —
    #    5 лондонских вакансий страховой компании проходили как worldwide.
    if structured_restricted:
        dealbreakers.append(
            f"location: source restricts hiring to '{vacancy.get('location_raw', '').strip()}'"
        )

    # Заголовочный блок самого работодателя внутри описания — точнее, чем
    # размашистое region-поле категорийного фида. Тоже НЕ снимается текстом.
    header_restricted, header_detail = _check_header_hiring_scope(vacancy, criteria)
    if header_detail:
        breakdown["header_scope"] = header_detail
    if header_restricted:
        dealbreakers.append(
            f"location: employer header says remote hiring is limited "
            f"('{header_detail['matched']}')"
        )

    tz_dealbreaker, tz_needs_review, tz_detail = _check_timezone_requirement(text, criteria, profile)
    if tz_detail:
        breakdown["timezone_requirement"] = tz_detail
    if tz_dealbreaker:
        if "range_utc" in tz_detail:
            lo, hi = tz_detail["range_utc"]
            dealbreakers.append(
                f"timezone: requires UTC{lo:+d}..{hi:+d}, "
                f"candidate is at UTC{tz_detail['my_utc_offset']:+d}"
            )
        else:
            dealbreakers.append(
                f"timezone: requires {tz_detail['zone']} ±{tz_detail['window_hours']}h, "
                f"candidate is at UTC{tz_detail['my_utc_offset']:+d}"
            )

    points = 0
    # Названная площадкой страна отменяет ПЛЮС за всемирную удалёнку из текста.
    #
    # Правило «структурное поле авторитетнее маркетинговой фразы» существовало
    # с 2026-07-30, но работало как отсев: вакансия с location="London" просто
    # отклонялась, и что там написано в блоке бенефитов, значения не имело.
    # Когда 2026-08-05 страна перестала быть возражением, фраза "work from
    # anywhere for a few weeks a year" из перечня плюшек начала приносить
    # максимальный балл за международный найм. Регрессию поймал тест, который
    # писался для прежней редакции правила, — поэтому он и сохранён.
    #
    # Смысл прежний: если площадка назвала город, работодатель не нанимает по
    # всему миру, что бы ни было написано в разделе про печеньки.
    structured_named_country = (structured_detail or {}).get("verdict") == "country_named"
    if worldwide_hits and not structured_named_country:
        points = max(points, rl["worldwide_remote"]["points"])
        breakdown["worldwide_remote_hits"] = worldwide_hits
    elif worldwide_hits:
        breakdown["worldwide_remote_hits_ignored"] = {
            "hits": worldwide_hits,
            "why": "площадка назвала страну: %s" % (structured_detail or {}).get("value"),
        }
    if eor_hits:
        points = max(points, rl["eor_or_contractor_international"]["points"])
        breakdown["eor_or_contractor_hits"] = eor_hits
    if region_hits:
        points = max(points, rl["acceptable_region_signal"]["points"])
        breakdown["acceptable_region_hits"] = region_hits

    location_unknown = False
    if not (worldwide_hits or eor_hits or region_hits or restrictive_hits):
        remote_word_hits = _matches(text, rl["remote_synonym_keywords"])
        # Источник, публикующий ТОЛЬКО удалённые вакансии (WWR, RemoteOK,
        # Remotive, Jobicy, Himalayas — см. sources.yaml remote_only), сам
        # по себе является достаточным подтверждением удалёнки. Реальный
        # найденный баг (2026-07-30): вакансии с таких площадок отклонялись
        # как "не подтверждено как remote" только потому, что в тексте
        # описания не встретилось английское слово "remote" — чистый
        # ложноотрицательный результат, вырезавший десятки живых кандидатов.
        from_remote_only_source = vacancy.get("source") in _remote_only_sources()
        if vacancy.get("remote") is True or remote_word_hits or from_remote_only_source:
            points = 4  # известно что remote, но неясно про международный найм
            location_unknown = True
        else:
            # Подтверждено человеком явно (2026-07-30): "мне нужны ТОЛЬКО
            # РЕМОУТ позиции" - ни одного сигнала о remote вообще (ни от
            # источника, ни в тексте) - dealbreaker, а не "неизвестно, но
            # пусть будет". Реальный найденный случай: вакансия Rangeview
            # (явно ONSITE, город "El Segundo, CA") не содержала слова
            # "remote" вообще нигде и получила needs_manual_review вместо
            # отказа.
            dealbreakers.append("location: not confirmed as a remote position (no remote signal found anywhere)")

    places_ambiguous, place_detail = _score_ambiguous_places(text, criteria)
    if place_detail:
        breakdown["ambiguous_place_hits"] = place_detail

    breakdown["points"] = points
    # needs_review как таковой (неоднозначный топоним всегда важно проверить
    # руками; общая неопределённость локации возвращается отдельно и
    # фильтруется на уровне score_vacancy() по итоговой классификации — иначе
    # на реальных данных флаг срабатывает почти на всём (большинство вакансий
    # просто не пишут явно "worldwide" или "US only") и раздел отчёта
    # становится бесполезным.
    needs_review = places_ambiguous or tz_needs_review
    return points, breakdown, dealbreakers, needs_review, location_unknown


def _score_stack_fit(text: str, criteria: dict, profile: dict):
    cfg = criteria["stack_fit"]
    text, noise_markers = _strip_stack_noise_sections(text, criteria)
    core_hits = _matches(text, profile["tech_stack"].get("core", []))
    # Технологии, чьё название невозможно записать безопасной подстрокой —
    # см. _matches_patterns. Без этого ".NET Developer" в заголовке давал
    # ровно ноль баллов за стек.
    core_hits += _matches_patterns(
        text, _pattern_specs_for(profile["tech_stack"].get("core", [])), core_hits)
    strong_hits = _matches(text, profile["tech_stack"]["strong"])
    familiar_hits = _matches(text, profile["tech_stack"]["familiar"])
    raw = (
        len(core_hits) * cfg["points_per_core_keyword"]
        + len(strong_hits) * cfg["points_per_strong_keyword"]
        + len(familiar_hits) * cfg["points_per_familiar_keyword"]
    )
    points = min(raw, cfg["cap"])
    # Глубина совпадения важнее широты перечня. Замер 2026-08-05: вакансия на
    # чистом C#/ASP.NET набирала 7 баллов за стек, а объявление кадрового
    # агентства, перечислившее TypeScript, JavaScript, React, HTML и CSS, —
    # 14. Формула "балл за каждое совпадение" систематически поднимает наверх
    # тех, кто перечисляет технологии списком, над теми, у кого стек ровно
    # тот, который нужен. Поэтому без единого core-совпадения стек не может
    # набрать больше, чем даёт настоящее попадание в ядро.
    cap_no_core = cfg.get("cap_when_no_core")
    if cap_no_core is not None and not core_hits:
        points = min(points, cap_no_core)
    breakdown = {
        "points": points,
        "core_hits": core_hits,
        "strong_hits": strong_hits,
        "familiar_hits": familiar_hits,
    }
    if noise_markers:
        breakdown["noise_sections_ignored"] = noise_markers
    return points, breakdown


def _score_role_complexity(text: str, title: str, criteria: dict):
    """Гейт "это не простая работа", отдельный от legacy_enterprise_signal
    (подтверждено человеком явно 2026-07-30 на примерах "Principal Machine
    Learning Scientist" и "Staff Software Engineer, Agentic Platform" —
    легаси/enterprise-слова в описании компании не значат, что сама РОЛЬ
    простая)."""
    cfg = criteria["role_complexity_signal"]
    title_norm = common.normalize_for_matching(title)
    title_hits = [p for p in cfg["title_red_flag_patterns"] if re.search(p, title_norm, re.IGNORECASE)]
    description_hits = _matches(text, cfg["description_red_flag_keywords"])
    # Реальный найденный случай (2026-07-30, через ручной чек-лист): "Staff
    # Software Engineer (AI CICD)" @ Chainguard упоминал "agentic AI
    # foundation" один раз - недостаточно для порога threshold_hits=2 у
    # расплывчатых слов, но "agentic"/"llm systems"/"genai" сами по себе
    # однозначны - одного упоминания достаточно.
    strong_hits = _matches(text, cfg.get("description_red_flag_keywords_strong_single_hit", []))
    gate_triggered = bool(title_hits) or bool(strong_hits) or len(description_hits) >= cfg["threshold_hits"]
    return gate_triggered, {
        "gate_triggered": gate_triggered,
        "title_hits": title_hits,
        "description_hits": description_hits,
        "strong_single_hit_matches": strong_hits,
    }


def _check_stack_relevance(text: str, core_hits: list, strong_hits: list, criteria: dict):
    """Гейт релевантности стека — ПОЛНЫЙ ОТСЕВ (dealbreaker), а не просто
    низкий score, если не пройден (подтверждено человеком явно, 2026-07-30:
    "не дотнет/js + нет указания что компания tech agnostic" -> 0% шанс).

    core/strong совпадение достаточно само по себе. Java/Scala САМИ ПО СЕБЕ
    не считаются (владелец на Java web-роль не годится), но Java/Scala +
    контекст дата-пайплайнов (Spark/Databricks/ETL) — приемлемый вариант,
    подтверждено человеком явно (реальный опыт, предыдущего места работы).
    Explicit "tech agnostic" заявление компании снимает это требование
    целиком."""
    cfg = criteria["stack_fit"]
    # Тот же срез "стекового спама", что и в _score_stack_fit: иначе гейт
    # релевантности проходил бы по перечню технологий из рекламного блока.
    text, _ = _strip_stack_noise_sections(text, criteria)
    tech_agnostic_hits = _matches(
        text, criteria["role_relevance_signal"]["tech_agnostic_override_keywords"]
    )
    data_pipeline_language_hits = _matches(text, cfg["data_pipeline_language_keywords"])
    data_pipeline_context_hits = _matches(text, cfg["data_pipeline_context_keywords"])
    data_pipeline_relevant = bool(data_pipeline_language_hits) and bool(data_pipeline_context_hits)

    # Нужен настоящий язык/фреймворк, а не только инфраструктурное слово
    # (Docker/Azure/HTML/CSS есть почти в любой вакансии — по ним нельзя
    # судить, что роль подходит .NET/JS-разработчику).
    primary_language_hits = _matches(text, cfg.get("primary_language_keywords", []))
    primary_language_hits += _matches_patterns(
        text, _pattern_specs_for(cfg.get("primary_language_keywords", [])),
        primary_language_hits)

    relevant = bool(primary_language_hits) or data_pipeline_relevant or bool(tech_agnostic_hits)
    return relevant, {
        "primary_language_hits": primary_language_hits,
        "tech_agnostic_override_hits": tech_agnostic_hits,
        "data_pipeline_exception_applied": data_pipeline_relevant,
    }


def _check_title_stack(title: str, criteria: dict, profile: dict):
    """Заголовок называет технологию, которой у человека нет — полный отсев.

    Реальная протечка 2026-08-04, замеченная человеком в готовой выдаче:
    "Senior Ruby on Rails Developer", "Senior Fullstack Developer (Python)",
    "Senior Vue Developer". Гейт релевантности искал знакомый язык по ВСЕМУ
    тексту, а в Rails-вакансии среди смежных навыков перечислены HTML, CSS и
    JavaScript. Совпадение формально есть, роль — совсем про другое.

    Роль определяет заголовок. Поэтому: если он называет хотя бы одну
    роль-образующую технологию и НИ ОДНА из названных не входит в core/strong
    — вакансия отсекается. Familiar-уровень намеренно не считается: это
    «трогал пару раз за карьеру», на такую роль человека не возьмут.
    """
    cfg = criteria.get("title_stack_gate")
    if not cfg:
        return False, {}

    title_norm = common.normalize_for_matching(title)
    named = [tech for tech in cfg.get("role_defining_technologies", [])
             if common.normalize_for_matching(tech) in title_norm]
    if not named:
        return False, {"named_technologies": []}

    stack = profile.get("tech_stack") or {}
    known = {common.normalize_for_matching(k)
             for k in (stack.get("core") or []) + (stack.get("strong") or [])}
    # Сравнение ТОЧНОЕ, а не по вхождению подстроки. Реальный баг 2026-08-05:
    # "java" считалась знакомой, потому что является подстрокой "javascript"
    # из strong-уровня, и "Java Engineer" снова проходил гейт. Тот же класс
    # ошибки, что ".NET" внутри "VB.NET" и "LESS" внутри "no less than".
    mine = [tech for tech in named if common.normalize_for_matching(tech) in known]

    return (not mine), {
        "named_technologies": named,
        "known_among_them": mine,
    }


def _score_role_relevance(text: str, title: str, criteria: dict):
    """Гейт "это вообще роль разработчика ПО" — ПОЛНЫЙ ОТСЕВ (dealbreaker).
    Подтверждено человеком явно (2026-07-30) на реальных находках: "CFO
    Controller", "Product Manager, Mapping and Weather Visualization" — не
    роли разработчика, независимо от legacy/enterprise-слов в описании
    компании. Срабатывает по заголовку вакансии; developer_role_override_
    patterns (например, "Engineer"/"Developer" в заголовке) снимает гейт,
    как и явное "tech agnostic" заявление где угодно в тексте."""
    cfg = criteria["role_relevance_signal"]
    title_norm = common.normalize_for_matching(title)

    # Если заголовок неинформативен, смотрим ещё и первую строку описания.
    #
    # Реальная находка 2026-08-04: запись с Hacker News приехала с заголовком
    # "YC 19" и компанией "Ashby" — парсер треда разобрал строку
    # "Ashby | YC 19 | REMOTE | Hiring Engineering Leaders | $200k-$275k"
    # по разделителям и взял не тот кусок. Гейт профессии смотрит ЗАГОЛОВОК,
    # а в заголовке "YC 19" нет ни одной профессии — вакансия менеджерская
    # (Engineering Leaders), но прошла как обычная и заняла место в выдаче.
    #
    # Расширяем область поиска ТОЛЬКО когда в заголовке нет ни одного слова,
    # означающего роль разработчика: у нормальной вакансии заголовок
    # информативен, и первая строка описания (обычно рассказ о компании) в
    # проверку не попадает — иначе слово "manager" из корпоративного блёрба
    # начало бы выбрасывать нормальные вакансии.
    developer_override_hits = [
        p for p in cfg["developer_role_override_patterns"] if re.search(p, title_norm, re.IGNORECASE)
    ]
    search_area = title_norm
    uninformative_title = not developer_override_hits
    if uninformative_title:
        # _vacancy_text уже схлопнул переносы, поэтому берём просто начало.
        search_area = f"{title_norm} {(text or '')[:300]}"

    wrong_profession_hits = [
        p for p in cfg["wrong_profession_title_patterns"] if re.search(p, search_area, re.IGNORECASE)
    ]
    # Жёсткий уровень: менеджмент/продажи/GTM/пресейл — заведомо не роль
    # рядового разработчика, даже если в заголовке есть "engineer"/"architect".
    hard_wrong_hits = [
        p for p in cfg.get("hard_wrong_profession_title_patterns", [])
        if re.search(p, search_area, re.IGNORECASE)
    ]
    tech_agnostic_hits = _matches(text, cfg["tech_agnostic_override_keywords"])

    soft_gate = bool(wrong_profession_hits) and not developer_override_hits and not tech_agnostic_hits
    gate_triggered = soft_gate or bool(hard_wrong_hits)
    return gate_triggered, {
        "gate_triggered": gate_triggered,
        "wrong_profession_hits": wrong_profession_hits + hard_wrong_hits,
        "hard_wrong_profession_hits": hard_wrong_hits,
        "developer_override_hits": developer_override_hits,
    }


def _score_language_fit(text: str, criteria: dict):
    """Гейт знания языков — ПОЛНЫЙ ОТСЕВ (dealbreaker). Подтверждено
    человеком явно (2026-07-30): владелец говорит только на русском и
    английском (см. profile.yaml → owner.languages). Реальная находка:
    "Web-Administration / Webmaster TYPO3" требовал "sehr gute
    Deutschkenntnisse". Дополнительно: многие вакансии с немецких бордов
    целиком написаны по-немецки без явной англоязычной фразы про язык —
    эвристика по частым немецким словам/разметке "m/w/d" ловит и такие."""
    cfg = criteria["language_requirement_signal"]
    explicit_hits = _matches(text, cfg["explicit_requirement_keywords"])
    german_market_hits = _matches(text, cfg["german_market_indicator_keywords"])
    # Гендерная разметка "(m/w/d)"/"(f/m/d)" однозначна сама по себе: она
    # существует только в немецкоязычных объявлениях (требование AGG). Порог
    # в 3 совпадения для неё избыточен — реальные вакансии Hygraph и
    # Boardwise (2026-07-31) содержали ровно один такой маркер и проходили.
    german_strong_hits = _matches(text, cfg.get("german_market_strong_single_markers", []))
    german_market_flagged = (
        len(german_market_hits) >= cfg["german_market_indicator_threshold"]
        or bool(german_strong_hits)
    )

    # Тот же приём, что и для немецкого, но для любого языка. Реальные
    # находки 2026-07-31 (ручной чек-лист): объявление Work and Study Travel
    # целиком на испанском, Base.com — целиком на польском; обе прошли, потому
    # что эвристика существовала ровно для одного языка. Немецкий блок выше
    # оставлен отдельно: на нём откалиброваны тесты и порог.
    foreign_language_hits = {}
    for entry in cfg.get("foreign_language_posting_indicators", []):
        hits = _matches(text, entry.get("markers", []))
        if len(hits) >= entry.get("threshold", 3):
            foreign_language_hits[entry["language"]] = hits

    # Письменность надёжнее списка слов. Объявление на иврите, арабском,
    # китайском или греческом нечитаемо для того, кто знает только латиницу и
    # кириллицу, — и выяснять это перечислением частых слов бессмысленно:
    # алфавит виден сразу и целиком.
    #
    # Реальная находка 2026-08-05 (чтение выдачи глазами): вакансия
    # "מפתח/ת C#/.NET — מערכות תוכנה-חומרה" стояла в выдаче на 13-м месте.
    # Списки слов существовали для пяти европейских языков, и ни один из них
    # не мог поймать другую письменность в принципе.
    script_detail = _check_unreadable_script(text, cfg)

    gate_triggered = (bool(explicit_hits) or german_market_flagged
                      or bool(foreign_language_hits) or bool(script_detail))
    return gate_triggered, {
        "gate_triggered": gate_triggered,
        "explicit_requirement_hits": explicit_hits,
        "german_market_indicator_hits": german_market_hits,
        "german_market_flagged": german_market_flagged,
        "foreign_language_posting_hits": foreign_language_hits,
        "unreadable_script": script_detail,
    }


# Диапазоны кодов письменностей, которые встречаются в объявлениях о работе.
# Латиница и кириллица сюда не входят: их читает владелец любой идентичности,
# где английский или русский указан в языках.
_SCRIPT_RANGES = (
    ("hebrew", 0x0590, 0x05FF),
    ("arabic", 0x0600, 0x06FF),
    ("greek", 0x0370, 0x03FF),
    ("thai", 0x0E00, 0x0E7F),
    ("devanagari", 0x0900, 0x097F),
    ("hangul", 0xAC00, 0xD7AF),
    ("cjk", 0x4E00, 0x9FFF),
    ("kana", 0x3040, 0x30FF),
)


def _check_unreadable_script(text: str, cfg: dict):
    """Доля текста в письменности, которой человек не читает.

    Порог долевой, а не абсолютный: одно-два слова на иврите может содержать
    и англоязычная вакансия израильской компании (название, адрес). Целиком
    написанное объявление даёт долю в десятки процентов.
    """
    readable = set(cfg.get("readable_scripts") or ["latin", "cyrillic"])
    threshold = cfg.get("unreadable_script_threshold", 0.15)

    counts = {}
    letters = 0
    for char in text:
        if not char.isalpha():
            continue
        letters += 1
        code = ord(char)
        for name, low, high in _SCRIPT_RANGES:
            if low <= code <= high:
                counts[name] = counts.get(name, 0) + 1
                break

    if letters < 80:
        return None
    for name, count in counts.items():
        if name in readable:
            continue
        share = count / letters
        if share >= threshold:
            return {"script": name, "share": round(share, 3)}
    return None


def _check_industry_dealbreaker(text: str, criteria: dict):
    """Отрасль, в которую человек не идёт принципиально — полный отсев.

    Порог обязателен: вакансия обычной компании может упомянуть крипто среди
    клиентов или интеграций, и одного слова недостаточно. Два и больше —
    это уже про саму компанию.
    """
    cfg = criteria.get("industry_dealbreaker_gate")
    if not cfg:
        return False, {}
    # Тот же срез "стекового спама", что и в оценке стека. Реальный случай
    # 2026-08-04: гейт отсёк все вакансии Lemon.io, потому что их рекламный
    # абзац "NOT YOUR TECH STACK?" перечисляет и Blockchain, и Ethereum, и
    # Solana. Компания к крипте отношения не имеет — это перечень стеков,
    # под которые они подбирают проекты. Ложный отказ прячет живые вакансии,
    # что хуже, чем лишняя вакансия в выдаче.
    text, _ = _strip_stack_noise_sections(text, criteria)
    hits = _matches(text, cfg.get("keywords", []))
    threshold = cfg.get("threshold_hits", 2)
    return len(hits) >= threshold, {
        "gate_triggered": len(hits) >= threshold,
        "hits": hits,
        "threshold": threshold,
    }


def _check_mobile_role(text: str, title: str, criteria: dict):
    """Мобильная разработка за нейтральным заголовком — полный отсев.

    Тот же класс, что и `_check_infrastructure_role`: заголовок говорит
    "Lead Full-stack Developer", а продукт — приложение на React Native и
    Expo, и вся работа состоит в нём. Гейт заголовка такое не видит.

    Порог обязателен: обычная веб-вакансия может упомянуть мобильное
    приложение среди прочих продуктов компании. Срез рекламных блоков —
    тоже: перечни стеков кадровых агентств содержат и React Native, и
    Flutter, из-за чего без него под гейт попадали "Senior Vue Developer" и
    "Senior Graphic Designer" от Lemon.io.
    """
    cfg = criteria.get("mobile_role_gate")
    if not cfg:
        return False, {}
    text, _ = _strip_stack_noise_sections(text, criteria)
    hits = _matches(common.normalize_for_matching(title) + " " + text,
                    cfg.get("keywords", []))
    threshold = cfg.get("threshold_hits", 2)
    triggered = len(hits) >= threshold
    return triggered, {
        "gate_triggered": triggered,
        "hits": hits,
        "threshold": threshold,
    }


def _check_ai_training_crowdwork(text: str, criteria: dict):
    """Краудворк по обучению ИИ, замаскированный под инженерную вакансию.

    Отдельный жанр, появившийся на бордах в 2024–2026 годах: площадка
    набирает разработчиков не строить софт, а порождать обучающие данные —
    писать эталонные решения, размечать, оценивать ответы модели, собирать
    RL-окружения. Формально это «Senior Software Engineer», по сути —
    сдельная подработка без проекта, команды и продукта.

    Такие объявления систематически побеждают в скоринге, и не случайно:
    они перечисляют все языки сразу («JavaScript, Python, Go, C++, Ruby»),
    честно пишут «no set schedules» (читается как низкая нагрузка) и почти
    всегда указывают почасовую ставку. Замер 2026-08-05: четыре из девяти
    верхних позиций выдачи, включая первую.

    Гейт, а не штраф: работа со сдельной оплатой за задачу — не то, что
    ищет человек с постоянным местом, и никакая сумма баллов этого не
    компенсирует. Маркеры намеренно длинные: короткие («ai», «training»)
    поймали бы половину рынка.
    """
    cfg = criteria.get("ai_training_crowdwork_gate")
    if not cfg:
        return False, {}
    hits = _matches(text, cfg.get("keywords", []))
    return bool(hits), {"gate_triggered": bool(hits), "hits": hits}


def _score_legacy_enterprise(text: str, criteria: dict):
    cfg = criteria["legacy_enterprise_signal"]
    hits = _matches(text, cfg["keywords"])
    points = min(len(hits) * cfg["points_per_keyword"], cfg["cap"])
    return points, {"points": points, "hits": hits}


def _score_low_intensity(text: str, criteria: dict):
    cfg = criteria["low_intensity_signal"]
    pos_hits = _matches(text, cfg["positive_keywords"])
    neg_hits = _matches(text, cfg["negative_keywords"])
    raw = len(pos_hits) * cfg["positive_points_per_keyword"] + len(neg_hits) * cfg[
        "negative_points_per_keyword"
    ]
    points = max(min(raw, cfg["cap"]), cfg["floor"])
    return points, {"points": points, "positive_hits": pos_hits, "negative_hits": neg_hits}


def _extract_amounts(text: str):
    """Best-effort извлечение денежных сумм из текста. Возвращает список
    (значение_в_год_или_None, значение_в_час_или_None, значение_в_месяц_или_None).

    Отдельно распознаём "$X/month" / "$X per month" / "$X/mo" — без этого
    типичное объявление вида "$5,000/month" трактовалось бы как ГОДОВАЯ
    ставка (число >= 500) и несправедливо штрафовалось бы как заниженное
    относительно annual_parttime_usd."""
    results = []
    for m in _AMOUNT_RE.finditer(text):
        # Контекст перед суммой. Реальный случай 2026-07-31: Sticker Mule
        # пишет "Salary: $150,000–$250,000 USD" и следом "$20,000 signing
        # bonus" — отчёт показывал вилку "$20,000-$250,000/год", то есть
        # заметно занижал нижнюю границу. Бонусы, стипендии и оборот
        # компании к ставке отношения не имеют.
        # Назад смотрим шире, вперёд — узко: "signing bonus" стоит сразу за
        # своей суммой, а вот заглядывать на 40 символов вперёд нельзя, иначе
        # настоящая вилка "$150,000-$250,000 USD. $20,000 signing bonus"
        # отбрасывалась бы целиком из-за соседнего бонуса.
        window = text[max(0, m.start() - 40):m.end() + 15]
        if any(w in window for w in _NON_SALARY_CONTEXT_WORDS):
            continue
        raw_num, suffix = m.group(1), (m.group(2) or "").strip().lower()
        try:
            value = float(raw_num.replace(",", ""))
        except ValueError:
            continue
        if suffix in _MAGNITUDE_SUFFIXES:
            continue  # оборот/инвестиции/суммарные выплаты, а не ставка
        if suffix == "k":
            results.append((value * 1000, None, None))
        elif suffix and ("month" in suffix or suffix.lstrip("/per ").strip() == "mo"):
            results.append((None, None, value))
        elif suffix and ("hour" in suffix or "hr" in suffix):
            results.append((None, value, None))
        elif value < 500:
            # маленькое число без суффикса - скорее всего почасовая ставка
            results.append((None, value, None))
        else:
            results.append((value, None, None))
    return results


def _score_external_salary_estimate(vacancy: dict, criteria: dict, profile: dict):
    """Оценка вручную найденной (Glassdoor и т.п.) вилки, когда сама
    вакансия зарплату не указывает. Подтверждено человеком явно
    (2026-07-30): "если ЗП не указана, но из сторонних источников понятен
    примерный рендж — маленький плюс". Заполняется через
    `tools/kb.py set-salary-estimate` в vacancy.external_signals — это
    top-level поле (не "manual"), поэтому оно участвует в rescoring."""
    cfg = criteria["compensation_signal"]
    estimate = (vacancy.get("external_signals") or {}).get("salary_estimate")
    if not estimate:
        return None

    points = cfg["external_estimate_points"]
    low, high = estimate.get("low"), estimate.get("high")
    period = estimate.get("period", "year")
    target = profile["goal"]["target_compensation"]
    range_key = {
        "year": "annual_parttime_usd",
        "month": "monthly_parttime_usd",
        "hour": "hourly_contractor_usd",
    }.get(period)
    if range_key and low is not None and high is not None:
        lo, hi = target[range_key]
        if high < lo:
            points += cfg["below_target_penalty"]
        elif low > hi:
            points += cfg["above_target_bonus"]
    return {
        "points": points,
        "explicit": False,
        "external_estimate": estimate,
    }


def _score_compensation(text: str, vacancy: dict, criteria: dict, profile: dict):
    cfg = criteria["compensation_signal"]
    target = profile["goal"]["target_compensation"]
    # ВАЖНО: "явно указана" определяется по РАСПОЗНАННЫМ суммам, а не по
    # факту наличия знака доллара в тексте. Иначе "$11M выплачено инженерам"
    # считалось бы указанной зарплатой, хотя _extract_amounts эту сумму
    # (справедливо) отбрасывает — и вакансия получала бы полный балл за
    # "прозрачную компенсацию" при пустом списке сумм.
    amounts = _extract_amounts(text)
    has_explicit = bool(vacancy.get("salary_raw")) or bool(amounts)
    if not has_explicit:
        external = _score_external_salary_estimate(vacancy, criteria, profile)
        if external is not None:
            return external["points"], external
        return cfg["no_range_points"], {"points": cfg["no_range_points"], "explicit": False}

    points = cfg["has_explicit_range_points"]
    annuals = [a for a, h, mo in amounts if a is not None]
    hourlies = [h for a, h, mo in amounts if h is not None]
    monthlies = [mo for a, h, mo in amounts if mo is not None]

    # Незаполненный диапазон просто не участвует в сравнении.
    #
    # Раньше здесь стояло target["annual_parttime_usd"] без оговорок, и профиль
    # с зарплатой в другой форме ронял ВЕСЬ прогон KeyError-ом посреди скоринга.
    # Найдено эмуляцией онбординга 2026-08-05: агент, записывающий ответ «5-8
    # тысяч в месяц», естественно пишет monthly_min/monthly_target. Форма
    # описана в шаблоне профиля; отсутствие ключа — не повод падать.
    def _range(name):
        value = target.get(name)
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return value[0], value[1]
        return None

    below = above = False
    annual_range = _range("annual_parttime_usd")
    if annuals and annual_range:
        lo, hi = annual_range
        if max(annuals) < lo:
            below = True
        elif min(annuals) > hi:
            above = True
    hourly_range = _range("hourly_contractor_usd")
    if hourlies and hourly_range:
        lo, hi = hourly_range
        if max(hourlies) < lo:
            below = True
        elif min(hourlies) > hi:
            above = True
    monthly_range = _range("monthly_parttime_usd")
    if monthly_range is None and annual_range:
        monthly_range = (annual_range[0] / 12, annual_range[1] / 12)
    if monthlies and monthly_range:
        lo, hi = monthly_range
        if max(monthlies) < lo:
            below = True
        elif min(monthlies) > hi:
            above = True

    if below:
        points += cfg["below_target_penalty"]
    elif above:
        points += cfg["above_target_bonus"]

    return points, {
        "points": points,
        "explicit": True,
        "annual_amounts_found": annuals,
        "hourly_amounts_found": hourlies,
        "monthly_amounts_found": monthlies,
    }


_RED_FLAG_CATALOGUE_CACHE = {}


def red_flag_catalogue() -> dict:
    """Общий каталог красных флагов (config/derivation/company_red_flags.yaml)."""
    if "data" not in _RED_FLAG_CATALOGUE_CACHE:
        path = common.ROOT / "config" / "derivation" / "company_red_flags.yaml"
        _RED_FLAG_CATALOGUE_CACHE["data"] = common.load_yaml(path) if path.exists() else {}
    return _RED_FLAG_CATALOGUE_CACHE["data"] or {}


def classify_red_flag(flag: str):
    """Категория свободнотекстового флага, либо None."""
    text = common.normalize_for_matching(flag)
    for name, spec in (red_flag_catalogue().get("categories") or {}).items():
        if any(common.normalize_for_matching(p) in text for p in spec.get("phrases") or []):
            return name
    return None


def _score_red_flags(flags: list, profile: dict):
    """Сумма весов красных флагов с учётом переопределений.

    Порядок приоритета — от общего к частному, побеждает частное:
      1. вес по умолчанию из общего каталога;
      2. `company_red_flag_severity` из профиля идентичности;
      3. то же поле, но со значением `local` — тогда веса приходят из Малой
         Конституции и в общий репозиторий не попадают.

    Переопределение работает В ЛЮБУЮ СТОРОНУ. Положительное значение —
    законный случай, а не ошибка: «непредсказуемая загрузка» бывает ровно
    тем, что человек ищет. Клампа на неположительные значения здесь
    сознательно нет.
    """
    catalogue = red_flag_catalogue()
    categories = catalogue.get("categories") or {}
    overrides = (profile or {}).get("company_red_flag_severity")
    # Незаполненный сентинел `local` доезжает сюда строкой — это не словарь
    # весов, а признак того, что Малая Конституция ничего не сказала.
    if not isinstance(overrides, dict):
        overrides = {}

    total = 0
    detail = []
    for flag in flags:
        category = classify_red_flag(flag)
        if category is None:
            points = catalogue.get("unrecognised_points", -5)
            source = "unrecognised"
        elif category in overrides:
            points = overrides[category]
            source = "override"
        else:
            points = (categories.get(category) or {}).get("default_points", -5)
            source = "catalogue"
        total += points
        detail.append({"flag": flag, "category": category,
                       "points": points, "source": source})
    return total, detail


def _score_company_reputation(vacancy: dict, criteria: dict, profile: dict = None):
    """Репутация работодателя по внешним источникам (Glassdoor и т.п.),
    собранная агентом вручную и хранящаяся на уровне компании.

    Возвращает (points, breakdown, needs_review). Для этого проекта
    work-life balance весит больше общего рейтинга: компания может иметь
    хороший общий балл за счёт зарплат и карьеры, но выжимать людей — а
    нужно ровно обратное."""
    cfg = criteria.get("company_reputation_signal")
    rep = vacancy.get("_company_reputation")
    if not cfg or not rep:
        return (cfg or {}).get("no_data_points", 0), {"has_data": False}, False

    # «Проверяли — не нашли» баллов не даёт и не отнимает: отсутствие отзывов
    # о небольшой компании ничего не говорит о том, как в ней работается.
    # Но в отчёт это состояние обязано попасть отдельной строкой, иначе оно
    # снова сольётся с «не проверяли» — а это разные вещи (reputation.py).
    if rep.get("verdict") == "insufficient_sources":
        return (cfg.get("no_data_points", 0), {
            "has_data": False,
            "verdict": "insufficient_sources",
            "checked_at": rep.get("checked_at"),
            "searched": rep.get("searched"),
        }, False)

    points = 0
    detail = {
        "has_data": True,
        "source": rep.get("source"),
        "retrieval": rep.get("retrieval"),
        "checked_at": rep.get("checked_at"),
    }
    needs_review = False

    rating = rep.get("overall_rating")
    if rating is not None:
        rc = cfg["overall_rating"]
        detail["overall_rating"] = rating
        if rating >= rc["excellent_threshold"]:
            points += rc["excellent_points"]
        elif rating >= rc["decent_threshold"]:
            points += rc["decent_points"]
        elif rating <= rc["poor_threshold"]:
            points += rc["poor_points"]
        if rating <= rc["alarming_threshold"]:
            needs_review = True
            detail["alarming_rating"] = True

    wlb = rep.get("work_life_balance")
    if wlb is not None:
        wc = cfg["work_life_balance"]
        detail["work_life_balance"] = wlb
        if wlb >= wc["excellent_threshold"]:
            points += wc["excellent_points"]
        elif wlb <= wc["poor_threshold"]:
            points += wc["poor_points"]

    red_flags = rep.get("red_flags") or []
    if red_flags:
        detail["red_flags"] = red_flags
        needs_review = True
        # Красный флаг обязан стоить баллов, а не только пометки. Реальный
        # случай 2026-08-05: платформа с отзывами "late payments" и
        # "unpredictable work availability" получала +14 за рейтинг 3.5 и
        # work-life balance 4.0 — и выходила на первое место в выдаче.
        #
        # Вес зависит от того, ЧТО именно за флаг, и берётся из общего
        # каталога, а идентичность или Малая Конституция могут перебить его
        # в любую сторону, включая плюс (docs/OVERRIDES.md).
        flag_points, flag_detail = _score_red_flags(red_flags, profile)
        points += flag_points
        detail["red_flag_penalty"] = flag_points
        detail["red_flag_breakdown"] = flag_detail

    detail["points"] = points
    return points, detail, needs_review


def _score_company_age(vacancy: dict, criteria: dict):
    """Зрелость компании из открытых данных (Wikidata, собирается
    автоматически через tools/company_intel.py). profile.yaml →
    ideal_company_traits просит "mature company (10+ years old)": у старой
    компании обычно устоявшиеся процессы и легаси — то, что нужно."""
    cfg = (criteria.get("company_reputation_signal") or {}).get("company_age")
    intel = vacancy.get("_company_intel")
    if not cfg or not intel or not intel.get("found"):
        return 0, {"has_data": False}

    age = intel.get("age_years")
    if age is None:
        return 0, {"has_data": False}

    if age >= cfg["mature_threshold_years"]:
        points = cfg["mature_points"]
    elif age >= cfg["established_threshold_years"]:
        points = cfg["established_points"]
    elif age <= cfg["very_young_threshold_years"]:
        points = cfg["very_young_points"]
    else:
        points = 0

    return points, {
        "has_data": True,
        "founded_year": intel.get("founded_year"),
        "age_years": age,
        "employees": intel.get("employees"),
        "points": points,
    }


def _score_contractor_friendliness(text: str, criteria: dict):
    cfg = criteria["contractor_friendliness"]
    hits = _matches(text, cfg["keywords"])
    points = min(len(hits) * cfg["points_per_keyword"], cfg["cap"])
    return points, {"points": points, "hits": hits}


def _score_personal_market_bonus(vacancy: dict, profile: dict):
    """Личная надбавка за конкретный рынок.

    ЗАЧЕМ ОТДЕЛЬНЫЙ СИГНАЛ И ПОЧЕМУ ЕГО ЗНАЧЕНИЯ ЖИВУТ ВНЕ РЕПОЗИТОРИЯ.
    Бывают причины предпочесть страну, которых нет ни в рынке, ни в профиле
    поиска: налоговое резидентство, пенсионный стаж, семья, планы на переезд.
    Это обстоятельства КОНКРЕТНОГО человека — они не должны попадать ни в
    общую машинерию (там им не место по определению), ни в идентичность
    (её может переиспользовать кто угодно другой).

    Поэтому в профиле идентичности стоит сентинел `local`, а сами страны и
    веса лежат в Малой Конституции, вне гита. Идентичность лишь объявляет,
    что такая надбавка может быть.

    Надбавка намеренно МЯГКАЯ: она двигает вакансию вверх в выдаче, но не
    делает непроходную проходной — гейты отрабатывают раньше и независимо.
    """
    bonuses = (profile or {}).get("personal_market_bonus")
    if not isinstance(bonuses, dict) or not bonuses:
        return 0, {}

    haystack = " ".join(str(x) for x in (
        vacancy.get("location_raw") or "",
        " ".join(vacancy.get("tags") or []),
    )).lower()

    hits = {}
    for country, cfg in bonuses.items():
        if common.normalize_for_matching(country) not in haystack:
            continue
        points = cfg.get("points", 0) if isinstance(cfg, dict) else cfg
        # Часть надбавок имеет смысл только для удалённой работы: «платить
        # налоги дома» работает, если работать можно откуда угодно.
        if isinstance(cfg, dict) and cfg.get("remote_only") and not vacancy.get("remote"):
            continue
        hits[country] = points

    if not hits:
        return 0, {}
    total = sum(hits.values())
    return total, {"points": total, "hits": hits}


def _score_title_role_penalty(title: str, criteria: dict):
    """Мягкий штраф за роли, которые человек закрыть может, но на которые его
    возьмут с меньшей вероятностью.

    Не гейт: это вопрос шансов, а не возможности. Реальный случай 2026-08-05:
    чистый Frontend Developer — работу человек сделает, но опыт у него в
    основном фуллстек, и в конкуренции с профильными фронтендерами он
    проигрывает. Выбрасывать такие вакансии неправильно, показывать наравне
    с профильными — тоже.
    """
    cfg = criteria.get("title_role_penalty")
    if not cfg:
        return 0, {}
    title_norm = common.normalize_for_matching(title)

    hits = []
    points = 0
    for rule in cfg.get("rules", []):
        pattern = rule.get("pattern")
        if not pattern or not re.search(pattern, title_norm, re.IGNORECASE):
            continue
        # Исключения: «Fullstack (React)» не должен считаться чистым фронтендом.
        if any(re.search(x, title_norm, re.IGNORECASE) for x in rule.get("unless", [])):
            continue
        hits.append(rule.get("label") or pattern)
        points += rule.get("points", 0)

    return points, ({"points": points, "hits": hits} if hits else {})


def _score_personal_tech_bonus(text: str, title: str, profile: dict, criteria: dict = None):
    """Личные надбавки и штрафы за конкретные технологии.

    ЗАЧЕМ ОТДЕЛЬНО ОТ stack_fit. Тот отвечает на вопрос «умеет ли человек это
    вообще» и одинаков для всех, кто пользуется идентичностью. А вот насколько
    один знакомый стек предпочтительнее другого — вопрос личного опыта: два
    разработчика с одинаковой строчкой ".NET/JS" в резюме могут быть сильны в
    разном. Поэтому значения живут в Малой Конституции, вне гита.

    Вес считается ОДИН РАЗ на группу, а не за каждое совпадение: иначе
    вакансия, перечислившая пять форм написания Node, получила бы пятикратный
    штраф, а упомянувшая .NET один раз — одинарную надбавку.
    """
    groups = (profile or {}).get("personal_tech_bonus")
    if not isinstance(groups, dict) or not groups:
        return 0, {}

    # Срез "стекового спама" — тот же, что в оценке стека и в гейте отрасли.
    # Без него аутстаф-компания с абзацем "NOT YOUR TECH STACK?" получает
    # надбавку за .NET на любой своей вакансии, включая чистый React.
    if criteria:
        text, _ = _strip_stack_noise_sections(text, criteria)
    haystack = f"{common.normalize_for_matching(title)} {text}"
    total = 0
    hits = {}
    for name, cfg in groups.items():
        if not isinstance(cfg, dict):
            continue
        matched = _matches(haystack, cfg.get("keywords") or [])
        if not matched:
            continue
        # Исключения нужны там, где технология упомянута как соседняя, а не
        # как суть роли: "React + .NET" — это .NET-вакансия, а не Node.
        if _matches(haystack, cfg.get("unless") or []):
            continue
        points = cfg.get("points", 0)
        total += points
        hits[name] = {"points": points, "matched": matched[:4]}

    return total, ({"points": total, "groups": hits} if hits else {})


def score_vacancy(vacancy: dict, criteria: Optional[dict] = None, profile: Optional[dict] = None) -> dict:
    criteria = criteria or load_criteria()
    profile = profile or load_profile()
    text = _vacancy_text(vacancy)

    rl_points, rl_bd, dealbreakers, needs_review, location_unknown = _score_remote_location(
        text, vacancy, criteria, profile
    )
    stack_points, stack_bd = _score_stack_fit(text, criteria, profile)
    complexity_gate, complexity_bd = _score_role_complexity(text, vacancy.get("title") or "", criteria)
    legacy_points, legacy_bd = _score_legacy_enterprise(text, criteria)
    intensity_points, intensity_bd = _score_low_intensity(text, criteria)
    comp_points, comp_bd = _score_compensation(text, vacancy, criteria, profile)
    contractor_points, contractor_bd = _score_contractor_friendliness(text, criteria)
    reputation_points, reputation_bd, reputation_needs_review = _score_company_reputation(
        vacancy, criteria, profile
    )
    if reputation_needs_review:
        needs_review = True
    age_points, age_bd = _score_company_age(vacancy, criteria)
    market_points, market_bd = _score_personal_market_bonus(vacancy, profile)
    tech_points, tech_bd = _score_personal_tech_bonus(
        text, vacancy.get("title") or "", profile, criteria)
    title_penalty, title_penalty_bd = _score_title_role_penalty(vacancy.get("title") or "", criteria)
    exporter_penalty, exporter_bd = _score_market_penalty(vacancy, criteria, profile)

    # Три ПОЛНЫХ ОТСЕВА (0% шанс попасть в выдачу), подтверждённых
    # человеком явно 2026-07-30 — не понижение приоритета, а dealbreaker:
    stack_relevant, stack_relevance_bd = _check_stack_relevance(
        text, stack_bd["core_hits"], stack_bd["strong_hits"], criteria
    )
    if not stack_relevant:
        stack_label = (criteria.get("stack_fit") or {}).get("stack_label") or "target-stack"
        dealbreakers.append(
            f"stack: not a {stack_label} developer role (and no tech-agnostic signal)"
        )
    stack_bd.update(stack_relevance_bd)

    role_irrelevant, role_relevance_bd = _score_role_relevance(text, vacancy.get("title") or "", criteria)
    if role_irrelevant:
        dealbreakers.append(
            f"role: title suggests non-developer profession ({', '.join(role_relevance_bd['wrong_profession_hits'])})"
        )

    title_mismatch, title_stack_bd = _check_title_stack(
        vacancy.get("title") or "", criteria, profile
    )
    if title_stack_bd:
        stack_bd["title_stack_gate"] = title_stack_bd
    # Дата-пайплайны — задокументированное исключение: Scala/Java в заголовке
    # при контексте Spark/Databricks/ETL остаются желанным вариантом.
    if title_mismatch and not stack_bd.get("data_pipeline_exception_applied"):
        dealbreakers.append(
            "stack: title names technology outside the core/strong stack "
            f"({', '.join(title_stack_bd['named_technologies'][:3])})"
        )

    infra_role, infra_bd = _check_infrastructure_role(text, vacancy.get("title") or "", criteria)
    role_relevance_bd["infrastructure_role_gate"] = infra_bd
    if infra_role:
        dealbreakers.append(
            "role: infrastructure/platform (DevOps) role despite a neutral title "
            f"({', '.join(infra_bd['hits'][:5])})"
        )

    industry_blocked, industry_bd = _check_industry_dealbreaker(text, criteria)
    if industry_bd:
        legacy_bd["industry_dealbreaker_gate"] = industry_bd
    if industry_blocked:
        dealbreakers.append(
            "industry: отрасль, которую этот поиск избегает "
            f"({', '.join(industry_bd['hits'][:4])})"
        )

    mobile_role, mobile_bd = _check_mobile_role(text, vacancy.get("title") or "", criteria)
    if mobile_bd:
        role_relevance_bd["mobile_role_gate"] = mobile_bd
    if mobile_role:
        dealbreakers.append(
            "role: mobile app development despite a neutral title "
            f"({', '.join(mobile_bd['hits'][:4])})"
        )

    crowdwork, crowdwork_bd = _check_ai_training_crowdwork(text, criteria)
    if crowdwork_bd:
        role_relevance_bd["ai_training_crowdwork_gate"] = crowdwork_bd
    if crowdwork:
        dealbreakers.append(
            "role: AI-training crowdwork, not a software engineering job "
            f"({', '.join(crowdwork_bd['hits'][:3])})"
        )

    language_mismatch, language_bd = _score_language_fit(text, criteria)
    if language_mismatch:
        foreign = language_bd.get("foreign_language_posting_hits") or {}
        reason = (
            ", ".join(language_bd["explicit_requirement_hits"])
            or ("posting appears to be written in " + ", ".join(foreign) if foreign else "")
            or "posting appears to be in German"
        )
        dealbreakers.append(f"language: {reason}")

    employment_dealbreakers = _matches(
        text, profile["employment_type_priority"]["dealbreaker_signals"]
    )
    if employment_dealbreakers:
        dealbreakers.extend(f"employment: {d}" for d in employment_dealbreakers)

    raw_total = (
        rl_points
        + stack_points
        + legacy_points
        + intensity_points
        + comp_points
        + contractor_points
        + reputation_points
        + age_points
        + market_points
        + tech_points
        + title_penalty
        + exporter_penalty
    )
    total = max(0, min(100, round(raw_total)))

    thresholds = criteria["classification_thresholds"]

    # Вакансия, у которой ЕДИНСТВЕННОЕ возражение — страна в структурном поле
    # локации, не отбрасывается молча, а выделяется в свой класс.
    #
    # Почему так, а не "отказ" (пересмотрено 2026-08-05 по прямому возражению
    # владельца). Замер: 501 вакансия с .NET в заголовке отклонена ровно по
    # этой причине и ни по какой другой, и ВСЕ 501 помечены источником как
    # remote. Из тех 78, у кого есть описание, работодатель сам ограничивает
    # право работать лишь в 16 случаях — в остальных 62 отказ выносится по
    # догадке "вакансия в стране N значит для резидентов N".
    #
    # Догадка чаще всего верна, и смешивать эти вакансии с основной выдачей
    # нельзя: их сотни, они утопят десяток настоящих кандидатов. Но и решать
    # за человека, что B2B-контракт с нидерландской компанией ему недоступен,
    # система не вправе — это его решение, а не её. Поэтому отдельный класс и
    # отдельный раздел отчёта.
    country_only = bool(dealbreakers) and all(
        d.startswith("location: source restricts hiring to") for d in dealbreakers
    )
    if country_only:
        classification = "national_market"
    elif dealbreakers:
        classification = "rejected"
    elif complexity_gate:
        classification = "low_priority"
    elif total >= thresholds["hot_lead"]:
        classification = "hot_lead"
    elif total >= thresholds["worth_a_look"]:
        classification = "worth_a_look"
    elif total >= thresholds["long_shot"]:
        classification = "long_shot"
    else:
        classification = "low_priority"

    # Общая неопределённость локации (никакого явного "worldwide"/"US only"/
    # EOR-сигнала) стоит перепроверять руками только для записей, которые и
    # так попали в поле зрения (long_shot и выше) — иначе на реальных данных
    # флаг срабатывает почти всегда и раздел отчёта становится бесполезным.
    if location_unknown and classification in ("hot_lead", "worth_a_look", "long_shot"):
        needs_review = True

    breakdown = {
        "remote_location_fit": rl_bd,
        "stack_fit": stack_bd,
        "role_complexity_signal": complexity_bd,
        "role_relevance_signal": role_relevance_bd,
        "language_requirement_signal": language_bd,
        "legacy_enterprise_signal": legacy_bd,
        "low_intensity_signal": intensity_bd,
        "compensation_signal": comp_bd,
        "contractor_friendliness": contractor_bd,
        "company_reputation_signal": reputation_bd,
        "company_age_signal": age_bd,
        "net_exporter_penalty": exporter_bd,
        "personal_market_bonus": market_bd,
        "personal_tech_bonus": tech_bd,
        "title_role_penalty": title_penalty_bd,
        "raw_total_before_clamp": raw_total,
    }

    return {
        "score": total,
        "score_breakdown": breakdown,
        "classification": classification,
        "dealbreakers": dealbreakers,
        "needs_manual_review": needs_review,
    }
