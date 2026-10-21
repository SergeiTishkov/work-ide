'use strict';
// "Sources..." (task 0054): how each board fares and what it brings. The
// pipeline keeps each board's last attempt in <dataDir>/<prefix>_state.json
// (tools/pipeline.py, `state["sources"]`); the base says how many of its
// vacancies the identity holds, shortlisted and applied to (store.sourceYield).
const fs = require('node:fs');
const path = require('node:path');

// { source: its last attempt } from the identity's state file; {} when the
// identity was never collected or the file cannot be read.
function readSourceState(dataDir, prefix) {
  try {
    const state = JSON.parse(fs.readFileSync(path.join(dataDir, `${prefix}_state.json`), 'utf8'));
    return state && typeof state.sources === 'object' && state.sources ? state.sources : {};
  } catch {
    return {};
  }
}

// One row a board, from either side: a board the base holds but no run
// fetched lately has no attempt; one fetched with nothing kept has no
// vacancies. Failing boards first, then the most shortlisted.
function sourceHealth(stateSources, yieldRows) {
  const rows = new Map();
  const blank = (source) => ({
    source, site: null, total: 0, shortlisted: 0, applied: 0,
    lastAttempt: null, lastSuccess: null, failures: 0, error: null, fetched: null,
  });
  for (const y of yieldRows) rows.set(y.source, { ...blank(y.source), ...y });
  for (const [source, s] of Object.entries(stateSources || {})) {
    const row = rows.get(source) || blank(source);
    rows.set(source, {
      ...row,
      lastAttempt: s.last_attempt_at || null,
      lastSuccess: s.last_success || null,
      failures: Number(s.consecutive_failures) || 0,
      error: s.last_error || null,
      fetched: s.fetched_count == null ? null : Number(s.fetched_count),
    });
  }
  return [...rows.values()].sort((a, b) => (b.failures > 0) - (a.failures > 0)
    || b.shortlisted - a.shortlisted || b.total - a.total || a.source.localeCompare(b.source));
}

module.exports = { readSourceState, sourceHealth };
