"""
Fetches vacancies straight from company careers pages via their ATS.

Greenhouse / Lever / Ashby / Recruitee are hiring-management systems in which
companies run their own careers pages. All of them have OFFICIAL public JSON
endpoints meant precisely to be read — the vacancy widgets on company sites
run off them. No authorisation, no anti-bot protection, nothing to circumvent:
an ordinary GET, HTTP 200 (measured 2026-07-31: Greenhouse Stripe 546
vacancies, Cloudflare 284, GitLab 185; Ashby Notion 111, Ramp 126).

Value to the project: these are vacancies FIRST-HAND, bypassing the job
boards. There is no third party's application funnel (unlike WWR), no paid
subscription and no intermediary that can go stale. On top of that, mature
enterprise companies turn up here that often never post on remote boards at
all.

The company list lives in config/ats_targets.yaml. It is worth extending with
companies that have already shown themselves in the knowledge base (legacy or
enterprise signals, maturity per Wikidata), or ones the agent found by hand.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOURCE_NAME = "ats"

# The pause between requests to one provider is ordinary politeness towards
# somebody else's server rather than a requirement of the board.
POLITE_DELAY_SEC = 0.3


def _endpoint(provider: str, token: str) -> Optional[str]:
    provider = (provider or "").lower()
    if provider == "greenhouse":
        return f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
    if provider == "lever":
        return f"https://api.lever.co/v0/postings/{token}?mode=json"
    if provider == "ashby":
        return f"https://api.ashbyhq.com/posting-api/job-board/{token}"
    if provider == "recruitee":
        return f"https://{token}.recruitee.com/api/offers/"
    if provider == "workable":
        # The careers-page widget. This is the ATS most Israeli technology
        # companies use — hence its value to the project: Israel's own boards
        # (Drushim) answer 403.
        return f"https://apply.workable.com/api/v1/widget/accounts/{token}?details=true"
    if provider == "smartrecruiters":
        return f"https://api.smartrecruiters.com/v1/companies/{token}/postings?limit=100"
    return None


def _parse_greenhouse(payload, company: str, token: str) -> list:
    records = []
    for j in (payload.get("jobs") or []):
        title = (j.get("title") or "").strip()
        url = (j.get("absolute_url") or "").strip()
        if not title or not url:
            continue
        location = ((j.get("location") or {}).get("name") or "").strip()
        records.append({
            "source": SOURCE_NAME,
            "external_id": f"greenhouse:{token}:{j.get('id')}",
            "title": title,
            "company": j.get("company_name") or company,
            "url": url,
            "location_raw": location,
            "remote": True if "remote" in location.lower() else None,
            "tags": [d.get("name") for d in (j.get("departments") or []) if d.get("name")],
            "description_html": j.get("content") or "",
            "posted_at": j.get("updated_at") or j.get("first_published"),
            "salary_raw": None,
        })
    return records


def _parse_lever(payload, company: str, token: str) -> list:
    records = []
    for j in (payload if isinstance(payload, list) else []):
        title = (j.get("text") or "").strip()
        url = (j.get("hostedUrl") or j.get("applyUrl") or "").strip()
        if not title or not url:
            continue
        categories = j.get("categories") or {}
        location = (categories.get("location") or "").strip()
        tags = [v for v in (categories.get("team"), categories.get("commitment"),
                            categories.get("department")) if v]
        records.append({
            "source": SOURCE_NAME,
            "external_id": f"lever:{token}:{j.get('id')}",
            "title": title,
            "company": company,
            "url": url,
            "location_raw": location,
            "remote": True if "remote" in location.lower() else None,
            "tags": tags,
            "description_html": j.get("descriptionPlain") or j.get("description") or "",
            "posted_at_epoch": int(j["createdAt"] / 1000) if j.get("createdAt") else None,
            "salary_raw": None,
        })
    return records


def _parse_ashby(payload, company: str, token: str) -> list:
    records = []
    for j in (payload.get("jobs") or []):
        title = (j.get("title") or "").strip()
        url = (j.get("jobUrl") or j.get("applyUrl") or "").strip()
        if not title or not url:
            continue
        location = (j.get("location") or "").strip()
        is_remote = j.get("isRemote")
        records.append({
            "source": SOURCE_NAME,
            "external_id": f"ashby:{token}:{j.get('id')}",
            "title": title,
            "company": j.get("companyName") or company,
            "url": url,
            "location_raw": location,
            "remote": bool(is_remote) if is_remote is not None else (
                True if "remote" in location.lower() else None),
            "tags": [t for t in [j.get("department"), j.get("team"), j.get("employmentType")] if t],
            "description_html": j.get("descriptionHtml") or j.get("descriptionPlain") or "",
            "posted_at": j.get("publishedAt"),
            "salary_raw": None,
        })
    return records


def _parse_recruitee(payload, company: str, token: str) -> list:
    records = []
    for j in (payload.get("offers") or []):
        title = (j.get("title") or "").strip()
        url = (j.get("careers_url") or j.get("careers_apply_url") or "").strip()
        if not title or not url:
            continue
        location = (j.get("location") or "").strip()
        records.append({
            "source": SOURCE_NAME,
            "external_id": f"recruitee:{token}:{j.get('id')}",
            "title": title,
            "company": company,
            "url": url,
            "location_raw": location,
            "remote": True if str(j.get("remote")).lower() == "true" else None,
            "tags": [t for t in [j.get("department"), j.get("employment_type")] if t],
            "description_html": j.get("description") or "",
            "posted_at": j.get("published_at"),
            "salary_raw": None,
        })
    return records


def _parse_workable(payload, company: str, token: str) -> list:
    records = []
    for j in (payload.get("jobs") or []):
        title = (j.get("title") or "").strip()
        url = (j.get("url") or j.get("shortlink") or "").strip()
        if not title or not url:
            continue
        location = ", ".join(
            str(part) for part in (j.get("city"), j.get("country")) if part
        )
        records.append({
            "source": SOURCE_NAME,
            "external_id": f"workable:{token}:{j.get('shortcode') or url}",
            "title": title,
            "company": payload.get("name") or company,
            "url": url,
            "location_raw": location,
            "remote": True if j.get("telecommuting") else None,
            "tags": [j["department"]] if j.get("department") else [],
            "description_html": j.get("description") or "",
            "posted_at": j.get("published_on"),
            "salary_raw": None,
        })
    return records


def _parse_smartrecruiters(payload, company: str, token: str) -> list:
    records = []
    for j in (payload.get("content") or []):
        title = (j.get("name") or "").strip()
        job_id = j.get("id")
        if not title or not job_id:
            continue
        loc = j.get("location") or {}
        location = ", ".join(
            str(part) for part in (loc.get("city"), loc.get("country")) if part
        )
        records.append({
            "source": SOURCE_NAME,
            "external_id": f"smartrecruiters:{token}:{job_id}",
            "title": title,
            "company": (j.get("company") or {}).get("name") or company,
            "url": f"https://jobs.smartrecruiters.com/{token}/{job_id}",
            "location_raw": location,
            "remote": True if loc.get("remote") else None,
            "tags": [(j.get("department") or {}).get("label")] if j.get("department") else [],
            "description_html": "",
            "posted_at": j.get("releasedDate"),
            "salary_raw": None,
        })
    return records


_PARSERS = {
    "greenhouse": _parse_greenhouse,
    "workable": _parse_workable,
    "smartrecruiters": _parse_smartrecruiters,
    "lever": _parse_lever,
    "ashby": _parse_ashby,
    "recruitee": _parse_recruitee,
}


def load_targets() -> list:
    path = common.identity_config("ats_targets.yaml")
    if not path.exists():
        return []  # a target-company list is optional for an identity
    cfg = common.load_yaml(path) or {}
    return [t for t in (cfg.get("targets") or []) if t.get("enabled", True)]


def fetch(targets: Optional[list] = None, timeout: int = common.DEFAULT_TIMEOUT):
    """Walks every configured ATS board. One company failing must not bring the
    rest down — it is routine, the company may have switched ATS or closed its
    board."""
    import requests

    if targets is None:
        targets = load_targets()

    session = requests.Session()
    session.headers.update({"User-Agent": common.USER_AGENT})

    records = []
    errors = []
    for t in targets:
        provider = (t.get("provider") or "").lower()
        token = t.get("token")
        company = t.get("company") or token
        url = _endpoint(provider, token)
        parser = _PARSERS.get(provider)
        if not url or not parser:
            errors.append(f"{company}: unknown provider '{provider}'")
            continue

        try:
            resp = session.get(url, timeout=timeout)
            if resp.status_code == 404:
                errors.append(f"{company}: board not found (404)")
                continue
            resp.raise_for_status()
            payload = resp.json()
            records.extend(parser(payload, company, token))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{company}: {type(exc).__name__}")
        time.sleep(POLITE_DELAY_SEC)

    error = "; ".join(errors[:8]) if errors else None
    if errors and len(errors) > 8:
        error += f" (+{len(errors) - 8} more)"
    return records, error


if __name__ == "__main__":
    import identity as identity_mod

    identity_mod.standalone_main(fetch, SOURCE_NAME)
