'use strict';
// The named queries of schemas/queries.sql, shared with tools/selections.py.
// `-- name: <name>` starts a query, `-- include: <name>` stands for another
// query's text; the parsing mirrors selections.load_queries.
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
  // `-- include: <name>` inside a query stands for that query's text
  for (const [key, query] of Object.entries(queries)) {
    queries[key] = query.split('\n')
      .map((line) => (line.startsWith('-- include:') ? queries[line.slice('-- include:'.length).trim()] : line))
      .join('\n');
  }
  return queries;
}

function loadQueries(schemaDir) {
  return parseQueries(fs.readFileSync(path.join(schemaDir, 'queries.sql'), 'utf8'));
}

module.exports = { parseQueries, loadQueries };
