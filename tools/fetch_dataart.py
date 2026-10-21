"""
Fetcher for DataArt's own vacancies (https://www.dataart.team/en/vacancies).

DataArt is an outsourcing company that hires remotely from a list of
countries named on each vacancy. The site is a single-page app; the list and
each vacancy come from a JSON API under /dataart-team/api with no key, cookie
or token (measured 2026-10-21: every one of ~25 requests 200, no Cloudflare,
robots.txt allows everything):

  * /vacancies/filter-fields-page: the filter dictionaries — countries,
    locations, skills, levels — each {id, parentId, title, total};
  * /vacancies/filter-content-page?countries=<id>&pageSize=200&page=1:
    {"pagesTotal", "page", "items"}. Banner cards are mixed into the items
    with contentType 1; a vacancy has contentType 0;
  * /vacancy/<slug>: one vacancy — positionInfo, projectInfo,
    technologiesStack, responsibilities, requirements, the countries.

`countries` names the countries a vacancy must hire from, as the site spells
them ("Georgia"): the identity's residency, so it lives in the identity's
sources file, not here. Measured 2026-10-21: 117 vacancies on the site, 29
open to Georgia, none of them .NET; the site's four .NET vacancies hired from
India, the USA or a list of EU countries.

No salary and no posting date anywhere in the API; the JSON-LD datePosted of
a vacancy page equalled the page's last-modified day, so it is not used.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Callable, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOURCE_NAME = "dataart"
API = "https://www.dataart.team/dataart-team/api"
FIELDS_URL = f"{API}/vacancies/filter-fields-page"
LIST_URL = f"{API}/vacancies/filter-content-page"
DETAIL_URL = f"{API}/vacancy/{{slug}}"
PAGE_SIZE = 200
PAUSE_SECONDS = 1.0
MAX_PAGES = 10
# A name in DataArt's countries list that is also something else: "Georgia"
# there is the country (the list holds countries only), while in most
# vacancies it is the US state. Written as "country of Georgia", which the
# ambiguous-place rules read as the country.
COUNTRY_NAMES = {"Georgia": "country of Georgia"}


def _get_json(url: str, params: Optional[dict] = None, timeout: int = common.DEFAULT_TIMEOUT):
    import requests

    resp = requests.get(url, params=params, timeout=timeout,
                        headers={"User-Agent": common.USER_AGENT, "Accept": "application/json"})
    resp.raise_for_status()
    return resp.json()


def _titles(tags) -> List[str]:
    return [str(t.get("title") or "").strip() for t in tags or [] if isinstance(t, dict) and t.get("title")]


def country_ids(fields: dict, names: List[str]) -> List[int]:
    """The ids of the countries named, from filter-fields-page. A name the
    site does not list raises: a misspelt country would fetch every vacancy."""
    known = {str(c.get("title") or "").strip().lower(): c.get("id")
             for c in (fields.get("countries") or []) if isinstance(c, dict)}
    missing = [n for n in names if n.strip().lower() not in known]
    if missing:
        raise ValueError(f"DataArt lists no country {missing}; it lists {sorted(known)}")
    return [known[n.strip().lower()] for n in names]


def description(detail: dict) -> str:
    """The vacancy's text as the page shows it, in its order."""
    parts = []
    for key in ("positionInfo", "projectInfo", "teamInfo", "clientInfo"):
        text = common.strip_html(str(detail.get(key) or "")).strip()
        if text:
            parts.append(text)
    stack = str(detail.get("technologiesStack") or "").strip()
    if stack:
        parts.append(f"Technologies: {stack}")
    for key, heading in (("responsibilities", "Responsibilities"), ("requirements", "Requirements"),
                         ("additionalRequirements", "Nice to have")):
        lines = [common.strip_html(str(x)).strip() for x in detail.get(key) or [] if x]
        lines = [line for line in lines if line]
        if lines:
            parts.append(heading + ":\n" + "\n".join(f"- {line}" for line in lines))
    countries = _titles(detail.get("countriesTags"))
    if countries:
        parts.append("Hires from: " + ", ".join(COUNTRY_NAMES.get(c, c) for c in countries))
    return "\n\n".join(parts)


