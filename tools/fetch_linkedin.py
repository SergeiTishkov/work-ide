"""
Фетчер LinkedIn через гостевой эндпоинт поиска вакансий.

ПОЧЕМУ ЭТО ЗАКОННО ДЛЯ ПРОЕКТА
------------------------------
Замер 2026-08-04: `linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search`
отвечает HTTP 200 на обычный GET с честным User-Agent проекта — без
авторизации, без CAPTCHA, без анти-бот блокировки. Это тот же эндпоинт,
которым пользуется гостевой интерфейс самого LinkedIn, когда страницу
открывает незалогиненный человек.

Граница проекта (CLAUDE.md §5): «парсеры того, что отдаётся обычным
GET-запросом — да; обход активной защиты — нет». Здесь первое. Для контраста,
тем же запросом в тот же день: Indeed — 403, Glassdoor — 403. Вот они закрыты
по-настоящему, и туда проект не идёт.

ПОЧЕМУ ЭТО ГЛАВНЫЙ ИСТОЧНИК ПРОЕКТА
-----------------------------------
Один фетчер закрывает все интересующие рынки разом: проверено по Израилю,
ОАЭ, Саудовской Аравии, Сингапуру, Швейцарии, Германии и Нидерландам — везде
200 и реальные вакансии. Страновые борды тех же рынков (Bayt, GulfTalent,
Drushim, NodeFlair) отвечают 403/404, то есть альтернативы им нет.

ЦЕНА РЕШЕНИЯ
------------
Это HTML недокументированной страницы. Вёрстка может измениться в любой день,
и тогда парсер обязан вернуть НОЛЬ записей и ошибку — а не поток мусора,
который тихо отравит базу. Поэтому здесь:
  * каждая запись проходит проверку обязательных полей;
  * если карточки в ответе есть, а разобрать не удалось ни одной — это
    считается сбоем формата и попадает в state.json как ошибка источника;
  * тест на зафиксированном слепке HTML проверяет оба поведения.
"""
from __future__ import annotations

import html
import re
import sys
import time
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote_plus

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOURCE_NAME = "linkedin"
API_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

# f_WT=2 — фильтр «Remote» в терминах LinkedIn.
REMOTE_WORKPLACE_TYPE = "2"

PAGE_SIZE = 25          # столько LinkedIn отдаёт на один запрос
# Сколько карточек за прогон догружать полным описанием. В карточке описания
# нет — только заголовок, компания и локация. Без описания гейт стека отсекает
# три четверти найденного (замер: 447 из 621), потому что не видит ни одного
# знакомого языка. Страница вакансии открывается тем же обычным GET и отдаёт
# полный текст, но это отдельный запрос на каждую вакансию — отсюда потолок.
ENRICH_LIMIT = 120
MAX_PAGES = 4           # 100 вакансий на пару (запрос × страна) — разумный потолок
PAUSE_SECONDS = 1.5     # вежливость: не долбим чужой сервер

_CARD_RE = re.compile(r"<li>(.*?)</li>", re.S)
_TITLE_RE = re.compile(r'base-search-card__title[^>]*>(.*?)</h3>', re.S)
_COMPANY_RE = re.compile(r'base-search-card__subtitle[^>]*>(.*?)</h4>', re.S)
_LOCATION_RE = re.compile(r'job-search-card__location[^>]*>(.*?)</span>', re.S)
_URL_RE = re.compile(r'href="(https://[a-z]{0,3}\.?linkedin\.com/jobs/view/[^"?]+)')
_DATE_RE = re.compile(r'datetime="([\d-]+)"')
_TAG_RE = re.compile(r"<[^>]+>")
_DESCRIPTION_RE = re.compile(r'description__text[^>]*>(.*?)</div>\s*</section>', re.S)
_DESCRIPTION_FALLBACK_RE = re.compile(r'description__text[^>]*>(.*?)</div>', re.S)


def _clean(fragment: Optional[str]) -> str:
    if not fragment:
        return ""
    return html.unescape(_TAG_RE.sub(" ", fragment)).replace(" ", " ").strip()


def _first(pattern, text: str) -> str:
    m = pattern.search(text)
    return _clean(m.group(1)) if m else ""


def _card_to_common_schema(card_html: str, location_query: str) -> Optional[dict]:
    title = _first(_TITLE_RE, card_html)
    company = _first(_COMPANY_RE, card_html)
    url_match = _URL_RE.search(card_html)
    url = url_match.group(1) if url_match else ""

    # Обязательные поля. Их отсутствие означает либо чужую карточку (реклама,
    # блок «похожие компании»), либо изменившуюся вёрстку — в обоих случаях
    # запись брать нельзя.
    if not title or not company or not url:
        return None

    location = _first(_LOCATION_RE, card_html)
    return {
        "source": SOURCE_NAME,
        "external_id": url,
        "title": title,
        "company": company,
        "url": url,
        # Страна запроса сохраняется отдельно: она надёжнее вольного текста
        # в карточке и нужна отчёту, чтобы показать, по какому рынку нашли.
        "location_raw": location or location_query,
        "remote": True,          # запрос всегда идёт с фильтром f_WT=2
        "tags": [f"market:{location_query}"],
        "description_text": "",  # в карточке описания нет, только на странице вакансии
        "posted_at": _first(_DATE_RE, card_html) or None,
        "salary_raw": None,
    }


