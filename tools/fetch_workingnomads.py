"""
Fetcher for WorkingNomads — a curated selection of remote vacancies.

Public JSON, no key (measured 2026-08-04: HTTP 200). The board is remote-only:
its remote flag is sufficient on its own, with no separate confirmation needed
in the text (see docs/SOURCES.md, on remote_only).

The format is extremely compact: title, company_name, location, tags, url,
description. Which is why this fetcher is so short — there is little to parse.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOURCE_NAME = "workingnomads"
API_URL = "https://www.workingnomads.com/api/exposed_jobs/"


def _to_common_schema(item: dict) -> Optional[dict]:
    if not isinstance(item, dict):
        return None
    title = str(item.get("title") or "").strip()
    company = str(item.get("company_name") or "").strip()
    url = str(item.get("url") or "").strip()
    if not title or not company or not url:
        return None

    tags = [t.strip() for t in str(item.get("tags") or "").split(",") if t.strip()]
    if item.get("category_name"):
        tags.append(str(item["category_name"]))

    return {
        "source": SOURCE_NAME,
        "external_id": url,
        "title": title,
        "company": company,
        "url": url,
        "location_raw": str(item.get("location") or "").strip(),
        "remote": True,          # the board publishes remote vacancies only
        "tags": tags,
        "description_text": common.strip_html(str(item.get("description") or "")),
        "posted_at": item.get("pub_date"),
        "salary_raw": None,
    }


def fetch(url: str = API_URL, timeout: int = common.DEFAULT_TIMEOUT):
    import requests

    try:
        resp = requests.get(url, headers={"User-Agent": common.USER_AGENT}, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        return [], f"{type(exc).__name__}: {exc}"

    if not isinstance(payload, list):
        return [], f"expected a list, got {type(payload).__name__}"

    records, skipped = [], 0
    for item in payload:
        rec = _to_common_schema(item)
        if rec is None:
            skipped += 1
            continue
        records.append(rec)

    return records, (f"skipped {skipped} malformed" if skipped else None)


def main() -> None:
    import argparse
    import identity as identity_mod

    parser = argparse.ArgumentParser(description="Collect vacancies from WorkingNomads")
    identity_mod.add_identity_arg(parser)
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)
    records, note = fetch()
    print(f"{SOURCE_NAME}: {len(records)} records ({note or 'no remarks'})")


if __name__ == "__main__":
    main()
