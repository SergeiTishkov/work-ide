'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { codeStamp, refreshAction } = require('../../main/code-stamp');
const { tempDir } = require('../helpers/fixture-db');

test('the stamp changes when a main-process file changes, and only then', () => {
  const dir = tempDir();
  fs.writeFileSync(path.join(dir, 'main.js'), 'a');
  fs.writeFileSync(path.join(dir, 'store.js'), 'b');
  fs.writeFileSync(path.join(dir, 'notes.txt'), 'c');
  const before = codeStamp(dir);
  assert.equal(codeStamp(dir), before, 'stable while nothing changes');

  fs.utimesSync(path.join(dir, 'notes.txt'), new Date(), new Date(Date.now() + 60000));
  assert.equal(codeStamp(dir), before, 'non-code files do not count');

  fs.utimesSync(path.join(dir, 'store.js'), new Date(), new Date(Date.now() + 60000));
  assert.notEqual(codeStamp(dir), before);

  fs.writeFileSync(path.join(dir, 'new-module.js'), 'd');
  assert.notEqual(codeStamp(dir), before, 'a new module counts');
});

test('Refresh reloads the page while the main process is current', () => {
  assert.equal(refreshAction({ startedWith: 'x', now: 'x', agentRunning: false }), 'reload');
  assert.equal(refreshAction({ startedWith: 'x', now: 'x', agentRunning: true }), 'reload');
});

test('Refresh restarts the app when the main process runs outdated code', () => {
  assert.equal(refreshAction({ startedWith: 'x', now: 'y', agentRunning: false }), 'relaunch');
});

test('...but never cuts off an agent run started from the app', () => {
  assert.equal(refreshAction({ startedWith: 'x', now: 'y', agentRunning: true }), 'reload-busy');
});
