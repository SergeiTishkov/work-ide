"""
The knowledge base: vacancies, companies, recruiters.

Stored as human-readable JSON under data/knowledge/*.json. This file also
holds the CLI for managing records by hand — marking a vacancy's status,
adding a note, looking at statistics — usable from an interactive session
without having to open the JSON.

An important invariant: re-running the pipeline must NEVER overwrite the
"manual" field (status/notes), which a person or agent may have edited. It is
created once, with a default value, when a vacancy is first seen, and after
that only merge_vacancy(..., manual_patch=) or this file's CLI commands
touch it.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import score  # noqa: E402

VALID_STATUSES = (
    "new",
    "shortlisted",
    "applied",
    "interviewing",
    "offer",
    "rejected_by_owner",
    "dead_link",
    "not_relevant",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Loading and saving ----------------------------------------------------
#
# Every function starts with require_identity(). That is rule zero implemented
# in code: without an active identity, any touch of the data must fail with a
# comprehensible explanation rather than "NoneType has no attribute 'exists'".
# Formally activate_identity() runs earlier anyway — but these six functions are
# the front door to the data, and checking here is cheaper than one day writing
# one person's vacancies into another person's database.

def load_vacancies() -> dict:
    common.require_identity()
    return common.load_json(common.VACANCIES_PATH, default={})


def save_vacancies(vacancies: dict) -> None:
    common.require_identity()
    common.save_json_atomic(common.VACANCIES_PATH, vacancies)


def load_companies() -> dict:
    common.require_identity()
    return common.load_json(common.COMPANIES_PATH, default={})


def save_companies(companies: dict) -> None:
    common.require_identity()
    common.save_json_atomic(common.COMPANIES_PATH, companies)


def load_recruiters() -> list:
    common.require_identity()
    return common.load_json(common.RECRUITERS_PATH, default=[])


def save_recruiters(recruiters: list) -> None:
    common.require_identity()
    common.save_json_atomic(common.RECRUITERS_PATH, recruiters)


# --- Merging vacancies -----------------------------------------------------

def merge_vacancy(kb: dict, normalized: dict, computed: dict) -> str:
    """Inserts or updates a vacancy in the kb (a dict keyed by id). Returns
    "new" or "updated". The "manual" and "external_signals" fields are created
    once and never touched by automation again — they hold what a person or
    agent entered (application status, a pay range found by hand on Glassdoor
    via `tools/kb.py set-salary-estimate`), and the next pipeline run has no
    right to erase that while rebuilding the record from scratch."""
    vid = normalized["id"]
    ts = now_iso()
    existing = kb.get(vid)

    if existing is None:
        kb[vid] = {
            **normalized,
            "first_seen": ts,
            "last_seen": ts,
            "fetched_at": ts,
            "computed": computed,
            "manual": {"status": "new", "notes": ""},
            "external_signals": {},
        }
        return "new"

    manual = existing.get("manual", {"status": "new", "notes": ""})
    external_signals = existing.get("external_signals", {})
    kb[vid] = {
        **normalized,
        "first_seen": existing.get("first_seen", ts),
        "last_seen": ts,
        "fetched_at": ts,
        "computed": computed,
        "manual": manual,
        "external_signals": external_signals,
    }
    return "updated"


def mark_duplicates(vacancies: dict) -> int:
    """Marks near-duplicates — the same vacancy posted twice. Observed in
    practice: We Work Remotely sometimes returns one post under two different
    URLs. Records count as duplicates only on an EXACT match of the normalised
    (company, title) pair. The canonical record is the one with the best score
    (ties broken by earliest first_seen); the rest get a top-level
    "duplicate_of" field and drop out of the report.

    Note: fuzzy title comparison is deliberately NOT used. On real data it
    produced serious false positives — "Software Engineer - Manchester" and
    "Software Engineer - Newcastle" (one company hiring for one role across
    several cities), or
    "(Native Danish) Support Consultant" / "(Native Finnish) Support
    Consultant" (separate vacancies for separate languages) matched at >90% and
    were wrongly collapsed into one, hiding genuinely different open positions
    from the owner. Hiding a real vacancy is far worse than occasionally
    showing a harmless exact repeat, so the threshold is deliberately strict.

    Recomputed from scratch on every run: otherwise, once a duplicate stopped
    appearing in a source's results, the mark would stay forever."""
    for v in vacancies.values():
        v.pop("duplicate_of", None)

    by_key: dict = {}
    for vid, v in vacancies.items():
        key = (
            common.normalize_company_name(v.get("company")),
            common.normalize_for_matching(v.get("title")),
        )
        by_key.setdefault(key, []).append(vid)

    marked = 0
    for ids in by_key.values():
        if len(ids) < 2:
            continue
        ids.sort(
            key=lambda vid: (
                -(vacancies[vid].get("computed", {}).get("score", 0)),
                vacancies[vid].get("first_seen") or "",
            )
        )
        canonical = ids[0]
        for vid in ids[1:]:
            vacancies[vid]["duplicate_of"] = canonical
            marked += 1
    return marked


