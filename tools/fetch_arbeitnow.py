"""
Фетчер источника Arbeitnow (https://www.arbeitnow.com/api/job-board-api).

Публичный JSON API, без ключа. Основной источник — структура стабильная и
чистая (title, company_name, description, remote, url, tags, job_types,
location, created_at).

Функция fetch() никогда не бросает исключение наружу в normal flow пайплайна:
сетевые/форматные ошибки возвращаются как (records, error) чтобы pipeline.py
мог залогировать проблему в state.json и продолжить работу с другими
источниками.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOURCE_NAME = "arbeitnow"
API_URL = "https://www.arbeitnow.com/api/job-board-api"


def fetch(url: str = API_URL, timeout: int = common.DEFAULT_TIMEOUT):
    """Возвращает (records: list[dict], error: Optional[str]).

    Каждый record — "сырой нормализованный" словарь в общем промежуточном
    формате, который затем достраивает tools/normalize.py.
    """
    import requests

    try:
        resp = requests.get(
            url, headers={"User-Agent": common.USER_AGENT}, timeout=timeout
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001 - defensively swallow, source may be down
        return [], f"{type(exc).__name__}: {exc}"

    raw_items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(raw_items, list):
        return [], "unexpected payload shape: 'data' list missing"

    records = []
    skipped = 0
    for item in raw_items:
        rec = _to_common_schema(item)
        if rec is None:
            skipped += 1
            continue
        records.append(rec)

    error = None
    if skipped:
        error = f"skipped {skipped}/{len(raw_items)} malformed records (non-fatal)"
    return records, error


def _to_common_schema(item: dict) -> Optional[dict]:
    if not isinstance(item, dict):
        return None
    title = (item.get("title") or "").strip()
    company = (item.get("company_name") or "").strip()
    url = (item.get("url") or "").strip()
    if not title or not company or not url:
        return None  # без этих трёх полей запись бесполезна для отчёта

    return {
        "source": SOURCE_NAME,
        "external_id": item.get("slug") or url,
        "title": title,
        "company": company,
        "url": url,
        "location_raw": item.get("location") or "",
        "remote": bool(item.get("remote")) if item.get("remote") is not None else None,
        "tags": list(item.get("tags") or []) + list(item.get("job_types") or []),
        "description_html": item.get("description") or "",
        "posted_at_epoch": item.get("created_at"),
        "salary_raw": None,  # arbeitnow редко указывает зарплату отдельным полем
    }


if __name__ == "__main__":
    import identity as identity_mod

    identity_mod.standalone_main(fetch, SOURCE_NAME)
