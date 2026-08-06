"""
Checks whether vacancy links are still alive.

A deliberately conservative approach (confirmed explicitly by the owner,
2026-07-30, after dead links turned up in a report): only 404 and 410 count as
unambiguously "dead" — they are the only statuses sites use for "this page is
gone" without ambiguity. Everything else (timeouts, 403/429/999 from anti-bot
protection, 5xx) is marked "unknown" and is NOT hidden from the report — better
to show a doubtful link by mistake than to hide a real vacancy by mistake (the
same principle as in kb.mark_duplicates).

Links are checked no more often than once per `recheck_after_hours` hours per
vacancy, so as not to hammer the same job boards on every pipeline run.
Duplicates (`duplicate_of` already set) are not checked at all — they will not
appear in the report anyway, so an external request would be wasted.
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

DEAD_STATUS_CODES = {404, 410}
DEFAULT_TIMEOUT = 6
DEFAULT_MAX_WORKERS = 12
DEFAULT_RECHECK_AFTER_HOURS = 12


def _should_check(vacancy: dict, recheck_after_hours: int, now: datetime) -> bool:
    if vacancy.get("duplicate_of"):
        return False
    if not vacancy.get("url"):
        return False
    link_check = vacancy.get("link_check")
    if not link_check or not link_check.get("checked_at"):
        return True
    try:
        checked_at = datetime.fromisoformat(link_check["checked_at"])
    except ValueError:
        return True
    return now - checked_at > timedelta(hours=recheck_after_hours)


def _try_request(session, method: str, url: str, timeout: int):
    try:
        if method == "head":
            resp = session.head(url, timeout=timeout, allow_redirects=True)
        else:
            resp = session.get(url, timeout=timeout, allow_redirects=True, stream=True)
        return resp, None
    except Exception as exc:  # noqa: BLE001 - the network is unpredictable; never fail
        return None, exc


def _check_one(session, url: str, timeout: int) -> dict:
    resp, err = _try_request(session, "head", url, timeout)
    if resp is None or resp.status_code in (405, 501):
        resp2, err2 = _try_request(session, "get", url, timeout)
        if resp2 is not None:
            resp, err = resp2, None
        elif err is None:
            err = err2

    if resp is None:
        return {
            "status": "unknown",
            "http_code": None,
            "error": f"{type(err).__name__}: {err}" if err else "unknown error",
        }
    if resp.status_code in DEAD_STATUS_CODES:
        return {"status": "dead", "http_code": resp.status_code}
    if 200 <= resp.status_code < 400:
        return {"status": "ok", "http_code": resp.status_code}
    return {"status": "unknown", "http_code": resp.status_code}


def check_links(
    vacancies: dict,
    max_workers: int = DEFAULT_MAX_WORKERS,
    timeout: int = DEFAULT_TIMEOUT,
    recheck_after_hours: int = DEFAULT_RECHECK_AFTER_HOURS,
) -> dict:
    """Mutates vacancies in place (adding or updating `link_check` on every
    record checked). Returns statistics for the run."""
    import requests

    now = datetime.now(timezone.utc)
    to_check = [v for v in vacancies.values() if _should_check(v, recheck_after_hours, now)]

    stats = {
        "checked": 0,
        "dead": 0,
        "ok": 0,
        "unknown": 0,
        "skipped_recent_or_duplicate": len(vacancies) - len(to_check),
    }
    if not to_check:
        return stats

    session = requests.Session()
    session.headers.update({"User-Agent": common.USER_AGENT})

    def _work(v):
        return v["id"], _check_one(session, v["url"], timeout)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_work, v) for v in to_check]
        for future in as_completed(futures):
            vid, result = future.result()
            vacancies[vid]["link_check"] = {**result, "checked_at": datetime.now(timezone.utc).isoformat()}
            stats["checked"] += 1
            stats[result["status"]] += 1

    return stats


if __name__ == "__main__":
    import kb

    vacancies = kb.load_vacancies()
    stats = check_links(vacancies)
    kb.save_vacancies(vacancies)
    print(f"Link check: {stats}")
