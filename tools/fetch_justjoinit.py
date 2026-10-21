"""
Fetcher for justjoin.it (https://justjoin.it), a Polish IT job board.

Its site reads a JSON API, no key and no cookie (measured 2026-10-21 and
2026-10-22):

  * GET /api/candidate-api/offers?categories=net&remoteWorkOptions=remote
    &employmentTypes=b2b&itemsCount=100&from=0 -> {"data": [...], "meta":
    {"from", "totalItems", "next": {"cursor", "itemsCount"}}}; `from` pages,
    `meta.next.cursor` is the next offset, `totalItems` counts what the
    filters left. 118 remote B2B .NET offers on 2026-10-21, 118 on
    2026-10-22.
    Silently ignored, the whole board coming back: `workplaceType=remote`
    and `perPage`. `keyword=c%23` returned 4,514 offers, nearly all
    unrelated; `categories` is the stack filter;
  * GET /api/candidate-api/offers/<slug> -> one offer with `body` (HTML),
    `languages`, `countryCode`, `companyUrl`, `isActive`; 404 "Entity not
    found" for an unknown slug.

A list item carries guid, slug, title, companyName, city, workplaceType,
workingTime (full_time 95 of 118, b2b_contract 21, part_time 1, freelance
1), requiredSkills, languages, publishedAt and employmentTypes: one entry
per contract type and currency, the employer's own figures marked
currencySource "original" and the board's conversions to USD, EUR, CHF and
GBP marked "conversion". For unit Hour and Day, `from`/`to` hold a monthly
figure (140 PLN an hour: from 23520) and fromPerUnit/toPerUnit the rate; for
Month the two are equal. 19 of 118 offers had a b2b entry with null figures.

Languages, 2026-10-21, 118 offers: none listed 51, English 31, English and
Polish 25, Polish 7 ("pl"), Polish 3 ("polish"), German and English 1.
Reading every text the same day: 66 needed Polish, 15 Polish or EU
residence, 40 said nothing about either, 4 "anywhere". Residence
requirements are written in the text only, so the location field says
where the office is and that the work is remote, and the text says the rest.

The language gate (score._score_language_fit) has no phrase for Polish in
SHARP's criteria on 2026-10-22: it reads Polish as required from "Polish
and English ... skills" (the pattern "English and another language") or
from a text written in Polish (foreign_language_posting_indicators). A
listed Polish is written into the text in the first of those forms when
English is listed too; see language_line.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Callable, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import places  # noqa: E402

SOURCE_NAME = "justjoinit"
SITE = "https://justjoin.it"
LIST_URL = f"{SITE}/api/candidate-api/offers"
DETAIL_URL = f"{LIST_URL}/{{slug}}"
PAGE_URL = f"{SITE}/job-offer/{{slug}}"
ITEMS_COUNT = 100   # 118 offers came in two pages of this size (2026-10-21)
MAX_PAGES = 20
PAUSE_SECONDS = 1.0
DEFAULT_CATEGORIES = ["net"]
DEFAULT_REMOTE_WORK_OPTIONS = "remote"
DEFAULT_EMPLOYMENT_TYPES = "b2b"
# workingTime as the engagement gate's words; b2b_contract says the same as
# the b2b employment type.
WORKING_TIME = {"full_time": "full-time", "part_time": "part-time", "freelance": "freelance",
                "b2b_contract": "contract", "internship": "internship"}
WORKPLACE = {"remote": "remote", "hybrid": "hybrid", "office": "on-site"}
LANGUAGE_NAMES = {"pl": "Polish", "polish": "Polish", "en": "English", "english": "English",
                  "de": "German", "german": "German", "uk": "Ukrainian", "ua": "Ukrainian",
                  "fr": "French", "es": "Spanish", "it": "Italian", "nl": "Dutch", "cs": "Czech"}
UNITS = {"hour": "hour", "day": "day", "month": "month", "year": "year"}
HOURS_A_DAY = 8


def _get(url: str, params: Optional[dict] = None, timeout: int = common.DEFAULT_TIMEOUT):
    import requests

    headers = {"User-Agent": common.USER_AGENT, "Accept": "application/json"}
    resp = requests.get(url, params=params, timeout=timeout, headers=headers)
    resp.raise_for_status()
    return resp.json()


def _as_list(value) -> List[str]:
    if value is None or value == "":
        return []
    items = value if isinstance(value, (list, tuple)) else [value]
    return [str(v).strip() for v in items if str(v).strip()]


def languages(item: dict, detail: Optional[dict] = None) -> List[tuple]:
    """(name, level) for each language the offer lists, the detail's list
    first."""
    found = []
    for entry in (detail or {}).get("languages") or item.get("languages") or []:
        if not isinstance(entry, dict):
            continue
        code = str(entry.get("code") or "").strip().lower()
        if not code:
            continue
        name = LANGUAGE_NAMES.get(code, code.upper() if len(code) <= 3 else code.capitalize())
        found.append((name, str(entry.get("level") or "").strip()))
    return found


def needs_polish(item: dict, detail: Optional[dict] = None) -> bool:
    return any(name == "Polish" for name, _ in languages(item, detail))


def language_line(item: dict, detail: Optional[dict] = None) -> str:
    """The board's language field as a sentence, in the words the scoring's
    language gate reads: "Polish and English skills required (Polish C1,
    English B2)." With Polish and no English: "Polish skills required
    (Polish B2).", which SHARP's criteria do not read as a refusal on
    2026-10-22 (the module docstring)."""
    langs = languages(item, detail)
    if not langs:
        return ""
    names = [name for name, _ in langs]
    listed = ", ".join(f"{name} {level}".strip() for name, level in langs)
    others = [n for n in names if n != "English"]
    if "English" in names and others:
        said = " and ".join(others) + " and English skills required"
    else:
        said = " and ".join(names) + " skills required"
    return f"Languages: {said} ({listed})."


def _rate(entry: dict):
    lo, hi = entry.get("fromPerUnit"), entry.get("toPerUnit")
    if lo is None and hi is None:
        lo, hi = entry.get("from"), entry.get("to")
    return lo, hi


def _usd(lo, hi, unit: str) -> str:
    """Dollars with the unit on each bound, the shape score._extract_amounts
    reads: "$36/hour to $43/hour". A day rate is given an hour at
    HOURS_A_DAY hours, since the extractor knows no "/day" and would read
    "$371" as an hourly rate."""
    note = ""
    if unit == "day":
        lo = lo / HOURS_A_DAY if lo is not None else None
        hi = hi / HOURS_A_DAY if hi is not None else None
        unit, note = "hour", f" at {HOURS_A_DAY} hours a day"
    if unit == "year":
        parts = [f"${round(v):,}" for v in (lo, hi) if v is not None]
        return "-".join(dict.fromkeys(parts)) + note
    parts = [f"${round(v):,}/{unit}" for v in (lo, hi) if v is not None]
    return " to ".join(dict.fromkeys(parts)) + note


def salary(item: dict) -> Optional[str]:
    """The employer's own B2B rate, then the board's conversion to dollars
    when the rate is in another currency: "140-170 PLN/hour net (B2B);
    justjoin.it's conversion: $36/hour to $43/hour"."""
    entries = [e for e in item.get("employmentTypes") or [] if isinstance(e, dict)]
    b2b = [e for e in entries if str(e.get("type") or "").lower() == "b2b"]
    original = next((e for e in b2b if e.get("currencySource") == "original" and any(_rate(e))), None)
    if original is None:
        return None
    unit = UNITS.get(str(original.get("unit") or "").lower(), str(original.get("unit") or "").lower())
    currency = str(original.get("currency") or "").upper()
    lo, hi = _rate(original)
    if currency == "USD":
        text = _usd(lo, hi, unit)
    else:
        figures = "-".join(dict.fromkeys(f"{round(v):,}" for v in (lo, hi) if v is not None))
        text = f"{figures} {currency}/{unit}"
    text += " net (B2B)" if original.get("gross") is False else " (B2B)"
    if currency != "USD":
        usd = next((e for e in b2b if e.get("currencySource") == "conversion"
                    and str(e.get("currency") or "").upper() == "USD"
                    and str(e.get("unit") or "").lower() == str(original.get("unit") or "").lower()
                    and any(_rate(e))), None)
        if usd is not None:
            text += "; justjoin.it's conversion: " + _usd(*_rate(usd), unit)
    return text


