"""
Фетчер jobs.ch — главный швейцарский джоб-борд.

Почему именно Швейцария заслуживает отдельного источника: для контрактора из
третьей страны она реалистичнее США. Ставки одни из самых высоких в мире, а
практика найма зарубежных подрядчиков распространена шире, чем в Штатах, где
большинство удалённых вакансий требуют резидентства.

Публичный поисковый API их сайта: обычный GET, без ключа и авторизации
(замер 2026-08-04 — HTTP 200).

Оговорка: борд национальный, и подавляющее большинство вакансий там локальные
и на немецком. Языковой фильтр и гейт удалёнки отсекут почти всё — но
оставшееся ценно, потому что других источников по Швейцарии у проекта нет.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote_plus

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOURCE_NAME = "jobs_ch"
API_URL = "https://www.jobs.ch/api/v1/public/search"
DEFAULT_QUERIES = ["software engineer", "backend developer", ".NET"]
# Площадка отдаёт ровно 20 записей на страницу и игнорирует параметр rows;
# объём набирается пагинацией (замер 2026-08-04: num_pages=33 по «developer»).
PAGES_PER_QUERY = 5


def _to_common_schema(item: dict) -> Optional[dict]:
    if not isinstance(item, dict):
        return None

    title = str(item.get("title") or "").strip()
    company = str(item.get("company_name") or "").strip()
    slug = str(item.get("slug") or item.get("job_id") or "").strip()
    if not title or not company or not slug:
        return None

    url = slug if str(slug).startswith("http") else f"https://www.jobs.ch/en/vacancies/detail/{slug}/"

    places = item.get("place") or item.get("location") or ""
    if isinstance(places, list):
        places = ", ".join(str(p) for p in places if p)
    location = str(places).strip() or "Switzerland"

    tags: List[str] = ["market:Switzerland"]
    for key in ("employment_position_ids", "categories", "employment_grades"):
        value = item.get(key)
        if isinstance(value, list):
            tags.extend(str(v) for v in value[:4] if v)

    return {
        "source": SOURCE_NAME,
        "external_id": str(item.get("job_id") or url),
        "title": title,
        "company": company,
        "url": url,
        "location_raw": location,
        # Борд национальный: удалёнку определяем по тексту, а не по умолчанию.
        "remote": None,
        "tags": tags,
        "description_text": common.strip_html(str(item.get("description") or "")),
        "posted_at": item.get("publication_date") or item.get("published"),
        "salary_raw": None,
    }


def fetch(queries: Optional[List[str]] = None,
          pages: int = PAGES_PER_QUERY,
          timeout: int = common.DEFAULT_TIMEOUT):
    import requests

    queries = queries or DEFAULT_QUERIES
    records: List[dict] = []
    seen = set()
    skipped = 0
    errors: List[str] = []

    for query in queries:
        for page in range(1, pages + 1):
            url = f"{API_URL}?query={quote_plus(query)}&page={page}"
            try:
                resp = requests.get(url, headers={"User-Agent": common.USER_AGENT}, timeout=timeout)
                resp.raise_for_status()
                payload = resp.json()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{query} стр.{page}: {type(exc).__name__}")
                break

            items = payload.get("documents") if isinstance(payload, dict) else None
            if not isinstance(items, list):
                errors.append(f"{query}: в ответе нет списка documents")
                break
            if not items:
                break

            for item in items:
                rec = _to_common_schema(item)
                if rec is None:
                    skipped += 1
                    continue
                if rec["external_id"] in seen:
                    continue
                seen.add(rec["external_id"])
                records.append(rec)

    note = []
    if skipped:
        note.append(f"пропущено {skipped} некорректных")
    if errors:
        note.append("; ".join(errors[:3]))
    return records, ("; ".join(note) or None)


def main() -> None:
    import argparse
    import identity as identity_mod

    parser = argparse.ArgumentParser(description="Сбор вакансий с jobs.ch (Швейцария)")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--query", action="append")
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)

    records, note = fetch(args.query)
    print(f"{SOURCE_NAME}: {len(records)} записей ({note or 'без замечаний'})")


if __name__ == "__main__":
    main()
