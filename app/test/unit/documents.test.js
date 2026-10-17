'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { documentsState, readLog, resolveRoot, vacancyDir } = require('../../main/documents');

function folder() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'work-ide-docs-'));
}

test('the logs say how many versions a vacancy has, and the error one ends with', () => {
  const root = folder();
  const dir = path.join(root, 'sharp', 'a1');
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'CV log.md'),
    '# CV log\n\n## V1 · 2026-10-13 14:02 · failed\nWithout a message.\nFailed: start over\n\n'
    + '## V2 · 2026-10-13 14:20\nMessage:\n> Shorter.\n');
  fs.writeFileSync(path.join(dir, 'Cover Letter log.md'),
    '# Cover Letter log\n\n## Error · 2026-10-13 14:25\nVacancy not found, possibly outdated: the link is dead.\n');
  assert.deepEqual(documentsState(root, 'sharp', ['a1', 'a2', '../x']), {
    a1: { dir, cv: 2, letter: 0, errors: { letter: 'Vacancy not found, possibly outdated: the link is dead.' } },
  });
  assert.deepEqual(readLog(path.join(dir, 'missing.md')), { versions: 0, error: null });
});

test('a version after an error clears it', () => {
  const file = path.join(folder(), 'log.md');
  fs.writeFileSync(file, '# CV log\n\n## Error · 2026-10-13 14:25\nVacancy not found.\n\n'
    + '## V1 · 2026-10-14 09:00\nWithout a message.\n');
  assert.deepEqual(readLog(file), { versions: 1, error: null });
});

test('identity then vacancy; a malformed one is refused', () => {
  assert.equal(vacancyDir('/docs', 'sharp', 'a1'), path.join('/docs', 'sharp', 'a1'));
  assert.throws(() => vacancyDir('/docs', 'sharp', '../a1'));
  assert.throws(() => vacancyDir('/docs', '../sharp', 'a1'));
});

test('the folder: the environment, else what tools/documents.py says', async () => {
  assert.equal(await resolveRoot({ root: '/repo', python: 'py', env: { WORK_IDE_DOCUMENTS_DIR: '/env' } }), '/env');
  const calls = [];
  const run = (command, args, options, callback) => {
    calls.push([command, args, options.cwd]);
    callback(null, '{"folder": "C:/Users/me/Downloads/Work IDE CVs and CLs", "source": "the default"}\n');
  };
  assert.equal(await resolveRoot({ root: '/repo', python: 'py', env: {}, run }),
    'C:/Users/me/Downloads/Work IDE CVs and CLs');
  assert.deepEqual(calls, [['py', [path.join('tools', 'documents.py'), 'where', '--json'], '/repo']]);
});
