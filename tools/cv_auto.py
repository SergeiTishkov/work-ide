"""
Which vacancies of the shortlist get a CV and a cover letter without a
click: the identity's own filters (the owner, 2026-10-13).

    python tools/cv_auto.py --identity sharp          # what would be generated
    python tools/cv_auto.py --identity sharp --json   # for the app

The filters live in the identity's profile, as many as wanted; a vacancy that
matches ANY of them is picked:

    cv:
      auto:
        documents: [cv, letter]     # what to generate; both when omitted
        filters:
          - markets: [worldwide]    # the markets of the app, by slug
          - classes: [hot_lead, worth_a_look, long_shot]
          - markets: [worldwide]
            sources: [devitjobs.com, weworkremotely.com]   # a board or its site
            classes: [hot_lead]
          - classes: [hot_lead, worth_a_look, long_shot]
            company_kinds: [agency, reposter, other]       # no freelance marketplaces

Inside one filter everything named must match; a key left out matches
anything. `company_kinds` are the groups of the app's "Company" drop-down
(config/company_kinds.yaml). Candidates are the vacancies of the latest
selection with no answer yet; a document already in the vacancy's folder
(tools/documents.py) is not made again, nor one whose vacancy was found gone
(an error in its log).

THE PERSON'S VACANCIES ARE LEFT ALONE (the owner, 2026-10-22, task 0087):
"the person has most likely worked with the vacancy already, and that's it".
Neither document is made for a vacancy that has
- any feedback (a status other than "new");
- a CV or a cover letter of the person's: a version the batch did not make
  (documents.py marks the batch's "Made automatically."). A CV alone is
  enough to make no letter, and the other way round;
- a CV or a letter task in the queue (tools/taskq.py), queued or running.
left_alone() says which; the batch asks it again before every document, after
a pause too, since the person may order a document while the batch runs. On
2026-10-22 it did not, and the batch made a CV and a letter for INSO while
the owner's own two tasks for it were queued.

EVERY MATCH, NOT ONLY THE FRESH ONES (the owner, 2026-10-21: "every such
vacancy must have a CV/CL"). Until then a filter already applied took only
the vacancies the latest run brought in for the first time, and one that
rose into a class later (a rescore, a description fetched, the AI read of a
stretch role) never got documents: 14 of 16 that day. The documents already
made are what keeps a vacancy from being made twice.

After a collection ends the app starts tools/cv_batch.py for the identity,
which asks this module what to make and makes it, one document at a time.
Without `cv.auto` nothing is picked.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import db  # noqa: E402
import documents  # noqa: E402
import selections  # noqa: E402

FILTER_KEYS = ("markets", "sources", "classes", "company_kinds")
DOCUMENT_KINDS = ("cv", "letter")


class AutoError(ValueError):
    pass


def auto_settings(profile: dict) -> Optional[dict]:
    """{"documents": [...], "filters": [{markets, sources, classes}]}, or None
    when the profile asks for nothing."""
    auto = (profile.get("cv") or {}).get("auto")
    if not auto:
        return None
    if not isinstance(auto, dict):
        raise AutoError("cv.auto must be a mapping with `filters`")
    kinds = auto.get("documents") or list(DOCUMENT_KINDS)
    unknown = [k for k in kinds if k not in DOCUMENT_KINDS]
    if unknown:
        raise AutoError(f"cv.auto.documents: unknown {unknown}; use {list(DOCUMENT_KINDS)}")
    filters = auto.get("filters") or []
    if not isinstance(filters, list) or not filters:
        raise AutoError("cv.auto.filters must be a non-empty list of filters")
    for index, one in enumerate(filters):
        if not isinstance(one, dict):
            raise AutoError(f"cv.auto.filters[{index}] must be a mapping")
        extra = [k for k in one if k not in FILTER_KEYS]
        if extra:
            raise AutoError(f"cv.auto.filters[{index}]: unknown keys {extra}; use {list(FILTER_KEYS)}")
        for key in FILTER_KEYS:
            if key in one and not isinstance(one[key], list):
                raise AutoError(f"cv.auto.filters[{index}].{key} must be a list")
        unknown = [k for k in one.get("company_kinds") or [] if k not in selections.COMPANY_KINDS]
        if unknown:
            raise AutoError(f"cv.auto.filters[{index}].company_kinds: unknown {unknown}; "
                            f"use {list(selections.COMPANY_KINDS)}")
    return {"documents": list(kinds), "filters": filters}


def _source_keys(names: List[str]) -> List[str]:
    """A board by its key ("devitjobs") or by its site ("devitjobs.com")."""
    sites = common.source_sites()
    keys = []
    for name in names:
        name = str(name).strip().lower()
        matched = [key for key, site in sites.items()
                   if key == name or name in [s.strip().lower() for s in str(site).split(",")]]
        keys += matched or [name]
    return keys


def manual_tasks(prefix: str, vacancy_ids: List[str], tasks_conn=None) -> set:
    """The vacancies with a CV or a letter task queued or running. The
    batch makes its documents itself, not through the queue, so each such
    task is the person's."""
    if not vacancy_ids:
        return set()
    import taskq
    if tasks_conn is None:
        if not taskq.path().exists():
            return set()
        with taskq.session() as conn:
            return manual_tasks(prefix, vacancy_ids, conn)
    marks = ",".join("?" * len(taskq.ACTIVE))
    rows = tasks_conn.execute(
        f"SELECT DISTINCT vacancy_id FROM tasks WHERE kind IN ('cv', 'letter') AND identity = ? "
        f"AND state IN ({marks})", (prefix, *taskq.ACTIVE)).fetchall()
    return {r[0] for r in rows} & set(vacancy_ids)


