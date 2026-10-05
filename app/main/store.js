'use strict';
// The app's access to the shared SQLite base (schemas/db.sql).
//
// One base holds every identity; each query names the identity it is about
// (:identity). The app reads selections and writes ONLY the feedback and
// funnel columns of `vacancy_identity`. Everything else in the base belongs
// to the pipeline; that column ownership is what lets both write at the same
// time.
const fs = require('node:fs');
const os = require('node:os');
const { DatabaseSync } = require('node:sqlite');
const { loadQueries } = require('./queries');
const funnel = require('../renderer/funnel.js');

const SCHEMA_VERSION = '8';
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
// The funnel filters list the person's applications across collections and
// markets (funnel_listing); the others look at the latest selection.
const FUNNEL = funnel.FUNNEL;
const FILTERS = ['fresh_new', 'no_feedback', 'all', 'fresh', 'rejected', 'bugged', 'expired', ...FUNNEL];
// The first answers, set directly; the funnel beyond "applied" is reached
// only step by step (advance).
const STATUSES = ['new', 'applied', 'rejected', 'bugged', 'expired'];

// The timestamp format tools/db.py writes (seconds, "+00:00"). Feedback and
// review times are compared as strings, so both writers must agree on it.
function nowIso(date = new Date()) {
  return date.toISOString().replace(/\.\d{3}Z$/, '+00:00');
}

function jsonArray(text) {
  if (!text) return [];
  const value = JSON.parse(text);
  return Array.isArray(value) ? value : [];
}

// A row's feedback columns -> the record renderer/funnel.js works with.
function recordOf(row) {
  return {
    status: row.feedback_status,
    at: row.feedback_at,
    rejectedReason: row.rejected_reason,
    buggedReason: row.bugged_reason,
    appliedAt: row.applied_at,
    contactComment: row.contact_comment,
    contactAt: row.contact_at,
    interviewComments: jsonArray(row.interview_comments),
    interviewAt: jsonArray(row.interview_at),
    finalComment: row.final_comment,
    finalAt: row.final_at,
    offerComment: row.awaiting_offer_comment,
    offerAt: row.awaiting_offer_at,
    declinedComment: row.declined_comment,
    declinedAt: row.declined_at,
    offeredComment: row.offered_comment,
    offeredAt: row.offered_at,
    startedComment: row.started_comment,
    startedAt: row.started_at,
  };
}

class SchemaMismatchError extends Error {}

class Store {
  // databasePathOf(identity) -> the base file (one for every identity; the
  // lookup keeps the app working on whatever the identity list says).
  constructor({
    schemaDir, databasePathOf, isPidAlive = pidAlive, hostname = os.hostname(), clock = nowIso,
  }) {
    this.queries = loadQueries(schemaDir);
    this.databasePathOf = databasePathOf;
    this.isPidAlive = isPidAlive;
    this.hostname = hostname;
    this.clock = clock;
    this.connections = new Map();
  }

