"""
Фетчер вакансий напрямую с карьерных страниц компаний через их ATS.

Greenhouse / Lever / Ashby / Recruitee — это системы управления наймом, в
которых компании ведут собственные карьерные страницы. У всех есть
ОФИЦИАЛЬНЫЕ публичные JSON-эндпоинты, предназначенные именно для того,
чтобы их читали (по ним работают виджеты вакансий на сайтах компаний).
Никакой авторизации, никакой анти-бот защиты, никакого обхода — обычный
GET, HTTP 200 (замер 2026-07-31: Greenhouse Stripe 546 вакансий,
Cloudflare 284, GitLab 185; Ashby Notion 111, Ramp 126).

Ценность для проекта: это вакансии ОТ ПЕРВОГО ЛИЦА, минуя джоб-борды.
Здесь нет чужой воронки отклика (в отличие от WWR), нет платных подписок и
нет посредника, который может протухнуть. Плюс сюда попадают вакансии
зрелых enterprise-компаний, которые часто вообще не публикуются на
remote-бордах.

Список компаний — в config/ats_targets.yaml. Расширять его стоит теми
компаниями, что уже показали себя в базе знаний (legacy/enterprise
сигналы, зрелость по Wikidata), либо найденными агентом вручную.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOURCE_NAME = "ats"

# Пауза между запросами к одному провайдеру — обычная вежливость к чужому
# серверу, а не требование площадки.
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


_PARSERS = {
    "greenhouse": _parse_greenhouse,
    "lever": _parse_lever,
    "ashby": _parse_ashby,
    "recruitee": _parse_recruitee,
}


def load_targets() -> list:
    path = common.identity_config("ats_targets.yaml")
    if not path.exists():
        return []  # список целевых компаний необязателен для идентичности
    cfg = common.load_yaml(path) or {}
    return [t for t in (cfg.get("targets") or []) if t.get("enabled", True)]


def fetch(targets: Optional[list] = None, timeout: int = common.DEFAULT_TIMEOUT):
    """Обходит все настроенные ATS-доски. Падение одной компании не должно
    ронять остальные — это обычное дело, компания могла сменить ATS или
    закрыть доску."""
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
