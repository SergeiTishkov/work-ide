"""
Orchestrates the Work IDE research cycle.

python tools/pipeline.py            -> the full cycle: fetch from every enabled
                                       source -> normalize -> merge into the
                                       knowledge base -> rescore THE WHOLE base
                                       (not only new records, so that
                                       improvements to criteria.yaml apply
                                       retroactively) -> rebuild companies.json
                                       -> the selection the app lists.

python tools/pipeline.py --top      -> the top vacancies first (the owner,
                                       2026-10-17): fetch every source but
                                       LinkedIn -> score -> read the
                                       descriptions the remote check needs ->
                                       the AI check of the top classes ->
                                       links, application channels, company
                                       facts for the top only -> the
                                       selection the app lists.
python tools/pipeline.py --linkedin -> LinkedIn, beside any other run (the
                                       owner, 2026-10-20): fetch its window
                                       without holding the base, then wait
                                       for the base, merge, and do the top
                                       run's steps on what it brought.
python tools/pipeline.py --rest     -> everything the top run left: the whole
                                       base rescored, links, descriptions,
                                       the AI check of what rose to the top;
                                       a "rebuild" selection.
                                       remote_unconfirmed gets nothing more.

It never fails wholesale because one source failed: each source is wrapped in
try/except, the error lands in the identity's state file, and the pipeline
carries on.
"""
from __future__ import annotations

import argparse
import contextlib
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import fetch_4dayweek  # noqa: E402
import fetch_arbeitnow  # noqa: E402
import fetch_ats  # noqa: E402
import fetch_himalayas  # noqa: E402
import fetch_hn_whoishiring  # noqa: E402
import fetch_jobicy  # noqa: E402
import fetch_linkedin  # noqa: E402
import fetch_contractoruk  # noqa: E402
import fetch_devitjobs  # noqa: E402
import fetch_jobs_ch  # noqa: E402
import fetch_jobserve  # noqa: E402
import fetch_landing_jobs  # noqa: E402
import fetch_mycareersfuture  # noqa: E402
import fetch_outside_ir35  # noqa: E402
import fetch_reed  # noqa: E402
import fetch_remoterocketship  # noqa: E402
import fetch_rss_boards  # noqa: E402
import fetch_workingnomads  # noqa: E402
import fetch_remoteok  # noqa: E402
import fetch_remotive  # noqa: E402
import fetch_wwr  # noqa: E402
import kb  # noqa: E402
import company_intel  # noqa: E402
import apply_channels  # noqa: E402
import enrich_descriptions  # noqa: E402
import ai_brief  # noqa: E402
import ai_screen  # noqa: E402
import link_check  # noqa: E402
import normalize  # noqa: E402
import score  # noqa: E402
import progress  # noqa: E402
import runstate  # noqa: E402
import selections  # noqa: E402

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
    # The UK, added 2026-09-08. Three of the four are contract boards:
    # day rates and IR35 status rather than payrolled employment.
    "contractoruk": fetch_contractoruk.fetch,
    "reed": fetch_reed.fetch,
    "jobserve": fetch_jobserve.fetch,
    "outside_ir35": fetch_outside_ir35.fetch,
    # Filters by engagement for real — part-time and contract as a field, not
    # a phrase. Added 2026-09-13 for a search looking for side work.
    "remoterocketship": fetch_remoterocketship.fetch,
}

# The classes the top run works on (the owner, 2026-10-17: "collect, check
# remoteness by script, check the remote ones with AI, polish, CVs; the rest
# afterwards"). remote_unconfirmed gets its description read once, in the run
# that brought it, and nothing more.
TOP_CLASSES = ai_screen.SCREENED_CLASSES
# How far back LinkedIn is asked for postings (linkedin_window): from the day
# of the last collection that covered it to today, both days included; the
# full window when there was none, or the base holds no LinkedIn vacancy any
# more. The owner, 2026-10-17: a first collection that asks for a day or two
# misses the long-open roles that always take CVs; one after a collection
# yesterday needs yesterday too, for what was posted after it. A week is the
# full window and the cap (the owner, 2026-10-18: a week takes hours
# already, a month is out of reach; it was 30 for a day). Before 2026-10-17
# every run asked for 7 days.
LINKEDIN_FULL_DAYS = 7
# LinkedIn is read to the end of its window in every mode, the top run
# included: the owner, 2026-10-18, had the 25-minute budget of the top run
# (2026-10-17) removed.
# The top run's budgets: pages read for the remote check, postings the AI
# reads. What is left waits for the rest run.
TOP_DESCRIPTION_LIMIT = 300
TOP_WANTED_LIMIT = 200
# The AI limit is high on purpose: the CV batch starts after this run, and a
# vacancy it picks should have been read. 2026-10-17: 462 to read, a limit of
# 400 left a long_shot unread that the batch then made a CV for; 400 took
# 5:39 at $3.14.
TOP_AI_LIMIT = 1000


