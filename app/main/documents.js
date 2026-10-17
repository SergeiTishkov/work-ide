'use strict';
// The folder of generated CVs and cover letters, laid out by
// tools/documents.py: <folder>/<identity>/<vacancy id>/, with "CV log.md" and
// "Cover Letter log.md" in it. The app reads the logs for its buttons — which
// documents a vacancy has — without starting Python for every list.
const fs = require('node:fs');
const path = require('node:path');
const { execFile } = require('node:child_process');

const LOGS = { cv: 'CV log.md', letter: 'Cover Letter log.md' };
const VERSION_RE = /^## V\d+ · /;
const ERROR_RE = /^## Error · /;
// The same rules as cv.js
const IDENTITY_PATTERN = /^[a-z][a-z0-9]{2,9}$/;
const VACANCY_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;

function vacancyDir(root, identity, vacancyId) {
  if (!IDENTITY_PATTERN.test(String(identity))) throw new Error(`invalid identity: ${identity}`);
  if (!VACANCY_PATTERN.test(String(vacancyId))) throw new Error(`invalid vacancy id: ${vacancyId}`);
  return path.join(root, identity, vacancyId);
}

// { versions, error }: how many versions the log records, and the error it
// ends with ("Vacancy not found, possibly outdated: ..."), if it does.
function readLog(file) {
  let text;
  try {
    text = fs.readFileSync(file, 'utf8');
  } catch {
    return { versions: 0, error: null };
  }
  let versions = 0;
  let error = null;
  for (const line of text.split(/\r?\n/)) {
    if (VERSION_RE.test(line)) {
      versions += 1;
      error = null;
    } else if (ERROR_RE.test(line)) {
      error = '';
    } else if (error === '' && line.trim()) {
      error = line.trim();
    }
  }
  return { versions, error: error || null };
}

// { id: { dir, cv, letter, errors: { kind: text } } } for the vacancies with a
// folder; the others are left out.
function documentsState(root, identity, vacancyIds) {
  const result = {};
  for (const id of vacancyIds || []) {
    if (!VACANCY_PATTERN.test(String(id))) continue;
    const dir = vacancyDir(root, identity, id);
    if (!fs.existsSync(dir)) continue;
    const entry = { dir, cv: 0, letter: 0, errors: {} };
    for (const [kind, name] of Object.entries(LOGS)) {
      const log = readLog(path.join(dir, name));
      entry[kind] = log.versions;
      if (log.error) entry.errors[kind] = log.error;
    }
    result[id] = entry;
  }
  return result;
}

// The folder: WORK_IDE_DOCUMENTS_DIR, else what tools/documents.py says (the
// person's setting, or ~/Downloads/Work IDE CVs and CLs).
function resolveRoot({ root, python, env = process.env, run = execFile }) {
  if (env.WORK_IDE_DOCUMENTS_DIR) return Promise.resolve(env.WORK_IDE_DOCUMENTS_DIR);
  return new Promise((resolve, reject) => {
    run(python, [path.join('tools', 'documents.py'), 'where', '--json'],
      { cwd: root, windowsHide: true, env: { ...env, PYTHONIOENCODING: 'utf-8' } },
      (error, stdout) => {
        if (error) {
          reject(new Error(`tools/documents.py where: ${error.message}`));
          return;
        }
        try {
          resolve(JSON.parse(String(stdout).trim().split(/\r?\n/).pop()).folder);
        } catch {
          reject(new Error(`tools/documents.py where: ${String(stdout).slice(0, 200)}`));
        }
      });
  });
}

module.exports = { documentsState, readLog, resolveRoot, vacancyDir, LOGS };
