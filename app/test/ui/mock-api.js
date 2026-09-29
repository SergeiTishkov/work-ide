'use strict';
// window.api for UI tests: in-memory data, and every call recorded in
// window.__calls so a test can assert on exactly what the UI asked for.
// installMockApi runs INSIDE the page (page.addInitScript), so it must be
// self-contained.

function installMockApi(fixture) {
  const calls = [];
  const listeners = [];
  const data = JSON.parse(JSON.stringify(fixture));
  window.__calls = calls;
  window.__emitRunEvent = (event) => listeners.forEach((l) => l(event));

  function record(name, args) {
    calls.push({ name, args });
  }

  function matches(row, filter) {
    const status = row.feedback.status;
    if (filter === 'fresh_new') return row.fresh && status === 'new';
    if (filter === 'all') return true;
    if (filter === 'fresh') return row.fresh;
    return status === filter;
  }

  function rowsOf(identity, segment) {
    return ((data.rows[identity] || {})[segment]) || [];
  }

  window.api = {
    async listIdentities() {
      record('listIdentities', []);
      return data.identities;
    },
    async loadSegments(identity) {
      record('loadSegments', [identity]);
      return data.segments[identity] || { selection: null, displayName: null, segments: [] };
    },
    async loadListing(identity, segment, filter) {
      record('loadListing', [identity, segment, filter]);
      return rowsOf(identity, segment).filter((row) => matches(row, filter));
    },
    async listingCounts(identity, segment) {
      record('listingCounts', [identity, segment]);
      const counts = {};
      for (const f of ['fresh_new', 'all', 'fresh', 'applied', 'rejected', 'bugged']) {
        counts[f] = rowsOf(identity, segment).filter((row) => matches(row, f)).length;
      }
      return counts;
    },
    async setFeedback(identity, id, status, reason) {
      record('setFeedback', [identity, id, status, reason]);
      for (const rows of Object.values(data.rows[identity] || {})) {
        for (const row of rows) {
          if (row.id !== id) continue;
          row.feedback = {
            status,
            rejectedReason: status === 'rejected' ? reason : null,
            buggedReason: status === 'bugged' ? reason : null,
          };
        }
      }
    },
    async pendingFeedbackCount(identity) {
      record('pendingFeedbackCount', [identity]);
      const seen = new Map();
      for (const rows of Object.values(data.rows[identity] || {})) {
        for (const row of rows) seen.set(row.id, row.feedback.status);
      }
      const statuses = [...seen.values()];
      return {
        bugged: statuses.filter((s) => s === 'bugged').length,
        rejected: statuses.filter((s) => s === 'rejected').length,
      };
    },
    async getRunState() {
      record('getRunState', []);
      return { running: false };
    },
    async startRun(request) {
      record('startRun', [request]);
      return data.startRunReply || { ok: true };
    },
    async stopRun() {
      record('stopRun', []);
      return { ok: true };
    },
    async openExternal(url) {
      record('openExternal', [url]);
    },
    onRunEvent(listener) {
      listeners.push(listener);
      return () => {};
    },
  };
}

function row(id, { cls = 'hot_lead', score = 60, fresh = true, status = 'new' } = {}) {
  return {
    id,
    class: cls,
    score,
    fresh,
    view: {
      id, title: `Senior .NET Developer ${id}`, company: `Company ${id}`,
      url: `https://example.test/${id}`, score, classification: cls,
      highlights: ['legacy/enterprise: insurance'], salary: 'not stated _(no data)_',
      to_confirm: [], company_url: null,
      eligibility: { level: 'likely', label: 'likely', reason: 'anywhere' },
      apply_channels: [], technologies: ['C#'], reputation: 'not checked',
      hiring_country: 'United Kingdom', company_age: null, note: null,
      needs_manual_review: id.endsWith('r'),
    },
    feedback: { status, rejectedReason: null, buggedReason: null },
  };
}

// kisel: collected, three markets; pjoice: collected, one market;
// newbie: never collected.
function standardFixture() {
  const full = [
    row('a1', { score: 80 }), row('a2r', { score: 70 }), row('a3', { score: 50, fresh: false }),
    row('b1', { cls: 'worth_a_look', score: 45 }),
    row('x1', { score: 40, status: 'bugged' }),
  ];
  const selection = { id: 7, run: 55, created_at: '2026-09-29T10:00:00+00:00', kind: 'run' };
  return {
    identities: [
      { prefix: 'kisel', displayName: 'Calm legacy work', hasDatabase: true },
      { prefix: 'pjoice', displayName: 'Part-time side work', hasDatabase: true },
      { prefix: 'newbie', displayName: 'Nothing yet', hasDatabase: false },
    ],
    segments: {
      kisel: {
        selection, displayName: 'Calm legacy work',
        segments: [
          { slug: 'worldwide', name: 'Worldwide', isDefault: false },
          { slug: 'uk', name: 'United Kingdom', isDefault: false },
          { slug: 'full', name: 'Everything', isDefault: true },
        ],
      },
      pjoice: {
        selection: { ...selection, id: 3 }, displayName: 'Part-time side work',
        segments: [{ slug: 'full', name: 'Everything', isDefault: true }],
      },
    },
    rows: {
      kisel: { full, uk: [row('u1'), row('u2', { fresh: false })], worldwide: [] },
      pjoice: { full: [row('p1')] },
    },
  };
}

module.exports = { installMockApi, standardFixture, row };
