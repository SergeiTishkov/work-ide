"""
Orchestrates the Work IDE research cycle.

python tools/pipeline.py            -> the full cycle: fetch from every enabled
                                       source -> normalize -> merge into the
                                       knowledge base -> rescore THE WHOLE base
                                       (not only new records, so that
                                       improvements to criteria.yaml apply
                                       retroactively) -> rebuild companies.json
                                       -> report.

It never fails wholesale because one source failed: each source is wrapped in
try/except, the error lands in data/state.json and in the report, and the
pipeline carries on.
"""
from __future__ import annotations

import argparse
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import fetch_4dayweek  # noqa: E402
import fetch_arbeitnow  # noqa: E402
import fetch_ats  # noqa: E402
import fetch_himalayas  # noqa: E402
import fetch_hn_whoishiring  # noqa: E402
import fetch_jobicy  # noqa: E402
import fetch_linkedin  # noqa: E402
import fetch_devitjobs  # noqa: E402
import fetch_jobs_ch  # noqa: E402
import fetch_landing_jobs  # noqa: E402
import fetch_mycareersfuture  # noqa: E402
import fetch_rss_boards  # noqa: E402
import fetch_workingnomads  # noqa: E402
import fetch_remoteok  # noqa: E402
import fetch_remotive  # noqa: E402
import fetch_wwr  # noqa: E402
import kb  # noqa: E402
import company_intel  # noqa: E402
import apply_channels  # noqa: E402
import enrich_descriptions  # noqa: E402
import reputation  # noqa: E402
import link_check  # noqa: E402
import normalize  # noqa: E402
import report  # noqa: E402
import score  # noqa: E402

FETCHERS = {
    "arbeitnow": fetch_arbeitnow.fetch,
    "remoteok": fetch_remoteok.fetch,
    "weworkremotely": fetch_wwr.fetch,
    "hn_whoishiring": fetch_hn_whoishiring.fetch,
    "remotive": fetch_remotive.fetch,
    "jobicy": fetch_jobicy.fetch,
    "himalayas": fetch_himalayas.fetch,
    "ats": fetch_ats.fetch,
    "linkedin": fetch_linkedin.fetch,
    "4dayweek": fetch_4dayweek.fetch,
    "devitjobs": fetch_devitjobs.fetch,
    "jobs_ch": fetch_jobs_ch.fetch,
    "mycareersfuture": fetch_mycareersfuture.fetch,
    "landing_jobs": fetch_landing_jobs.fetch,
    "workingnomads": fetch_workingnomads.fetch,
    "rss_boards": fetch_rss_boards.fetch,
}


def _archive_raw_records(source_name: str, raw_records: list) -> None:
    """An audit trail: the source's raw data as it was at run time, before any
    normalisation or scoring. Not critical to the pipeline — a write error must
    not stop it."""
    if not raw_records:
        return
    try:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = common.RAW_DIR / source_name / f"{date_str}.jsonl"
        common.append_jsonl(path, raw_records)
    except Exception as exc:  # noqa: BLE001 - the audit trail is optional
        common.eprint(f"[pipeline] failed to archive raw records for '{source_name}': {exc}")


def load_sources_config() -> list:
    return common.load_sources()


def fetch_params(src: dict) -> dict:
    """The arguments a fetcher will receive: the endpoint from the shared
    catalogue plus the identity's parameters.

    Before the configs were split, the `url` field in source configuration was
    dead: every fetcher hard-coded its own API_URL, and the pipeline called
    `fetch_fn()` with no arguments at all. Now configuration really does drive
    """
    params = dict(src.get("params") or {})
    # url/urls come from the catalogue, but only if the fetcher accepts them and
    # the identity did not set its own value.
    for key in ("url", "urls"):
        if key in src and key not in params:
            params[key] = src[key]
    return params


def fetch_source_safely(name: str, fetch_fn, params: Optional[dict] = None):
    """Never raises — network or parsing bugs in one source must not bring down
    the whole research cycle.

    A parameter the fetcher does not know is no reason to fail: the config may
    have moved ahead of the code, or the other way round. Such a parameter is
    dropped with a log line, and collection continues with what the fetcher does
    """
    params = params or {}
    try:
        try:
            records, note = fetch_fn(**params)
        except TypeError as exc:
            if params and "unexpected keyword argument" in str(exc):
                common.eprint(
                    f"[pipeline] source '{name}' does not accept some parameters "
                    f"({exc}); calling without them"
                )
                records, note = fetch_fn()
            else:
                raise
        return records or [], note
    except Exception as exc:  # noqa: BLE001 - deliberately broad at a source boundary
        tb = traceback.format_exc(limit=3)
        common.eprint(f"[pipeline] source '{name}' crashed:\n{tb}")
        return [], f"CRASHED: {type(exc).__name__}: {exc}"


