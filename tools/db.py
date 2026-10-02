"""
The SQLite knowledge base of the active identity: data/<prefix>/<prefix>.sqlite.

WHY SQLITE, AND NOT THE JSON FILES IT REPLACES
----------------------------------------------
Two writers now touch the vacancy base: the pipeline, and the desktop app
recording a person's feedback on a vacancy. With one JSON file of 150 MB, every
click in the app meant rewriting the whole file, possibly while the pipeline
was rewriting it too, and one of the two would silently lose. SQLite gives each
writer its own columns inside one transactional file, so neither can overwrite
the other (the column ownership is written down in schemas/db.sql).

The rest of the code did not have to change: kb.load_vacancies() still returns
a plain dict keyed by id, and kb.save_vacancies() still takes one.

The schema lives in schemas/db.sql, shared with the app's tests.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

# 2: pipeline_runs — a new table, created by applying the schema.
# 3: feedback status 'expired'; 4: the application funnel (contacted,
#    interview, awaiting_final) with a comment and a date per step. Both change
#    the vacancies table, rebuilt by _rebuild_vacancies.
SCHEMA_VERSION = 7
SCHEMA_PATH = common.ROOT / "schemas" / "db.sql"

# How long a writer waits for another writer's transaction before giving up.
# The pipeline's largest transaction (saving the whole base) takes seconds.
BUSY_TIMEOUT_MS = 60_000

FEEDBACK_STATUSES = ("new", "applied", "rejected", "bugged", "expired",
                     "contacted", "interview", "awaiting_final", "awaiting_offer",
                     "declined", "offered", "started")


class NotMigratedError(RuntimeError):
    """The identity still has its knowledge base in the old JSON files."""


class SchemaVersionError(RuntimeError):
    """The database was created by a different version of the schema."""


def db_path() -> Path:
    common.require_identity()
    return common.DB_PATH


def exists() -> bool:
    return db_path().exists()


def _check_not_legacy() -> None:
    """A database that is missing while the old JSON is present means the
    identity has not been migrated yet. Starting an empty database next to it
    would quietly hide the person's whole history, so refuse instead."""
    legacy = [p for p in (common.VACANCIES_PATH, common.COMPANIES_PATH) if p and p.exists()]
    if legacy and not exists():
        raise NotMigratedError(
            f"Identity '{common.ACTIVE_IDENTITY}' still keeps its knowledge base in "
            f"JSON ({legacy[0].name}). Migrate it once:\n"
            f"  python tools/kb.py --identity {common.ACTIVE_IDENTITY} migrate-to-sqlite"
        )


def _table_body(ddl: str) -> str:
    """What is between the outer parentheses of a CREATE TABLE, whitespace
    normalised — for comparing a stored definition with the schema file."""
    body = ddl[ddl.index("(") + 1:ddl.rindex(")")]
    return " ".join(body.split())


def _rebuild_vacancies(conn: sqlite3.Connection) -> None:
    """Brings the vacancies table to its definition in schemas/db.sql.

    SQLite cannot change a CHECK constraint (the allowed feedback statuses),
    so the table is rebuilt the documented way: a new table from the schema
    file, the shared columns copied, the old table dropped, the new one
    renamed — in one transaction, with foreign keys off so that the selection
    rows referring to vacancies survive the swap. Columns the new definition
    adds start empty. Skipped when the table already matches."""
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    match = re.search(r"CREATE TABLE IF NOT EXISTS vacancies (\(.*?\n\));", schema, re.S)
    if match is None:
        raise SchemaVersionError("schemas/db.sql defines no vacancies table")
    target = "CREATE TABLE vacancies_new " + match.group(1)
    (current,) = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'vacancies'").fetchone()
    if _table_body(current) == _table_body(target):
        return
    old_columns = [row[1] for row in conn.execute("PRAGMA table_info(vacancies)")]
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        with conn:
            conn.execute(target)
            new_columns = {row[1] for row in conn.execute("PRAGMA table_info(vacancies_new)")}
            shared = ", ".join(c for c in old_columns if c in new_columns)
            conn.execute(f"INSERT INTO vacancies_new ({shared}) SELECT {shared} FROM vacancies")
            conn.execute("DROP TABLE vacancies")
            conn.execute("ALTER TABLE vacancies_new RENAME TO vacancies")
            conn.execute("CREATE INDEX IF NOT EXISTS vacancies_feedback "
                         "ON vacancies(feedback_status, feedback_reviewed_at)")
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


# version reached -> the step that reaches it. Versions without a step only
# added tables, which applying the schema already did. Version 3 (status
# 'expired') and 4 (the funnel) both change the vacancies table; one rebuild
# to the current definition, at 4, covers both. Version 5 adds `views`; on a
# base coming from 3, the rebuild at 4 has already added it and 5 is a no-op.
MIGRATIONS = {4: _rebuild_vacancies, 5: _rebuild_vacancies, 6: _rebuild_vacancies,
              7: _rebuild_vacancies}


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    if row is None:
        with conn:
            conn.execute("INSERT INTO meta (key, value) VALUES ('schema_version', ?)",
                         (str(SCHEMA_VERSION),))
        return
    version = int(row[0])
    if version > SCHEMA_VERSION:
        raise SchemaVersionError(
            f"the database has schema version {row[0]}, newer than this code "
            f"({SCHEMA_VERSION}); update the code before using it."
        )
    while version < SCHEMA_VERSION:
        version += 1
        step = MIGRATIONS.get(version)
        if step is not None:
            step(conn)
        with conn:
            conn.execute("UPDATE meta SET value = ? WHERE key = 'schema_version'",
                         (str(version),))


