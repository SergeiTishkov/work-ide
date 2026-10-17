'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { loadQueries, parseQueries } = require('../../main/queries');
const { SCHEMA_DIR } = require('../helpers/fixture-db');

test('the shared query file parses into the queries the app needs', () => {
  const queries = loadQueries(SCHEMA_DIR);
  for (const name of ['latest_selection', 'selection', 'segments', 'display_name', 'view_listing',
    'view_counts', 'view_class_totals', 'view_sources', 'view_companies', 'set_feedback',
    'pending_feedback_counts']) {
    assert.ok(queries[name] && queries[name].length > 10, name);
  }
  for (const name of ['view_listing', 'view_counts', 'view_class_totals', 'view_sources', 'view_companies']) {
    assert.ok(!queries[name].includes('-- include:'), name);
    assert.ok(queries[name].includes('pool AS ('), name);
  }
});

// 2026-10-18: folded into the join, company_kinds parsed the meta value
// again for every row of the pool — 1.9 s for the list's queries, every click.
test('the company kinds are a table built once, looked up by an index, in every view query', () => {
  const fs = require('node:fs');
  const path = require('node:path');
  const { DatabaseSync } = require('node:sqlite');
  const db = new DatabaseSync(':memory:');
  db.exec(fs.readFileSync(path.join(SCHEMA_DIR, 'db.sql'), 'utf8'));
  const queries = loadQueries(SCHEMA_DIR);
  for (const name of ['view_listing', 'view_counts', 'view_class_totals', 'view_sources', 'view_companies',
    'view_ages']) {
    const params = Object.fromEntries([...queries[name].matchAll(/:(\w+)/g)].map((m) => [m[1], null]));
    const plan = db.prepare(`EXPLAIN QUERY PLAN ${queries[name]}`).all(params).map((r) => r.detail);
    assert.ok(plan.includes('MATERIALIZE company_kinds'), `${name}: ${plan.join(' | ')}`);
    assert.ok(!plan.some((d) => /SCAN json_each.*LEFT-JOIN/.test(d)), `${name}: ${plan.join(' | ')}`);
  }
});

test('an include line stands for the named query', () => {
  const queries = parseQueries('-- name: part\nx AS (SELECT 1)\n\n-- name: whole\nWITH\n-- include: part\nSELECT * FROM x;\n');
  assert.equal(queries.whole, 'WITH\nx AS (SELECT 1)\nSELECT * FROM x;');
});