def employment(item: dict) -> List[str]:
    found = []
    if any(str(e.get("type") or "").lower() == "b2b" for e in item.get("employmentTypes") or []
           if isinstance(e, dict)):
        found.append("contract")
    working = WORKING_TIME.get(str(item.get("workingTime") or "").lower())
    if working and working not in found:
        found.append(working)
    return found


def location(item: dict, detail: Optional[dict] = None) -> str:
    """"Remote; office in Kraków, Poland". No " only": score.py reads it as
    a refusal, and the board's field does not say one. A requirement to live
    in Poland or the EU is in the text when the employer wrote one."""
    detail = detail or {}
    workplace = str(item.get("workplaceType") or detail.get("workplaceType") or "").lower()
    head = {"remote": "Remote", "hybrid": "Hybrid", "office": "On-site"}.get(workplace, "Remote")
    city = str(detail.get("city") or item.get("city") or "").strip()
    country = places.country_of_code(detail.get("countryCode")) if detail.get("countryCode") else None
    office = ", ".join(p for p in (city, country) if p)
    return f"{head}; office in {office}" if office else head


def description(item: dict, detail: Optional[dict] = None) -> str:
    """The language line first (the text is cut at 6,000 characters in
    normalize.py), then the offer's body, then the skills. With no detail,
    the list's fields alone."""
    detail = detail or {}
    parts = [language_line(item, detail),
             common.strip_html(str(detail.get("body") or "")).strip()]
    skills = [str(s.get("name")).strip() for s in item.get("requiredSkills") or []
              if isinstance(s, dict) and s.get("name")]
    if skills:
        parts.append("Required skills: " + ", ".join(skills))
    nice = [str(s.get("name")).strip() for s in item.get("niceToHaveSkills") or []
            if isinstance(s, dict) and s.get("name")]
    if nice:
        parts.append("Nice to have: " + ", ".join(nice))
    if item.get("experienceLevel"):
        parts.append(f"Level: {item['experienceLevel']}")
    return "\n\n".join(p for p in parts if p)


