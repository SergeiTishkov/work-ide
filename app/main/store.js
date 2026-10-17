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

const SCHEMA_VERSION = '10';
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
// The view: what the four drop-downs chose (schemas/queries.sql, THE VIEW).
// Statuses: no answer yet ("not applied or denied"), the applications —
// listed across collections and markets — and the ones denied.
const FUNNEL = funnel.FUNNEL;
const NEW = ['new'];
const DENIED = ['rejected', 'bugged', 'expired'];
const VIEW_STATUSES = [...NEW, ...FUNNEL, ...DENIED];
const FRESHNESS = ['fresh', 'earlier'];
// The "Company" drop-down's groups (tools/company_kinds.py): the intermediaries
// by kind, then every other company.
const COMPANY_KINDS = ['marketplace', 'agency', 'reposter', 'other'];
// The "Age" drop-down's bands (AGE in schemas/queries.sql).
const AGES = ['today', 'week', 'month', 'older'];
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

// selection_segments.names: {language: name}, NULL in selections from before
// version 9.
function parseNames(text) {
  if (!text) return {};
  const value = JSON.parse(text);
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
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
        .map((s) => ({
          slug: s.slug, name: s.name, names: parseNames(s.names), isDefault: s.is_default === 1,
          everything: s.everything === 1,
        }))
      : [];
    return { selection, displayName: name ? name.value : null, segments };
  }

  // The view's query parameters. `segments` null means every market: the one
  // holding everything, or all of them when the selection names none.
  // `sources` and `fits` null mean every board and class; `companies`
  // null every company, or { kinds: [shown], hidden: [names hidden among them] }.
  viewParams(db, identity, selection, view = {}) {
    const statuses = view.statuses || [];
    const fresh = view.fresh || [];
    const unknown = [...statuses.filter((s) => !VIEW_STATUSES.includes(s)),
      ...fresh.filter((f) => !FRESHNESS.includes(f)),
      ...(view.ages || []).filter((a) => !AGES.includes(a))];
    if (unknown.length) throw new Error(`unknown status, freshness or age: ${unknown.join(', ')}`);
    const companies = view.companies == null ? null
      : { kinds: view.companies.kinds || [], hidden: view.companies.hidden || [] };
    const kinds = companies ? companies.kinds.filter((k) => !COMPANY_KINDS.includes(k)) : [];
    if (kinds.length) throw new Error(`unknown company kind: ${kinds.join(', ')}`);
    let segments = view.segments;
    if (segments == null) {
      const markets = db.prepare(this.queries.segments).all({ selection_id: selection.id });
      const everything = markets.filter((m) => m.everything === 1);
      segments = (everything.length ? everything : markets).map((m) => m.slug);
    }
    const listed = (values) => (values == null ? null : JSON.stringify(values));
    return {
      identity,
      selection_id: selection.id,
      segments: JSON.stringify(segments),
      statuses: JSON.stringify(statuses),
      fresh: JSON.stringify(fresh.map((f) => (f === 'fresh' ? 1 : 0))),
      sources: listed(view.sources),
      fits: listed(view.fits),
      companies: companies && JSON.stringify(companies),
      ages: listed(view.ages),
    };
  }

  // The top of each class — as many as `shown` asks for a class
  // ({ hot_lead: 25 }) — and every row of the classes in `expanded`; rows
  // with an answer are never capped.
  listing(identity, view, { shown = {}, expanded = [] } = {}) {
    const db = this.connection(identity);
    const selection = db && this.latestSelection(db, identity);
    if (!selection) return [];
    const rows = db.prepare(this.queries.view_listing).all({
      ...this.viewParams(db, identity, selection, view),
      expanded: `,${expanded.join(',')},`,
      shown: JSON.stringify(shown),
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

  // { class: how many the view holds }, the chosen classes aside: the "Fit"
  // drop-down, and "N more" under a capped class.
  classTotals(identity, view) {
    const db = this.connection(identity);
    const selection = db && this.latestSelection(db, identity);
    if (!selection) return {};
    // node:sqlite refuses a parameter the query does not name: this one ignores the classes
    const { fits, ...params } = this.viewParams(db, identity, selection, view);
    const rows = db.prepare(this.queries.view_class_totals).all(params);
    return Object.fromEntries(rows.map((r) => [r.class, r.total]));
  }

  // [{ source, site, total }], largest first, the chosen boards aside: the
  // "Source" drop-down.
  sources(identity, view) {
    const db = this.connection(identity);
    const selection = db && this.latestSelection(db, identity);
    if (!selection) return [];
    const { sources, ...params } = this.viewParams(db, identity, selection, view);   // the boards aside
    const rows = db.prepare(this.queries.view_sources).all(params);
    const sites = this.sourceSites(db);
    return rows.map((r) => ({ source: r.source, site: sites[r.source] || null, total: r.total }));
  }

  // The "Show" drop-down's numbers: { statuses: { status: n } } under the
  // chosen freshness, { fresh: { fresh, earlier } } under the chosen statuses.
  counts(identity, view) {
    const result = {
      statuses: Object.fromEntries(VIEW_STATUSES.map((s) => [s, 0])),
      fresh: Object.fromEntries(FRESHNESS.map((f) => [f, 0])),
    };
    const db = this.connection(identity);
    const selection = db && this.latestSelection(db, identity);
    if (!selection) return result;
    for (const row of db.prepare(this.queries.view_counts).all(this.viewParams(db, identity, selection, view))) {
      if (row.axis === 'status') result.statuses[row.key] = row.total;
      else result.fresh[row.key === '1' ? 'fresh' : 'earlier'] = row.total;
    }
    return result;
  }

  // [{ kind, name, total }], largest first, the chosen companies aside: the
  // "Company" drop-down. Every company not an intermediary is one row of kind
  // 'other', name null.
  companies(identity, view) {
    const db = this.connection(identity);
    const selection = db && this.latestSelection(db, identity);
    if (!selection) return [];
    const { companies, ...params } = this.viewParams(db, identity, selection, view);   // the companies aside
    return db.prepare(this.queries.view_companies).all(params)
      .map((r) => ({ kind: r.kind, name: r.name, total: r.total }));
  }

  // { age band: how many }, the chosen ages aside: the "Age" drop-down.
  ages(identity, view) {
    const result = Object.fromEntries(AGES.map((a) => [a, 0]));
    const db = this.connection(identity);
    const selection = db && this.latestSelection(db, identity);
    if (!selection) return result;
    const { ages, ...params } = this.viewParams(db, identity, selection, view);   // the ages aside
    for (const row of db.prepare(this.queries.view_ages).all(params)) result[row.age] = row.total;
    return result;
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

  // Every write below answers with the vacancy's record as the base now holds
  // it, read back after the write: the renderer redraws that one card from it
  // instead of reloading the list (the owner, 2026-10-18).

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
    return this.record(identity, vacancyId).record;
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
    return this.record(identity, vacancyId).record;
  }

  // "Undo" on a vacancy with an answer: one step back.
  stepBack(identity, vacancyId) {
    const { db, record } = this.record(identity, vacancyId);
    this.write(db, identity, vacancyId, funnel.stepBack(record, this.clock()));
    return this.record(identity, vacancyId).record;
  }

  // Rewrites one comment of the timeline under a vacancy.
  editComment(identity, vacancyId, kind, index, text) {
    const { db, record } = this.record(identity, vacancyId);
    this.write(db, identity, vacancyId, funnel.editComment(record, kind, index, text, this.clock()));
    return this.record(identity, vacancyId).record;
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

module.exports = {
  Store, SchemaMismatchError, STATUSES, FUNNEL, NEW, DENIED, VIEW_STATUSES, FRESHNESS, COMPANY_KINDS, AGES, nowIso,
};