def rescore_all(vacancies: dict, criteria: dict, profile: dict, companies: Optional[dict] = None) -> None:
    """Retroactive rescoring of THE WHOLE base — if criteria.yaml or profile.yaml
    have grown smarter since the last run, old vacancies must get the current
    verdict too, not only new ones. Used both by the full pipeline and by
    tools/ingest_manual.py.

    companies is needed in order to feed employer reputation into scoring — it
    is stored per company, while score is computed per vacancy."""
    if companies:
        kb.attach_company_reputation(vacancies, companies)
    for v in vacancies.values():
        vacancy_view = {k: val for k, val in v.items() if k not in ("computed", "manual")}
        v["computed"] = score.score_vacancy(vacancy_view, criteria, profile)


def finalize_and_report(vacancies: dict, prev_companies: dict, state: dict) -> str:
    """The shared tail of the cycle: recompute companies, save KB and state,
    generate the report. Returns the path to the report."""
    criteria = score.load_criteria()
    profile = score.load_profile()
    # prev_companies holds the reputation gathered so far — it is passed into
    # scoring before companies.json is rebuilt.
    rescore_all(vacancies, criteria, profile, prev_companies)
    kb.mark_duplicates(vacancies)
    link_stats = link_check.check_links(vacancies)
    state["last_link_check"] = link_stats
    companies = kb.build_companies_from_vacancies(vacancies, prev_companies)

    # Fetching descriptions for shortlist vacancies that arrived without one.
    #
    # LinkedIn returns cards, and a card has no description. Measured
    # 2026-08-11: 1023 such cards in the base, 251 of them in the head of the
    # shortlist — every gate that reads text was deciding those blind.
    #
    # This runs AFTER scoring on purpose: which cards reached the shortlist is a
    # far better signal for spending a request than guessing from a title, and
    # it is a signal the fetcher does not have. Details in
    # tools/enrich_descriptions.py.
    try:
        state["last_description_enrich"] = enrich_descriptions.enrich(vacancies)
    except Exception as exc:  # noqa: BLE001 — a description must not kill the cycle
        state["last_description_enrich"] = {"error": f"{type(exc).__name__}: {exc}"}
    else:
        # Rescore: the gates now have text they did not have.
        rescore_all(vacancies, criteria, profile, prev_companies)

    # Where a person can apply without going through the board. Last of the
    # enrichment steps and deliberately so: it needs the FINAL classification,
    # since it only spends requests on the top of the shortlist. See
    # tools/apply_channels.py — including why a board answering 200 is not a
    # board.
    try:
        state["last_apply_channels"] = apply_channels.collect(
            vacancies, criteria["classification_thresholds"]["hot_lead"])
    except Exception as exc:  # noqa: BLE001 — a channel must not kill the cycle
        state["last_apply_channels"] = {"error": f"{type(exc).__name__}: {exc}"}

    # Enriching shortlist companies with Wikidata facts (year founded, size).
    #
    # This module used to exist, be documented and be mentioned in the report —
    # and be called from nowhere. Audit 2026-08-04: of 1083 companies, 22 had a
    # known age, and all of them got there through manual runs. Meanwhile the
    # trait "mature company, 10+ years" is written into ideal_company_traits
    # outright — the system was asking for what it did not collect.
    #
    # ONLY companies in the visible part of the shortlist are enriched: the rest
    # are filtered out anyway, and Wikidata does not deserve hundreds of pointless
    # requests. A 30-day cache, on the same principle as link_check.
    shortlist_companies = {
        v.get("company")
        for v in vacancies.values()
        if (v.get("computed") or {}).get("classification") in
           ("hot_lead", "worth_a_look", "long_shot")
        and not v.get("duplicate_of") and v.get("company")
    }
    if shortlist_companies:
        try:
            state["last_company_intel"] = company_intel.enrich_companies(
                companies, only_names=shortlist_companies, limit=60
            )
        except Exception as exc:  # noqa: BLE001 — enrichment must not kill the cycle
            state["last_company_intel"] = {"error": f"{type(exc).__name__}: {exc}"}
        # Rescore after enrichment: company age takes part in the score.
        rescore_all(vacancies, criteria, profile, companies)

    # Reputation of shortlist companies is tracked separately, because it cannot
    # be collected by script (the sites answer 403) while the system is obliged
    # to know that it has not been collected. What remains to check goes into
    # state and is printed in the report: work not done must be visible rather
    # than living in somebody's memory. Details in tools/reputation.py.
    state["reputation_coverage"] = reputation.coverage(vacancies, companies)
    state["reputation_worklist"] = [
        item["company"] for item in reputation.worklist(vacancies, companies)
    ]

    kb.save_vacancies(vacancies)
    kb.save_companies(companies)
    common.save_json_atomic(common.STATE_PATH, state)

    if not (common.KNOWLEDGE_DIR / "insights.md").exists():
        (common.KNOWLEDGE_DIR / "insights.md").write_text(
            "# Insights — accumulated patterns about the market\n\n"
            "_This file is maintained by hand, by the agent or the owner, from "
            "the analysis of reports. The pipeline never overwrites it._\n",
            encoding="utf-8",
        )

    # Every shortlist this identity is configured to produce. An identity that
    # has said nothing about markets gets exactly one file, at the historical
    # path — see tools/segments.py.
    written = report.write_segmented_reports(vacancies, companies, state)
    state["last_reports"] = {slug or "latest": str(path)
                             for slug, path in written.items()}
    return str(written.get("") or next(iter(written.values())))