def to_record(item: dict, detail: Optional[dict] = None) -> Optional[dict]:
    """One list item (with its detail, when fetched) in the common schema;
    None for a malformed item."""
    if not isinstance(item, dict):
        return None
    guid = str(item.get("guid") or "").strip()
    slug = str(item.get("slug") or "").strip()
    title = str(item.get("title") or "").strip()
    company = str(item.get("companyName") or "").strip()
    if not guid or not slug or not title or not company:
        return None
    detail = detail if isinstance(detail, dict) else None
    workplace = WORKPLACE.get(str(item.get("workplaceType") or "").lower())
    return {
        "source": SOURCE_NAME,
        "external_id": guid,
        "title": title,
        "company": company,
        "url": PAGE_URL.format(slug=slug),
        "company_url": str((detail or {}).get("companyUrl") or "").strip() or None,
        "apply_url": str(item.get("applyUrl") or "").strip() or None,
        "location_raw": location(item, detail),
        "remote": workplace == "remote" if workplace else None,
        "workplace_type": workplace,
        "employment_types": employment(item),
        "tags": [str(s.get("name")).strip() for s in item.get("requiredSkills") or []
                 if isinstance(s, dict) and s.get("name")][:8],
        "description_text": description(item, detail),
        "posted_at": str(item.get("publishedAt") or "").strip() or None,
        "salary_raw": salary(item),
    }


def _list(get: Callable, filters: dict, pause: float):
    """Every offer one filter set gives, page by page; (items, total, note)."""
    items, offset, total = [], 0, None
    for page in range(MAX_PAGES):
        if page:
            time.sleep(pause)
        try:
            payload = get(LIST_URL, {**filters, "itemsCount": ITEMS_COUNT, "from": offset})
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, list):
                raise ValueError("the answer has no `data` list")
        except Exception as exc:  # noqa: BLE001
            if not page:
                raise
            return items, total, f"from={offset}: {type(exc).__name__}"
        items += data
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        total = meta.get("totalItems") if isinstance(meta.get("totalItems"), int) else total
        cursor = (meta.get("next") or {}).get("cursor") if isinstance(meta.get("next"), dict) else None
        if not data or cursor is None or (isinstance(total, int) and offset + len(data) >= total):
            return items, total, None
        offset = cursor if isinstance(cursor, int) and cursor > offset else offset + len(data)
    return items, total, f"stopped after {MAX_PAGES} pages"


