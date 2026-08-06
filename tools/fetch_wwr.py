"""
Fetcher for We Work Remotely — the "Remote Programming Jobs" RSS category.

RSS, no key, parsed with the standard library's xml.etree.ElementTree (rather
than feedparser, to avoid an extra dependency). WWR returns a useful `region`
field ("Anywhere in the World" / "USA Only" and so on) — a direct, dependable
signal for remote_location_fit, far more accurate than guessing keywords from
the description, so it is stored separately.
"""
from __future__ import annotations

import re
import sys
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOURCE_NAME = "weworkremotely"

# Measured 2026-07-30: the remote-programming-jobs category alone gives 25
# vacancies, whereas all five together give about 277 (and ten times as many
# .NET-relevant ones). Only the first used to be used — that was the main
# reason the pipeline's yield was so thin.
FEED_URLS = [
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-front-end-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
]
FEED_URL = FEED_URLS[0]  # backwards compatibility for existing callers

# The namespace WWR mixes into some elements (content:encoded and the like)
_NS = {"content": "http://purl.org/rss/1.0/modules/content/"}


def fetch(urls=None, timeout: int = common.DEFAULT_TIMEOUT):
    """Walks ALL of WWR's category feeds and merges the result, deduplicating by
    link (one vacancy is often published in several categories at once — in
    full-stack and back-end, for instance)."""
    import requests

    if urls is None:
        urls = FEED_URLS
    elif isinstance(urls, str):
        urls = [urls]

    records = []
    seen_ids = set()
    skipped = 0
    errors = []
    total_items = 0

    for url in urls:
        try:
            resp = requests.get(
                url, headers={"User-Agent": common.USER_AGENT}, timeout=timeout
            )
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except Exception as exc:  # noqa: BLE001 - one dead feed must not kill the rest
            errors.append(f"{url.rsplit('/', 1)[-1]}: {type(exc).__name__}")
            continue

        items = root.findall("./channel/item")
        total_items += len(items)
        for item in items:
            rec = _to_common_schema(item)
            if rec is None:
                skipped += 1
                continue
            if rec["external_id"] in seen_ids:
                continue  # the same vacancy from another category
            seen_ids.add(rec["external_id"])
            records.append(rec)

    error_parts = []
    if skipped:
        error_parts.append(f"skipped {skipped}/{total_items} malformed items (non-fatal)")
    if errors:
        error_parts.append("feed errors: " + "; ".join(errors))
    error = " | ".join(error_parts) if error_parts else None
    return records, error


def _text(item, tag: str) -> str:
    el = item.find(tag)
    return (el.text or "").strip() if el is not None and el.text else ""


_COMPANY_URL_RE = re.compile(r"URL:\s*(https?://[^\s<>\"')]+)", re.IGNORECASE)


def _extract_company_url(description_html: str) -> Optional[str]:
    """Extracts the company's official site from WWR's structured block
    ("Headquarters: ... / URL: ...").

    Why: WWR keeps the application funnel to itself — the "To apply:" field in
    most vacancies leads back to weworkremotely.com rather than to the
    employer (verified 2026-07-30: 71% of vacancies do exactly that). The
    company site makes it possible to find the same vacancy on their careers
    page and apply directly, with no WWR account."""
    if not description_html:
        return None
    # Searched in the CLEANED text: in raw HTML the link is wrapped in
    # <a href=...>, and "URL:" is separated from it by markup.
    m = _COMPANY_URL_RE.search(common.strip_html(description_html))
    if not m:
        return None
    url = m.group(1).rstrip(".,;)")
    if "weworkremotely" in url.lower():
        return None
    return url


def _to_common_schema(item) -> Optional[dict]:
    title_raw = _text(item, "title")
    link = _text(item, "link") or _text(item, "guid")
    if not title_raw or not link:
        return None

    # WWR usually encodes the title as "Company: Job Title"
    company, sep, title = title_raw.partition(":")
    if not sep:
        company, title = "", title_raw
    company = company.strip() or "Unknown"
    title = title.strip() or title_raw

    region = _text(item, "region")
    category = _text(item, "category")
    pub_date_raw = _text(item, "pubDate")
    posted_at_epoch = None
    if pub_date_raw:
        try:
            posted_at_epoch = int(parsedate_to_datetime(pub_date_raw).timestamp())
        except Exception:  # noqa: BLE001 - a date is not critical to the pipeline
            posted_at_epoch = None

    remote = None
    if region:
        remote = "only" not in region.lower() or "anywhere" in region.lower()

    description_html = _text(item, "description")

    return {
        "source": SOURCE_NAME,
        "external_id": link,
        "title": title,
        "company": company,
        "url": link,
        "company_url": _extract_company_url(description_html),
        "location_raw": region,
        "remote": remote,
        "tags": [t for t in [category] if t],
        "description_html": description_html,
        "posted_at_epoch": posted_at_epoch,
        "salary_raw": None,
    }


if __name__ == "__main__":
    import identity as identity_mod

    identity_mod.standalone_main(fetch, SOURCE_NAME)
