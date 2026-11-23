"""
Selections: what one run showed, recorded in the database.

A selection is the shortlist of one identity's run, split by market (segment)
(tools/segments.py). The desktop app reads its lists from here with
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

# The person's own picks (tools/add_vacancy.py, task 0122): vacancies they
# added by hand are listed in a section of their own, whatever the scripts'
# class, in every market, until a near-duplicate or a dead link takes them
# out like any other row. The scripts' verdict stays in the base for the
# record: the row carries the real score.
# The class of a starred vacancy (task 0139): the app's star, read by the
# view queries (schemas/queries.sql, STARRED); no selection writes it.
STAR_CLASS = "starred"
HAND_CLASS = "added_by_hand"
HAND_CLASS_POSITION = -1
PICKS_NAME = "added_by_hand.json"


def listed_vacancies(vacancies: dict) -> list:
    """The vacancies a shortlist can show: no near-duplicates, no confirmed
    dead links, a listed class."""
    import report

    return [
        v for v in vacancies.values()
        if not v.get("duplicate_of")
        and (v.get("link_check") or {}).get("status") != "dead"
        and (v.get("computed") or {}).get("classification") in report.LISTED_CLASSES
    ]


# Listed classes the app never shows (schemas/queries.sql, NOT LISTED; the
# owner, 2026-10-24, task 0098), as app/renderer/app.js UNLISTED_CLASSES.
NOT_SHOWN = ("remote_unconfirmed",)


def shown_vacancies(vacancies: dict) -> list:
    """The listed vacancies the app shows: listed_vacancies less the
    classes in NOT_SHOWN. What a person can open, answer or apply to."""
    return [v for v in listed_vacancies(vacancies)
            if (v.get("computed") or {}).get("classification") not in NOT_SHOWN]


def _view_row(v: dict) -> tuple:
    """(view, views, identity, id) for the UPDATE of one vacancy's display
    row: `view` in the identity's language, `views` in every language of the
    app."""
    import i18n
    import report

    views = report.vacancy_views(v)
    own = views.get(i18n.language()) or report.vacancy_view(v)
    return db.dumps(own), db.dumps(views), db.identity(), v["id"]


UPDATE_VIEWS = ("UPDATE vacancy_identity SET view = ?, views = ? "
                "WHERE identity_id = ? AND vacancy_id = ?")


def refresh_views(vacancies: dict) -> int:
    """Renders the display row again for every vacancy that has one, without
    recording a selection: after the rendering itself changed (a new language,
    a new line), so rows shown from older selections — the funnel keeps them
    for weeks — change too. Returns how many were rendered."""
    with db.session() as conn:
        shown = {row[0] for row in conn.execute(
            "SELECT vacancy_id FROM vacancy_identity WHERE identity_id = ? "
            "AND view IS NOT NULL", (db.identity(),))}
    rows = [_view_row(v) for vid, v in vacancies.items() if vid in shown]
    with db.session() as conn:
        conn.executemany(UPDATE_VIEWS, rows)
        write_company_kinds(conn)
    return len(rows)


def picks_path() -> Path:
    """data/identities/<prefix>/added_by_hand.json: {vacancy id: {added_at, url}}."""
    return common.DATA_DIR / PICKS_NAME


def load_picks() -> dict:
    return common.load_json(picks_path(), default={}) or {}


def save_pick(vacancy_id: str, url: str) -> None:
    """Remembers a vacancy the person added by hand; a second add keeps the
    first date."""
    picks = load_picks()
    picks.setdefault(vacancy_id, {"added_at": db.now_iso(), "url": url})
    common.save_json_atomic(picks_path(), picks)


def _hand_items(v: dict, segment_slugs) -> list:
    """The selection rows of one pick: one per market."""
    import report

    score = int((v.get("computed") or {}).get("score") or 0)
    return [(slug, v["id"], HAND_CLASS, HAND_CLASS_POSITION, report.TOP_N_PER_SECTION, score,
             report._eligibility_rank(v)) for slug in segment_slugs]


def _pick_listed(v: Optional[dict]) -> bool:
    return bool(v) and not v.get("duplicate_of")         and (v.get("link_check") or {}).get("status") != "dead"


INSERT_ITEMS = ("INSERT INTO selection_items (selection_id, segment, vacancy_id, class, "
                "class_position, section_limit, score, eligibility_rank) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)")


def add_by_hand(vacancy: dict) -> Optional[int]:
    """Lists one pick in the active identity's latest selection, so it shows
    now rather than after the next run; returns that selection's id, None
    when there is no selection yet (the first run lists it, record()).

    The one change ever made to a recorded selection: a row added, nothing
    else in it moved. A new selection would do the same through a rebuild
    of the whole base, which is what the person asked not to wait for.
    Must be called after kb.save_vacancies()."""
    view_row = _view_row(vacancy)
    with db.session() as conn:
        selection_id = latest_selection_id(conn)
        if selection_id is None:
            return None
        slugs = [row[0] for row in conn.execute(
            "SELECT slug FROM selection_segments WHERE selection_id = ? ORDER BY position",
            (selection_id,))]
        conn.execute("DELETE FROM selection_items WHERE selection_id = ? AND vacancy_id = ?",
                     (selection_id, vacancy["id"]))
        conn.executemany(INSERT_ITEMS, ((selection_id, *item) for item in _hand_items(vacancy, slugs)))
        conn.execute(UPDATE_VIEWS, view_row)
    return selection_id


def _configured_segments() -> list:
    """The identity's markets; an identity that configured none gets one
    segment holding everything."""
    import segments as segments_mod

    try:
        configured = segments_mod.load_segments()
    except Exception as exc:  # noqa: BLE001 — a broken file must not lose the run's shortlist
        common.eprint(f"[selections] cannot read the market segmentation ({exc}); "
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

    picks = load_picks()
    listed = listed_vacancies(vacancies)
    views, items = [], []
    for v in listed:
        vid = v["id"]
        if vid in picks:
            continue
        c = v.get("computed") or {}
        cls = c["classification"]
        views.append(_view_row(v))
        group = report.market_group(v)
        for segment in configured:
            if segment.holds(group, claimed):
                items.append((segment.slug, vid, cls, class_position[cls],
                              report.TOP_N_PER_SECTION, int(c.get("score") or 0),
                              report._eligibility_rank(v)))
    for vid in picks:
        v = vacancies.get(vid)
        if _pick_listed(v):
            views.append(_view_row(v))
            items.extend(_hand_items(v, [s.slug for s in configured]))

    with db.session() as conn:
        prefix = db.ensure_identity(conn, display_name=_display_name())
        selection_id = conn.execute(
            "INSERT INTO selections (identity_id, run, created_at, kind) VALUES (?, ?, ?, ?)",
            (prefix, run, db.now_iso(), kind),
        ).lastrowid
        conn.executemany(
            "INSERT INTO selection_segments "
            "(selection_id, slug, name, names, position, is_default, everything) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ((selection_id, s.slug, s.name, json.dumps(s.names(), ensure_ascii=False), i, int(s.default),
              int(s.everything))
             for i, s in enumerate(configured)),
        )
        conn.executemany(UPDATE_VIEWS, views)
        conn.executemany(INSERT_ITEMS, ((selection_id, *item) for item in items))
        write_source_sites(conn)
        write_company_kinds(conn)
        write_listed_classes(conn, prefix)
    return selection_id


def write_source_sites(conn) -> None:
    """The catalogue's websites and its paid boards (task 0101), for the
    app's "Source" drop-down: the app reads the database only, never the
    YAML."""
    for key, value in (("source_sites", common.source_sites()), ("paid_sources", common.paid_sources())):
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value, ensure_ascii=False, sort_keys=True)),
        )


def listed_classes(criteria: dict) -> list:
    """The classes the app lists for an identity (the owner, 2026-11-21, task
    0137): the ones its criteria can put a row in. "Never say never" only
    with its threshold (task 0124), "Hours not confirmed" only with an
    engagement_fit that does not accept silence; the others always. The
    app's own order decides how they are shown."""
    import score

    thresholds = criteria.get("classification_thresholds") or {}
    classes = [STAR_CLASS, HAND_CLASS, "hot_lead", "worth_a_look", "long_shot"]
    if thresholds.get(score.NEVER_SAY_NEVER) is not None:
        classes.append(score.NEVER_SAY_NEVER)
    classes.append("ai_unscreened")
    engagement = criteria.get("engagement_fit")
    if engagement and engagement.get("unconfirmed_policy", "manual_check") != "accept":
        classes.append("engagement_unconfirmed")
    return classes


