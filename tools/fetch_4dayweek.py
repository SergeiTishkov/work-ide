"""
Fetcher for 4dayweek.io — a board about reduced working hours.

WHY THIS SOURCE IS DIFFERENT
------------------------------
Every other source in the project searches by STACK, and calmness is computed
afterwards from the description text. A measurement on 2026-08-05 showed what
is wrong with that: of 10,215 vacancies in the database, 27 passed all the
gates, and only 8 had any sign of low intensity at all. The word "part-time"
appeared in the entire database once.

Calm part-time work is not a subset of ordinary vacancies but a separate
market. Here it is present in full, and via a STRUCTURED `schedule_type` field:
4_day_week, 4_day_week_pro_rata, 9_day_fortnight, compressed_week,
half_day_fridays, flexible_hours. That is more dependable than any guess from
text — the board itself sorts employers by working pattern.

Measured: 23,182 vacancies in total; in a sample of 100, about 21% engineering.

WHAT THIS MEANS FOR SCORING
--------------------------
The working pattern goes into the tags (`schedule:4_day_week`), where the
identity's low_intensity_signal picks it up. So the source does not merely
bring vacancies — it brings them with a proven mark of low intensity.
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

# schedule_type values the board returns verbatim. Translated into readable
# text so they read well both in the tag and in the report.
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
    """A ready-made string from the board beats recomputing it.

    The numeric salary_lower/upper fields arrive in hundredths of a unit
    ($162k looks like 16250866), and reconstructing the sum from them is an
    extra chance to be wrong by two orders of magnitude in the field that
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
        # Both machine-readable and human-readable: the first survives a change
        # of vocabulary on the board's side, the second reads well in the report.
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
        # The list response carries no description. The working pattern is the
        # main thing wanted here, and it arrives as a structured field.
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
                errors.append(f"{category} page {page}: {type(exc).__name__}")
                break

            items = payload.get("jobs") if isinstance(payload, dict) else None
            if not isinstance(items, list):
                errors.append(f"{category}: no jobs list in the response")
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
        note.append(f"skipped {skipped} (expired or incomplete)")
    if errors:
        note.append("; ".join(errors[:3]))
    return records, ("; ".join(note) or None)


def main() -> None:
    import argparse
    import identity as identity_mod

    parser = argparse.ArgumentParser(description="Collect vacancies from 4dayweek.io")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--category", action="append")
    parser.add_argument("--pages", type=int, default=MAX_PAGES)
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)

    records, note = fetch(args.category, args.pages)
    print(f"{SOURCE_NAME}: {len(records)} records ({note or 'no remarks'})")
    for r in records[:8]:
        line = f"  - {r['title']} @ {r['company']} [{', '.join(r['tags'][:2])}] {r['salary_raw'] or ''}"
        print(line.encode(sys.stdout.encoding or "utf-8", "replace")
                  .decode(sys.stdout.encoding or "utf-8", "replace"))


if __name__ == "__main__":
    main()
