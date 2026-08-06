"""
Brings "raw" records from different sources to one canonical vacancy schema.
All the defensive validation lives here too: a record that cannot be
meaningfully normalised is discarded, with a reason, rather than breaking the
pipeline.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

REQUIRED_FIELDS = ("source", "external_id", "title", "company", "url")


def epoch_to_iso(epoch) -> Optional[str]:
    if epoch is None:
        return None
    try:
        return datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()
    except (ValueError, OSError, OverflowError, TypeError):
        return None


def normalize_record(raw: dict) -> Optional[dict]:
    """raw -> canonical vacancy dict (without first_seen/last_seen/computed/
    manual — those are added when merging into the knowledge base in kb.py).

    Returns None if the record will not do (required fields missing).
    """
    if not isinstance(raw, dict):
        return None
    for field in REQUIRED_FIELDS:
        if not str(raw.get(field) or "").strip():
            return None

    source = str(raw["source"]).strip()
    external_id = str(raw["external_id"]).strip()
    title = str(raw["title"]).strip()
    company = str(raw["company"]).strip()
    url = str(raw["url"]).strip()

    description_text = common.strip_html(
        raw.get("description_html") or raw.get("description_text") or ""
    )
    description_text = common.truncate(description_text, 6000)

    posted_at = raw.get("posted_at")
    if not posted_at and raw.get("posted_at_epoch") is not None:
        posted_at = epoch_to_iso(raw.get("posted_at_epoch"))

    tags = raw.get("tags") or []
    if not isinstance(tags, list):
        tags = [str(tags)]
    tags = [str(t).strip() for t in tags if str(t).strip()]

    remote = raw.get("remote")
    if remote is not None and not isinstance(remote, bool):
        remote = bool(remote)

    return {
        "id": common.stable_id(source, external_id),
        "source": source,
        "external_id": external_id,
        "title": title,
        "company": company,
        "url": url,
        # The company's official site, if the source gave one. Needed in order
        # to apply directly with the employer, bypassing a job-board account
        # (relevant for WWR: it keeps the application funnel to itself).
        "company_url": str(raw.get("company_url") or "").strip() or None,
        "location_raw": str(raw.get("location_raw") or "").strip(),
        "remote": remote,
        "tags": tags,
        "description_text": description_text,
        "posted_at": posted_at,
        "salary_raw": raw.get("salary_raw"),
    }


def normalize_batch(raw_records: list) -> tuple:
    """Returns (normalized: list[dict], skipped_count: int)."""
    normalized = []
    skipped = 0
    for raw in raw_records or []:
        rec = normalize_record(raw)
        if rec is None:
            skipped += 1
        else:
            normalized.append(rec)
    return normalized, skipped
