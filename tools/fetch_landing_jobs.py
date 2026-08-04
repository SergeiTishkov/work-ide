"""
Фетчер Landing.jobs — европейский борд (база в Португалии).

Публичный JSON без ключа (замер 2026-08-04: HTTP 200). Ценность в
структурных полях, которых нет у большинства источников: явный флаг `remote`,
вилка `gross_salary_low/high` и признак `relocation_paid` — по последнему
сразу видно, ждёт ли компания переезда, а не удалённой работы.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOURCE_NAME = "landing_jobs"
API_URL = "https://landing.jobs/api/v1/jobs?limit=100"


def _format_salary(item: dict) -> Optional[str]:
    lo, hi = item.get("gross_salary_low"), item.get("gross_salary_high")
    if not lo and not hi:
        return None
    currency = (item.get("currency_code") or "EUR").upper()
    symbol = {"EUR": "€", "USD": "$", "GBP": "£"}.get(currency, f"{currency} ")
    if lo and hi:
        return f"{symbol}{int(lo):,}-{symbol}{int(hi):,}/year"
    return f"{symbol}{int(lo or hi):,}/year"


def _to_common_schema(item: dict) -> Optional[dict]:
    if not isinstance(item, dict):
        return None
    title = str(item.get("title") or "").strip()
    company = str((item.get("company") or {}).get("name")
                  if isinstance(item.get("company"), dict)
                  else item.get("company") or "").strip()
    url = str(item.get("url") or "").strip()
    if not title or not url:
        return None
    if not company:
        # Часть вакансий публикуется анонимно. Компанию можно достать из
        # ссылки: landing.jobs/at/<company>/<vacancy-slug>.
        parts = [p for p in url.split("/") if p]
        company = parts[parts.index("at") + 1] if "at" in parts else ""
    if not company:
        return None

    locations = item.get("locations") or []
    if isinstance(locations, list):
        location = ", ".join(str(x) for x in locations if x)
    else:
        location = str(locations)

    tags = [str(t) for t in (item.get("main_requirements") or [])[:6] if t]
    if item.get("relocation_paid"):
        tags.append("relocation_paid")

    return {
        "source": SOURCE_NAME,
        "external_id": str(item.get("id") or url),
        "title": title,
        "company": company,
        "url": url,
        "location_raw": location or "Europe",
        "remote": bool(item.get("remote")),
        "tags": tags,
        "description_text": common.strip_html(str(item.get("role_description") or "")),
        "posted_at": item.get("published_at") or item.get("created_at"),
        "salary_raw": _format_salary(item),
    }


def fetch(url: str = API_URL, timeout: int = common.DEFAULT_TIMEOUT):
    import requests

    try:
        resp = requests.get(url, headers={"User-Agent": common.USER_AGENT}, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        return [], f"{type(exc).__name__}: {exc}"

    items = payload if isinstance(payload, list) else payload.get("jobs")
    if not isinstance(items, list):
        return [], "ожидался список вакансий"

    records, skipped = [], 0
    for item in items:
        rec = _to_common_schema(item)
        if rec is None:
            skipped += 1
            continue
        records.append(rec)
    return records, (f"пропущено {skipped} некорректных" if skipped else None)


def main() -> None:
    import argparse
    import identity as identity_mod

    parser = argparse.ArgumentParser(description="Сбор вакансий с Landing.jobs")
    identity_mod.add_identity_arg(parser)
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)
    records, note = fetch()
    print(f"{SOURCE_NAME}: {len(records)} записей ({note or 'без замечаний'})")


if __name__ == "__main__":
    main()
