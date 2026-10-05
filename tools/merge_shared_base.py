"""
Merges the per-identity bases of schema 1-7 (data/<p>/<p>.sqlite) into the
one shared base of schema 8 (data/workide.sqlite), and moves the identities'
own files into data/identities/<p>/. Run once, on 2026-10-05; kept as the
record of how the shared base was built.

    python tools/merge_shared_base.py --identity sharp --identity pjoice
    python tools/merge_shared_base.py --identity sharp --identity pjoice --move-files

The first command builds the base and checks it against the old ones; it only
reads the old files. The second also moves each identity's files:

    data/<p>/.identity, <p>_state.json, runs/, feedback/  -> data/identities/<p>/
    data/<p>/knowledge/<p>_insights.md, salary_benchmark.json
                                                          -> data/identities/<p>/knowledge/
    data/<p>/raw/<source>/<day>.jsonl                     -> data/raw/<source>/ (appended
                                                             when both identities wrote that day)

What stays behind in data/<p>/ is what the shared base replaced — the old
base, the *.json.bak of the JSON era, the unprefixed insights.md placeholder —
and is listed at the end for deletion by hand.

HOW TWO RECORDS OF ONE VACANCY ARE MERGED
----------------------------------------
Both identities fetched it; the facts are the same posting seen at two
moments. The later fetch is taken (what the source says now), first_seen is
the earlier one, and what was learned later is kept from whichever learned it
(kb.LEARNED_KEYS, kb.FILLED_LATER_KEYS): the newer link check, the longer
description, every employment type and tag either one saw. `manual` — the
status of the markdown era — is dropped: every "not_relevant" in it was
already a rejection in the feedback columns, and the rest were agent notes.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import db  # noqa: E402
import kb  # noqa: E402
import normalize  # noqa: E402

OLD_SCHEMA_VERSION = "7"

# Keys of an old record that are not facts about the vacancy.
NOT_FACTS = (*db.PER_IDENTITY_KEYS, *db.TRANSIENT_KEYS, "manual")

# vacancy_identity columns copied as they are from the old `vacancies` row.
CARRIED_COLUMNS = (
    "view", "views", "feedback_status", "rejected_reason", "bugged_reason", "feedback_at",
    "applied_at", "contact_comment", "contact_at", "interview_comments", "interview_at",
    "final_comment", "final_at", "awaiting_offer_comment", "awaiting_offer_at",
    "declined_comment", "declined_at", "offered_comment", "offered_at",
    "started_comment", "started_at", "feedback_reviewed_at",
)


def old_base(data_root: Path, prefix: str) -> Path:
    return data_root / prefix / f"{prefix}.sqlite"


def open_old(path: Path) -> sqlite3.Connection:
    """Read-only, so the merge cannot change what it is merged from."""
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    (version,) = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    if version != OLD_SCHEMA_VERSION:
        raise SystemExit(f"{path}: schema version {version}, this merge reads version "
                         f"{OLD_SCHEMA_VERSION} only")
    return conn


def meta_value(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


# --- Facts -----------------------------------------------------------------

def facts_of(record: dict) -> dict:
    return {k: v for k, v in record.items() if k not in NOT_FACTS}


def _union(lists) -> list:
    seen: list = []
    for values in lists:
        for value in values or []:
            if value not in seen:
                seen.append(value)
    return seen


def merge_facts(records: list) -> dict:
    """One vacancy as several identities stored it -> one record of facts."""
    if len(records) == 1:
        return records[0]
    ordered = sorted(records, key=lambda r: r.get("last_seen") or "")
    merged = dict(ordered[-1])
    firsts = [r["first_seen"] for r in ordered if r.get("first_seen")]
    if firsts:
        merged["first_seen"] = min(firsts)

    signals: dict = {}
    for r in ordered:
        signals.update(r.get("external_signals") or {})
    merged["external_signals"] = signals
    checks = [r["link_check"] for r in ordered if r.get("link_check")]
    if checks:
        merged["link_check"] = max(checks, key=lambda c: c.get("checked_at") or "")
    fetches = [r["description_fetch"] for r in ordered if r.get("description_fetch")]
    if fetches:
        merged["description_fetch"] = max(fetches, key=lambda f: f.get("attempted_at") or "")
    if not merged.get("apply_channels"):
        channels = [r["apply_channels"] for r in ordered if r.get("apply_channels")]
        if channels:
            merged["apply_channels"] = channels[-1]

    for key in kb.FILLED_LATER_KEYS:
        if not merged.get(key):
            filled = [r[key] for r in ordered if r.get(key)]
            if filled:
                merged[key] = filled[-1]
    texts = [r.get("description_text") or "" for r in ordered]
    if max(texts, key=len):
        merged["description_text"] = max(texts, key=len)
    if any(r.get("tags") for r in ordered):
        merged["tags"] = _union(r.get("tags") for r in ordered)
    if any(r.get("employment_types") for r in ordered):
        merged["employment_types"] = normalize.employment_types(
            _union(r.get("employment_types") for r in ordered))
    return merged


def merge_companies(records: list) -> dict:
    """One company as several identities stored it. The counters are rebuilt
    on the next run (kb.build_companies_from_vacancies); what is kept is what
    was gathered by hand — reputation, intel, notes — and the dates."""
    if len(records) == 1:
        return records[0]
    merged = dict(records[0])
    for other in records[1:]:
        for key in ("reputation", "intel"):
            if other.get(key) and not merged.get(key):
                merged[key] = other[key]
        notes = [n for n in (merged.get("notes"), other.get("notes")) if n]
        merged["notes"] = "\n".join(dict.fromkeys(notes))
        firsts = [d for d in (merged.get("first_seen"), other.get("first_seen")) if d]
        lasts = [d for d in (merged.get("last_seen"), other.get("last_seen")) if d]
        merged["first_seen"] = min(firsts) if firsts else None
        merged["last_seen"] = max(lasts) if lasts else None
        merged["vacancy_ids"] = _union([merged.get("vacancy_ids"), other.get("vacancy_ids")])
    return merged


# --- Building the base -------------------------------------------------------

def build(data_root: Path, prefixes: list, target: Path) -> dict:
    """Writes the shared base to `target`. Returns {prefix: {old selection id:
    new id}} for the checks."""
    olds = {p: open_old(old_base(data_root, p)) for p in prefixes}
    selection_ids: dict = {p: {} for p in prefixes}
    try:
        facts: dict = {}
        for p, old in olds.items():
            for vid, data in old.execute("SELECT id, data FROM vacancies"):
                facts.setdefault(vid, []).append(facts_of(json.loads(data)))

        with closing(db.connect(target)) as new, new:
            new.executemany("INSERT INTO vacancies (id, data) VALUES (?, ?)",
                            ((vid, db.dumps(merge_facts(rs))) for vid, rs in facts.items()))

            companies: dict = {}
            for old in olds.values():
                for key, data in old.execute("SELECT key, data FROM companies"):
                    companies.setdefault(key, []).append(json.loads(data))
            new.executemany("INSERT INTO companies (key, data) VALUES (?, ?)",
                            ((k, db.dumps(merge_companies(rs))) for k, rs in companies.items()))

            sites = [meta_value(old, "source_sites") for old in olds.values()]
            sites = [s for s in sites if s]
            if sites:
                merged_sites: dict = {}
                for s in sites:
                    merged_sites.update(json.loads(s))
                new.execute("INSERT INTO meta (key, value) VALUES ('source_sites', ?)",
                            (db.dumps(merged_sites),))

            for p, old in olds.items():
                _carry_identity(old, new, p, data_root, selection_ids[p])
    finally:
        for old in olds.values():
            old.close()
    with closing(sqlite3.connect(str(target))) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return selection_ids


def _carry_identity(old: sqlite3.Connection, new: sqlite3.Connection, p: str,
                    data_root: Path, selection_ids: dict) -> None:
    first = old.execute("SELECT MIN(created_at) FROM selections").fetchone()[0]
    new.execute("INSERT INTO identities (id, display_name, created_at) VALUES (?, ?, ?)",
                (p, meta_value(old, "display_name"), first or db.now_iso()))

    for old_id, run, created_at, kind in old.execute(
            "SELECT id, run, created_at, kind FROM selections ORDER BY id"):
        selection_ids[old_id] = new.execute(
            "INSERT INTO selections (identity_id, run, created_at, kind) VALUES (?, ?, ?, ?)",
            (p, run, created_at, kind)).lastrowid
    new.executemany(
        "INSERT INTO selection_segments (selection_id, slug, name, position, is_default) "
        "VALUES (?, ?, ?, ?, ?)",
        ((selection_ids[s], *rest) for s, *rest in old.execute(
            "SELECT selection_id, slug, name, position, is_default FROM selection_segments")))
    new.executemany(
        "INSERT INTO selection_items (selection_id, segment, vacancy_id, class, class_position, "
        "section_limit, score, eligibility_rank) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ((selection_ids[s], *rest) for s, *rest in old.execute(
            "SELECT selection_id, segment, vacancy_id, class, class_position, section_limit, "
            "score, eligibility_rank FROM selection_items")))

    columns = ", ".join(CARRIED_COLUMNS)
    marks = ", ".join("?" for _ in CARRIED_COLUMNS)
    rows = []
    for vid, data, selection_id, *carried in old.execute(
            f"SELECT id, data, feedback_selection_id, {columns} FROM vacancies"):
        record = json.loads(data)
        computed = record.get("computed")
        c = computed or {}
        rows.append((p, vid, db.dumps(computed) if computed is not None else None,
                     c.get("score"), c.get("classification"), record.get("duplicate_of"),
                     selection_ids.get(selection_id) if selection_id is not None else None,
                     *carried))
    new.executemany(
        "INSERT INTO vacancy_identity (identity_id, vacancy_id, computed, score, class, "
        f"duplicate_of, feedback_selection_id, {columns}) "
        f"VALUES (?, ?, ?, ?, ?, ?, ?, {marks})", rows)

    old_runs = str(data_root / p / "runs")
    new_runs = str(common.identity_data_dir(p, data_root) / "runs")
    new.executemany(
        "INSERT INTO pipeline_runs (identity_id, started_at, heartbeat_at, finished_at, status, "
        "stage, pid, host, log_path, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ((p, *rest[:7], log.replace(old_runs, new_runs) if log else log, error)
         for *rest, log, error in old.execute(
            "SELECT started_at, heartbeat_at, finished_at, status, stage, pid, host, "
            "log_path, error FROM pipeline_runs ORDER BY id")))


# --- Checking it -------------------------------------------------------------

def check(data_root: Path, prefixes: list, target: Path, selection_ids: dict) -> list:
    """Every difference between the new base and the old ones that should not
    be there. Empty when the merge is faithful."""
    problems = []
    with closing(sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True)) as new:
        all_ids: set = set()
        for p in prefixes:
            with closing(open_old(old_base(data_root, p))) as old:
                ids = {r[0] for r in old.execute("SELECT id FROM vacancies")}
                all_ids |= ids
                mine = {r[0] for r in new.execute(
                    "SELECT vacancy_id FROM vacancy_identity WHERE identity_id = ?", (p,))}
                if ids != mine:
                    problems.append(f"{p}: {len(ids)} vacancies before, {len(mine)} rows after")

                columns = ", ".join(CARRIED_COLUMNS)
                before = {r[0]: r[1:] for r in old.execute(
                    f"SELECT id, {columns}, feedback_selection_id FROM vacancies")}
                after = {r[0]: r[1:] for r in new.execute(
                    f"SELECT vacancy_id, {columns}, feedback_selection_id FROM vacancy_identity "
                    "WHERE identity_id = ?", (p,))}
                remap = selection_ids[p]
                changed = [vid for vid, row in before.items()
                           if (*row[:-1], remap.get(row[-1]) if row[-1] is not None else None)
                           != after.get(vid)]
                if changed:
                    problems.append(f"{p}: feedback or views differ on {len(changed)}, "
                                    f"e.g. {changed[:3]}")

                verdicts = {vid: json.loads(data).get("computed") for vid, data in
                            old.execute("SELECT id, data FROM vacancies")}
                moved = {vid: json.loads(c) if c else None for vid, c in new.execute(
                    "SELECT vacancy_id, computed FROM vacancy_identity WHERE identity_id = ?",
                    (p,))}
                if verdicts != moved:
                    problems.append(f"{p}: the scores differ")

                for table, key in (("selection_items", "segment, vacancy_id, class, "
                                    "class_position, section_limit, score, eligibility_rank"),
                                   ("selection_segments", "slug, name, position, is_default")):
                    for old_id, new_id in remap.items():
                        a = sorted(old.execute(f"SELECT {key} FROM {table} WHERE selection_id = ?",
                                               (old_id,)))
                        b = sorted(new.execute(f"SELECT {key} FROM {table} WHERE selection_id = ?",
                                               (new_id,)))
                        if a != b:
                            problems.append(f"{p}: {table} of selection {old_id} differ")
                runs = old.execute("SELECT COUNT(*) FROM pipeline_runs").fetchone()[0]
                if runs != new.execute("SELECT COUNT(*) FROM pipeline_runs WHERE identity_id = ?",
                                       (p,)).fetchone()[0]:
                    problems.append(f"{p}: pipeline runs differ")
        total = new.execute("SELECT COUNT(*) FROM vacancies").fetchone()[0]
        if total != len(all_ids):
            problems.append(f"{total} vacancies in the shared base, {len(all_ids)} distinct before")
        leaked = new.execute(
            "SELECT COUNT(*) FROM vacancies WHERE json_type(data, '$.computed') IS NOT NULL "
            "OR json_type(data, '$.manual') IS NOT NULL "
            "OR json_type(data, '$._company_reputation') IS NOT NULL").fetchone()[0]
        if leaked:
            problems.append(f"{leaked} vacancies still carry per-identity keys in their facts")
    return problems


# --- Moving the files --------------------------------------------------------

def _move(src: Path, dst: Path, moved: list) -> None:
    if not src.exists():
        return
    if dst.exists():
        raise SystemExit(f"{dst} exists already; not overwriting it with {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    moved.append(f"{src} -> {dst}")


def move_files(data_root: Path, prefixes: list) -> list:
    moved: list = []
    for p in prefixes:
        old = data_root / p
        new = common.identity_data_dir(p, data_root)
        for name in (".identity", f"{p}_state.json"):
            _move(old / name, new / name, moved)
        for name in (f"{p}_insights.md", "salary_benchmark.json"):
            _move(old / "knowledge" / name, new / "knowledge" / name, moved)
        for folder in ("runs", "feedback"):
            if (old / folder).exists():
                for f in sorted((old / folder).iterdir()):
                    _move(f, new / folder / f.name, moved)
                (old / folder).rmdir()
        raw = old / "raw"
        if raw.exists():
            for f in sorted(raw.rglob("*")):
                if not f.is_file():
                    continue
                dst = data_root / "raw" / f.relative_to(raw)
                if dst.exists():
                    # Both identities fetched that source that day: one log.
                    with f.open("rb") as src, dst.open("ab") as out:
                        shutil.copyfileobj(src, out)
                    f.unlink()
                    moved.append(f"{f} >> {dst}")
                else:
                    _move(f, dst, moved)
            for d in sorted((d for d in raw.rglob("*") if d.is_dir()), reverse=True):
                d.rmdir()
            raw.rmdir()
    return moved


def leftovers(data_root: Path, prefixes: list) -> list:
    return sorted(str(f) for p in prefixes for f in (data_root / p).rglob("*") if f.is_file())


def main(argv: Optional[list] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("--identity", action="append", required=True,
                        help="an identity whose data/<p>/<p>.sqlite is merged (repeat)")
    parser.add_argument("--data-root", type=Path, default=common.DATA_ROOT,
                        help="the data/ folder (a copy, for a rehearsal)")
    parser.add_argument("--move-files", action="store_true",
                        help="after a clean check, move the identities' files too")
    args = parser.parse_args(argv)
    data_root = args.data_root.resolve()
    target = data_root / common.DB_NAME
    if target.exists():
        raise SystemExit(f"{target} exists already: the merge builds it from nothing")

    building = target.with_name(target.name + ".building")
    for leftover in building.parent.glob(building.name + "*"):
        leftover.unlink()
    selection_ids = build(data_root, args.identity, building)
    problems = check(data_root, args.identity, building, selection_ids)
    if problems:
        print("The merged base differs from the old ones; nothing moved:", *problems, sep="\n  ")
        raise SystemExit(1)
    # Closed and checkpointed: what is left beside it is empty.
    for aux in ("-wal", "-shm"):
        building.with_name(building.name + aux).unlink(missing_ok=True)
    building.rename(target)
    with closing(sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True)) as new:
        print(f"{target}: built and checked")
        for p, n, scored, answered in new.execute(
                "SELECT identity_id, COUNT(*), COUNT(computed), "
                "SUM(feedback_status <> 'new') FROM vacancy_identity GROUP BY identity_id"):
            print(f"  {p}: {n} vacancies ({scored} scored), {answered} answered, "
                  f"{len(selection_ids[p])} selections")
        (total,) = new.execute("SELECT COUNT(*) FROM vacancies").fetchone()
        print(f"  {total} distinct vacancies")

    if args.move_files:
        moved = move_files(data_root, args.identity)
        print(f"moved {len(moved)} files into {data_root / 'identities'} and {data_root / 'raw'}")
        rest = leftovers(data_root, args.identity)
        print("left behind, replaced by the shared base — delete once it is checked:",
              *rest, sep="\n  ")


if __name__ == "__main__":
    main()
