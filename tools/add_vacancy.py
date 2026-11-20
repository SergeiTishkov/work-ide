"""
Puts one vacancy the person found into the list, by its link (task 0122).

    python tools/add_vacancy.py --identity sharp --url https://www.linkedin.com/jobs/view/4474971398/
    python tools/add_vacancy.py --identity sharp --url <link> --title "..." --company "..." \\
        --location "Remote, Europe" --description-file posting.txt

What it does, for that one vacancy and nothing else:

1. finds it in the base: a LinkedIn link by its job number (any subdomain,
   any slug: the same posting comes as www., es., uk.linkedin.com), another
   link by its address;
2. reads its page: LinkedIn gives the title, company, place, description and
   employment type to an anonymous request; another board with a page reader
   (enrich_descriptions) gives its facts; anything else takes
   --description-file. Given flags win over what the page says;
3. scores it with the identity's current criteria and saves it;
4. remembers it as the person's pick and lists it in the latest selection,
   in the "Added by hand" section, whatever its class (selections.HAND_CLASS).

No AI read, no other vacancy rescored, no new selection: the whole-base
rebuild of tools/ingest_manual.py takes about half an hour, this takes
seconds. The next run lists the pick again (selections.record).

Exit codes: 0 added, 1 not added (the message says why).
"""
from __future__ import annotations

import argparse
import html
import re
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import db  # noqa: E402
import fetch_linkedin  # noqa: E402
import kb  # noqa: E402
import normalize  # noqa: E402
import score  # noqa: E402
import selections  # noqa: E402

# The top card of an anonymous LinkedIn posting page (checked 2026-11-20).
_LI_TITLE_RE = re.compile(r"<h1[^>]*topcard__title[^>]*>\s*([^<]+?)\s*</h1>")
_LI_COMPANY_RE = re.compile(r"topcard__org-name-link[^>]*>\s*([^<]+?)\s*<")
_LI_PLACE_RE = re.compile(r'topcard__flavor--bullet">\s*([^<]+?)\s*<')
# The first read of a posting came back empty once in two tries on
# 2026-11-20 (the same page answered in full a minute later).
READ_TRIES = 3
READ_PAUSE_SECONDS = 5
TIMEOUT = 30


class NotAdded(Exception):
    """Why the vacancy was not added, for the person."""


linkedin_job_id = fetch_linkedin.job_id


def find_existing(url: str) -> Optional[str]:
    """The id of the vacancy this link names, or None. A LinkedIn posting is
    matched by its job number in any copy's address, the earliest seen first."""
    job_id = linkedin_job_id(url)
    with db.session() as conn:
        if job_id:
            rows = conn.execute(
                "SELECT id, json_extract(data, '$.url'), json_extract(data, '$.external_id'), "
                "json_extract(data, '$.first_seen') FROM vacancies "
                "WHERE data LIKE ?", (f"%{job_id}%",)).fetchall()
            hits = [(first or "", vid) for vid, link, ext, first in rows
                    if job_id in (linkedin_job_id(link or ""), linkedin_job_id(ext or ""))]
            return min(hits)[1] if hits else None
        row = conn.execute(
            "SELECT id FROM vacancies WHERE json_extract(data, '$.url') = ? "
            "OR json_extract(data, '$.external_id') = ? LIMIT 1", (url, url)).fetchone()
        return row[0] if row else None


def _first(pattern: re.Pattern, body: str) -> Optional[str]:
    match = pattern.search(body)
    return " ".join(html.unescape(match.group(1)).split()) if match else None


def read_linkedin(job_id: str) -> dict:
    """The posting's facts and top card, read anonymously."""
    import requests

    url = f"https://www.linkedin.com/jobs/view/{job_id}/"
    body = ""
    for attempt in range(READ_TRIES):
        if attempt:
            time.sleep(READ_PAUSE_SECONDS)
        try:
            resp = requests.get(url, headers={"User-Agent": common.USER_AGENT}, timeout=TIMEOUT)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001 — retried, then reported
            body = ""
            error = f"{type(exc).__name__}: {exc}"
            continue
        body = resp.text
        if fetch_linkedin.page_facts(body)["description"]:
            break
        error = "the page came without a description"
    else:
        raise NotAdded(f"LinkedIn posting {job_id} not read after {READ_TRIES} tries: {error}")
    facts = fetch_linkedin.page_facts(body)
    if not facts["employment_types"]:
        facts["employment_types"] = fetch_linkedin._employment_types_from_guest_fragment(url, TIMEOUT)
    facts.update(title=_first(_LI_TITLE_RE, body), company=_first(_LI_COMPANY_RE, body),
                 location=_first(_LI_PLACE_RE, body), url=url)
    return facts


def read_page(url: str, source: str) -> dict:
    """The facts a board's page reader gives, or {} when there is none."""
    import enrich_descriptions

    reader = enrich_descriptions._reader_for(source)
    return reader(url, TIMEOUT) if reader else {}


