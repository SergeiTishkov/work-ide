"""
Фетчер источника Jobicy (https://jobicy.com/api/v2/remote-jobs).

Публичный JSON API, без ключа, только удалённые вакансии (remote_only).
Фильтр industry=dev даёт максимальную долю разработки (замер 2026-07-30:
100 вакансий против 100 общих с заметно меньшей долей IT). Параметр tag=
на практике возвращает пустой результат — не использовать.

Ценность источника: структурированная зарплата (salaryMin/Max/Currency/
Period) и структурное гео-ограничение (jobGeo) — надёжнее парсинга текста.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOURCE_NAME = "jobicy"
API_URL = "https://jobicy.com/api/v2/remote-jobs?count=100&industry=dev"


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
    lo, hi = item.get("salaryMin"), item.get("salaryMax")
    if not lo and not hi:
        return None
    currency = item.get("salaryCurrency") or "USD"
    period = (item.get("salaryPeriod") or "yearly").lower()
    unit = {"yearly": "year", "annual": "year", "monthly": "month", "hourly": "hour"}.get(period, period)
    symbol = "$" if currency.upper() == "USD" else f"{currency} "
    if lo and hi:
        return f"{symbol}{int(lo):,}-{symbol}{int(hi):,}/{unit}"
    value = lo or hi
    return f"{symbol}{int(value):,}/{unit}"


def _to_common_schema(item: dict) -> Optional[dict]:
    if not isinstance(item, dict):
        return None
    title = (item.get("jobTitle") or "").strip()
    company = (item.get("companyName") or "").strip()
    url = (item.get("url") or "").strip()
    if not title or not company or not url:
        return None

    tags = []
    for key in ("jobIndustry", "jobType"):
        value = item.get(key)
        if isinstance(value, list):
            tags.extend(str(v) for v in value)
        elif value:
            tags.append(str(value))
    if item.get("jobLevel"):
        tags.append(str(item["jobLevel"]))

    # jobDescription — полный HTML; jobExcerpt — короткая выжимка. Берём
    # полное описание, оно нужно и для скоринга, и для ручного чек-листа.
    description = item.get("jobDescription") or item.get("jobExcerpt") or ""

    return {
        "source": SOURCE_NAME,
        "external_id": str(item.get("id") or url),
        "title": title,
        "company": company,
        "url": url,
        "location_raw": (item.get("jobGeo") or "").strip(),
        "remote": True,  # Jobicy — remote-only площадка по определению
        "tags": tags,
        "description_html": description,
        "posted_at": item.get("pubDate"),
        "salary_raw": _format_salary(item),
    }


if __name__ == "__main__":
    import identity as identity_mod

    identity_mod.standalone_main(fetch, SOURCE_NAME)
