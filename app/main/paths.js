'use strict';
// Where the repository is. WORK_IDE_ROOT points the app at a fixture tree in
// tests; in normal use the app lives in <repo>/app and the repo is its parent.
const path = require('node:path');

function repoRoot() {
  return process.env.WORK_IDE_ROOT || path.resolve(__dirname, '..', '..');
}

function schemaDir(root = repoRoot()) {
  return path.join(root, 'schemas');
}

// The Python of the repository's virtual environment, when there is one.
function pythonExecutable(root = repoRoot()) {
  const fs = require('node:fs');
  const candidates = process.platform === 'win32'
    ? [path.join(root, '.venv', 'Scripts', 'python.exe')]
    : [path.join(root, '.venv', 'bin', 'python')];
  return candidates.find((p) => fs.existsSync(p)) || 'python';
}

module.exports = { repoRoot, schemaDir, pythonExecutable };