def source_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if host == "linkedin.com" or host.endswith(".linkedin.com"):
        return "linkedin"
    for name, site in common.source_sites().items():
        site_host = (urlparse(site if "//" in site else f"https://{site}").hostname or "").lower()
        if site_host and (host == site_host or host.endswith("." + site_host)):
            return name
    return "manual"


def gather(url: str, given: dict) -> tuple:
    """(existing record or None, facts read or given). Raises NotAdded."""
    job_id = linkedin_job_id(url)
    source = "linkedin" if job_id else source_of(url)
    existing_id = find_existing(url)
    existing = db.load_vacancy(existing_id) if existing_id else None
    page = read_linkedin(job_id) if job_id else read_page((existing or {}).get("url") or url, source)
    if page.get("closed"):
        raise NotAdded("the posting no longer accepts applications")
    facts = {
        "source": source,
        "url": page.get("url") or url,
        "external_id": f"https://www.linkedin.com/jobs/view/{job_id}/" if job_id else url,
        "title": given.get("title") or page.get("title"),
        "company": given.get("company") or page.get("company"),
        "location_raw": given.get("location") or page.get("location"),
        "description_text": given.get("description") or page.get("description") or "",
        "employment_types": page.get("employment_types") or [],
        "workplace_type": page.get("workplace_type"),
        "salary_raw": page.get("salary_raw"),
    }
    if not facts["description_text"] and not (existing or {}).get("description_text"):
        raise NotAdded("no description: the page gave none; pass --description-file")
    if existing is None and not (facts["title"] and facts["company"]):
        raise NotAdded("a new vacancy needs a title and a company: the page gave none; "
                       "pass --title and --company")
    return existing, facts


def merged(existing: Optional[dict], facts: dict, given=()) -> dict:
    """The record to save: the stored one with what the page added (a longer
    description, the employment type, the workplace and salary it states), or
    a new one through normalize. `given`: the facts the person passed, which
    replace the stored ones."""
    if existing is None:
        record = normalize.normalize_record(facts)
        if record is None:
            raise NotAdded("the vacancy lacks a required field")
        now = kb.now_iso()
        record.update(first_seen=now, last_seen=now, fetched_at=now, external_signals={})
        return record
    record = dict(existing)
    text = common.truncate(common.strip_html(facts["description_text"]), 6000)
    if len(text) > len(record.get("description_text") or ""):
        record["description_text"] = text
    record["employment_types"] = normalize.employment_types(
        list(record.get("employment_types") or []) + list(facts["employment_types"]))
    for key in ("workplace_type", "salary_raw"):
        if facts.get(key) and not record.get(key):
            record[key] = facts[key]
    for key, flag in (("title", "title"), ("company", "company"), ("location_raw", "location")):
        if facts.get(key) and (not record.get(key) or flag in given):
            record[key] = facts[key]
    return record


def add(url: str, given: dict) -> dict:
    """Adds the vacancy; returns what the person is told."""
    existing, facts = gather(url, given)
    record = merged(existing, facts, [k for k, v in given.items() if v])
    one = {record["id"]: record}
    kb.attach_company_reputation(one, kb.load_companies())
    view = {k: v for k, v in record.items() if k != "computed"}
    record["computed"] = score.score_vacancy(view, score.load_criteria(), score.load_profile())
    kb.save_vacancies(one)
    selections.save_pick(record["id"], url)
    selection_id = selections.add_by_hand(record)
    computed = record["computed"]
    return {
        "id": record["id"], "found": existing is not None, "title": record.get("title"),
        "company": record.get("company"), "description_chars": len(record.get("description_text") or ""),
        "score": computed.get("score"), "class": computed.get("classification"),
        "dealbreakers": computed.get("dealbreakers") or [], "selection_id": selection_id,
    }


def main() -> None:
    import identity as identity_mod

    parser = argparse.ArgumentParser(description="Put one vacancy into the list by its link")
    parser.add_argument("--url", required=True, help="the vacancy's page")
    parser.add_argument("--title", help="the title, when the page does not give it")
    parser.add_argument("--company", help="the company, when the page does not give it")
    parser.add_argument("--location", help="where, as the posting says it")
    parser.add_argument("--description-file", help="a text file with the posting, when the page cannot be read")
    identity_mod.add_identity_arg(parser)
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)

    given = {"title": args.title, "company": args.company, "location": args.location}
    if args.description_file:
        given["description"] = Path(args.description_file).read_text(encoding="utf-8")
    try:
        result = add(args.url.strip(), given)
    except NotAdded as exc:
        print(f"Not added: {exc}")
        sys.exit(1)
    print(f"{'Updated' if result['found'] else 'Added'}: {result['company']} | {result['title']} "
          f"(id {result['id']}, description {result['description_chars']} characters)")
    print(f"  the scripts: {result['score']} points, {result['class']}")
    for reason in result["dealbreakers"]:
        print(f"    - {reason}")
    if result["selection_id"] is None:
        print("  no selection yet: the first run lists it under \"Added by hand\"")
    else:
        print(f"  listed under \"Added by hand\" in selection #{result['selection_id']}")


if __name__ == "__main__":
    main()
