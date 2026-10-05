"""
Fetcher for Devitjobs — IT vacancies in the UK and the US.

One module for two boards: devitjobs.uk and devitjobs.com differ only in
domain, and share a response format. Two nearly identical files for the sake
of a different host is just an invitation to let them drift apart.

Measured 2026-08-04: the UK board returns 2449 records in one call, the US one
1590. This is the project's largest source by volume. The format is
"lightweight": no description text, but with structured fields — pay range
(annualSalaryFrom/To), level (expLevel), company type and a remote flag.

AN IMPORTANT LIMITATION: the response carries no description. Gates that read
the vacancy text (language, industry, infrastructure role) work blind on these
records and rely on the title and tags alone. The manual candidate checklist
therefore matters especially for anything from here.

THE UK BOARD CLOSED, 2026-10-04. Every devitjobs.uk address, the API too,
answers 302 to https://devitjobs.jobcopilot.com/signup?utm_source=dot_uk_old.
On 2026-10-03 at 03:13 UTC the API still served its list. A board asked for
here is reported as closed instead of being requested.

WHAT A RECORD OF devitjobs.com HOLDS (measured 2026-10-04, 2 918 records):
  * `jobUrl` — the slug of the vacancy page a person opens
    (/jobs/<jobUrl>). There is no `url` field, so the link used to be built
    from `_id`, and /jobs/<_id> serves the app's empty shell. The `_id` form is
    kept as `read_url`: the detail API the description is read from takes the
    id (enrich_descriptions._devitjobs_facts).
  * `workplace` — "office" 2 635, "remote" 142, "hybrid" 132: the board's own
    statement, so it goes into `workplace_type` (the arrangement gate). Before
    it was read, four office jobs sat among SHARP's hot leads.
  * `redirectJobUrl` — where the board's "Apply" button sends a person, for 2
    910 of them: jobg8 (1 940), appcast (428), Indeed (285), j-vers (233),
    Adzuna. Kept as `apply_url` and shown beside the vacancy. It is never
    requested: these are paid-click links, and a check would cost the
    advertiser a click.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOURCE_NAME = "devitjobs"

BOARDS = {
    "us": "https://devitjobs.com/api/jobsLight",
}

# A board that is gone, with why. Asked for anyway (an old sources file), it is
# reported in the note rather than requested.
CLOSED_BOARDS = {
    "uk": "closed 2026-10-04: every devitjobs.uk page redirects to a JobCopilot signup",
}

# The board's `workplace` in the words normalize.WORKPLACE_TYPES uses.
_WORKPLACE = {"remote": "remote", "hybrid": "hybrid", "office": "on-site"}


def _format_salary(item: dict) -> Optional[str]:
    lo, hi = item.get("annualSalaryFrom"), item.get("annualSalaryTo")
    if not lo and not hi:
        return None
    currency = (item.get("currency") or "").strip()
    symbol = {"GBP": "£", "USD": "$", "EUR": "€"}.get(currency.upper(), f"{currency} " if currency else "$")
    if lo and hi:
        return f"{symbol}{int(lo):,}-{symbol}{int(hi):,}/year"
    return f"{symbol}{int(lo or hi):,}/year"


def _to_common_schema(item: dict, board: str) -> Optional[dict]:
    if not isinstance(item, dict):
        return None

    # The board calls the title `name` rather than `title`.
    title = str(item.get("name") or item.get("title") or "").strip()
    company = str(item.get("company") or "").strip()
    job_id = str(item.get("_id") or "").strip()
    slug = str(item.get("jobUrl") or item.get("url") or job_id).strip()
    if not title or not company or not slug:
        return None

    host = "devitjobs.uk" if board == "uk" else "devitjobs.com"
    url = slug if slug.startswith("http") else f"https://{host}/jobs/{slug}"
    read_url = f"https://{host}/jobs/{job_id}" if job_id else url
    apply_url = str(item.get("redirectJobUrl") or "").strip()
    if not apply_url.startswith(("https://", "http://")):
        apply_url = None
    workplace = _WORKPLACE.get(str(item.get("workplace") or "").strip().lower())

    tags: List[str] = [f"board:{board}"]
    for key in ("expLevel", "companyType", "cityCategory", "jobType"):
        value = item.get(key)
        if isinstance(value, list):
            tags.extend(str(v) for v in value if v)
        elif value:
            tags.append(str(value))

    location = str(item.get("actualCity") or item.get("address") or "").strip()
    # The board marks remote work with a city category, not a separate flag.
    is_remote = (workplace == "remote" or "remote" in " ".join(tags).lower()
                 or "remote" in location.lower())

    return {
        "source": SOURCE_NAME,
        "external_id": f"{board}:{item.get('_id') or url}",
        "title": title,
        "company": company,
        "url": url,
        "read_url": read_url,
        "apply_url": apply_url,
        "location_raw": location or ("United Kingdom" if board == "uk" else "United States"),
        "remote": is_remote,
        "workplace_type": workplace,
        "tags": tags,
        "description_text": str(item.get("description") or "").strip(),
        "posted_at": item.get("activeFrom"),
        "salary_raw": _format_salary(item),
    }


def fetch(boards: Optional[List[str]] = None, timeout: int = common.DEFAULT_TIMEOUT):
    import requests

    boards = boards or ["us"]
    records: List[dict] = []
    skipped = 0
    errors: List[str] = []

    for board in boards:
        if board in CLOSED_BOARDS:
            errors.append(f"{board}: {CLOSED_BOARDS[board]}")
            continue
        url = BOARDS.get(board)
        if not url:
            errors.append(f"unknown board '{board}'")
            continue
        try:
            resp = requests.get(url, headers={"User-Agent": common.USER_AGENT}, timeout=timeout)
            resp.raise_for_status()
            # A board that moves away answers with a redirect, and the page
            # it lands on is not the list. Said so, rather than as a JSON error.
            if urlparse(resp.url).netloc != urlparse(url).netloc:
                errors.append(f"{board}: redirected to {resp.url}")
                continue
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{board}: {type(exc).__name__}")
            continue

        if not isinstance(payload, list):
            errors.append(f"{board}: expected a list, got {type(payload).__name__}")
            continue

        for item in payload:
            rec = _to_common_schema(item, board)
            if rec is None:
                skipped += 1
                continue
            records.append(rec)

    note_parts = []
    if skipped:
        note_parts.append(f"skipped {skipped} malformed records")
    if errors:
        note_parts.append("; ".join(errors))
    return records, ("; ".join(note_parts) or None)


def main() -> None:
    import argparse
    import identity as identity_mod

    parser = argparse.ArgumentParser(description="Collect vacancies from Devitjobs (UK/US)")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--board", action="append",
                        choices=sorted({*BOARDS, *CLOSED_BOARDS}), default=None)
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)

    records, note = fetch(args.board)
    print(f"{SOURCE_NAME}: {len(records)} records ({note or 'no remarks'})")


if __name__ == "__main__":
    main()