def connect(path: Optional[Path] = None) -> sqlite3.Connection:
    """Opens (creating if needed) the database and applies the schema."""
    if path is None:
        _check_not_legacy()
        path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=BUSY_TIMEOUT_MS / 1000)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema(conn)
    return conn


@contextmanager
def session(path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    """A connection that is committed on success and always closed."""
    with closing(connect(path)) as conn:
        with conn:
            yield conn


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)


# --- Vacancies and companies ------------------------------------------------

def load_vacancies() -> dict:
    """Every vacancy record, keyed by id. A missing database reads as empty —
    reading must not create files (tests and fresh identities rely on that)."""
    _check_not_legacy()
    if not exists():
        return {}
    with session() as conn:
        return {vid: json.loads(data)
                for vid, data in conn.execute("SELECT id, data FROM vacancies")}


def save_vacancies(vacancies: dict) -> None:
    """Upserts the `data` column only. The feedback columns belong to the app
    and are never touched here; rows are never deleted, the pipeline has never
    removed a vacancy from the base."""
    with session() as conn:
        conn.executemany(
            "INSERT INTO vacancies (id, data) VALUES (?, ?) "
            "ON CONFLICT(id) DO UPDATE SET data = excluded.data",
            ((vid, dumps(v)) for vid, v in vacancies.items()),
        )


def load_companies() -> dict:
    _check_not_legacy()
    if not exists():
        return {}
    with session() as conn:
        return {key: json.loads(data)
                for key, data in conn.execute("SELECT key, data FROM companies")}


def save_companies(companies: dict) -> None:
    """Companies are rebuilt whole on every run (kb.build_companies_from_vacancies),
    so the table is replaced whole too."""
    with session() as conn:
        conn.execute("DELETE FROM companies")
        conn.executemany("INSERT INTO companies (key, data) VALUES (?, ?)",
                         ((key, dumps(c)) for key, c in companies.items()))


def load_feedback() -> dict:
    """The person's feedback, keyed by vacancy id; vacancies without any are
    absent. Kept out of load_vacancies() on purpose: the vacancy records feed
    scoring, and feedback must not leak into what the scorer reads."""
    if not exists():
        return {}
    with session() as conn:
        rows = conn.execute(
            "SELECT id, feedback_status, rejected_reason, bugged_reason, feedback_at, "
            "feedback_selection_id, feedback_reviewed_at "
            "FROM vacancies WHERE feedback_status <> 'new'"
        )
        return {
            row[0]: {
                "status": row[1], "rejected_reason": row[2], "bugged_reason": row[3],
                "at": row[4], "selection_id": row[5], "reviewed_at": row[6],
            }
            for row in rows
        }


# --- Migration from JSON -----------------------------------------------------

def migrate_from_json() -> dict:
    """Moves the identity's JSON knowledge base into SQLite, once.

    Old hand-set statuses are carried over where they mean the same thing as
    the new feedback: `not_relevant` is the person saying "not for me", which is
    exactly `rejected`, with the old note as the reason. The `manual` field
    itself stays in the record untouched, so nothing is lost either way.
    The JSON files are renamed to *.json.bak, not deleted."""
    common.require_identity()
    if exists():
        raise RuntimeError(f"{db_path()} already exists — nothing to migrate.")
    vac_path, comp_path = common.VACANCIES_PATH, common.COMPANIES_PATH
    if not vac_path.exists():
        raise RuntimeError(f"{vac_path} not found — nothing to migrate.")

    vacancies = common.load_json(vac_path, default={})
    companies = common.load_json(comp_path, default={}) if comp_path.exists() else {}
    migrated_at = now_iso()

    rejected = 0
    # An explicit path skips the "not migrated yet" guard — this IS the migration.
    with session(db_path()) as conn:
        conn.executemany("INSERT INTO vacancies (id, data) VALUES (?, ?)",
                         ((vid, dumps(v)) for vid, v in vacancies.items()))
        conn.executemany("INSERT INTO companies (key, data) VALUES (?, ?)",
                         ((key, dumps(c)) for key, c in companies.items()))
        for vid, v in vacancies.items():
            manual = v.get("manual") or {}
            if manual.get("status") == "not_relevant":
                # Reviewed as of the migration: these marks were made, and acted
                # on, under the old process. Left pending, the first /feedback
                # after migrating would re-open a hundred settled cases.
                conn.execute(
                    "UPDATE vacancies SET feedback_status = 'rejected', "
                    "rejected_reason = ?, feedback_at = ?, feedback_reviewed_at = ? "
                    "WHERE id = ?",
                    ((manual.get("notes") or "").strip() or None, migrated_at,
                     migrated_at, vid),
                )
                rejected += 1

    vac_path.rename(vac_path.with_name(vac_path.name + ".bak"))
    if comp_path.exists():
        comp_path.rename(comp_path.with_name(comp_path.name + ".bak"))
    return {"vacancies": len(vacancies), "companies": len(companies), "rejected": rejected}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