def to_record(item: dict, detail: Optional[dict] = None, countries: Optional[List[str]] = None) -> Optional[dict]:
    """One list item (with its detail, when fetched) in the common schema;
    None for a banner or a malformed item. Remote when a location tag says
    "Remote.<country>" for one of `countries` (any country when none are
    named): "Remote.Poland" with only an office in Tbilisi is not remote
    work from Georgia."""
    if not isinstance(item, dict) or item.get("contentType") not in (0, None):
        return None
    title = str(item.get("title") or "").strip()
    url = str(item.get("fullUrl") or "").strip()
    slug = str(item.get("slug") or "").strip()
    if not title or not url or not slug:
        return None
    hires_from = _titles(item.get("countriesTags"))
    places = _titles(item.get("locationTags"))
    wanted = {c.strip().lower() for c in countries or []}
    remote = any(p.lower().startswith("remote") and (not wanted or p.split(".", 1)[-1].strip().lower() in wanted)
                 for p in places)
    location = ", ".join(COUNTRY_NAMES.get(c, c) for c in hires_from) or ", ".join(places)
    text = description(detail) if detail else common.strip_html(str(item.get("text") or ""))
    return {
        "source": SOURCE_NAME,
        "external_id": slug.lower(),
        "title": title,
        "company": "DataArt",
        "url": url,
        "location_raw": (f"Remote from: {location}" if remote else location) or "",
        "remote": remote,
        "workplace_type": "remote" if remote else None,
        "tags": _titles(item.get("skillsTags"))[:6],
        "description_text": text,
        "posted_at": None,
        "salary_raw": None,
    }


def fetch(countries: Optional[List[str]] = None, details: bool = True,
          timeout: int = common.DEFAULT_TIMEOUT, get: Callable = None, pause: float = PAUSE_SECONDS):
    """Every vacancy open to one of `countries` (every vacancy when none are
    named), each with its full text when `details`."""
    get = get or (lambda url, params=None: _get_json(url, params, timeout))
    try:
        params = {"pageSize": PAGE_SIZE}
        if countries:
            params["countries"] = ",".join(str(i) for i in country_ids(get(FIELDS_URL), countries))
        items, page = [], 1
        while page <= MAX_PAGES:
            payload = get(LIST_URL, {**params, "page": page})
            items += [i for i in payload.get("items") or [] if isinstance(i, dict)]
            if page >= int(payload.get("pagesTotal") or 1):
                break
            page += 1
            time.sleep(pause)
    except Exception as exc:  # noqa: BLE001
        return [], f"{type(exc).__name__}: {exc}"

    records, skipped, notes, seen = [], 0, [], set()
    for item in items:
        if item.get("contentType") not in (0, None):
            continue   # a banner
        slug = str(item.get("slug") or "").strip().lower()
        if slug in seen:
            continue
        seen.add(slug)
        detail = None
        if details and slug:
            try:
                time.sleep(pause)
                detail = get(DETAIL_URL.format(slug=slug))
            except Exception as exc:  # noqa: BLE001
                notes.append(f"{slug}: {type(exc).__name__}")   # the list's short text stands in
        record = to_record(item, detail, countries)
        if record is None:
            skipped += 1
            continue
        records.append(record)
    if skipped:
        notes.append(f"skipped {skipped} malformed")
    return records, ("; ".join(notes) or None)


def main() -> None:
    import argparse
    import identity as identity_mod

    parser = argparse.ArgumentParser(description="Collect DataArt's own vacancies")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--countries", nargs="*", default=None, help='as the site spells them, e.g. "Georgia"')
    parser.add_argument("--no-details", action="store_true", help="the list's short text only")
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)
    records, note = fetch(args.countries, details=not args.no_details)
    print(f"{SOURCE_NAME}: {len(records)} records ({note or 'no remarks'})")
    for r in records:
        print(f"  {r['title']} | {r['location_raw']}")


if __name__ == "__main__":
    main()
