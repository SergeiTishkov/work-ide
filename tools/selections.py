"""
Selections: what one run showed, recorded in the database.

A selection is the shortlist of one run, split by market (segment) exactly as
the Markdown report splits it. The desktop app reads its lists from here with
the queries in schemas/queries.sql, instead of from files.

WHY RECORDED, NOT RECOMPUTED BY THE APP
---------------------------------------
Which market a vacancy belongs to (report.hiring_country, segments.group_of)
and which class it is in (score.py) is Python logic with years of edge cases
in it. SQL does not repeat any of it: the pipeline records the outcome, and a
query only filters, orders and limits.

WHY EVERY RUN IS KEPT
---------------------
Selections are only ever added. When a person marks a vacancy "wrong pick",
the feedback remembers the selection they were looking at, so the agent fixing
the filter can compare the class and score then with the class and score now,
and see whether its fix actually took.

Every listed vacancy is recorded, not only the top of each section: once a
person marks one, the next one by score has to move up without a new run.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import db  # noqa: E402

QUERIES_PATH = common.ROOT / "schemas" / "queries.sql"

KINDS = ("run", "rebuild")


def listed_vacancies(vacancies: dict) -> list:
    """The vacancies a shortlist can show: the same cut the Markdown report
    makes (no near-duplicates, no confirmed dead links, a listed class)."""
    import report

    return [
        v for v in vacancies.values()
        if not v.get("duplicate_of")
        and (v.get("link_check") or {}).get("status") != "dead"
        and (v.get("computed") or {}).get("classification") in report.LISTED_CLASSES
    ]


def _configured_segments() -> list:
    """The identity's markets; an identity that configured none gets one
    segment holding everything — the same fallback the report uses."""
    import segments as segments_mod

    try:
        configured = segments_mod.load_segments()
    except Exception as exc:  # noqa: BLE001 — same policy as report.write_segmented_reports
        common.eprint(f"[selections] cannot read the report segmentation ({exc}); "
                      "recording one undivided selection instead")
        configured = []
    return configured or [segments_mod.Segment(
        "all", "Everything together", everything=True, default=True)]


def record(vacancies: dict, state: Optional[dict] = None, kind: str = "run") -> int:
    """Records the selection for the current state of the base; returns its id.

    Must be called after kb.save_vacancies(): selection rows reference
    vacancies that exist in the database."""
    import report
    import segments as segments_mod

    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}, not {kind!r}")
    configured = _configured_segments()
    claimed = segments_mod._claimed_groups(configured)
    class_position = {cls: i for i, cls in enumerate(report.LISTED_CLASSES)}
    run = int((state or {}).get("run_count") or 0)

    listed = listed_vacancies(vacancies)
    views, items = [], []
    for v in listed:
        vid = v["id"]
        c = v.get("computed") or {}
        cls = c["classification"]
        views.append((db.dumps(report.vacancy_view(v)), vid))
        group = segments_mod.group_of(report.hiring_country(v)[0])
        for segment in configured:
            if segment.holds(group, claimed):
                items.append((segment.slug, vid, cls, class_position[cls],
                              report.TOP_N_PER_SECTION, int(c.get("score") or 0),
                              report._eligibility_rank(v)))

    with db.session() as conn:
        selection_id = conn.execute(
            "INSERT INTO selections (run, created_at, kind) VALUES (?, ?, ?)",
            (run, db.now_iso(), kind),
        ).lastrowid
        conn.executemany(
            "INSERT INTO selection_segments (selection_id, slug, name, position, is_default) "
            "VALUES (?, ?, ?, ?, ?)",
            ((selection_id, s.slug, s.name, i, int(s.default))
             for i, s in enumerate(configured)),
        )
        conn.executemany("UPDATE vacancies SET view = ? WHERE id = ?", views)
        conn.executemany(
            "INSERT INTO selection_items (selection_id, segment, vacancy_id, class, "
            "class_position, section_limit, score, eligibility_rank) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ((selection_id, *item) for item in items),
        )
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('display_name', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (_display_name(),),
        )
    return selection_id


def _display_name() -> str:
    """What the search is about, in the identity's own words — the caption of
    its tab in the app."""
    profile = common.load_profile()
    return ((profile.get("identity") or {}).get("display_name")
            or common.ACTIVE_IDENTITY or "")


# --- Queries (shared with the app through schemas/queries.sql) ----------------

def load_queries() -> dict:
    """The named queries of schemas/queries.sql: `-- name: <name>` starts one."""
    queries, name, lines = {}, None, []
    for line in QUERIES_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("-- name:"):
            if name:
                queries[name] = "\n".join(lines).strip()
            name, lines = line.split(":", 1)[1].strip(), []
        elif name:
            lines.append(line)
    if name:
        queries[name] = "\n".join(lines).strip()
    return queries


FILTERS = ("fresh_new", "all", "fresh", "applied", "rejected", "bugged")


def latest_selection_id(conn) -> Optional[int]:
    row = conn.execute(load_queries()["latest_selection"]).fetchone()
    return row[0] if row and row[0] is not None else None


def listing(conn, selection_id: int, segment: str, filter_name: str,
            expanded=()) -> list:
    """The rows of one market under one filter: the top of each class, and
    every row of the classes named in `expanded`."""
    if filter_name not in FILTERS:
        raise ValueError(f"unknown filter {filter_name!r}")
    conn.row_factory = _dict_row
    try:
        return conn.execute(load_queries()["listing"], {
            "selection_id": selection_id, "segment": segment, "filter": filter_name,
            "expanded": "," + ",".join(expanded) + ",",
        }).fetchall()
    finally:
        conn.row_factory = None


def class_totals(conn, selection_id: int, segment: str, filter_name: str) -> dict:
    """{class: how many the filter holds} — for "N more" under a capped class."""
    if filter_name not in FILTERS:
        raise ValueError(f"unknown filter {filter_name!r}")
    rows = conn.execute(load_queries()["listing_class_totals"], {
        "selection_id": selection_id, "segment": segment, "filter": filter_name,
    }).fetchall()
    return {cls: total for cls, total in rows}


def listing_counts(conn, selection_id: int, segment: str) -> dict:
    conn.row_factory = _dict_row
    try:
        row = conn.execute(load_queries()["listing_counts"], {
            "selection_id": selection_id, "segment": segment,
        }).fetchone()
    finally:
        conn.row_factory = None
    return {name: row[name] or 0 for name in FILTERS}


def _dict_row(cursor, row) -> dict:
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}