def fetch(categories=None, remote_work_options: Optional[str] = DEFAULT_REMOTE_WORK_OPTIONS,
          employment_types: Optional[str] = DEFAULT_EMPLOYMENT_TYPES, details: bool = True,
          timeout: int = common.DEFAULT_TIMEOUT, get: Callable = None, pause: float = PAUSE_SECONDS,
          counts: Optional[dict] = None):
    """Every offer in `categories` (one listing each) that the work-option
    and contract filters leave, each with its full text when `details`.
    `counts`, when given, receives how many were found, kept and list
    Polish."""
    get = get or (lambda url, params=None: _get(url, params, timeout))
    categories = _as_list(categories) or DEFAULT_CATEGORIES
    extra = {key: ",".join(_as_list(value)) for key, value in
             (("remoteWorkOptions", remote_work_options), ("employmentTypes", employment_types))
             if _as_list(value)}
    hits, errors, notes = {}, [], []
    for i, category in enumerate(categories):
        if i:
            time.sleep(pause)
        try:
            items, total, note = _list(get, {"categories": category, **extra}, pause)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{category}: {type(exc).__name__}")
            continue
        if note:
            notes.append(f"{category} {note}")
        if isinstance(total, int) and len(items) < total and not note:
            notes.append(f"{category}: read {len(items)} of {total}")
        for item in items:
            if isinstance(item, dict) and item.get("guid"):
                hits.setdefault(str(item["guid"]), item)
    if len(errors) == len(categories):
        return [], "every listing failed: " + ", ".join(errors)

    records, skipped, closed, polish = [], 0, 0, 0
    for item in hits.values():
        detail = None
        slug = str(item.get("slug") or "").strip()
        if details and slug:
            try:
                time.sleep(pause)
                detail = get(DETAIL_URL.format(slug=slug))
            except Exception as exc:  # noqa: BLE001
                notes.append(f"{slug}: {type(exc).__name__}")   # the list's fields stand in
            if isinstance(detail, dict) and detail.get("isActive") is False:
                closed += 1
                continue
        record = to_record(item, detail)
        if record is None:
            skipped += 1
            continue
        polish += needs_polish(item, detail if isinstance(detail, dict) else None)
        records.append(record)
    if counts is not None:
        counts.update(found=len(hits), kept=len(records), polish=polish)
    if errors:
        notes.insert(0, "listings failed: " + ", ".join(errors))
    if skipped:
        notes.append(f"skipped {skipped} malformed")
    if closed:
        notes.append(f"{closed} inactive on their detail page")
    return records, ("; ".join(notes) or None)


def _configured_params() -> dict:
    """The params the active identity's sources file gives this source."""
    for src in common.load_sources():
        if src.get("name") == SOURCE_NAME:
            return dict(src.get("params") or {})
    return {}


def main() -> None:
    import argparse
    import identity as identity_mod

    parser = argparse.ArgumentParser(description="Collect remote B2B offers from justjoin.it")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--categories", nargs="*", default=None,
                        help='the board\'s category keys, e.g. "net"; default: the identity\'s sources file, else net')
    parser.add_argument("--no-details", action="store_true", help="the list's fields only")
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)
    params = _configured_params()
    counts: dict = {}
    records, note = fetch(args.categories or params.get("categories"),
                          params.get("remote_work_options", DEFAULT_REMOTE_WORK_OPTIONS),
                          params.get("employment_types", DEFAULT_EMPLOYMENT_TYPES),
                          details=not args.no_details, counts=counts)
    print(f"{SOURCE_NAME}: {len(records)} records of {counts.get('found', 0)} found, "
          f"{counts.get('polish', 0)} list Polish ({note or 'no remarks'})")
    for r in records:
        print(f"  {r['title']} @ {r['company']} | {r['location_raw']} | {r['salary_raw']}")


if __name__ == "__main__":
    main()