def _parse_stamp(stamp) -> Optional[datetime]:
    if not stamp:
        return None
    try:
        then = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    return then if then.tzinfo else then.replace(tzinfo=timezone.utc)


def linkedin_covered_to(state: dict):
    """Until when LinkedIn's postings were fetched without a gap. A fetch that
    failed leaves it where it was."""
    return (state.get("linkedin_covered_to")
            or (state.get("sources", {}).get("linkedin") or {}).get("last_success"))


def linkedin_window(state: dict, vacancies: dict, now: Optional[datetime] = None) -> int:
    """Days LinkedIn is asked for: the days from the local date of
    linkedin_covered_to to today, both included, at most LINKEDIN_FULL_DAYS;
    LINKEDIN_FULL_DAYS when nothing was collected yet or no LinkedIn vacancy
    is left in the base."""
    return linkedin_window_of(
        state, any(v.get("source") == "linkedin" for v in vacancies.values()), now)


def linkedin_window_of(state: dict, base_holds_linkedin: bool, now: Optional[datetime] = None) -> int:
    """linkedin_window, told whether the base holds a LinkedIn vacancy rather
    than handed the base (the LinkedIn run reads it before it may load it)."""
    now = now or datetime.now(timezone.utc)
    covered = _parse_stamp(linkedin_covered_to(state))
    if covered is None or not base_holds_linkedin:
        return LINKEDIN_FULL_DAYS
    days = (now.astimezone().date() - covered.astimezone().date()).days + 1
    return max(1, min(LINKEDIN_FULL_DAYS, days))


def note_linkedin_window(state: dict, started: datetime, covered_before) -> None:
    """After a LinkedIn fetch that started at `started` with the window from
    linkedin_window: moves linkedin_covered_to to `started` when it did not
    fail. Otherwise it stays at `covered_before` (linkedin_covered_to read
    before the fetch: the fallback, last_success, has just moved to now and
    would hide the gap), so the next LinkedIn run asks for those days again.
    linkedin_gap records which it was."""
    linkedin = state.get("sources", {}).get("linkedin") or {}
    if not linkedin.get("consecutive_failures"):
        state["linkedin_covered_to"] = started.isoformat()
        state["linkedin_gap"] = False
    else:
        if covered_before:
            state["linkedin_covered_to"] = covered_before
        state["linkedin_gap"] = True


def linkedin_window_text(days: int) -> str:
    """The fetch stage's words for the window; the summary repeats them."""
    text = f"LinkedIn: posted in the last {days} day{'s' if days > 1 else ''}"
    if days >= LINKEDIN_FULL_DAYS:
        text += ", the full window"
    return text


def collected_text(state: dict, days: Optional[int], linkedin_apart: bool = False) -> str:
    """What the run collected, in the words the summary to the person repeats
    (the owner, 2026-10-17: say after every collection how many days of
    vacancies were collected). linkedin_apart: the top run, which leaves
    LinkedIn to its own run."""
    if linkedin_apart:
        return ("LinkedIn is not in this run: it is fetched by its own run beside it "
                "(pipeline.py --linkedin); the other sources serve their whole current feed")
    if not days:
        return "LinkedIn not asked; the other sources serve their whole current feed"
    text = f"{linkedin_window_text(days)} - the days since the last collection, both included"
    if days >= LINKEDIN_FULL_DAYS:
        text = (f"{linkedin_window_text(days)} - no earlier collection to start from, "
                f"or it was {LINKEDIN_FULL_DAYS} days ago or more")
    if (state.get("sources", {}).get("linkedin") or {}).get("consecutive_failures"):
        text += "; the fetch failed, the next run asks for the window again"
    return text + "; the other sources serve their whole current feed"


def top_subset(vacancies: dict, extra=()) -> dict:
    """The top classes, plus the vacancies named in `extra` (what this run
    fetched); the records are shared with `vacancies`."""
    extra = set(extra)
    return {vid: v for vid, v in vacancies.items()
            if vid in extra or (v.get("computed") or {}).get("classification") in TOP_CLASSES}


def screened_subset(vacancies: dict) -> dict:
    """What the AI check may have read: the top classes and the stretches
    waiting for a read (score.STRETCH_UNREAD); taken before the rescore that
    settles the stretches."""
    return {vid: v for vid, v in vacancies.items()
            if (v.get("computed") or {}).get("classification") in TOP_CLASSES
            or (v.get("computed") or {}).get("screen_wanted")}


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
    tick = progress.Progress(len(vacancies), "rescore")
    for v in vacancies.values():
        vacancy_view = {k: val for k, val in v.items() if k != "computed"}
        v["computed"] = score.score_vacancy(vacancy_view, criteria, profile)
        tick()


