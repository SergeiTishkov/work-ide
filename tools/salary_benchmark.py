"""
What the UK market pays for this stack, as a yardstick beside the shortlist.

WHY THIS IS NOT A SOURCE OF VACANCIES
-------------------------------------
IT Jobs Watch publishes no jobs. It publishes six-month rolling medians per
technology — "summary statistics and salary benchmarking for jobs requiring
.NET skills" — and there is nothing on it to apply to.

What it fills is a different gap. CLAUDE.md section 5 defines three levels of
trust in a salary, and the report today shows the first (stated in the vacancy)
and the third (nothing known) while the middle one is filled in by hand, a few
companies at a time. A person reading "£55,000 - £60,000" has no way of telling
whether that is generous or poor. With the market median beside it, they do.

WHAT IT MUST NEVER DO, AND WHY
------------------------------
**It must not fill in a vacancy's own salary.** This is a market median, not
what THIS employer pays. Putting it on a record would invent a fact about a
company — the exact confusion CLAUDE.md section 5 forbids in the other
direction ("do not confuse no data with bad pay").

**It must not touch the score.** Every UK .NET vacancy would gain the same
points, changing no ordering and making the number less honest.

So it is one block of context in the report, and nothing else reads it.

A REAL LIMIT
------------
The site is British. There are eight market shortlists and this serves one of
them, so the block is rendered only where UK vacancies actually appear. No
equivalent of this quality is known for the EU or Canada; there the middle
level of salary trust still has to be filled in by hand.

THE SLUGS ARE MEASURED, NOT GUESSED
-----------------------------------
Measured 2026-09-08: `.net`, `asp.net` and `azure` work; `c%23`, `sql-server`,
`angular` and `entity-framework` all answer 404. The site's own names for them
are `csharp`, `t-sql` and `angularjs`. A benchmark that silently covers half a
stack is worse than none, so the mapping is written down.
"""
from __future__ import annotations

import html
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

BASE_URL = "https://www.itjobswatch.co.uk"

# Technology as this project names it -> the slug IT Jobs Watch uses.
# Everything here was verified to return a median on 2026-09-08; anything that
# did not is absent rather than hopeful.
SLUGS = {
    ".NET": ".net",
    "C#": "csharp",
    "ASP.NET": "asp.net",
    "SQL Server": "t-sql",
    "Angular": "angularjs",
    "Azure": "azure",
}

# Six-month rolling statistics move slowly. Refetching them daily would be
# rude and would tell nobody anything new.
REFRESH_AFTER_DAYS = 30
PAUSE_SECONDS = 1.5

_MEDIAN_RE = re.compile(
    r"Median (?:annual salary|daily rate) \(50 th Percentile\)\s*(£[\d,]+)")
_YOY_RE = re.compile(r"% change year-on-year\s*([+-]?[\d.]+)")
_TAG_RE = re.compile(r"<[^>]+>")


def _text(body: str) -> str:
    return " ".join(html.unescape(_TAG_RE.sub(" ", body)).split())


def _fetch_one(kind: str, slug: str, timeout: int) -> Optional[dict]:
    """kind is "jobs" (permanent) or "contracts" (day rate)."""
    import requests

    url = f"{BASE_URL}/{kind}/uk/{slug}.do"
    try:
        resp = requests.get(url, headers={"User-Agent": common.USER_AGENT},
                            timeout=timeout)
        if resp.status_code != 200:
            return None
    except Exception:  # noqa: BLE001 — a yardstick must never break a run
        return None

    text = _text(resp.text)
    median = _MEDIAN_RE.search(text)
    if not median:
        return None
    yoy = _YOY_RE.search(text)
    return {"median": median.group(1),
            "year_on_year": yoy.group(1) + "%" if yoy else None,
            "url": url}


def collect(technologies: Optional[List[str]] = None,
            timeout: int = common.DEFAULT_TIMEOUT) -> dict:
    """{technology: {permanent, contract}}. Never raises."""
    wanted = [t for t in (technologies or list(SLUGS)) if t in SLUGS]
    result = {}
    for name in wanted:
        slug = SLUGS[name]
        permanent = _fetch_one("jobs", slug, timeout)
        time.sleep(PAUSE_SECONDS)
        contract = _fetch_one("contracts", slug, timeout)
        time.sleep(PAUSE_SECONDS)
        if permanent or contract:
            result[name] = {"permanent": permanent, "contract": contract}
    return {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "market": "United Kingdom",
        "source": "IT Jobs Watch",
        "technologies": result,
    }


def _cache_path() -> Path:
    return common.KNOWLEDGE_DIR / "salary_benchmark.json"


def is_stale(data: Optional[dict], days: int = REFRESH_AFTER_DAYS) -> bool:
    if not data or not data.get("technologies"):
        return True
    stamp = data.get("collected_at")
    if not stamp:
        return True
    try:
        when = datetime.fromisoformat(stamp)
    except ValueError:
        return True
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - when > timedelta(days=days)


def load() -> Optional[dict]:
    path = _cache_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def save(data: dict) -> Path:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path


def refresh_if_stale(technologies: Optional[List[str]] = None) -> dict:
    """The pipeline's entry point. Returns whatever is known, fresh or not:
    a month-old median is still a useful yardstick, and a failed fetch must
    never cost somebody the block entirely."""
    existing = load()
    if not is_stale(existing):
        return existing
    collected = collect(technologies)
    if collected.get("technologies"):
        save(collected)
        return collected
    return existing or collected


def technologies_from_profile(profile: dict) -> List[str]:
    """Which technologies to benchmark: the identity's own core stack, so this
    follows the person rather than needing configuration of its own."""
    core = ((profile or {}).get("tech_stack") or {}).get("core") or []
    return [name for name in SLUGS if name in core] or list(SLUGS)


def main() -> None:
    import argparse

    import identity as identity_mod
    import score as score_mod

    parser = argparse.ArgumentParser(
        description="UK market salary medians for this identity's stack")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--force", action="store_true",
                        help="refetch even if the cache is fresh")
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)

    wanted = technologies_from_profile(score_mod.load_profile())
    data = collect(wanted) if args.force else refresh_if_stale(wanted)
    if args.force and data.get("technologies"):
        save(data)

    print(f"{data.get('source')} / {data.get('market')}, "
          f"collected {(data.get('collected_at') or '?')[:10]}")
    for name, entry in (data.get("technologies") or {}).items():
        permanent = (entry.get("permanent") or {}).get("median") or "—"
        contract = (entry.get("contract") or {}).get("median") or "—"
        print(f"  {name:<12} permanent {permanent:<10} contract {contract}/day")


if __name__ == "__main__":
    main()
