"""
Фетчер 4dayweek.io — площадка про сокращённую занятость.

ПОЧЕМУ ЭТОТ ИСТОЧНИК ОСОБЕННЫЙ
------------------------------
Все остальные источники проекта ищут по СТЕКУ, а спокойствие вычисляется потом,
из текста описания. Замер 2026-08-05 показал, чем это плохо: из 10 215 вакансий
в базе все гейты проходили 27, и лишь у 8 нашёлся хоть какой-то признак низкой
нагрузки. Слово "part-time" встретилось во всей базе один раз.

Спокойная неполная занятость — не подмножество обычных вакансий, а отдельный
рынок. Здесь он представлен целиком, причём СТРУКТУРНЫМ полем `schedule_type`:
4_day_week, 4_day_week_pro_rata, 9_day_fortnight, compressed_week,
half_day_fridays, flexible_hours. Это надёжнее любого угадывания по тексту —
площадка сама сортирует работодателей по режиму работы.

Замер: 23 182 вакансии всего, в выборке из 100 около 21% — engineering.

ЧТО ЭТО ЗНАЧИТ ДЛЯ СКОРИНГА
--------------------------
Режим работы кладётся в теги (`schedule:4_day_week`), и его подхватывает
low_intensity_signal идентичности. То есть источник не просто приносит
вакансии, а приносит их с уже доказанным признаком низкой нагрузки.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOURCE_NAME = "4dayweek"
API_URL = "https://4dayweek.io/api/jobs"
JOB_URL = "https://4dayweek.io/remote-job/{slug}"

DEFAULT_CATEGORIES = ["engineering"]
PAGE_SIZE = 100
MAX_PAGES = 6
PAUSE_SECONDS = 0.5

# Значения schedule_type, которые площадка отдаёт в чистом виде. Переводим в
# человеческий текст, чтобы они читались и в теге, и в отчёте.
SCHEDULE_LABELS = {
    "4_day_week": "4-day week",
    "4_day_week_pro_rata": "4-day week (pro rata)",
    "9_day_fortnight": "9-day fortnight",
    "compressed_week": "compressed week",
    "rotating_4_day": "rotating 4-day week",
    "half_day_fridays": "half-day Fridays",
    "flexible_hours": "flexible hours",
    "generous_pto": "generous PTO",
}


def _format_salary(item: dict) -> Optional[str]:
    """Готовая строка от площадки надёжнее пересчёта.

    Числовые поля salary_lower/upper приходят в сотых долях единицы
    ($162k выглядит как 16250866), и восстанавливать из них сумму — лишний
    риск ошибиться на два порядка в самом важном для решения поле.
    """
    text = str(item.get("salary") or "").strip()
    if not text:
        return None
    period = str(item.get("salary_period") or "year")
    return f"{text}/{period}"


def _format_location(item: dict) -> str:
    places = item.get("locations") or []
    names = []
    for place in places:
        if not isinstance(place, dict):
            continue
        name = place.get("country") or place.get("continent")
        if name and name not in names:
            names.append(str(name))
    if not names:
        return "Worldwide" if item.get("work_arrangement") == "remote" else ""
    return ", ".join(names[:3])


def _to_common_schema(item: dict) -> Optional[dict]:
    if not isinstance(item, dict):
        return None

    title = str(item.get("title") or "").strip()
    company = str(item.get("company_name") or "").strip()
    slug = str(item.get("slug") or "").strip()
    if not title or not company or not slug:
        return None
    if item.get("is_expired"):
        return None

    schedule = str(item.get("schedule_type") or "").strip()
    tags: List[str] = []
    if schedule:
        # И машиночитаемый вид, и человеческий: первый переживёт смену
        # словаря на стороне площадки, второй читается в отчёте.
        tags.append(f"schedule:{schedule}")
        label = SCHEDULE_LABELS.get(schedule)
        if label:
            tags.append(label)
    for key in ("category", "level", "work_arrangement"):
        value = item.get(key)
        if value:
            tags.append(str(value))

    return {
        "source": SOURCE_NAME,
        "external_id": str(item.get("id") or slug),
        "title": title,
        "company": company,
        "url": JOB_URL.format(slug=slug),
        "location_raw": _format_location(item),
        "remote": item.get("work_arrangement") == "remote",
        "tags": tags,
        # Описания в списочном ответе нет. Режим работы — главное, что нужно
        # от этого источника, и он приходит структурным полем.
        "description_text": "",
        "posted_at": item.get("posted"),
        "salary_raw": _format_salary(item),
    }


def fetch(categories: Optional[List[str]] = None,
          pages: int = MAX_PAGES,
          timeout: int = common.DEFAULT_TIMEOUT):
    import requests

    categories = categories or DEFAULT_CATEGORIES
    records: List[dict] = []
    seen = set()
    skipped = 0
    errors: List[str] = []

    for category in categories:
        for page in range(1, pages + 1):
            url = f"{API_URL}?limit={PAGE_SIZE}&page={page}&category={category}"
            try:
                resp = requests.get(url, headers={"User-Agent": common.USER_AGENT}, timeout=timeout)
                resp.raise_for_status()
                payload = resp.json()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{category} стр.{page}: {type(exc).__name__}")
                break

            items = payload.get("jobs") if isinstance(payload, dict) else None
            if not isinstance(items, list):
                errors.append(f"{category}: в ответе нет списка jobs")
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

            time.sleep(PAUSE_SECONDS)
            if not payload.get("has_more"):
                break

    note = []
    if skipped:
        note.append(f"пропущено {skipped} (истёкшие или неполные)")
    if errors:
        note.append("; ".join(errors[:3]))
    return records, ("; ".join(note) or None)


def main() -> None:
    import argparse
    import identity as identity_mod

    parser = argparse.ArgumentParser(description="Сбор вакансий с 4dayweek.io")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--category", action="append")
    parser.add_argument("--pages", type=int, default=MAX_PAGES)
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)

    records, note = fetch(args.category, args.pages)
    print(f"{SOURCE_NAME}: {len(records)} записей ({note or 'без замечаний'})")
    for r in records[:8]:
        line = f"  - {r['title']} @ {r['company']} [{', '.join(r['tags'][:2])}] {r['salary_raw'] or ''}"
        print(line.encode(sys.stdout.encoding or "utf-8", "replace")
                  .decode(sys.stdout.encoding or "utf-8", "replace"))


if __name__ == "__main__":
    main()