  // Is a pipeline run of this identity going right now — started from here,
  // from a terminal or by the agent? tools/runstate.py keeps the row; a run
  // killed without cleaning up is recognised by its silent heartbeat, or at
  // once by its dead pid when it ran on this machine. A run of another
  // identity is not this one's, but it holds the base: `busyWith` names it.
  pipelineStatus(identity, now = Date.now()) {
    const db = this.connection(identity);
    if (!db) return { running: false };
    const row = db.prepare(this.queries.pipeline_running).get();
    if (!row) return { running: false };
    const beat = Date.parse(row.heartbeat_at);
    if (Number.isNaN(beat) || now - beat > STALE_AFTER_MS) return { running: false };
    if (row.host === this.hostname && row.pid && !this.isPidAlive(row.pid)) return { running: false };
    if (row.identity_id !== identity) return { running: false, busyWith: row.identity_id };
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
          `${file}: schema version ${row ? row.value : 'missing'}, the app expects ${SCHEMA_VERSION}`
          + ' — any Python tool (e.g. tools/feedback.py count) upgrades a newer one;'
          + ' bases before 8 were merged into one by tools/merge_shared_base.py');
      }
      this.connections.set(file, db);
    }
    return db;
  }

  latestSelection(db, identity) {
    const row = db.prepare(this.queries.latest_selection).get({ identity });
    if (!row || row.id == null) return null;
    return { ...db.prepare(this.queries.selection).get({ selection_id: row.id, identity }) };
  }

  // { selection, displayName, segments } — selection is null before the first
  // run of this identity.
  segments(identity) {
    const db = this.connection(identity);
    if (!db) return { selection: null, displayName: null, segments: [] };
    const selection = this.latestSelection(db, identity);
    const name = db.prepare(this.queries.display_name).get({ identity });
    const segments = selection
      ? db.prepare(this.queries.segments).all({ selection_id: selection.id })
        .map((s) => ({ slug: s.slug, name: s.name, isDefault: s.is_default === 1 }))
      : [];
    return { selection, displayName: name ? name.value : null, segments };
  }

  // The top of each class — as many as `shown` asks for a class
  // ({ hot_lead: 25 }) — and every row of the classes in `expanded`; the
  // funnel filters list every application, uncapped. `source` narrows any of
  // them to one board, `fit` to one class ('' for all).
  listing(identity, segment, filter, expanded = [], source = '', { shown = {}, fit = '' } = {}) {
    if (!FILTERS.includes(filter)) throw new Error(`unknown filter: ${filter}`);
    const db = this.connection(identity);
    const selection = db && this.latestSelection(db, identity);
    if (!selection) return [];
    const rows = FUNNEL.includes(filter)
      ? db.prepare(this.queries.funnel_listing).all({ identity, filter, source, fit })
      : db.prepare(this.queries.listing).all({
        identity, selection_id: selection.id, segment, filter, expanded: `,${expanded.join(',')},`,
        source, shown: JSON.stringify(shown), fit,
      });
    return rows.map((row) => ({
      id: row.vacancy_id,
      class: row.class,
      score: row.score,
      fresh: row.fresh === 1,
      view: row.view ? JSON.parse(row.view) : null,
      // the same row in every interface language; the renderer picks one
      views: row.views ? JSON.parse(row.views) : null,
      feedback: recordOf(row),
    }));
  }

  // { class: how many the filter holds } — "N more" under a capped class.
  classTotals(identity, segment, filter, source = '') {
    if (!FILTERS.includes(filter)) throw new Error(`unknown filter: ${filter}`);
    const db = this.connection(identity);
    const selection = db && this.latestSelection(db, identity);
    if (!selection) return {};
    if (FUNNEL.includes(filter)) {
      const totals = {};
      for (const row of this.listing(identity, segment, filter, [], source)) {
        totals[row.class] = (totals[row.class] || 0) + 1;
      }
      return totals;
    }
    const rows = db.prepare(this.queries.listing_class_totals)
      .all({ identity, selection_id: selection.id, segment, filter, source });
    return Object.fromEntries(rows.map((r) => [r.class, r.total]));
  }

  // [{ source, total }], largest first: the boards the status filter holds in
  // this market — the "Source" drop-down. The source filter does not apply;
  // the class (`fit`) does.
  sources(identity, segment, filter, fit = '') {
    if (!FILTERS.includes(filter)) throw new Error(`unknown filter: ${filter}`);
    const db = this.connection(identity);
    const selection = db && this.latestSelection(db, identity);
    if (!selection) return [];
    const rows = FUNNEL.includes(filter)
      ? db.prepare(this.queries.funnel_sources).all({ identity, filter, fit })
      : db.prepare(this.queries.listing_sources).all({
        identity, selection_id: selection.id, segment, filter, fit,
      });
    const sites = this.sourceSites(db);
    return rows.map((r) => ({ source: r.source, site: sites[r.source] || null, total: r.total }));
  }

  // { source: website } — a database collected before 2026-10-04 has none,
  // and the drop-down shows the source's own name.
  sourceSites(db) {
    const row = db.prepare(this.queries.source_sites).get();
    if (!row || !row.value) return {};
    try {
      return JSON.parse(row.value);
    } catch {
      return {};
    }
  }

  counts(identity, segment, source = '', fit = '') {
    const empty = Object.fromEntries(FILTERS.map((f) => [f, 0]));
    const db = this.connection(identity);
    const selection = db && this.latestSelection(db, identity);
    if (!selection) return empty;
    const row = db.prepare(this.queries.listing_counts)
      .get({ identity, selection_id: selection.id, segment, source, fit });
    const inFunnel = db.prepare(this.queries.funnel_counts).get({ identity, source, fit });
    return Object.fromEntries(FILTERS.map((f) => [f, (FUNNEL.includes(f) ? inFunnel[f] : row[f]) || 0]));
  }

  // The first answer on a vacancy. 'new' takes it back; a reason is kept only
  // for the status it explains.
  setFeedback(identity, vacancyId, status, reason = null) {
    if (!STATUSES.includes(status)) throw new Error(`unknown feedback status: ${status}`);
    const db = this.connection(identity);
    if (!db) throw new Error(`no database for identity ${identity}`);
    const selection = this.latestSelection(db, identity);
    const text = typeof reason === 'string' && reason.trim() ? reason.trim() : null;
    const result = db.prepare(this.queries.set_feedback).run({
      identity,
      id: vacancyId,
      status,
      rejected_reason: status === 'rejected' ? text : null,
      bugged_reason: status === 'bugged' ? text : null,
      at: this.clock(),
      selection_id: status === 'new' || !selection ? null : selection.id,
    });
    if (result.changes !== 1) throw new Error(`no vacancy ${vacancyId} in ${identity}`);
  }

  // --- the application funnel (renderer/funnel.js decides, this writes) ---

  record(identity, vacancyId) {
    const db = this.connection(identity);
    if (!db) throw new Error(`no database for identity ${identity}`);
    const row = db.prepare(this.queries.vacancy_progress).get({ identity, id: vacancyId });
    if (!row) throw new Error(`no vacancy ${vacancyId} in ${identity}`);
    return { db, record: recordOf(row) };
  }

  write(db, identity, vacancyId, record) {
    db.prepare(this.queries.write_progress).run({
      identity,
      id: vacancyId,
      status: record.status,
      at: record.at,
      rejected_reason: record.rejectedReason ?? null,
      bugged_reason: record.buggedReason ?? null,
      applied_at: record.appliedAt ?? null,
      contact_comment: record.contactComment ?? null,
      contact_at: record.contactAt ?? null,
      interview_comments: record.interviewComments.length ? JSON.stringify(record.interviewComments) : null,
      interview_at: record.interviewAt.length ? JSON.stringify(record.interviewAt) : null,
      final_comment: record.finalComment ?? null,
      final_at: record.finalAt ?? null,
      awaiting_offer_comment: record.offerComment ?? null,
      awaiting_offer_at: record.offerAt ?? null,
      declined_comment: record.declinedComment ?? null,
      declined_at: record.declinedAt ?? null,
      offered_comment: record.offeredComment ?? null,
      offered_at: record.offeredAt ?? null,
      started_comment: record.startedComment ?? null,
      started_at: record.startedAt ?? null,
    });
  }

  // One step forward: contacted, interview (again and again), awaiting_final,
  // awaiting_offer, offered, started — or declined, from any of them up to
  // the offer.
  advance(identity, vacancyId, step, comment) {
    const { db, record } = this.record(identity, vacancyId);
    this.write(db, identity, vacancyId, funnel.advance(record, step, comment, this.clock()));
  }

  // "Undo" on a vacancy with an answer: one step back.
  stepBack(identity, vacancyId) {
    const { db, record } = this.record(identity, vacancyId);
    this.write(db, identity, vacancyId, funnel.stepBack(record, this.clock()));
  }

  // Rewrites one comment of the timeline under a vacancy.
  editComment(identity, vacancyId, kind, index, text) {
    const { db, record } = this.record(identity, vacancyId);
    this.write(db, identity, vacancyId, funnel.editComment(record, kind, index, text, this.clock()));
  }

  pendingFeedback(identity) {
    const db = this.connection(identity);
    if (!db) return { bugged: 0, rejected: 0 };
    const row = db.prepare(this.queries.pending_feedback_counts).get({ identity });
    return { bugged: row.bugged, rejected: row.rejected };
  }

  // Before a run: the agent may rebuild the database, so let go of it.
  closeAll() {
    for (const db of this.connections.values()) db.close();
    this.connections.clear();
  }
}

module.exports = { Store, SchemaMismatchError, FILTERS, STATUSES, FUNNEL, nowIso };
