"""
Fetcher for MyCareersFuture — Singapore's government job portal.

A rare case: an official government API with clean structured data, no key
and no anti-bot protection (measured 2026-08-04: HTTP 200, 919 results for
"software engineer").

Singapore is the region's hub and a pronounced importer of development work:
engineers are scarce and hiring from abroad is routine. Its own commercial
boards (NodeFlair, Glints) answer 403, so this portal is the only available
way into the market.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote_plus

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOURCE_NAME = "mycareersfuture"
API_URL = "https://api.mycareersfuture.gov.sg/v2/jobs"
DEFAULT_QUERIES = ["software engineer", "backend developer", ".NET developer"]
LIMIT = 100
MAX_PAGES = 3


def _to_common_schema(item: dict) -> Optional[dict]:
    if not isinstance(item, dict):
        return None

    titles = item.get("jobTitles") or []
    title = str(item.get("title") or (titles[0] if titles else "")).strip()

    hiring = item.get("hiringCompany") or item.get("postedCompany") or {}
    company = str((hiring or {}).get("name") or "").strip()

    uuid = str(item.get("uuid") or item.get("metadata", {}).get("jobPostId") or "").strip()
    if not title or not company or not uuid:
        return None

    address = item.get("address") or {}
    location = ", ".join(
        str(part) for part in (address.get("building"), address.get("district"))
        if part
    ) or "Singapore"

    tags: List[str] = ["market:Singapore"]
    for cat in item.get("categories") or []:
        if isinstance(cat, dict) and cat.get("category"):
            tags.append(str(cat["category"]))
    for arrangement in item.get("flexibleWorkArrangements") or []:
        if isinstance(arrangement, dict) and arrangement.get("workArrangement"):
            tags.append(str(arrangement["workArrangement"]))

    salary = item.get("salary") or {}
    salary_raw = None
    if salary.get("minimum") and salary.get("maximum"):
        period = (salary.get("type") or {}).get("salaryType", "month")
        salary_raw = f"SGD {salary['minimum']:,}-{salary['maximum']:,}/{period}"

    return {
        "source": SOURCE_NAME,
        "external_id": uuid,
        "title": title,
        "company": company,
        "url": f"https://www.mycareersfuture.gov.sg/job/{uuid}",
        "location_raw": location,
        # The portal is national: remoteness comes from the text and the tags.
        "remote": None,
        "tags": tags,
        "description_text": common.strip_html(str(item.get("description") or "")),
        "posted_at": (item.get("metadata") or {}).get("originalPostingDate"),
        "salary_raw": salary_raw,
    }


def fetch(queries: Optional[List[str]] = None,
          pages: int = MAX_PAGES,
          timeout: int = common.DEFAULT_TIMEOUT):
    import requests

    queries = queries or DEFAULT_QUERIES
    records: List[dict] = []
    seen = set()
    skipped = 0
    errors: List[str] = []

    for query in queries:
        for page in range(pages):
            url = f"{API_URL}?limit={LIMIT}&page={page}&search={quote_plus(query)}"
            try:
                resp = requests.get(url, headers={"User-Agent": common.USER_AGENT}, timeout=timeout)
                resp.raise_for_status()
                payload = resp.json()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{query} page {page}: {type(exc).__name__}")
                break

            items = payload.get("results") if isinstance(payload, dict) else None
            if not isinstance(items, list):
                errors.append(f"{query}: no results list in the response")
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
        note.append(f"skipped {skipped} malformed")
    if errors:
        note.append("; ".join(errors[:3]))
    return records, ("; ".join(note) or None)


def main() -> None:
    import argparse
    import identity as identity_mod

    parser = argparse.ArgumentParser(description="Collect vacancies from MyCareersFuture (Singapore)")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--query", action="append")
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)

    records, note = fetch(args.query)
    print(f"{SOURCE_NAME}: {len(records)} records ({note or 'no remarks'})")


if __name__ == "__main__":
    main()
