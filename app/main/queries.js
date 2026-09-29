'use strict';
// The named queries of schemas/queries.sql, shared with tools/selections.py.
// `-- name: <name>` starts a query; the parsing mirrors selections.load_queries.
const fs = require('node:fs');
const path = require('node:path');

function parseQueries(text) {
  const queries = {};
  let name = null;
  let lines = [];
  for (const line of text.split(/\r?\n/)) {
    if (line.startsWith('-- name:')) {
      if (name) queries[name] = lines.join('\n').trim();
      name = line.slice('-- name:'.length).trim();
      lines = [];
    } else if (name) {
      lines.push(line);
    }
  }
  if (name) queries[name] = lines.join('\n').trim();
  return queries;
}

function loadQueries(schemaDir) {
  return parseQueries(fs.readFileSync(path.join(schemaDir, 'queries.sql'), 'utf8'));
}

module.exports = { parseQueries, loadQueries };