def build_companies_from_vacancies(vacancies: dict, previous_companies: Optional[dict] = None) -> dict:
    """companies.json is a view derived from vacancies.json, plus per-company
    notes entered by hand. It is rebuilt whole on every run so that the
    counters (vacancy_ids, signals) can never drift away from the real state of
    the vacancy database. first_seen and notes are carried over from the
    previous version so that history is not lost."""
    companies: dict = {}
    for slug, old in (previous_companies or {}).items():
        carried = {
            "name": old.get("name", slug),
            "first_seen": old.get("first_seen"),
            "last_seen": old.get("last_seen"),
            "vacancy_ids": [],
            "signals": {
                "legacy_enterprise_hits": 0,
                "eor_or_contractor_mentioned": False,
                "worldwide_remote_seen": False,
            },
            "notes": old.get("notes", ""),
        }
        # Reputation is gathered by the agent by hand — expensive, requiring web
        # search — so it is carried over like notes and first_seen. Otherwise it
        # would be lost on every rebuild of companies.json.
        if old.get("reputation"):
            carried["reputation"] = old["reputation"]
        if old.get("intel"):
            carried["intel"] = old["intel"]
        companies[slug] = carried
    for v in vacancies.values():
        upsert_company(companies, v.get("company", "Unknown"), v)
    return companies


def upsert_company(companies: dict, company_name: str, vacancy: dict) -> None:
    slug = common.normalize_company_name(company_name)
    ts = now_iso()
    entry = companies.get(slug)
    computed = vacancy.get("computed", {})
    breakdown = computed.get("score_breakdown", {})

    eor_hits = breakdown.get("remote_location_fit", {}).get("eor_or_contractor_hits", [])
    worldwide_hits = breakdown.get("remote_location_fit", {}).get("worldwide_remote_hits", [])
    legacy_hits = breakdown.get("legacy_enterprise_signal", {}).get("hits", [])

    if entry is None:
        entry = {
            "name": company_name,
            "first_seen": ts,
            "last_seen": ts,
            "vacancy_ids": [],
            "signals": {
                "legacy_enterprise_hits": 0,
                "eor_or_contractor_mentioned": False,
                "worldwide_remote_seen": False,
            },
            "notes": "",
        }
        companies[slug] = entry

    entry["last_seen"] = ts
    if vacancy["id"] not in entry["vacancy_ids"]:
        entry["vacancy_ids"].append(vacancy["id"])
    entry["signals"]["legacy_enterprise_hits"] = max(
        entry["signals"]["legacy_enterprise_hits"], len(legacy_hits)
    )
    entry["signals"]["eor_or_contractor_mentioned"] = (
        entry["signals"]["eor_or_contractor_mentioned"] or bool(eor_hits)
    )
    entry["signals"]["worldwide_remote_seen"] = (
        entry["signals"]["worldwide_remote_seen"] or bool(worldwide_hits)
    )


# --- CLI --------------------------------------------------------------

def cmd_stats(_args) -> None:
    vacancies = load_vacancies()
    if not vacancies:
        print("The knowledge base is empty. Run tools/pipeline.py.")
        return
    by_class = {}
    for v in vacancies.values():
        cls = v.get("computed", {}).get("classification", "unknown")
        by_class[cls] = by_class.get(cls, 0) + 1
    print(f"Vacancies in the database: {len(vacancies)}")
    for cls, n in sorted(by_class.items(), key=lambda kv: -kv[1]):
        print(f"  {cls}: {n}")
    review = sum(1 for v in vacancies.values() if v.get("computed", {}).get("needs_manual_review"))
    print(f"  needing manual review: {review}")
    dupes = sum(1 for v in vacancies.values() if v.get("duplicate_of"))
    print(f"  near-duplicates (hidden from the report): {dupes}")
    dead = sum(1 for v in vacancies.values() if v.get("link_check", {}).get("status") == "dead")
    print(f"  dead links (hidden from the report): {dead}")