def _rescore_stage(vacancies: dict, criteria: dict, profile: dict,
                   companies: Optional[dict], why: str) -> None:
    with progress.stage(f"rescore the base, {why} ({progress.number(len(vacancies))} vacancies)"):
        rescore_all(vacancies, criteria, profile, companies)


def _stats_note(stats) -> str:
    """A stage's own statistics, short: "checked 812, dead 40"."""
    if not isinstance(stats, dict):
        return str(stats)
    return ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in stats.items()
                     if isinstance(v, (int, float, str)))


def ai_check_stage(vacancies: dict, state: dict, limit: Optional[int] = None) -> bool:
    """The screening brief (rewritten when the CV or the identity changed),
    then the cheap model on the top classes (tools/ai_screen.py). True when
    an answer was added, so the caller rescores. Never raises."""
    prefix = common.ACTIVE_IDENTITY
    try:
        with progress.stage("AI brief") as st:
            brief = ai_brief.ensure(prefix)
            st.note = "written" if brief["written"] else "current"
    except Exception as exc:  # noqa: BLE001 — without a brief the check is skipped, not the run
        state["last_ai_screen"] = {"error": f"brief: {type(exc).__name__}: {exc}"}
        return False
    try:
        with progress.stage("AI check of the top") as st:
            stats = ai_screen.screen(vacancies, prefix, ai_brief.load(prefix), limit=limit)
            st.note = _stats_note(stats)
    except Exception as exc:  # noqa: BLE001
        state["last_ai_screen"] = {"error": f"{type(exc).__name__}: {exc}"}
        return False
    state["last_ai_screen"] = {**stats, "at": kb.now_iso()}
    return bool(stats.get("screened"))


def finalize(vacancies: dict, prev_companies: dict, state: dict,
             selection_kind: str = "run",
             description_classes=enrich_descriptions.HEAD_CLASSES) -> int:
    """The shared tail of the cycle: recompute companies, save KB and state,
    record the selection. Returns the selection's id.

    selection_kind is "run" for a fetch cycle and "rebuild" otherwise (see
    tools/selections.py): only a real run moves the baseline of what counts as
    a fresh vacancy, so re-selecting must not make unread vacancies look old."""
    criteria = score.load_criteria()
    profile = score.load_profile()
    # prev_companies holds the reputation gathered so far — it is passed into
    # scoring before companies.json is rebuilt.
    _rescore_stage(vacancies, criteria, profile, prev_companies, "current criteria")
    with progress.stage("mark near-duplicates") as st:
        st.note = f"{kb.mark_duplicates(vacancies)} marked"
    with progress.stage("check links") as st:
        link_stats = link_check.check_links(vacancies)
        st.note = _stats_note(link_stats)
    state["last_link_check"] = link_stats
    with progress.stage("rebuild companies") as st:
        companies = kb.build_companies_from_vacancies(vacancies, prev_companies)
        st.note = f"{progress.number(len(companies))} companies"

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
        # A search that asks about hours also needs the page of a vacancy that
        # already has text but no stated engagement — see worklist().
        with progress.stage("fetch missing descriptions") as st:
            state["last_description_enrich"] = enrich_descriptions.enrich(
                vacancies, classes=description_classes,
                need_employment_types=bool(criteria.get("engagement_fit")))
            st.note = _stats_note(state["last_description_enrich"])
    except Exception as exc:  # noqa: BLE001 — a description must not kill the cycle
        state["last_description_enrich"] = {"error": f"{type(exc).__name__}: {exc}"}
    else:
        # Rescore: the gates now have text they did not have.
        _rescore_stage(vacancies, criteria, profile, prev_companies, "with the new descriptions")

    # The cheap model reads what reached the top classes (tools/ai_screen.py).
    # Answers are kept, so a vacancy is read once per text and brief.
    if ai_check_stage(vacancies, state):
        top = screened_subset(vacancies)
        with progress.stage(f"rescore the top, with the AI check ({progress.number(len(top))} vacancies)"):
            rescore_all(top, criteria, profile, prev_companies)

    # Where a person can apply without going through the board. Last of the
    # enrichment steps and deliberately so: it needs the FINAL classification,
    # since it only spends requests on the top of the shortlist. See
    # tools/apply_channels.py — including why a board answering 200 is not a
    # board.
    try:
        with progress.stage("find direct application channels") as st:
            state["last_apply_channels"] = apply_channels.collect(
                vacancies, criteria["classification_thresholds"]["hot_lead"])
            st.note = _stats_note(state["last_apply_channels"])
    except Exception as exc:  # noqa: BLE001 — a channel must not kill the cycle
        state["last_apply_channels"] = {"error": f"{type(exc).__name__}: {exc}"}

    # Enriching shortlist companies with Wikidata facts (year founded, size).
    #
    # This module used to exist, be documented and be mentioned in the
    # Markdown report — and be called from nowhere. Audit 2026-08-04: of 1083
    # companies, 22 had a known age, and all of them got there through manual
    # runs. Meanwhile the
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
            with progress.stage("company facts from Wikidata") as st:
                state["last_company_intel"] = company_intel.enrich_companies(
                    companies, only_names=shortlist_companies, limit=60
                )
                st.note = _stats_note(state["last_company_intel"])
        except Exception as exc:  # noqa: BLE001 — enrichment must not kill the cycle
            state["last_company_intel"] = {"error": f"{type(exc).__name__}: {exc}"}
        # Rescore after enrichment: company age takes part in the score.
        _rescore_stage(vacancies, criteria, profile, companies, "with company facts")

    return _save_and_select(vacancies, companies, state, selection_kind)


