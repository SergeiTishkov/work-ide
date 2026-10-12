'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { loadQueries, parseQueries } = require('../../main/queries');
const { SCHEMA_DIR } = require('../helpers/fixture-db');

test('the shared query file parses into the queries the app needs', () => {
  const queries = loadQueries(SCHEMA_DIR);
  for (const name of ['latest_selection', 'selection', 'segments', 'display_name', 'view_listing',
    'view_counts', 'view_class_totals', 'view_sources', 'set_feedback', 'pending_feedback_counts']) {
    assert.ok(queries[name] && queries[name].length > 10, name);
  }
  for (const name of ['view_listing', 'view_counts', 'view_class_totals', 'view_sources']) {
    assert.ok(!queries[name].includes('-- include:'), name);
    assert.ok(queries[name].includes('pool AS ('), name);
  }
});

test('an include line stands for the named query', () => {
  const queries = parseQueries('-- name: part\nx AS (SELECT 1)\n\n-- name: whole\nWITH\n-- include: part\nSELECT * FROM x;\n');
  assert.equal(queries.whole, 'WITH\nx AS (SELECT 1)\nSELECT * FROM x;');
});
