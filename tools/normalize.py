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


# The vocabulary the arrangement gate understands. A source that invents a
# spelling gets None rather than a value nothing downstream can read.
WORKPLACE_TYPES = ("remote", "hybrid", "on-site")


def _workplace_type(value):
    if not value:
        return None
    text = str(value).strip().lower().replace("onsite", "on-site")
    return text if text in WORKPLACE_TYPES else None


# The vocabulary the engagement gate understands, in a fixed order so that two
# records saying the same thing store the same list.
EMPLOYMENT_TYPES = ("full-time", "part-time", "contract", "freelance",
                    "temporary", "internship")

# Every spelling a board has been seen to use. Boards disagree on case,
# separators and even the noun: Remotive "part_time", Himalayas "Part Time",
# schema.org "PART_TIME", LinkedIn "Part-time", Remote Rocketship "part-time".
#
# "permanent" is deliberately ABSENT. It says how long the job lasts, not how
# many hours it takes, and a UK "Permanent" role can be part-time. Mapping it
# to full-time would turn a board's silence about hours into a refusal.
_EMPLOYMENT_SPELLINGS = {
    "full-time": "full-time", "fulltime": "full-time", "full time": "full-time",
    "full_time": "full-time",
    "part-time": "part-time", "parttime": "part-time", "part time": "part-time",
    "part_time": "part-time",
    "contract": "contract", "contractor": "contract", "contract to hire": "contract",
    "contract-to-hire": "contract",
    "freelance": "freelance", "freelancer": "freelance",
    "temporary": "temporary", "temp": "temporary",
    "internship": "internship", "intern": "internship",
}


def employment_types(value) -> list:
    """A board's statement of the engagement, as canonical values.

    Accepts a string, a comma-separated string or a list — boards use all
    three. Anything unrecognised is dropped rather than kept: a value the gate
    cannot read looks like knowledge and behaves like silence.
    """
    if not value:
        return []
    items = value if isinstance(value, (list, tuple)) else str(value).split(",")
    found = set()
    for item in items:
        text = " ".join(str(item or "").strip().lower().replace("_", " ").split())
        canonical = (_EMPLOYMENT_SPELLINGS.get(text)
                     or _EMPLOYMENT_SPELLINGS.get(text.replace(" ", "-")))
        if canonical:
            found.add(canonical)
    return [t for t in EMPLOYMENT_TYPES if t in found]


def normalize_record(raw: dict) -> Optional[dict]:
    """raw -> canonical vacancy dict (without first_seen/last_seen/computed —
    those are added when merging into the knowledge base in kb.py).

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
        # Where the board's own "Apply" button sends a person, when it is not
        # the page above (devitjobs: a jobg8/appcast/Indeed link). Shown, never
        # requested.
        "apply_url": str(raw.get("apply_url") or "").strip() or None,
        # Where the description is read from, when that is not the page a
        # person opens (devitjobs: its detail API takes the id, the page has a
        # slug). See enrich_descriptions.
        "read_url": str(raw.get("read_url") or "").strip() or None,
        "location_raw": str(raw.get("location_raw") or "").strip(),
        "remote": remote,
        # Where the employer or the board says the work happens: "remote",
        # "hybrid", "on-site", or None for "nobody said". A separate field from
        # `remote` on purpose — that one is a boolean guess, this one is a
        # statement, and the arrangement gate reads only this.
        #
        # Added 2026-09-08 after it was found MISSING: ContractorUK badges 52
        # of 142 vacancies Remote and Outside IR35 Jobs badges all 50, and
        # every stored record had None. The tags beside it survived, so the
        # loss looked like "those boards do not publish it".
        "workplace_type": _workplace_type(raw.get("workplace_type")),
        # How the board classifies the engagement: ["part-time"], ["full-time",
        # "contract"], or [] for "nobody said". Read by the engagement gate
        # (score._check_engagement) before any phrase in the description, for
        # the same reason as workplace_type: a board ticking a box is a
        # statement, a word in prose is a guess.
        "employment_types": employment_types(raw.get("employment_types")),
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