def cmd_list(args) -> None:
    vacancies = load_vacancies()
    items = [v for v in vacancies.values() if not v.get("duplicate_of") or args.include_duplicates]
    if args.classification:
        items = [v for v in items if v.get("computed", {}).get("classification") == args.classification]
    items.sort(key=lambda v: -v.get("computed", {}).get("score", 0))
    for v in items[: args.limit]:
        c = v.get("computed", {})
        print(f"[{c.get('score'):>3}] {c.get('classification'):14} {v['company'][:30]:30} | {v['title'][:60]}")
        print(f"       id={v['id']} status={v.get('manual', {}).get('status')} url={v['url']}")


def cmd_show(args) -> None:
    vacancies = load_vacancies()
    v = vacancies.get(args.id)
    if not v:
        print(f"No vacancy with id={args.id}.")
        sys.exit(1)
    import json

    print(json.dumps(v, ensure_ascii=False, indent=2))


def cmd_set_status(args) -> None:
    if args.status not in VALID_STATUSES:
        print(f"Invalid status. Valid ones: {', '.join(VALID_STATUSES)}")
        sys.exit(1)
    vacancies = load_vacancies()
    v = vacancies.get(args.id)
    if not v:
        print(f"No vacancy with id={args.id}.")
        sys.exit(1)
    v.setdefault("manual", {"status": "new", "notes": ""})
    v["manual"]["status"] = args.status
    if args.notes is not None:
        v["manual"]["notes"] = args.notes
    save_vacancies(vacancies)
    print(f"OK: {args.id} -> status={args.status}")


def cmd_set_salary_estimate(args) -> None:
    """Records a pay range found by hand (on Glassdoor, say) for a vacancy that
    states no salary itself. Confirmed explicitly by the owner (2026-07-30):
    such an estimate earns a small plus — less than a rate stated in the
    vacancy itself, more than no data at all. Stored in
    vacancy.external_signals rather than in manual, which is precisely why it
    takes part in scoring instead of only being displayed."""
    vacancies = load_vacancies()
    v = vacancies.get(args.id)
    if not v:
        print(f"No vacancy with id={args.id}.")
        sys.exit(1)

    v.setdefault("external_signals", {})
    v["external_signals"]["salary_estimate"] = {
        "low": args.low,
        "high": args.high,
        "period": args.period,
        "source": args.source,
        "note": args.note or "",
    }

    # Rescore immediately, so the change is visible at once rather than after
    # the next tools/pipeline.py run.
    criteria = score.load_criteria()
    profile = score.load_profile()
    vacancy_view = {k: val for k, val in v.items() if k not in ("computed", "manual")}
    v["computed"] = score.score_vacancy(vacancy_view, criteria, profile)
    save_vacancies(vacancies)
    print(
        f"OK: {args.id} -> external salary estimate "
        f"{args.low}-{args.high}/{args.period} (source: {args.source}). "
        f"New score: {v['computed']['score']} ({v['computed']['classification']})"
    )


def cmd_set_company_reputation(args) -> None:
    """Records employer reputation found by the agent on external sites
    (Glassdoor, Indeed, Trustpilot). Stored at COMPANY level, so it applies to
    all of that company's vacancies at once.

    Those sites cannot be scraped by script — they answer 403 behind bot
    protection — so the agent finds the data by ordinary web search and enters
    it here, on the same principle as `set-salary-estimate`."""
    companies = load_companies()
    slug = common.normalize_company_name(args.company)
    entry = companies.get(slug)
    if entry is None:
        matches = [s for s in companies if args.company.lower().replace(" ", "-") in s]
        hint = f" Similar: {', '.join(matches[:5])}" if matches else ""
        print(f"Company '{args.company}' (slug={slug}) is not in the database.{hint}")
        sys.exit(1)

    reputation = {
        "overall_rating": args.rating,
        "work_life_balance": args.wlb,
        "source": args.source,
        # HOW the numbers were obtained. An important distinction that surfaced
        # from the owner's question (2026-07-31): "source: Glassdoor" reads as
        # "the agent opened the Glassdoor page and looked", whereas in fact
        # Glassdoor answers 403 to any script and the numbers come from SEARCH
        # RESULT SNIPPETS. That is second-hand: if a snippet is stale, or the
        # search engine pulled the number out of a different context, the agent
        # will not notice. Data must be honest about its own reliability.
        #   web_search  - from search results; the primary source was NOT opened
        #   direct      - the primary source page was actually read
        #   owner       - the owner said so personally
        "retrieval": args.retrieval,
        "review_count": args.reviews,
        "red_flags": [f.strip() for f in (args.red_flags or "").split(",") if f.strip()],
        "notes": args.notes or "",
        "checked_at": now_iso(),
    }
    entry["reputation"] = reputation
    save_companies(companies)

    # Rescore every vacancy of this company at once, so the effect is visible
    # immediately rather than after the next pipeline.py run.
    vacancies = load_vacancies()
    criteria = score.load_criteria()
    profile = score.load_profile()
    updated = 0
    for vid in entry.get("vacancy_ids", []):
        v = vacancies.get(vid)
        if not v:
            continue
        vacancy_view = {k: val for k, val in v.items() if k not in ("computed", "manual")}
        vacancy_view["_company_reputation"] = reputation
        v["computed"] = score.score_vacancy(vacancy_view, criteria, profile)
        updated += 1
    save_vacancies(vacancies)

    print(
        f"OK: {entry['name']} -> rating={args.rating} wlb={args.wlb} "
        f"(source: {args.source}). Vacancies rescored: {updated}"
    )