def _save_and_select(vacancies: dict, companies: dict, state: dict, selection_kind: str) -> int:
    """Saves the base and the state, records the selection. Returns the
    selection's id."""
    with progress.stage("save the knowledge base"):
        kb.save_vacancies(vacancies)
        kb.save_companies(companies)
        common.save_json_atomic(common.STATE_PATH, state)
    # What the desktop app lists. After the save: selection rows reference
    # vacancies that must already be in the database.
    with progress.stage(f"record the selection ({selection_kind})") as st:
        selection_id = selections.record(vacancies, state, kind=selection_kind)
        st.note = (f"#{selection_id}, "
                   f"{progress.number(len(selections.listed_vacancies(vacancies)))} listed")

    if not common.INSIGHTS_PATH.exists():
        common.INSIGHTS_PATH.write_text(
            "# Insights — accumulated patterns about the market\n\n"
            "_This file is maintained by hand, by the agent or the owner, from "
            "the analysis of runs and feedback. The pipeline never overwrites it._\n",
            encoding="utf-8",
        )
    return selection_id


def check_source_contracts(names: list) -> dict:
    """The live contract of every source about to be fetched that has one.

    A source can change under its fetcher without breaking it — a shorter page,
    a filter that stopped filtering — and then the only symptom is a thinner
    shortlist. Checked before the fetch, so the log says which source to
    repair (/source-doctor <source>) instead of leaving it to be guessed from
    the numbers. A broken source is still fetched: part of a harvest is better
    than none, and the fetcher's own defences keep rubbish out.
    """
    import source_contract

    results = {}
    with progress.stage("check source contracts") as st:
        for name in names:
            if source_contract.contract_of(name) is None:
                continue
            result = source_contract.check_source(name)
            results[name] = result
            progress.log(f"   {'ok' if result['status'] == 'ok' else '!!'} {name}: "
                         f"{result['status']}"
                         + (f" - {result['detail'][:200]}" if result.get("detail") else ""))
        st.note = ", ".join(f"{n} {r['status']}" for n, r in results.items()) or "none to check"
    return results


def fetched_sources(sources_cfg: list, criteria: dict) -> list:
    """The sources this run fetches: enabled, with a fetcher, and not closed
    for this identity. A source named in the criteria's closed_sources (by its
    name; a website key names no source) is rejected on scoring anyway, so
    fetching it only fills the base (2026-10-17, contractoruk)."""
    closed = criteria.get("closed_sources") or {}
    chosen = []
    for src in sources_cfg:
        name = src.get("name")
        if not src.get("enabled", True) or src.get("kind") == "manual_ingest":
            continue
        if FETCHERS.get(name) is None:
            continue
        if name in closed:
            progress.log(f"   -- {name}: not fetched, closed for this identity: {closed[name]}")
            continue
        chosen.append(src)
    return chosen


