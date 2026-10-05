"""
The SQLite knowledge base shared by every identity: data/workide.sqlite.

WHY SQLITE, AND NOT THE JSON FILES IT REPLACES
----------------------------------------------
Two writers touch the vacancy base: the pipeline, and the desktop app
recording a person's feedback on a vacancy. With one JSON file of 150 MB, every
click in the app meant rewriting the whole file, possibly while the pipeline
was rewriting it too, and one of the two would silently lose. SQLite gives each
writer its own columns inside one transactional file, so neither can overwrite
the other (the column ownership is written down in schemas/db.sql).

WHY ONE BASE FOR EVERY IDENTITY
-------------------------------
A vacancy is the same posting whoever looks at it; only its score, its class
and the person's answer depend on the identity. Since 2026-10-05 the facts
live once (`vacancies`) and the rest per identity (`vacancy_identity`), so a
vacancy fetched for one search is scored for every search.

The rest of the code did not have to change: load_vacancies() returns a plain
dict keyed by id — the facts with the active identity's `computed` and
`duplicate_of` on top — and save_vacancies() takes one and splits it again.

The schema lives in schemas/db.sql, shared with the app's tests.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

# 8: one base for every identity. The per-identity files of versions 1-7 are
# not upgraded in place: tools/merge_shared_base.py merged them once.
SCHEMA_VERSION = 8
SCHEMA_PATH = common.ROOT / "schemas" / "db.sql"

# How long a writer waits for another writer's transaction before giving up.
# The pipeline's largest transaction (saving the whole base) takes seconds.
BUSY_TIMEOUT_MS = 60_000

FEEDBACK_STATUSES = ("new", "applied", "rejected", "bugged", "expired",
                     "contacted", "interview", "awaiting_final", "awaiting_offer",
                     "declined", "offered", "started")

# The keys of a loaded record that belong to the identity, not to the vacancy.
PER_IDENTITY_KEYS = ("computed", "duplicate_of")

# Copied onto a record for one scoring pass (kb.attach_company_reputation);
# the company table is where they live.
TRANSIENT_KEYS = ("_company_reputation", "_company_intel")


class SchemaVersionError(RuntimeError):
    """The database was created by a different version of the schema."""


def db_path() -> Path:
    return common.DB_PATH


def exists() -> bool:
    return db_path().exists()


def identity() -> str:
    common.require_identity()
    return common.ACTIVE_IDENTITY


# version reached -> the step that reaches it. Empty since version 8 started
# the shared base afresh; the next change to an existing table adds its step
# here.
MIGRATIONS: dict = {}


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
        if step is None:
            raise SchemaVersionError(
                f"the database has schema version {row[0]} and there is no step to "
                f"version {version}: a base from before the shared one (version 8) is "
                "merged by tools/merge_shared_base.py, not upgraded in place.")
        step(conn)
        with conn:
            conn.execute("UPDATE meta SET value = ? WHERE key = 'schema_version'",
                         (str(version),))


def connect(path: Optional[Path] = None) -> sqlite3.Connection:
    """Opens (creating if needed) the database and applies the schema."""
    path = path or db_path()
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


def now_iso() -> str:
    """The one timestamp format of the base: seconds, "+00:00". Feedback and
    review times are compared as strings, so every writer — the app included
    (store.js nowIso) — must agree on it."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_identity(conn: sqlite3.Connection, prefix: Optional[str] = None,
                    display_name: Optional[str] = None) -> str:
    """The identity's row, created on first use; the display name refreshed
    when given. Returns the prefix."""
    prefix = prefix or identity()
    conn.execute("INSERT INTO identities (id, display_name, created_at) VALUES (?, ?, ?) "
                 "ON CONFLICT(id) DO NOTHING", (prefix, display_name, now_iso()))
    if display_name is not None:
        conn.execute("UPDATE identities SET display_name = ? WHERE id = ?",
                     (display_name, prefix))
    return prefix


# --- Vacancies and companies ------------------------------------------------

def split_record(record: dict) -> tuple:
    """(facts, computed, duplicate_of) of one loaded record."""
    facts = {k: v for k, v in record.items()
             if k not in PER_IDENTITY_KEYS and k not in TRANSIENT_KEYS}
    return facts, record.get("computed"), record.get("duplicate_of")


def join_record(data: str, computed: Optional[str], duplicate_of: Optional[str]) -> dict:
    record = json.loads(data)
    if computed is not None:
        record["computed"] = json.loads(computed)
    if duplicate_of is not None:
        record["duplicate_of"] = duplicate_of
    return record


def load_vacancies() -> dict:
    """Every vacancy in the base, keyed by id, with the active identity's
    verdict on it. A vacancy the identity has not scored yet comes without
    `computed`. A missing database reads as empty — reading must not create
    files (tests and fresh identities rely on that)."""
    prefix = identity()
    if not exists():
        return {}
    with session() as conn:
        rows = conn.execute(
            "SELECT v.id, v.data, vi.computed, vi.duplicate_of FROM vacancies v "
            "LEFT JOIN vacancy_identity vi ON vi.vacancy_id = v.id AND vi.identity_id = ?",
            (prefix,))
        return {vid: join_record(data, computed, dup) for vid, data, computed, dup in rows}


def save_vacancies(vacancies: dict) -> None:
    """Upserts the facts and the active identity's verdict, in one
    transaction. The feedback columns belong to the app and are never touched
    here; rows are never deleted, the pipeline has never removed a vacancy
    from the base."""
    prefix = identity()
    facts_rows, verdict_rows = [], []
    for vid, record in vacancies.items():
        facts, computed, duplicate_of = split_record(record)
        facts_rows.append((vid, dumps(facts)))
        c = computed or {}
        verdict_rows.append((prefix, vid, dumps(computed) if computed is not None else None,
                             c.get("score"), c.get("classification"), duplicate_of))
    with session() as conn:
        ensure_identity(conn, prefix)
        conn.executemany(
            "INSERT INTO vacancies (id, data) VALUES (?, ?) "
            "ON CONFLICT(id) DO UPDATE SET data = excluded.data", facts_rows)
        conn.executemany(
            "INSERT INTO vacancy_identity (identity_id, vacancy_id, computed, score, class, "
            "duplicate_of) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(identity_id, vacancy_id) DO UPDATE SET computed = excluded.computed, "
            "score = excluded.score, class = excluded.class, "
            "duplicate_of = excluded.duplicate_of", verdict_rows)


def load_companies() -> dict:
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