def run_pipeline(include_manual_placeholder_note: bool = True) -> dict:
    common.ensure_dirs()
    sources_cfg = load_sources_config()
    criteria = score.load_criteria()
    profile = score.load_profile()

    vacancies = kb.load_vacancies()
    prev_companies = kb.load_companies()
    state = common.load_json(common.STATE_PATH, default={"run_count": 0, "sources": {}})
    state.setdefault("sources", {})

    new_count = 0
    updated_count = 0
    total_fetched = 0
    total_skipped = 0

    for src in sources_cfg:
        name = src.get("name")
        if not src.get("enabled", True) or src.get("kind") == "manual_ingest":
            continue
        fetch_fn = FETCHERS.get(name)
        if fetch_fn is None:
            continue

        raw_records, err = fetch_source_safely(name, fetch_fn, fetch_params(src))
        _archive_raw_records(name, raw_records)
        normalized, skipped = normalize.normalize_batch(raw_records)
        total_fetched += len(normalized)
        total_skipped += skipped

        src_state = state["sources"].setdefault(name, {"consecutive_failures": 0})
        fetch_failed = bool(err) and not normalized
        src_state["consecutive_failures"] = (
            src_state.get("consecutive_failures", 0) + 1 if fetch_failed else 0
        )
        src_state["last_error"] = err
        src_state["fetched_count"] = len(normalized)
        src_state["skipped_count"] = skipped
        src_state["last_attempt_at"] = kb.now_iso()
        if not fetch_failed:
            src_state["last_success"] = kb.now_iso()

        for rec in normalized:
            computed = score.score_vacancy(rec, criteria, profile)
            action = kb.merge_vacancy(vacancies, rec, computed)
            if action == "new":
                new_count += 1
            else:
                updated_count += 1

    state["run_count"] = state.get("run_count", 0) + 1
    state["last_run_at"] = kb.now_iso()
    state["last_run_stats"] = {
        "new_vacancies": new_count,
        "updated_vacancies": updated_count,
        "total_fetched_this_run": total_fetched,
        "total_skipped_this_run": total_skipped,
    }

    report_path = finalize_and_report(vacancies, prev_companies, state)

    return {
        "new_vacancies": new_count,
        "updated_vacancies": updated_count,
        "total_in_kb": len(vacancies),
        "report_path": report_path,
    }


def main() -> None:
    import identity as identity_mod

    parser = argparse.ArgumentParser(description="The full Work IDE research cycle")
    identity_mod.add_identity_arg(parser)
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)

    result = run_pipeline()
    print("Pipeline finished:")
    for k, v in result.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