def write_listed_classes(conn, prefix: str) -> None:
    """listed_classes() of the identity, as meta "listed_classes:<prefix>",
    for the app's "Identity fit" drop-down (it reads the database only)."""
    import score

    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (f"listed_classes:{prefix}", json.dumps(listed_classes(score.load_criteria()))),
    )


def write_company_kinds(conn) -> None:
    """{company: {"kind", "name"}} for every intermediary among the companies
    any identity's rows show, for the app's "Company" drop-down
    (config/company_kinds.yaml; a company missing from it is "other"). Over
    every identity, since the base and this key are shared: 0.5 s on 8.5k rows
    (2026-10-14)."""
    import company_kinds

    names = [row[0] for row in conn.execute(
        "SELECT DISTINCT json_extract(view, '$.company') FROM vacancy_identity "
        "WHERE view IS NOT NULL")]
    conn.execute(
        "INSERT INTO meta (key, value) VALUES ('company_kinds', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (json.dumps(company_kinds.mapping(names), ensure_ascii=False, sort_keys=True),),
    )


def _display_name() -> str:
    """What the search is about, in the identity's own words — the caption of
    its tab in the app."""
    profile = common.load_profile()
    return ((profile.get("identity") or {}).get("display_name")
            or common.ACTIVE_IDENTITY or "")