def _fetch_page(keyword: str, location: str, start: int, timeout: int):
    import requests

    url = (
        f"{API_URL}?keywords={quote_plus(keyword)}&location={quote_plus(location)}"
        f"&f_WT={REMOTE_WORKPLACE_TYPE}&start={start}"
    )
    resp = requests.get(url, headers={"User-Agent": common.USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    return resp.text


_DEV_TITLE_RE = re.compile(
    r"develop|engineer|programm|architect|\.net|dotnet|c#|javascript|typescript|"
    r"backend|back-end|frontend|front-end|full[ -]?stack|software",
    re.IGNORECASE,
)


def _looks_like_dev_role(title: str) -> bool:
    return bool(_DEV_TITLE_RE.search(title or ""))


def _fetch_description(url: str, timeout: int) -> str:
    """Полный текст вакансии со страницы объявления.

    Страница отдаётся анониму обычным GET — так же, как страница поиска.
    Пустая строка означает «не получилось»: это не ошибка прогона, вакансия
    просто останется с оценкой по заголовку.
    """
    import requests

    try:
        resp = requests.get(url, headers={"User-Agent": common.USER_AGENT}, timeout=timeout)
        resp.raise_for_status()
    except Exception:  # noqa: BLE001
        return ""

    match = _DESCRIPTION_RE.search(resp.text) or _DESCRIPTION_FALLBACK_RE.search(resp.text)
    if not match:
        return ""
    return " ".join(_clean(match.group(1)).split())


def fetch(keywords: Optional[List[str]] = None,
          locations: Optional[List[str]] = None,
          max_pages: int = MAX_PAGES,
          enrich_limit: int = ENRICH_LIMIT,
          timeout: int = common.DEFAULT_TIMEOUT):
    """Обходит пары (ключевое слово × страна) и возвращает (записи, заметка).

    keywords/locations приходят из <префикс>_sources.yaml -> params. Локации
    по умолчанию берутся из ярусов рынков активной идентичности, чтобы список
    стран жил в одном месте (см. tools/markets.py).
    """
    import markets

    profile = common.load_profile()
    keywords = keywords or (profile.get("tech_stack", {}).get("core") or [])[:3]
    locations = locations or markets.target_locations(profile)

    if not keywords or not locations:
        return [], "нечего запрашивать: пустой список ключевых слов или стран"

    records: List[dict] = []
    seen_urls = set()
    cards_seen = 0
    errors: List[str] = []

    for keyword in keywords:
        for location in locations:
            for page in range(max_pages):
                try:
                    page_html = _fetch_page(keyword, location, page * PAGE_SIZE, timeout)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{keyword}/{location}: {type(exc).__name__}")
                    break

                cards = _CARD_RE.findall(page_html)
                if not cards:
                    break
                cards_seen += len(cards)

                added_here = 0
                for card in cards:
                    rec = _card_to_common_schema(card, location)
                    if rec is None or rec["url"] in seen_urls:
                        continue
                    seen_urls.add(rec["url"])
                    records.append(rec)
                    added_here += 1

                time.sleep(PAUSE_SECONDS)
                if len(cards) < PAGE_SIZE:
                    break

    # Ключевая защита от смены вёрстки: карточки пришли, но ни одна не
    # разобралась. Молча вернуть пусто нельзя — это выглядело бы как «на рынке
    # ничего нет», хотя на деле сломался парсер.
    if cards_seen and not records:
        return [], (
            f"формат страницы изменился: получено {cards_seen} карточек, "
            "не удалось разобрать ни одной"
        )

    # Догрузка описаний. Порядок важен: сначала те, чей заголовок вообще
    # похож на разработку — если лимит закончится, он закончится на менее
    # интересных записях, а не на первой попавшейся.
    enriched = 0
    if enrich_limit:
        records.sort(key=lambda r: 0 if _looks_like_dev_role(r["title"]) else 1)
        for rec in records[:enrich_limit]:
            description = _fetch_description(rec["url"], timeout)
            if description:
                rec["description_text"] = description
                enriched += 1
            time.sleep(PAUSE_SECONDS)

    note_parts = [f"карточек {cards_seen}, записей {len(records)}, с описанием {enriched}"]
    if errors:
        note_parts.append("ошибки: " + "; ".join(errors[:3]))
    return records, "; ".join(note_parts)


def main() -> None:
    import argparse
    import identity as identity_mod

    parser = argparse.ArgumentParser(description="Сбор вакансий с LinkedIn (гостевой поиск)")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--keyword", action="append", help="Ключевое слово (можно несколько)")
    parser.add_argument("--location", action="append", help="Страна (можно несколько)")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES)
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)

    records, note = fetch(args.keyword, args.location, args.max_pages)
    print(f"{SOURCE_NAME}: {len(records)} записей ({note})")
    for r in records[:10]:
        # Названия компаний бывают с символами, которых нет в кодировке
        # консоли Windows. Падать на печати из-за этого — глупо: данные
        # собраны, ломается только вывод.
        line = f"  - {r['title']} @ {r['company']} [{r['location_raw']}]"
        print(line.encode(sys.stdout.encoding or "utf-8", "replace")
                  .decode(sys.stdout.encoding or "utf-8", "replace"))


if __name__ == "__main__":
    main()
