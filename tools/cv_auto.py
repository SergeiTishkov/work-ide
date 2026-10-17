"""
Which vacancies of the latest collection get a CV and a cover letter without
a click: the identity's own filters (the owner, 2026-10-13).

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

Inside one filter everything named must match; a key left out matches
anything. Candidates are the vacancies of the latest selection with no
answer yet; a document already in the vacancy's folder (tools/documents.py)
is not made again, nor one whose vacancy was found gone (an error in its log).

FRESH, AND THE CATCH-UP (the owner, 2026-10-13). A filter the collections
already applied picks only the fresh vacancies (the latest run brought them
in for the first time). A filter that is new — auto-generation just turned
on, a filter added, `documents` changed — picks the earlier vacancies of the
latest selection too, once: at the end of the next collection. What was
applied is kept in data/identities/<prefix>/cv_auto.json; cv_batch.py writes
it when it takes the pick (--remember does the same). --all treats every
filter as new.

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

FILTER_KEYS = ("markets", "sources", "classes")
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
    return {"documents": list(kinds), "filters": filters}


def filter_key(one: dict, kinds: List[str]) -> str:
    """One filter with the documents it makes, as the applied list keeps it:
    the order of keys and values does not matter."""
    return json.dumps({"filter": {k: sorted(str(v) for v in one[k]) for k in sorted(one)},
                       "documents": sorted(kinds)}, sort_keys=True)


def state_path() -> Path:
    return common.DATA_DIR / "cv_auto.json"


def applied_filters() -> List[str]:
    return list((common.load_json(state_path(), {}) or {}).get("applied") or [])


def remember(settings: Optional[dict]) -> None:
    """Every filter of the profile is applied from now on: fresh only. With
    no filters the list empties, so a filter turned on again is new again."""
    keys = [filter_key(one, settings["documents"]) for one in settings["filters"]] if settings else []
    common.save_json_atomic(state_path(), {"applied": keys})


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


def pick(conn, settings: dict, prefix: str, base: Optional[Path] = None,
         applied: Optional[List[str]] = None) -> List[dict]:
    """[{"vacancy_id", "title", "company", "class", "documents": [kinds to
    make]}] in the order of the app's list (the class, then the score), each
    vacancy once. A filter in `applied` takes the fresh vacancies only; any
    other one the earlier ones too (the catch-up)."""
    applied = set(applied or [])
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
        chosen = selections.view(markets, statuses=selections.NEW,
                                 fresh=(("fresh",) if filter_key(one, settings["documents"]) in applied
                                        else selections.FRESHNESS),
                                 sources=_source_keys(one["sources"]) if one.get("sources") else None,
                                 fits=one.get("classes"))
        for row in selections.listing(conn, selection_id, chosen, expanded=classes):
            picked.setdefault(row["vacancy_id"], row)
    existing = documents.state(prefix, list(picked), base)
    result = []
    for vacancy_id, row in picked.items():
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
    parser.add_argument("--all", action="store_true",
                        help="Every filter as new: the earlier vacancies of the latest selection too")
    parser.add_argument("--remember", action="store_true",
                        help="Record the filters as applied: from now on they take fresh vacancies only "
                             "(cv_batch.py does it when it takes the pick)")
    args = parser.parse_args(argv)

    import identity as identity_mod
    prefix = identity_mod.activate_or_exit(args.identity, quiet=args.json)
    try:
        settings = auto_settings(common.load_profile(prefix))
        if settings is None or not db.exists():
            items = []
        else:
            with db.session() as conn:
                items = pick(conn, settings, prefix, applied=[] if args.all else applied_filters())
        if args.remember:
            remember(settings)
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