# --- Queries (shared with the app through schemas/queries.sql) ----------------

def load_queries() -> dict:
    """The named queries of schemas/queries.sql: `-- name: <name>` starts one,
    and a line `-- include: <name>` inside a query stands for that query's
    text (the view's common start, view_pool). app/main/queries.js reads the
    file the same way."""
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
    for key, text in queries.items():
        queries[key] = "\n".join(
            queries[line.split(":", 1)[1].strip()] if line.startswith("-- include:") else line
            for line in text.split("\n"))
    return queries


# --- The view: what the app's four drop-downs chose ----------------------------
# Several markets, statuses, boards and classes at once (the owner,
# 2026-10-07); see THE VIEW in schemas/queries.sql.

# "Not applied or denied": no answer yet.
NEW = ("new",)
# The person's applications: listed across collections, selections and
# markets, since an application lives for weeks.
FUNNEL = ("applied", "contacted", "interview", "awaiting_final", "awaiting_offer", "offered",
          "started", "declined")
# Denied: turned down in this collection.
DENIED = ("rejected", "bugged", "expired")
STATUSES = NEW + FUNNEL + DENIED
# Fresh: no selection before the latest run held it; earlier: one did.
FRESHNESS = ("fresh", "earlier")
# The "Company" drop-down's groups: company_kinds.KINDS, then every other company.
COMPANY_KINDS = ("marketplace", "agency", "reposter", "other")
# The "Age" drop-down's bands (AGE in schemas/queries.sql): posted today, up to
# a week, up to a month, longer ago.
AGES = ("today", "week", "month", "older")
# The "Category" drop-down's second group (ROLE in schemas/queries.sql, task
# 0049): on the CV's stack, another stack the CV fits, a stretch for the CV.
ROLES = ("stack", "off_stack", "stretch")


def view(segments, statuses=NEW, fresh=FRESHNESS, sources=None, fits=None, companies=None,
         ages=None, roles=None, text="") -> dict:
    """What to list. `sources`, `fits`, `ages` and `roles` are None for every
    board, class, age and kind of role (a list, even an empty one, names them). `companies` is None
    for every company, or {"kinds": [the kinds shown], "hidden": [names hidden
    among them]} — see THE VIEW in schemas/queries.sql. `text` is the words
    a row must hold (WORDS there), empty for any."""
    return {"text": text, "segments": list(segments), "statuses": list(statuses), "fresh": list(fresh),
            "sources": None if sources is None else list(sources),
            "fits": None if fits is None else list(fits),
            "ages": None if ages is None else list(ages),
            "roles": None if roles is None else list(roles),
            "companies": None if companies is None else {
                "kinds": list(companies.get("kinds") or []),
                "hidden": list(companies.get("hidden") or [])}}


