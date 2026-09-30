'use strict';
// The app's access to the identities' SQLite databases (schemas/db.sql).
//
// The app reads selections and writes ONLY the feedback columns of
// `vacancies`. Everything else in the database belongs to the pipeline; that
// column ownership is what lets both write at the same time.
const fs = require('node:fs');
const os = require('node:os');
const { DatabaseSync } = require('node:sqlite');
const { loadQueries } = require('./queries');

const SCHEMA_VERSION = '2';
// The same threshold as tools/runstate.STALE_AFTER_SECONDS: a run that has not
// beaten for this long is gone, whatever its row still says.
const STALE_AFTER_MS = 45000;

// process.kill(pid, 0) sends nothing; it only asks whether the process exists,
// on Windows as elsewhere. EPERM means it exists but is not ours.
function pidAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error.code === 'EPERM';
  }
}
const BUSY_TIMEOUT_MS = 60000;
const FILTERS = ['fresh_new', 'all', 'fresh', 'applied', 'rejected', 'bugged'];
const STATUSES = ['new', 'applied', 'rejected', 'bugged'];

// The timestamp format tools/db.py writes (seconds, "+00:00"). Feedback and
// review times are compared as strings, so both writers must agree on it.
function nowIso(date = new Date()) {
  return date.toISOString().replace(/\.\d{3}Z$/, '+00:00');
}

class SchemaMismatchError extends Error {}

class Store {
  // databasePathOf(identity) -> the file of that identity's database.
  constructor({ schemaDir, databasePathOf, isPidAlive = pidAlive, hostname = os.hostname() }) {
    this.queries = loadQueries(schemaDir);
    this.databasePathOf = databasePathOf;
    this.isPidAlive = isPidAlive;
    this.hostname = hostname;
    this.connections = new Map();
  }

  // Is a pipeline run of this identity going right now — started from here,
  // from a terminal or by the agent? tools/runstate.py keeps the row; a run
  // killed without cleaning up is recognised by its silent heartbeat, or at
  // once by its dead pid when it ran on this machine.
  pipelineStatus(identity, now = Date.now()) {
    const db = this.connection(identity);
    if (!db) return { running: false };
    const row = db.prepare(this.queries.pipeline_running).get();
    if (!row) return { running: false };
    const beat = Date.parse(row.heartbeat_at);
    if (Number.isNaN(beat) || now - beat > STALE_AFTER_MS) return { running: false };
    if (row.host === this.hostname && row.pid && !this.isPidAlive(row.pid)) return { running: false };
    return { running: true, stage: row.stage, startedAt: row.started_at, pid: row.pid, host: row.host };
  }

  // null when the identity has never been collected: the app never creates a
  // database, the schema belongs to the Python side.
  connection(identity) {
    const file = this.databasePathOf(identity);
    if (!file || !fs.existsSync(file)) return null;
    let db = this.connections.get(file);
    if (!db) {
      db = new DatabaseSync(file);
      db.exec(`PRAGMA busy_timeout = ${BUSY_TIMEOUT_MS}`);
      const row = db.prepare("SELECT value FROM meta WHERE key = 'schema_version'").get();
      if (!row || row.value !== SCHEMA_VERSION) {
        db.close();
        throw new SchemaMismatchError(
          `${file}: schema version ${row ? row.value : 'missing'}, the app expects ${SCHEMA_VERSION}`);
      }
      this.connections.set(file, db);
    }
    return db;
  }

  latestSelection(db) {
    const row = db.prepare(this.queries.latest_selection).get();
    if (!row || row.id == null) return null;
    return { ...db.prepare(this.queries.selection).get({ selection_id: row.id }) };
  }

  // { selection, displayName, segments } — selection is null before the first
  // run of this identity.
  segments(identity) {
    const db = this.connection(identity);
    if (!db) return { selection: null, displayName: null, segments: [] };
    const selection = this.latestSelection(db);
    const name = db.prepare(this.queries.display_name).get();
    const segments = selection
      ? db.prepare(this.queries.segments).all({ selection_id: selection.id })
        .map((s) => ({ slug: s.slug, name: s.name, isDefault: s.is_default === 1 }))
      : [];
    return { selection, displayName: name ? name.value : null, segments };
  }

  // The top of each class, and every row of the classes in `expanded`.
  listing(identity, segment, filter, expanded = []) {
    if (!FILTERS.includes(filter)) throw new Error(`unknown filter: ${filter}`);
    const db = this.connection(identity);
    const selection = db && this.latestSelection(db);
    if (!selection) return [];
    return db.prepare(this.queries.listing)
      .all({ selection_id: selection.id, segment, filter, expanded: `,${expanded.join(',')},` })
      .map((row) => ({
        id: row.vacancy_id,
        class: row.class,
        score: row.score,
        fresh: row.fresh === 1,
        view: row.view ? JSON.parse(row.view) : null,
        feedback: {
          status: row.feedback_status,
          rejectedReason: row.rejected_reason,
          buggedReason: row.bugged_reason,
          at: row.feedback_at,
        },
      }));
  }

  // { class: how many the filter holds } — "N more" under a capped class.
  classTotals(identity, segment, filter) {
    if (!FILTERS.includes(filter)) throw new Error(`unknown filter: ${filter}`);
    const db = this.connection(identity);
    const selection = db && this.latestSelection(db);
    if (!selection) return {};
    const rows = db.prepare(this.queries.listing_class_totals)
      .all({ selection_id: selection.id, segment, filter });
    return Object.fromEntries(rows.map((r) => [r.class, r.total]));
  }

  counts(identity, segment) {
    const empty = Object.fromEntries(FILTERS.map((f) => [f, 0]));
    const db = this.connection(identity);
    const selection = db && this.latestSelection(db);
    if (!selection) return empty;
    const row = db.prepare(this.queries.listing_counts)
      .get({ selection_id: selection.id, segment });
    return Object.fromEntries(FILTERS.map((f) => [f, row[f] || 0]));
  }

  // status 'new' takes the mark back; a reason is kept only for the status it
  // explains.
  setFeedback(identity, vacancyId, status, reason = null) {
    if (!STATUSES.includes(status)) throw new Error(`unknown feedback status: ${status}`);
    const db = this.connection(identity);
    if (!db) throw new Error(`no database for identity ${identity}`);
    const selection = this.latestSelection(db);
    const text = typeof reason === 'string' && reason.trim() ? reason.trim() : null;
    const result = db.prepare(this.queries.set_feedback).run({
      id: vacancyId,
      status,
      rejected_reason: status === 'rejected' ? text : null,
      bugged_reason: status === 'bugged' ? text : null,
      at: nowIso(),
      selection_id: status === 'new' || !selection ? null : selection.id,
    });
    if (result.changes !== 1) throw new Error(`no vacancy ${vacancyId} in ${identity}`);
  }

  pendingFeedback(identity) {
    const db = this.connection(identity);
    if (!db) return { bugged: 0, rejected: 0 };
    const row = db.prepare(this.queries.pending_feedback_counts).get();
    return { bugged: row.bugged, rejected: row.rejected };
  }

  // Before a run: the agent may rebuild the database, so let go of it.
  closeAll() {
    for (const db of this.connections.values()) db.close();
    this.connections.clear();
  }
}

module.exports = { Store, SchemaMismatchError, FILTERS, STATUSES, nowIso };
