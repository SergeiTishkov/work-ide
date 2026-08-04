"""
Фетчер источника Remotive (https://remotive.com/api/remote-jobs).

Публичный JSON API, без ключа, только удалённые вакансии (remote_only).

Ценность источника: поле `candidate_required_location` — явное, структурное
гео-ограничение ("Worldwide", "USA Only", "Europe", ...), надёжнее, чем
угадывание по тексту описания. Прокидываем его в location_raw как есть,
чтобы score.py применил свою обычную логику restrictive_region_signal.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOURCE_NAME = "remotive"
API_URL = "https://remotive.com/api/remote-jobs?limit=200"


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


def _to_common_schema(item: dict) -> Optional[dict]:
    if not isinstance(item, dict):
        return None
    title = (item.get("title") or "").strip()
    company = (item.get("company_name") or "").strip()
    url = (item.get("url") or "").strip()
    if not title or not company or not url:
        return None

    tags = list(item.get("tags") or [])
    for extra in (item.get("category"), item.get("job_type")):
        if extra:
            tags.append(str(extra))

    return {
        "source": SOURCE_NAME,
        "external_id": str(item.get("id") or url),
        "title": title,
        "company": company,
        "url": url,
        # Структурное гео-ограничение площадки — важнее и надёжнее текста.
        "location_raw": (item.get("candidate_required_location") or "").strip(),
        "remote": True,  # Remotive — remote-only площадка по определению
        "tags": tags,
        "description_html": item.get("description") or "",
        "posted_at": item.get("publication_date"),
        "salary_raw": (item.get("salary") or "").strip() or None,
    }


if __name__ == "__main__":
    import identity as identity_mod

    identity_mod.standalone_main(fetch, SOURCE_NAME)