def fetch_sources(enabled: list, vacancies: dict, state: dict, criteria: dict, profile: dict,
                  contracts: Optional[dict] = None, overrides: Optional[dict] = None,
                  prefetched: Optional[dict] = None) -> dict:
    """Fetches every source in `enabled`, merges and scores what came.
    `overrides` {source: {param: value}} replaces fetcher parameters for this
    run (the LinkedIn window). `prefetched` {source: (records, note)} is what
    was fetched already (the LinkedIn run's merge): merged without asking.
    Returns {"new", "updated", "fetched", "skipped", "touched": set of vacancy
    ids merged this run}."""
    contracts = contracts or {}
    overrides = overrides or {}
    prefetched = prefetched or {}
    new_count = updated_count = total_fetched = total_skipped = 0
    touched = set()
    for src in enabled:
        name = src.get("name")
        fetch_fn = FETCHERS[name]
        source_started = time.monotonic()
        new_before, updated_before = new_count, updated_count
        params = {**fetch_params(src), **(overrides.get(name) or {})}
        if name in prefetched:
            raw_records, err = prefetched[name]
        elif name == "linkedin":
            with runstate.LinkedInFetch():
                raw_records, err = fetch_source_safely(name, fetch_fn, params)
        else:
            raw_records, err = fetch_source_safely(name, fetch_fn, params)
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
        if name in contracts:
            src_state["contract"] = {key: contracts[name].get(key)
                                     for key in ("status", "detail", "checked_at")}

        for rec in normalized:
            computed = score.score_vacancy(rec, criteria, profile)
            action = kb.merge_vacancy(vacancies, rec, computed)
            touched.add(rec.get("id"))
            if action == "new":
                new_count += 1
            else:
                updated_count += 1

        outcome = (f"{len(normalized)} records, {new_count - new_before} new, "
                   f"{updated_count - updated_before} updated"
                   + (f", {skipped} skipped" if skipped else ""))
        if err:
            outcome += f" - {err.splitlines()[0][:160]}"
        progress.log(f"   {'!!' if fetch_failed else 'ok'} {name}: {outcome} "
                     f"- {progress.duration(time.monotonic() - source_started)}")

    return {"new": new_count, "updated": updated_count, "fetched": total_fetched,
            "skipped": total_skipped, "touched": touched}


def run_pipeline(include_manual_placeholder_note: bool = True,
                 check_contracts: bool = False) -> dict:
    common.ensure_dirs()
    sources_cfg = load_sources_config()
    criteria = score.load_criteria()
    profile = score.load_profile()

    with progress.stage("load the knowledge base") as st:
        vacancies = kb.load_vacancies()
        prev_companies = kb.load_companies()
        st.note = (f"{progress.number(len(vacancies))} vacancies, "
                   f"{progress.number(len(prev_companies))} companies")
    state = common.load_json(common.STATE_PATH, default={"run_count": 0, "sources": {}})
    state.setdefault("sources", {})

    enabled = fetched_sources(sources_cfg, criteria)
    contracts = (check_source_contracts([s.get("name") for s in enabled])
                 if check_contracts else {})
    names = [s.get("name") for s in enabled]
    days = linkedin_window(state, vacancies)
    covered_before = linkedin_covered_to(state)
    started_at = datetime.now(timezone.utc)
    progress.log(f">> fetch {len(enabled)} sources ({linkedin_window_text(days)}): "
                 + ", ".join(names))
    fetch_started = time.monotonic()
    counts = fetch_sources(enabled, vacancies, state, criteria, profile, contracts,
                           overrides={"linkedin": linkedin_params(days)})
    if "linkedin" in names:
        note_linkedin_window(state, started_at, covered_before)
    new_count, updated_count = counts["new"], counts["updated"]
    total_fetched, total_skipped = counts["fetched"], counts["skipped"]

    progress.log(f"ok fetch - {progress.duration(time.monotonic() - fetch_started)} "
                 f"({progress.number(total_fetched)} records, {progress.number(new_count)} new)")
    state["run_count"] = state.get("run_count", 0) + 1
    state["last_run_at"] = kb.now_iso()
    state["last_run_stats"] = {
        "new_vacancies": new_count,
        "updated_vacancies": updated_count,
        "total_fetched_this_run": total_fetched,
        "total_skipped_this_run": total_skipped,
        "linkedin_days": days if "linkedin" in names else None,
    }

    selection_id = finalize(vacancies, prev_companies, state)

    return {
        "new_vacancies": new_count,
        "updated_vacancies": updated_count,
        "total_in_kb": len(vacancies),
        "selection_id": selection_id,
        "collected": collected_text(state, days if "linkedin" in names else None),
        "source_contracts": {name: r["status"] for name, r in contracts.items()},
    }


def linkedin_params(days: int) -> dict:
    """The LinkedIn fetcher's parameters for a run: the window, and the file
    for what each query brought (fetch_linkedin.query_stats_path)."""
    return {"posted_within_days": days, "query_stats_to": fetch_linkedin.query_stats_path()}


def _load():
    common.ensure_dirs()
    with progress.stage("load the knowledge base") as st:
        vacancies = kb.load_vacancies()
        prev_companies = kb.load_companies()
        st.note = (f"{progress.number(len(vacancies))} vacancies, "
                   f"{progress.number(len(prev_companies))} companies")
    state = common.load_json(common.STATE_PATH, default={"run_count": 0, "sources": {}})
    state.setdefault("sources", {})
    return vacancies, prev_companies, state


