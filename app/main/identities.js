'use strict';
// The identities to show as tabs. Python is the authority on what an identity
// is (tools/identity.py), so the app asks it rather than scanning folders.
// WORK_IDE_IDENTITIES_JSON replaces the call with a file, for tests.
const fs = require('node:fs');
const path = require('node:path');
const { execFile } = require('node:child_process');
const { repoRoot, pythonExecutable } = require('./paths');

function parse(text) {
  return JSON.parse(text).map((e) => ({
    prefix: e.prefix,
    displayName: e.display_name || '',
    database: e.database,
    // the identity's own folder: insights, state, feedback packages, run logs
    dataDir: e.data_dir || null,
    hasDatabase: Boolean(e.has_database),
  }));
}

function listIdentities({ root = repoRoot(), exec = execFile } = {}) {
  const fixture = process.env.WORK_IDE_IDENTITIES_JSON;
  if (fixture) {
    const entries = parse(fs.readFileSync(fixture, 'utf8'));
    // A fixture names paths relative to the fixture root.
    return Promise.resolve(entries.map((e) => {
      const database = path.resolve(root, e.database);
      const dataDir = path.resolve(root, e.dataDir || path.join('data', 'identities', e.prefix));
      return { ...e, database, dataDir, hasDatabase: fs.existsSync(database) };
    }));
  }
  return new Promise((resolve, reject) => {
    exec(pythonExecutable(root), [path.join('tools', 'identity.py'), 'list', '--json'],
      { cwd: root, windowsHide: true },
      (error, stdout, stderr) => {
        if (error) reject(new Error(`tools/identity.py list failed: ${stderr || error.message}`));
        else resolve(parse(stdout));
      });
  });
}

module.exports = { listIdentities, parse };