def answered(conn, vacancy_ids: List[str]) -> set:
    """The vacancies with feedback: a status other than "new"."""
    if not vacancy_ids:
        return set()
    marks = ",".join("?" * len(vacancy_ids))
    rows = conn.execute(
        f"SELECT vacancy_id FROM vacancy_identity WHERE identity_id = ? AND feedback_status <> 'new' "
        f"AND vacancy_id IN ({marks})", (db.identity(), *vacancy_ids)).fetchall()
    return {r[0] for r in rows}


def left_alone(conn, prefix: str, vacancy_ids: List[str], base: Optional[Path] = None,
               tasks_conn=None, existing: Optional[dict] = None) -> dict:
    """{vacancy id: why the batch makes nothing for it} for the vacancies
    the person works with (THE PERSON'S VACANCIES ARE LEFT ALONE)."""
    if existing is None:
        existing = documents.state(prefix, list(vacancy_ids), base)
    why = {}
    for vacancy_id in answered(conn, vacancy_ids):
        why[vacancy_id] = "the person gave feedback"
    for vacancy_id in vacancy_ids:
        if vacancy_id not in why and (existing.get(vacancy_id) or {}).get("by_person"):
            why[vacancy_id] = "the person made a document for it"
    for vacancy_id in manual_tasks(prefix, vacancy_ids, tasks_conn):
        why.setdefault(vacancy_id, "the person generates a document for it")
    return why


def pick(conn, settings: dict, prefix: str, base: Optional[Path] = None, tasks_conn=None) -> List[dict]:
    """[{"vacancy_id", "title", "company", "class", "documents": [kinds to
    make]}] in the order of the app's list (the class, then the score), each
    vacancy once: every vacancy of the latest selection with no answer that
    matches a filter and lacks a document, except those left_alone()."""
    selection_id = selections.latest_selection_id(conn)
    if selection_id is None:
        return []
    all_markets = [r[0] for r in conn.execute(
        "SELECT slug FROM selection_segments WHERE selection_id = ? ORDER BY position", (selection_id,))]
    classes = [r[0] for r in conn.execute(
        "SELECT DISTINCT class FROM selection_items WHERE selection_id = ?", (selection_id,))]
    picked: dict = {}
    for one in settings["filters"]:
        markets = one.get("markets") or all_markets
        unknown = [m for m in markets if m not in all_markets]
        if unknown:
            raise AutoError(f"cv.auto: unknown markets {unknown}; this identity has {all_markets}")
        kinds = one.get("company_kinds")
        chosen = selections.view(markets, statuses=selections.NEW, fresh=selections.FRESHNESS,
                                 sources=_source_keys(one["sources"]) if one.get("sources") else None,
                                 fits=one.get("classes"),
                                 companies={"kinds": list(kinds), "hidden": []} if kinds is not None else None)
        for row in selections.listing(conn, selection_id, chosen, expanded=classes):
            picked.setdefault(row["vacancy_id"], row)
    existing = documents.state(prefix, list(picked), base)
    alone = left_alone(conn, prefix, list(picked), base, tasks_conn, existing)
    result = []
    for vacancy_id, row in picked.items():
        if vacancy_id in alone:
            continue
        have = existing.get(vacancy_id, {})
        kinds = [k for k in settings["documents"]
                 if not have.get(k) and not (have.get("errors") or {}).get(k)]
        if not kinds:
            continue
        view = json.loads(row["view"]) if row.get("view") else {}
        result.append({"vacancy_id": vacancy_id, "title": view.get("title") or "",
                       "company": view.get("company") or "", "class": row.get("class"),
                       "documents": kinds})
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="The vacancies to generate a CV and a cover letter for")
    parser.add_argument("--identity", default=None, help="Search identity prefix")
    parser.add_argument("--json", action="store_true", help="Print the result as one JSON line")
    args = parser.parse_args(argv)

    import identity as identity_mod
    prefix = identity_mod.activate_or_exit(args.identity, quiet=args.json)
    try:
        settings = auto_settings(common.load_profile(prefix))
        if settings is None or not db.exists():
            items = []
        else:
            with db.session() as conn:
                items = pick(conn, settings, prefix)
    except (AutoError, documents.DocumentsError) as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        else:
            common.eprint(f"cv_auto: {exc}")
        return 1
    if args.json:
        print(json.dumps({"ok": True, "items": items}, ensure_ascii=False))
        return 0
    if settings is None:
        print("cv.auto is not set in the profile: nothing is generated automatically")
        return 0
    for item in items:
        print(f"{item['vacancy_id']}  {'+'.join(item['documents']):10}  {item['class']:14}  "
              f"{item['title']} — {item['company']}")
    print(f"{len(items)} vacancies")
    return 0


if __name__ == "__main__":
    sys.exit(main())