def run_top(check_contracts: bool = False) -> dict:
    """The top vacancies first (the owner, 2026-10-17: about an hour, daily):
    fetch every source but LinkedIn -> the remote check by script (the pages
    of the top classes and of what this run brought) -> the AI check of the
    top -> links, application channels and company facts of the top ->
    the selection. LinkedIn is its own run (run_linkedin), beside this
    one; the whole base is rescored by the rest run (run_rest)."""
    sources_cfg = load_sources_config()
    criteria = score.load_criteria()
    profile = score.load_profile()
    vacancies, prev_companies, state = _load()

    enabled = [s for s in fetched_sources(sources_cfg, criteria) if s.get("name") != "linkedin"]
    names = [s.get("name") for s in enabled]
    contracts = check_source_contracts(names) if check_contracts else {}
    with progress.stage(f"fetch {len(enabled)} sources (LinkedIn apart)") as st:
        progress.log("   " + ", ".join(names))
        counts = fetch_sources(enabled, vacancies, state, criteria, profile, contracts)
        st.note = (f"{progress.number(counts['fetched'])} records, "
                   f"{progress.number(counts['new'])} new")
    companies = process_top(vacancies, prev_companies, state, criteria, profile, counts["touched"])

    state["run_count"] = state.get("run_count", 0) + 1
    state["last_run_at"] = state["last_top_run_at"] = kb.now_iso()
    state["last_run_stats"] = {
        "mode": "top",
        "new_vacancies": counts["new"],
        "updated_vacancies": counts["updated"],
        "total_fetched_this_run": counts["fetched"],
        "total_skipped_this_run": counts["skipped"],
        "linkedin_days": None,
    }
    selection_id = _save_and_select(vacancies, companies, state, "run")
    return {
        "new_vacancies": counts["new"],
        "updated_vacancies": counts["updated"],
        "total_in_kb": len(vacancies),
        "selection_id": selection_id,
        "collected": collected_text(state, None, linkedin_apart=True),
        "source_contracts": {name: r["status"] for name, r in contracts.items()},
    }


def process_top(vacancies: dict, prev_companies: dict, state: dict, criteria: dict,
                profile: dict, touched) -> dict:
    """The top run's steps after its fetch, on the top classes and what the
    fetch brought (`touched`); the LinkedIn run's merge does the same. Returns
    the rebuilt companies."""
    # The remote check by script: the page of every top vacancy with no text,
    # and of what this run brought into remote_unconfirmed — for a LinkedIn
    # card the page is what says "remote". Older remote_unconfirmed is not
    # read again (the owner, 2026-10-17).
    top = top_subset(vacancies, touched)
    with progress.stage(f"rescore the top ({progress.number(len(top))} vacancies)"):
        rescore_all(top, criteria, profile, prev_companies)
    try:
        with progress.stage("remote check by the descriptions") as st:
            state["last_description_enrich"] = enrich_descriptions.enrich(
                top, limit=TOP_DESCRIPTION_LIMIT, wanted_limit=TOP_WANTED_LIMIT,
                need_employment_types=bool(criteria.get("engagement_fit")))
            st.note = _stats_note(state["last_description_enrich"])
    except Exception as exc:  # noqa: BLE001 — a description must not kill the cycle
        state["last_description_enrich"] = {"error": f"{type(exc).__name__}: {exc}"}
    with progress.stage(f"rescore the top, with the descriptions ({progress.number(len(top))} vacancies)"):
        rescore_all(top, criteria, profile, prev_companies)

    if ai_check_stage(vacancies, state, limit=TOP_AI_LIMIT):
        top = screened_subset(vacancies)
        with progress.stage(f"rescore the top, with the AI check ({progress.number(len(top))} vacancies)"):
            rescore_all(top, criteria, profile, prev_companies)

    with progress.stage("mark near-duplicates") as st:
        st.note = f"{kb.mark_duplicates(vacancies)} marked"
    with progress.stage("check links of the top") as st:
        state["last_link_check"] = link_check.check_links(top_subset(vacancies))
        st.note = _stats_note(state["last_link_check"])
    with progress.stage("rebuild companies") as st:
        companies = kb.build_companies_from_vacancies(vacancies, prev_companies)
        st.note = f"{progress.number(len(companies))} companies"
    try:
        with progress.stage("find direct application channels") as st:
            state["last_apply_channels"] = apply_channels.collect(
                vacancies, criteria["classification_thresholds"]["hot_lead"])
            st.note = _stats_note(state["last_apply_channels"])
    except Exception as exc:  # noqa: BLE001
        state["last_apply_channels"] = {"error": f"{type(exc).__name__}: {exc}"}
    shortlist_companies = {v.get("company") for v in top_subset(vacancies).values()
                           if not v.get("duplicate_of") and v.get("company")}
    if shortlist_companies:
        try:
            with progress.stage("company facts from Wikidata") as st:
                state["last_company_intel"] = company_intel.enrich_companies(
                    companies, only_names=shortlist_companies, limit=60)
                st.note = _stats_note(state["last_company_intel"])
        except Exception as exc:  # noqa: BLE001
            state["last_company_intel"] = {"error": f"{type(exc).__name__}: {exc}"}
        top = top_subset(vacancies)
        with progress.stage(f"rescore the top, with company facts ({progress.number(len(top))} vacancies)"):
            rescore_all(top, criteria, profile, companies)
    return companies


