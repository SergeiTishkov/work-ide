"""
Фетчер источника We Work Remotely — категория "Remote Programming Jobs" RSS.

RSS без ключа, парсится стандартной библиотекой xml.etree.ElementTree (без
feedparser, чтобы не тянуть лишнюю зависимость). WWR отдаёт полезное поле
"region" (например, "Anywhere in the World" / "USA Only") — это прямой,
надёжный сигнал для remote_location_fit, гораздо точнее, чем keyword-угадывание
по описанию, поэтому сохраняем его отдельно.
"""
from __future__ import annotations

import re
import sys
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOURCE_NAME = "weworkremotely"

# Замер 2026-07-30: одна только категория remote-programming-jobs даёт 25
# вакансий, тогда как все пять вместе — ~277 (и в 10 раз больше
# .NET-релевантных). Раньше использовалась только первая — это была главная
# причина скудного выхода пайплайна.
FEED_URLS = [
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-front-end-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
]
FEED_URL = FEED_URLS[0]  # обратная совместимость для существующих вызовов

# Namespace, который WWR подмешивает в некоторые элементы (content:encoded и т.п.)
_NS = {"content": "http://purl.org/rss/1.0/modules/content/"}


def fetch(urls=None, timeout: int = common.DEFAULT_TIMEOUT):
    """Обходит ВСЕ категорийные фиды WWR и объединяет результат, дедуплицируя
    по ссылке (одна вакансия часто публикуется сразу в нескольких
    категориях — например, и в full-stack, и в back-end)."""
    import requests

    if urls is None:
        urls = FEED_URLS
    elif isinstance(urls, str):
        urls = [urls]

    records = []
    seen_ids = set()
    skipped = 0
    errors = []
    total_items = 0

    for url in urls:
        try:
            resp = requests.get(
                url, headers={"User-Agent": common.USER_AGENT}, timeout=timeout
            )
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except Exception as exc:  # noqa: BLE001 - один упавший фид не должен ронять остальные
            errors.append(f"{url.rsplit('/', 1)[-1]}: {type(exc).__name__}")
            continue

        items = root.findall("./channel/item")
        total_items += len(items)
        for item in items:
            rec = _to_common_schema(item)
            if rec is None:
                skipped += 1
                continue
            if rec["external_id"] in seen_ids:
                continue  # та же вакансия из другой категории
            seen_ids.add(rec["external_id"])
            records.append(rec)

    error_parts = []
    if skipped:
        error_parts.append(f"skipped {skipped}/{total_items} malformed items (non-fatal)")
    if errors:
        error_parts.append("feed errors: " + "; ".join(errors))
    error = " | ".join(error_parts) if error_parts else None
    return records, error


def _text(item, tag: str) -> str:
    el = item.find(tag)
    return (el.text or "").strip() if el is not None and el.text else ""


_COMPANY_URL_RE = re.compile(r"URL:\s*(https?://[^\s<>\"')]+)", re.IGNORECASE)


def _extract_company_url(description_html: str) -> Optional[str]:
    """Достаёт официальный сайт компании из структурного блока WWR
    ("Headquarters: ... / URL: ...").

    Зачем: WWR держит воронку отклика у себя — поле "To apply:" в
    большинстве вакансий ведёт обратно на weworkremotely.com, а не на
    работодателя (проверено 2026-07-30: 71% вакансий именно так). Сайт
    компании позволяет найти ту же вакансию на её карьерной странице и
    откликнуться напрямую, без аккаунта на WWR."""
    if not description_html:
        return None
    # Ищем в ОЧИЩЕННОМ тексте: в сыром HTML ссылка обёрнута в <a href=...>,
    # и "URL:" отделено от неё разметкой.
    m = _COMPANY_URL_RE.search(common.strip_html(description_html))
    if not m:
        return None
    url = m.group(1).rstrip(".,;)")
    if "weworkremotely" in url.lower():
        return None
    return url


def _to_common_schema(item) -> Optional[dict]:
    title_raw = _text(item, "title")
    link = _text(item, "link") or _text(item, "guid")
    if not title_raw or not link:
        return None

    # WWR обычно кодирует заголовок как "Company: Job Title"
    company, sep, title = title_raw.partition(":")
    if not sep:
        company, title = "", title_raw
    company = company.strip() or "Unknown"
    title = title.strip() or title_raw

    region = _text(item, "region")
    category = _text(item, "category")
    pub_date_raw = _text(item, "pubDate")
    posted_at_epoch = None
    if pub_date_raw:
        try:
            posted_at_epoch = int(parsedate_to_datetime(pub_date_raw).timestamp())
        except Exception:  # noqa: BLE001 - дата не критична для работы пайплайна
            posted_at_epoch = None

    remote = None
    if region:
        remote = "only" not in region.lower() or "anywhere" in region.lower()

    description_html = _text(item, "description")

    return {
        "source": SOURCE_NAME,
        "external_id": link,
        "title": title,
        "company": company,
        "url": link,
        "company_url": _extract_company_url(description_html),
        "location_raw": region,
        "remote": remote,
        "tags": [t for t in [category] if t],
        "description_html": description_html,
        "posted_at_epoch": posted_at_epoch,
        "salary_raw": None,
    }


if __name__ == "__main__":
    import identity as identity_mod

    identity_mod.standalone_main(fetch, SOURCE_NAME)
