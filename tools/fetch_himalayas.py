"""
Фетчер источника Himalayas (https://himalayas.app/jobs/api).

Публичный JSON API, без ключа, только удалённые вакансии (remote_only).
Отдаёт ~20 вакансий за вызов независимо от параметра limit — мало, но
бесплатно и без ключа.

Ценность источника: `locationRestrictions` — явный, структурный список
разрешённых стран (пустой = worldwide), плюс структурированная зарплата.
Это самый надёжный гео-сигнал среди всех источников проекта: не нужно
угадывать по фразам в тексте.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOURCE_NAME = "himalayas"
API_URL = "https://himalayas.app/jobs/api?limit=100"


def fetch(url: str = API_URL, timeout: int = common.DEFAULT_TIMEOUT):
    import requests

    try:
        resp = requests.get(
            url, headers={"User-Agent": common.USER_AGENT}, timeout=timeout
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        return [], f"{type(exc).__name__}: {exc}"

    raw_items = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(raw_items, list):
        return [], "unexpected payload shape: 'jobs' list missing"

    records = []
    skipped = 0
    for item in raw_items:
        rec = _to_common_schema(item)
        if rec is None:
            skipped += 1
            continue
        records.append(rec)

    error = f"skipped {skipped}/{len(raw_items)} malformed records (non-fatal)" if skipped else None
    return records, error


def _format_salary(item: dict) -> Optional[str]:
    lo, hi = item.get("minSalary"), item.get("maxSalary")
    if not lo and not hi:
        return None
    currency = item.get("currency") or "USD"
    period = (item.get("salaryPeriod") or "annual").lower()
    unit = {"annual": "year", "yearly": "year", "monthly": "month", "hourly": "hour"}.get(period, period)
    symbol = "$" if currency.upper() == "USD" else f"{currency} "
    if lo and hi:
        return f"{symbol}{int(lo):,}-{symbol}{int(hi):,}/{unit}"
    value = lo or hi
    return f"{symbol}{int(value):,}/{unit}"


def _format_location(item: dict) -> str:
    """locationRestrictions — список разрешённых стран. Пустой список
    означает "без ограничений" (worldwide). Приводим к фразам, которые
    понимает score.py: явное "only" для ограниченных, "Worldwide" для
    свободных — так структурный сигнал площадки корректно превращается в
    dealbreaker там, где нужно."""
    restrictions = item.get("locationRestrictions")
    if not restrictions:
        return "Worldwide"
    if isinstance(restrictions, str):
        restrictions = [restrictions]
    names = [str(r).strip() for r in restrictions if str(r).strip()]
    if not names:
        return "Worldwide"
    return ", ".join(names) + " only"


def _extract_company(item: dict) -> str:
    """Имя компании из записи Himalayas, в каком бы виде оно ни пришло.

    Площадка меняла форму этого поля: раньше `companyName`, сейчас `company`
    строкой, а когда-то — вложенным объектом `{"name": ...}`. Реальный случай
    2026-08-04: парсер читал только `companyName`, поле стало приходить пустым,
    и ВСЕ 60 записей источника молча отбрасывались как «без компании». Отказ
    был совершенно тихим: источник числился рабочим и отдавал HTTP 200.

    Отсюда правило: у внешнего API не бывает «того самого» имени поля.
    Перебираем известные формы и берём первую непустую.
    """
    value = item.get("companyName") or item.get("company") or item.get("organization")
    if isinstance(value, dict):
        value = value.get("name") or value.get("title") or ""
    return str(value or "").strip()


def _to_common_schema(item: dict) -> Optional[dict]:
    if not isinstance(item, dict):
        return None
    title = (item.get("title") or "").strip()
    company = _extract_company(item)
    url = (item.get("applicationLink") or item.get("guid") or "").strip()
    if not title or not company or not url:
        return None

    tags = []
    for key in ("categories", "parentCategories", "seniority"):
        value = item.get(key)
        if isinstance(value, list):
            tags.extend(str(v) for v in value)
        elif value:
            tags.append(str(value))
    if item.get("employmentType"):
        tags.append(str(item["employmentType"]))

    return {
        "source": SOURCE_NAME,
        "external_id": str(item.get("guid") or url),
        "title": title,
        "company": company,
        "url": url,
        "location_raw": _format_location(item),
        "remote": True,  # Himalayas — remote-only площадка по определению
        "tags": tags,
        "description_html": item.get("description") or item.get("excerpt") or "",
        "posted_at_epoch": item.get("pubDate"),
        "salary_raw": _format_salary(item),
    }


if __name__ == "__main__":
    import identity as identity_mod

    identity_mod.standalone_main(fetch, SOURCE_NAME)
