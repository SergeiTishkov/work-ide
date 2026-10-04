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

import json
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


def _view_row(v: dict) -> tuple:
    """(view, views, id) for the UPDATE of one vacancy's display row: `view`
    in the identity's language, `views` in every language of the app."""
    import i18n
    import report

    views = report.vacancy_views(v)
    own = views.get(i18n.language()) or report.vacancy_view(v)
    return db.dumps(own), db.dumps(views), v["id"]


UPDATE_VIEWS = "UPDATE vacancies SET view = ?, views = ? WHERE id = ?"


def refresh_views(vacancies: dict) -> int:
    """Renders the display row again for every vacancy that has one, without
    recording a selection: after the rendering itself changed (a new language,
    a new line), so rows shown from older selections — the funnel keeps them
    for weeks — change too. Returns how many were rendered."""
    with db.session() as conn:
        shown = {row[0] for row in conn.execute(
            "SELECT id FROM vacancies WHERE view IS NOT NULL")}
    rows = [_view_row(v) for vid, v in vacancies.items() if vid in shown]
    with db.session() as conn:
        conn.executemany(UPDATE_VIEWS, rows)
    return len(rows)


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
        views.append(_view_row(v))
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
        conn.executemany(UPDATE_VIEWS, views)
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
        write_source_sites(conn)
    return selection_id


def write_source_sites(conn) -> None:
    """The catalogue's websites, for the app's "Source" drop-down: the app
    reads the database only, never the YAML."""
    conn.execute(
        "INSERT INTO meta (key, value) VALUES ('source_sites', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (json.dumps(common.source_sites(), ensure_ascii=False, sort_keys=True),),
    )


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


# The person's applications: listed across collections, selections and
# markets, since an application lives for weeks (see funnel_listing in
# schemas/queries.sql). The other filters look at the selection.
FUNNEL = ("applied", "contacted", "interview", "awaiting_final", "awaiting_offer", "offered",
          "started", "declined")
FILTERS = ("fresh_new", "all", "fresh", "rejected", "bugged", "expired") + FUNNEL


def latest_selection_id(conn) -> Optional[int]:
    row = conn.execute(load_queries()["latest_selection"]).fetchone()
    return row[0] if row and row[0] is not None else None


def _check_filter(filter_name: str) -> None:
    if filter_name not in FILTERS:
        raise ValueError(f"unknown filter {filter_name!r}")


def listing(conn, selection_id: int, segment: str, filter_name: str,
            expanded=(), source: str = "") -> list:
    """The rows of one market under one filter: the top of each class, and
    every row of the classes named in `expanded`. Funnel filters list every
    application, uncapped. `source` narrows it to one board ("" for all)."""
    _check_filter(filter_name)
    conn.row_factory = _dict_row
    try:
        if filter_name in FUNNEL:
            return conn.execute(load_queries()["funnel_listing"],
                                {"filter": filter_name, "source": source}).fetchall()
        return conn.execute(load_queries()["listing"], {
            "selection_id": selection_id, "segment": segment, "filter": filter_name,
            "expanded": "," + ",".join(expanded) + ",", "source": source,
        }).fetchall()
    finally:
        conn.row_factory = None


def class_totals(conn, selection_id: int, segment: str, filter_name: str,
                 source: str = "") -> dict:
    """{class: how many the filter holds} — for "N more" under a capped class."""
    _check_filter(filter_name)
    if filter_name in FUNNEL:
        totals = {}
        for row in listing(conn, selection_id, segment, filter_name, source=source):
            totals[row["class"]] = totals.get(row["class"], 0) + 1
        return totals
    rows = conn.execute(load_queries()["listing_class_totals"], {
        "selection_id": selection_id, "segment": segment, "filter": filter_name,
        "source": source,
    }).fetchall()
    return {cls: total for cls, total in rows}


def listing_sources(conn, selection_id: int, segment: str, filter_name: str) -> dict:
    """{board: how many the status filter holds from it}, largest first —
    the app's "Source" drop-down. The source filter itself does not apply."""
    _check_filter(filter_name)
    if filter_name in FUNNEL:
        rows = conn.execute(load_queries()["funnel_sources"], {"filter": filter_name})
    else:
        rows = conn.execute(load_queries()["listing_sources"], {
            "selection_id": selection_id, "segment": segment, "filter": filter_name,
        })
    return {source: total for source, total in rows.fetchall()}


def listing_counts(conn, selection_id: int, segment: str, source: str = "") -> dict:
    conn.row_factory = _dict_row
    try:
        row = conn.execute(load_queries()["listing_counts"], {
            "selection_id": selection_id, "segment": segment, "source": source,
        }).fetchone()
        funnel = conn.execute(load_queries()["funnel_counts"], {"source": source}).fetchone()
    finally:
        conn.row_factory = None
    counts = {name: row[name] or 0 for name in FILTERS if name not in FUNNEL}
    counts.update({name: funnel[name] or 0 for name in FUNNEL})
    return counts


def _dict_row(cursor, row) -> dict:
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}
