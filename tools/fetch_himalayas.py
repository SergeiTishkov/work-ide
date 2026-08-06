"""
Fetcher for the Himalayas source (https://himalayas.app/jobs/api).

A public JSON API, no key, remote vacancies only (remote_only). It returns
about 20 vacancies per call regardless of the limit parameter — not many, but
free and keyless.

The source's value: `locationRestrictions` — an explicit, structured list of
permitted countries (empty = worldwide), plus structured salary. This is the
most dependable geography signal among all the project's sources: no guessing
from phrases in the text.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOURCE_NAME = "himalayas"
API_URL = "https://himalayas.app/jobs/api?limit=100"


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

    raw_items = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(raw_items, list):
        return [], "unexpected payload shape: 'jobs' list missing"

    records = []
    skipped = 0
    for item in raw_items:
        rec = _to_common_schema(item)
        if rec is None:
            skipped += 1
            continue
        records.append(rec)

    error = f"skipped {skipped}/{len(raw_items)} malformed records (non-fatal)" if skipped else None
    return records, error


def _format_salary(item: dict) -> Optional[str]:
    lo, hi = item.get("minSalary"), item.get("maxSalary")
    if not lo and not hi:
        return None
    currency = item.get("currency") or "USD"
    period = (item.get("salaryPeriod") or "annual").lower()
    unit = {"annual": "year", "yearly": "year", "monthly": "month", "hourly": "hour"}.get(period, period)
    symbol = "$" if currency.upper() == "USD" else f"{currency} "
    if lo and hi:
        return f"{symbol}{int(lo):,}-{symbol}{int(hi):,}/{unit}"
    value = lo or hi
    return f"{symbol}{int(value):,}/{unit}"


def _format_location(item: dict) -> str:
    """locationRestrictions is a list of permitted countries. An empty list
    means "no restriction" (worldwide). It is turned into the phrases score.py
    understands: an explicit "only" for restricted ones, "Worldwide" for free
    ones — so the board's structured signal correctly becomes a dealbreaker
    where it should."""
    restrictions = item.get("locationRestrictions")
    if not restrictions:
        return "Worldwide"
    if isinstance(restrictions, str):
        restrictions = [restrictions]
    names = [str(r).strip() for r in restrictions if str(r).strip()]
    if not names:
        return "Worldwide"
    return ", ".join(names) + " only"


# Values the board returns in place of real data.
#
# Measured 2026-08-04: Himalayas returns `companyName: "name"` and
# `companyLogo: "thumbnail_url"` — literally THE FIELD NAMES instead of the
# values, meaning their response serialisation is broken. That is how vacancies
# from a company called "name" got into the database, and a person saw them in
# the report.
#
# The real name is available in `companySlug` all the while. Hence a general
# rule for any external API: an empty value is not the only form absence takes;
# a placeholder looks like a valid string and passes checks silently.
_PLACEHOLDER_VALUES = {"name", "title", "company", "companyname", "null", "none",
                       "undefined", "string", "thumbnail_url", "n/a"}


def _extract_company(item: dict) -> str:
    """The company name from a Himalayas record, in whatever form it arrives.

    The board has changed this field's shape: it used to be `companyName`, it is
    now `company` as a string, and at one point it was a nested object
    `{"name": ...}`. A real case, 2026-08-04: the parser read only `companyName`,
    the field started arriving empty, and ALL 60 records from the source were
    silently discarded as "no company". The failure was completely quiet: the
    source counted as working and returned HTTP 200.

    Hence the rule: an external API has no such thing as "the" field name. Walk
    the known forms and take the first non-empty one.
    """
    for key in ("companyName", "company", "organization"):
        value = item.get(key)
        if isinstance(value, dict):
            value = value.get("name") or value.get("title") or ""
        value = str(value or "").strip()
        if value and value.lower() not in _PLACEHOLDER_VALUES:
            return value

    # The fallback: the company slug. It is also used in the vacancy URL.
    slug = str(item.get("companySlug") or "").strip()
    return slug


def _to_common_schema(item: dict) -> Optional[dict]:
    if not isinstance(item, dict):
        return None
    title = (item.get("title") or "").strip()
    company = _extract_company(item)
    url = (item.get("applicationLink") or item.get("guid") or "").strip()
    if not title or not company or not url:
        return None

    tags = []
    for key in ("categories", "parentCategories", "seniority"):
        value = item.get(key)
        if isinstance(value, list):
            tags.extend(str(v) for v in value)
        elif value:
            tags.append(str(value))
    if item.get("employmentType"):
        tags.append(str(item["employmentType"]))

    return {
        "source": SOURCE_NAME,
        "external_id": str(item.get("guid") or url),
        "title": title,
        "company": company,
        "url": url,
        "location_raw": _format_location(item),
        "remote": True,  # Himalayas is a remote-only board by definition
        "tags": tags,
        "description_html": item.get("description") or item.get("excerpt") or "",
        "posted_at_epoch": item.get("pubDate"),
        "salary_raw": _format_salary(item),
    }


if __name__ == "__main__":
    import identity as identity_mod

    identity_mod.standalone_main(fetch, SOURCE_NAME)
