"""
Фетчер Devitjobs — IT-вакансии Великобритании и США.

Один модуль на две площадки: devitjobs.uk и devitjobs.com отличаются только
доменом, формат ответа у них общий. Заводить два почти одинаковых файла ради
разного хоста — лишний повод для расхождения.

Замер 2026-08-04: UK отдаёт 2449 записей одним вызовом, US — 1590. Это
крупнейший по объёму источник проекта. Формат «lightweight»: без текста
описания, зато со структурными полями — вилка зарплаты (annualSalaryFrom/To),
уровень (expLevel), тип компании и признак удалёнки.

ВАЖНОЕ ОГРАНИЧЕНИЕ: описания в ответе нет. Гейты, читающие текст вакансии
(язык, отрасль, инфраструктурная роль), по этим записям работают вслепую и
опираются только на заголовок и теги. Поэтому ручной чек-лист по кандидатам
отсюда особенно важен.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOURCE_NAME = "devitjobs"

BOARDS = {
    "uk": "https://devitjobs.uk/api/jobsLight",
    "us": "https://devitjobs.com/api/jobsLight",
}


def _format_salary(item: dict) -> Optional[str]:
    lo, hi = item.get("annualSalaryFrom"), item.get("annualSalaryTo")
    if not lo and not hi:
        return None
    currency = (item.get("currency") or "").strip()
    symbol = {"GBP": "£", "USD": "$", "EUR": "€"}.get(currency.upper(), f"{currency} " if currency else "$")
    if lo and hi:
        return f"{symbol}{int(lo):,}-{symbol}{int(hi):,}/year"
    return f"{symbol}{int(lo or hi):,}/year"


def _to_common_schema(item: dict, board: str) -> Optional[dict]:
    if not isinstance(item, dict):
        return None

    # Площадка называет заголовок `name`, а не `title`.
    title = str(item.get("name") or item.get("title") or "").strip()
    company = str(item.get("company") or "").strip()
    slug = str(item.get("url") or item.get("_id") or "").strip()
    if not title or not company or not slug:
        return None

    host = "devitjobs.uk" if board == "uk" else "devitjobs.com"
    url = slug if slug.startswith("http") else f"https://{host}/jobs/{slug}"

    tags: List[str] = [f"board:{board}"]
    for key in ("expLevel", "companyType", "cityCategory", "jobType"):
        value = item.get(key)
        if isinstance(value, list):
            tags.extend(str(v) for v in value if v)
        elif value:
            tags.append(str(value))

    location = str(item.get("actualCity") or item.get("address") or "").strip()
    # Площадка помечает удалёнку категорией города, а не отдельным флагом.
    is_remote = "remote" in " ".join(tags).lower() or "remote" in location.lower()

    return {
        "source": SOURCE_NAME,
        "external_id": f"{board}:{item.get('_id') or url}",
        "title": title,
        "company": company,
        "url": url,
        "location_raw": location or ("United Kingdom" if board == "uk" else "United States"),
        "remote": is_remote,
        "tags": tags,
        "description_text": str(item.get("description") or "").strip(),
        "posted_at": item.get("activeFrom"),
        "salary_raw": _format_salary(item),
    }


def fetch(boards: Optional[List[str]] = None, timeout: int = common.DEFAULT_TIMEOUT):
    import requests

    boards = boards or ["uk"]
    records: List[dict] = []
    skipped = 0
    errors: List[str] = []

    for board in boards:
        url = BOARDS.get(board)
        if not url:
            errors.append(f"неизвестная доска '{board}'")
            continue
        try:
            resp = requests.get(url, headers={"User-Agent": common.USER_AGENT}, timeout=timeout)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{board}: {type(exc).__name__}")
            continue

        if not isinstance(payload, list):
            errors.append(f"{board}: ожидался список, пришло {type(payload).__name__}")
            continue

        for item in payload:
            rec = _to_common_schema(item, board)
            if rec is None:
                skipped += 1
                continue
            records.append(rec)

    note_parts = []
    if skipped:
        note_parts.append(f"пропущено {skipped} некорректных записей")
    if errors:
        note_parts.append("; ".join(errors))
    return records, ("; ".join(note_parts) or None)


def main() -> None:
    import argparse
    import identity as identity_mod

    parser = argparse.ArgumentParser(description="Сбор вакансий с Devitjobs (UK/US)")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--board", action="append", choices=sorted(BOARDS), default=None)
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)

    records, note = fetch(args.board)
    print(f"{SOURCE_NAME}: {len(records)} записей ({note or 'без замечаний'})")


if __name__ == "__main__":
    main()
