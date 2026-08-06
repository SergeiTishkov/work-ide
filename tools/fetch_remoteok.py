"""
Fetcher for the RemoteOK source (https://remoteok.com/api).

Public JSON, no key. In practice the feed carries irrelevant content mixed in
— observed during development: ordinary news items with no job title or
company arrive alongside vacancies. So the parser is as strict as it can be
about required fields and never trusts the feed blindly.

The first element of a RemoteOK response is a housekeeping legal record rather
than a vacancy, so it is skipped per the API contract.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOURCE_NAME = "remoteok"
API_URL = "https://remoteok.com/api"


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

    if not isinstance(payload, list):
        return [], "unexpected payload shape: expected a list"

    items = payload[1:] if payload and not _looks_like_job(payload[0]) else payload

    records = []
    skipped = 0
    for item in items:
        rec = _to_common_schema(item)
        if rec is None:
            skipped += 1
            continue
        records.append(rec)

    error = None
    if skipped:
        error = f"skipped {skipped}/{len(items)} malformed/non-job records (non-fatal, source is known to be noisy)"
    return records, error


def _looks_like_job(item: dict) -> bool:
    return isinstance(item, dict) and bool(item.get("position")) and bool(item.get("company"))


def _to_common_schema(item: dict) -> Optional[dict]:
    if not isinstance(item, dict):
        return None
    title = (item.get("position") or "").strip()
    company = (item.get("company") or "").strip()
    apply_url = (item.get("url") or item.get("apply_url") or "").strip()
    if not title or not company or not apply_url:
        return None

    salary_raw = None
    smin, smax = item.get("salary_min"), item.get("salary_max")
    if smin or smax:
        salary_raw = f"{smin or '?'}-{smax or '?'} USD/year"

    return {
        "source": SOURCE_NAME,
        "external_id": str(item.get("id") or apply_url),
        "title": title,
        "company": company,
        "url": apply_url,
        "location_raw": item.get("location") or "",
        "remote": True,  # RemoteOK carries remote vacancies only, by definition
        "tags": list(item.get("tags") or []),
        "description_html": item.get("description") or "",
        "posted_at_epoch": item.get("epoch"),
        "salary_raw": salary_raw,
    }


if __name__ == "__main__":
    import identity as identity_mod

    identity_mod.standalone_main(fetch, SOURCE_NAME)