def _params(selection_id: int, chosen: dict) -> dict:
    unknown = [s for s in chosen["statuses"] if s not in STATUSES]
    unknown += [f for f in chosen["fresh"] if f not in FRESHNESS]
    unknown += [a for a in chosen.get("ages") or () if a not in AGES]
    unknown += [r for r in chosen.get("roles") or () if r not in ROLES]
    if unknown:
        raise ValueError(f"unknown status, freshness, age or role: {unknown}")
    companies = chosen.get("companies")
    if companies is not None:
        unknown = [k for k in companies["kinds"] if k not in COMPANY_KINDS]
        if unknown:
            raise ValueError(f"unknown company kind: {unknown}")

    def listed(values):
        return None if values is None else json.dumps(list(values))

    return {
        "identity": db.identity(), "selection_id": selection_id,
        "segments": json.dumps(list(chosen["segments"])),
        "statuses": json.dumps(list(chosen["statuses"])),
        "fresh": json.dumps([1 if f == "fresh" else 0 for f in chosen["fresh"]]),
        "sources": listed(chosen.get("sources")),
        "fits": listed(chosen.get("fits")),
        "companies": None if companies is None else json.dumps(companies),
        "ages": listed(chosen.get("ages")),
        "roles": listed(chosen.get("roles")),
        "words": words(chosen.get("text")),
    }


def words(text) -> Optional[str]:
    """The text field's words as the query takes them (WORDS in
    schemas/queries.sql): a JSON list, None when nothing was typed."""
    found = list(dict.fromkeys((text or "").split()))
    return json.dumps(found) if found else None


def listing(conn, selection_id: int, chosen: dict, shown=None, expanded=()) -> list:
    """The rows of the view: the top of each class, as many as `shown` asks
    for a class ({"hot_lead": 25}), and every row of the classes named in
    `expanded`. Rows with an answer are never capped."""
    conn.row_factory = _dict_row
    try:
        return conn.execute(load_queries()["view_listing"], {
            **_params(selection_id, chosen),
            "expanded": "," + ",".join(expanded) + ",", "shown": json.dumps(shown or {}),
        }).fetchall()
    finally:
        conn.row_factory = None


def counts(conn, selection_id: int, chosen: dict) -> dict:
    """The "Show" drop-down's numbers: {"statuses": {status: n}} under the
    chosen freshness, {"fresh": {"fresh": n, "earlier": n}} under the chosen
    statuses."""
    result = {"statuses": {s: 0 for s in STATUSES}, "fresh": {f: 0 for f in FRESHNESS}}
    for axis, key, total in conn.execute(load_queries()["view_counts"],
                                         _params(selection_id, chosen)):
        if axis == "status":
            result["statuses"][key] = total
        else:
            result["fresh"]["fresh" if key == "1" else "earlier"] = total
    return result


def class_totals(conn, selection_id: int, chosen: dict) -> dict:
    """{class: how many the view holds}, the chosen classes aside: the "Fit"
    drop-down, and "N more" under a capped class."""
    rows = conn.execute(load_queries()["view_class_totals"], _params(selection_id, chosen))
    return {cls: total for cls, total in rows.fetchall()}


def sources(conn, selection_id: int, chosen: dict) -> dict:
    """{board: how many the view holds from it}, largest first, the chosen
    boards aside: the "Source" drop-down."""
    rows = conn.execute(load_queries()["view_sources"], _params(selection_id, chosen))
    return {source: total for source, total in rows.fetchall()}


def companies(conn, selection_id: int, chosen: dict) -> list:
    """[(kind, name, how many)], largest first, the chosen companies aside:
    the "Company" drop-down. Every other company is one row, name None."""
    rows = conn.execute(load_queries()["view_companies"], _params(selection_id, chosen))
    return [tuple(row) for row in rows.fetchall()]


def ages(conn, selection_id: int, chosen: dict) -> dict:
    """{age band: how many the view holds}, the chosen ages aside: the "Age"
    drop-down."""
    result = {age: 0 for age in AGES}
    for age, total in conn.execute(load_queries()["view_ages"], _params(selection_id, chosen)):
        result[age] = total
    return result


def roles(conn, selection_id: int, chosen: dict) -> dict:
    """{kind of role: how many the view holds}, the chosen kinds aside: the
    "Category" drop-down's second group."""
    result = {role: 0 for role in ROLES}
    for role, total in conn.execute(load_queries()["view_roles"], _params(selection_id, chosen)):
        result[role] = total
    return result


def latest_selection_id(conn) -> Optional[int]:
    """The active identity's latest selection."""
    row = conn.execute(load_queries()["latest_selection"], {"identity": db.identity()}).fetchone()
    return row[0] if row and row[0] is not None else None


def _dict_row(cursor, row) -> dict:
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}