def linkedin_staged_path() -> Path:
    """What the LinkedIn run fetched, kept until it is merged."""
    return common.DATA_DIR / "runs" / "linkedin_fetched.json"


def fetch_linkedin_apart() -> Optional[dict]:
    """The LinkedIn run's first half: its window fetched without holding the
    base, so the other runs go on meanwhile, and kept in
    linkedin_staged_path(). Writes nothing else: the window is read from the
    state, and the base is only asked whether it holds a LinkedIn vacancy.
    One LinkedIn fetch at a time on the machine (runstate.LinkedInFetch).
    None when this identity does not fetch LinkedIn."""
    criteria = score.load_criteria()
    linkedin = [s for s in fetched_sources(load_sources_config(), criteria)
                if s.get("name") == "linkedin"]
    if not linkedin:
        return None
    import db

    state = common.load_json(common.STATE_PATH, default={})
    days = linkedin_window_of(state, db.any_from_source("linkedin"))
    covered_before = linkedin_covered_to(state)
    path = linkedin_staged_path()
    if path.exists():
        progress.log("   an earlier LinkedIn fetch was never merged; its days are asked again")
    with runstate.LinkedInFetch():
        started_at = datetime.now(timezone.utc)
        with progress.stage(f"fetch LinkedIn ({linkedin_window_text(days)})") as st:
            records, note = fetch_source_safely(
                "linkedin", FETCHERS["linkedin"], {**fetch_params(linkedin[0]), **linkedin_params(days)})
            st.note = f"{progress.number(len(records))} records"
    staged = {"started_at": started_at.isoformat(), "days": days, "covered_before": covered_before,
              "note": note, "records": records}
    common.save_json_atomic(path, staged)
    return staged


def merge_linkedin(staged: dict) -> dict:
    """The LinkedIn run's second half, holding the base: what was fetched is
    merged, the window noted, and the top run's steps done on the top classes
    and what LinkedIn brought (process_top). A "rebuild" selection: the
    baseline of what is fresh stays the top run's, so its vacancies stay
    fresh, and so do LinkedIn's new ones."""
    sources_cfg = load_sources_config()
    criteria = score.load_criteria()
    profile = score.load_profile()
    linkedin = [s for s in fetched_sources(sources_cfg, criteria) if s.get("name") == "linkedin"]
    records, note = staged.get("records") or [], staged.get("note")
    started_at = _parse_stamp(staged.get("started_at")) or datetime.now(timezone.utc)
    days = staged.get("days")
    if not records:
        # Nothing to merge: the failure is recorded, the base is not loaded.
        state = common.load_json(common.STATE_PATH, default={"run_count": 0, "sources": {}})
        state.setdefault("sources", {})
        fetch_sources(linkedin, {}, state, criteria, profile, prefetched={"linkedin": (records, note)})
        note_linkedin_window(state, started_at, staged.get("covered_before"))
        common.save_json_atomic(common.STATE_PATH, state)
        linkedin_staged_path().unlink(missing_ok=True)
        return {"new_vacancies": 0, "collected": collected_text(state, days)}

    vacancies, prev_companies, state = _load()
    with progress.stage("merge LinkedIn's vacancies") as st:
        counts = fetch_sources(linkedin, vacancies, state, criteria, profile,
                               prefetched={"linkedin": (records, note)})
        st.note = (f"{progress.number(counts['fetched'])} records, "
                   f"{progress.number(counts['new'])} new")
    note_linkedin_window(state, started_at, staged.get("covered_before"))
    companies = process_top(vacancies, prev_companies, state, criteria, profile, counts["touched"])
    state["last_linkedin_run_at"] = kb.now_iso()
    state["last_linkedin_stats"] = {"new_vacancies": counts["new"], "updated_vacancies": counts["updated"],
                                    "total_fetched_this_run": counts["fetched"], "linkedin_days": days}
    selection_id = _save_and_select(vacancies, companies, state, "rebuild")
    linkedin_staged_path().unlink(missing_ok=True)
    return {"new_vacancies": counts["new"], "updated_vacancies": counts["updated"],
            "total_in_kb": len(vacancies), "selection_id": selection_id,
            "collected": collected_text(state, days)}


