'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { loadQueries } = require('../../main/queries');
const { SCHEMA_DIR } = require('../helpers/fixture-db');

test('the shared query file parses into the queries the app needs', () => {
  const queries = loadQueries(SCHEMA_DIR);
  for (const name of ['latest_selection', 'selection', 'segments', 'display_name', 'listing',
    'listing_counts', 'set_feedback', 'pending_feedback_counts']) {
    assert.ok(queries[name] && queries[name].length > 10, name);
  }
});