def attach_company_reputation(vacancies: dict, companies: dict) -> None:
    """Pushes company reputation into each of its vacancies before scoring.
    Called by the pipeline: reputation lives at company level, while score is
    computed per vacancy."""
    by_slug = {}
    for slug, entry in companies.items():
        payload = {}
        if entry.get("reputation"):
            payload["reputation"] = entry["reputation"]
        if entry.get("intel"):
            payload["intel"] = entry["intel"]
        if payload:
            by_slug[slug] = payload
    for v in vacancies.values():
        payload = by_slug.get(common.normalize_company_name(v.get("company")), {})
        if payload.get("reputation"):
            v["_company_reputation"] = payload["reputation"]
        else:
            v.pop("_company_reputation", None)
        if payload.get("intel"):
            v["_company_intel"] = payload["intel"]
        else:
            v.pop("_company_intel", None)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Manage the Work IDE knowledge base")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("stats", help="Summary statistics for the knowledge base"
                   ).set_defaults(func=cmd_stats)

    p_list = sub.add_parser("list", help="List vacancies, sorted by score")
    p_list.add_argument("--classification", default=None, choices=[
        "hot_lead", "worth_a_look", "long_shot", "low_priority", "rejected"
    ])
    p_list.add_argument("--limit", type=int, default=20)
    p_list.add_argument("--include-duplicates", action="store_true",
                        help="Do not hide records marked as duplicates")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="The full vacancy record, by id")
    p_show.add_argument("--id", required=True)
    p_show.set_defaults(func=cmd_show)

    p_status = sub.add_parser("set-status",
                              help="Change a vacancy's manual.status/notes")
    p_status.add_argument("--id", required=True)
    p_status.add_argument("--status", required=True)
    p_status.add_argument("--notes", default=None)
    p_status.set_defaults(func=cmd_set_status)

    p_salary = sub.add_parser(
        "set-salary-estimate",
        help="Record a pay range found by hand (e.g. on Glassdoor) for a vacancy "
             "that states no rate",
    )
    p_salary.add_argument("--id", required=True)
    p_salary.add_argument("--low", type=float, required=True)
    p_salary.add_argument("--high", type=float, required=True)
    p_salary.add_argument("--period", choices=["year", "month", "hour"], default="year")
    p_salary.add_argument("--source", required=True, help="For example: Glassdoor")
    p_salary.add_argument("--note", default=None)
    p_salary.set_defaults(func=cmd_set_salary_estimate)

    p_rep = sub.add_parser(
        "set-company-reputation",
        help="Record company reputation from external sources (Glassdoor etc.)",
    )
    p_rep.add_argument("--company", required=True,
                       help="Company name as it appears in the database")
    p_rep.add_argument("--rating", type=float, default=None,
                       help="Overall rating, 1..5")
    p_rep.add_argument("--wlb", type=float, default=None, help="Work-life balance 1..5")
    p_rep.add_argument("--source", required=True,
                       help="Primary source of the data, for example: Glassdoor")
    p_rep.add_argument(
        "--retrieval",
        choices=["web_search", "direct", "owner"],
        default="web_search",
        help="HOW the numbers were obtained: web_search — from search results "
             "(the primary source was not opened, so the data is second-hand); "
             "direct — the page was actually read; owner — the owner said so",
    )
    p_rep.add_argument("--reviews", type=int, default=None,
                       help="Number of reviews")
    p_rep.add_argument("--red-flags", default=None,
                       help="Comma-separated: layoffs,toxic,...")
    p_rep.add_argument("--notes", default=None)
    p_rep.set_defaults(func=cmd_set_company_reputation)

    return p


def main(argv: Optional[list] = None) -> None:
    import identity as identity_mod

    parser = build_parser()
    identity_mod.add_identity_arg(parser)
    args = parser.parse_args(argv)
    identity_mod.activate_or_exit(getattr(args, "identity", None))
    args.func(args)


if __name__ == "__main__":
    main()
