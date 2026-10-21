'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { readSourceState, sourceHealth } = require('../../main/source-health');
const { tempDir } = require('../helpers/fixture-db');

test('the state file\'s boards, or nothing when there is no readable file', () => {
  const dir = tempDir();
  assert.deepEqual(readSourceState(dir, 'sharp'), {});
  assert.deepEqual(readSourceState(null, 'sharp'), {});
  fs.writeFileSync(path.join(dir, 'sharp_state.json'), '{not json');
  assert.deepEqual(readSourceState(dir, 'sharp'), {});
  fs.writeFileSync(path.join(dir, 'sharp_state.json'), JSON.stringify({ run_count: 3, sources: { jobicy: { consecutive_failures: 0 } } }));
  assert.deepEqual(readSourceState(dir, 'sharp'), { jobicy: { consecutive_failures: 0 } });
});

test('one row a board from either side; failing first, then the most shortlisted', () => {
  const state = {
    jobicy: { consecutive_failures: 2, last_error: 'HTTPError: 503', fetched_count: 0,
      last_attempt_at: '2026-10-21T08:00:00+00:00', last_success: '2026-10-19T08:00:00+00:00' },
    remotive: { consecutive_failures: 0, last_error: null, fetched_count: 10,
      last_attempt_at: '2026-10-21T08:00:00+00:00', last_success: '2026-10-21T08:00:00+00:00' },
    dataart: { consecutive_failures: 0, fetched_count: 0, last_attempt_at: '2026-10-21T08:00:00+00:00' },
  };
  const yieldRows = [
    { source: 'linkedin', site: 'linkedin.com', total: 900, shortlisted: 30, applied: 2 },
    { source: 'remotive', site: 'remotive.com', total: 80, shortlisted: 3, applied: 0 },
    { source: 'jobicy', site: null, total: 50, shortlisted: 5, applied: 1 },
  ];
  const rows = sourceHealth(state, yieldRows);
  assert.deepEqual(rows.map((r) => r.source), ['jobicy', 'linkedin', 'remotive', 'dataart']);
  assert.deepEqual(rows[0], {
    source: 'jobicy', site: null, total: 50, shortlisted: 5, applied: 1,
    lastAttempt: '2026-10-21T08:00:00+00:00', lastSuccess: '2026-10-19T08:00:00+00:00',
    failures: 2, error: 'HTTPError: 503', fetched: 0,
  });
  assert.equal(rows[1].lastAttempt, null);   // in the base, no attempt on record
  assert.deepEqual([rows[3].total, rows[3].fetched, rows[3].lastSuccess], [0, 0, null]);
});