def run_rest() -> dict:
    """What the top run left: the full tail (finalize) — the whole
    base rescored, every link, the pages of the top classes
    (remote_unconfirmed no more), the AI check of what rose to the top. A
    "rebuild" selection, so what the top run marked fresh stays fresh.

    It fetched LinkedIn's window again after a failed fetch until 2026-10-20;
    LinkedIn has its own run since, and a failed one leaves the coverage
    where it was, so the next asks for those days (note_linkedin_window)."""
    vacancies, prev_companies, state = _load()
    selection_id = finalize(
        vacancies, prev_companies, state, selection_kind="rebuild",
        description_classes=tuple(c for c in enrich_descriptions.HEAD_CLASSES if c != "remote_unconfirmed"))
    return {"new_vacancies": 0, "total_in_kb": len(vacancies), "selection_id": selection_id,
            "collected": "nothing: the rest run fetches nothing"}


def _run_mode(args, staged: Optional[dict]) -> dict:
    if args.linkedin:
        return merge_linkedin(staged)
    if args.top:
        return run_top(check_contracts=not args.skip_contracts)
    if args.rest:
        return run_rest()
    return run_pipeline(check_contracts=not args.skip_contracts)


def main() -> None:
    import identity as identity_mod

    parser = argparse.ArgumentParser(description="The full Work IDE research cycle")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--skip-contracts", action="store_true",
                        help="do not check the sources' live contracts before fetching "
                             "(when they were just checked with tools/source_contract.py)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--top", action="store_true",
                      help="the top vacancies first, in about an hour (see run_top)")
    mode.add_argument("--rest", action="store_true",
                      help="what the top run left: the whole base (see run_rest)")
    mode.add_argument("--linkedin", action="store_true",
                      help="LinkedIn alone, beside any other run: fetched without holding "
                           "the base, then merged when the base is free (see fetch_linkedin_apart)")
    args = parser.parse_args()
    prefix = identity_mod.activate_or_exit(args.identity)
    if identity_mod.skip_if_inactive(prefix):
        return

    # Mirrored into a file, so a run started by the agent or the app can be
    # followed from outside: tail -f data/identities/<prefix>/runs/pipeline_<time>.log
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    log_path = progress.open_log(common.DATA_DIR / "runs" / f"pipeline_{stamp}.log")
    started = time.monotonic()
    mode_name = "top" if args.top else "rest" if args.rest else "linkedin" if args.linkedin else "full"
    progress.log(f"pipeline ({mode_name}) for '{common.ACTIVE_IDENTITY}' started; log: {log_path}")
    try:
        staged = fetch_linkedin_apart() if args.linkedin else None
        # Marks the run as going in the database (the app's indicator), and
        # refuses to start while another run is alive — of any identity: the
        # base is shared. The LinkedIn run waits for it instead: its fetch
        # is done, and the merge takes minutes.
        if args.linkedin and staged is None:
            result = {"collected": "nothing: this identity does not fetch LinkedIn"}
        else:
            with contextlib.ExitStack() as held:
                run = runstate.PipelineRun(log_path=log_path, wait=args.linkedin)
                if args.linkedin:
                    with progress.stage("wait for the base"):
                        held.enter_context(run)
                else:
                    held.enter_context(run)
                result = _run_mode(args, staged)
    except runstate.AlreadyRunningError as exc:
        progress.log(f"!! not started: {exc}")
        progress.close_log()
        sys.exit(2)
    finally:
        progress.log(f"pipeline finished in {progress.duration(time.monotonic() - started)}")
        progress.close_log()
    print("Pipeline finished:")
    for k, v in result.items():
        print(f"  {k}: {v}")
    # Same idea as the feedback reminder below: what needs a repair is said in
    # the output, with the command that repairs it.
    statuses = result.get("source_contracts") or {}
    broken = [n for n, status in statuses.items() if status == "broken"]
    blocked = [n for n, status in statuses.items() if status == "blocked"]
    if broken:
        print(f"  sources answering differently than their fetchers expect: {', '.join(broken)}"
              f" — repair with /source-doctor <source>")
    if blocked:
        print(f"  sources now refusing anonymous requests: {', '.join(blocked)}"
              f" — tell the owner")
    # A reminder that lives in the output rather than in somebody's memory:
    # feedback left in the app is a bug report against the filter.
    import feedback

    pending = feedback.count()
    if pending["bugged"] or pending["rejected"]:
        print(f"  pending feedback: {pending['bugged']} wrong picks, "
              f"{pending['rejected']} not for me — review with /feedback "
              f"(python tools/feedback.py --identity {common.ACTIVE_IDENTITY} collect)")


if __name__ == "__main__":
    main()
