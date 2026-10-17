'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { batchPaths, batchTask, BatchWatch, startBatch, stopBatch, holdBatch } = require('../../main/batch');

const STATUS = {
  pid: 4242, state: 'running', holding: false, identities: ['sharp', 'partsharp'],
  started_at: '2026-10-13T03:30:54+04:00', ended_at: null, total: 971, index: 8,
  made: 6, failed: 1, gone: 0, error: null, log_offset: 0,
  current: { identity: 'sharp', kind: 'cv', vacancy_id: 'a1', title: 'Dev', company: 'Acme' },
};

function tempRoot() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'work-ide-batch-'));
}

test('the status file becomes a task of the panel', () => {
  const task = batchTask(STATUS, { alive: () => true });
  assert.equal(task.id, 'batch');
  assert.equal(task.state, 'running');
  assert.equal(task.identity, 'sharp, partsharp');
  assert.deepEqual(task.progress, { index: 8, total: 971, made: 6, failed: 1, gone: 0 });
  assert.deepEqual(task.current, { identity: 'sharp', kind: 'cv', vacancyId: 'a1', title: 'Dev', company: 'Acme' });
  assert.equal(batchTask({ ...STATUS, state: 'finished', current: null }, { alive: () => false }).state, 'done');
  assert.equal(batchTask({ ...STATUS, state: 'stopped' }).state, 'stopped');
  assert.equal(batchTask(STATUS, { alive: () => true, stopAsked: true }).stopping, true);
  assert.equal(batchTask(null), null);
});

test('a batch whose process is gone while it says running is a failed one', () => {
  const task = batchTask(STATUS, { alive: () => false });
  assert.equal(task.state, 'failed');
  assert.match(task.error, /ended without finishing/);
  assert.equal(task.current, null);
});

test('the watch reads this batch\'s lines only, and starts over with a new batch', () => {
  const root = tempRoot();
  const where = batchPaths(root);
  fs.writeFileSync(where.log, 'old batch line\n');
  const offset = fs.statSync(where.log).size;
  fs.writeFileSync(where.status, JSON.stringify({ ...STATUS, log_offset: offset }));
  fs.appendFileSync(where.log, 'start: sharp\n[1/971] sharp cv a1\n[2/9');
  const seen = [];
  const watch = new BatchWatch({ dataRoot: root, interval: 0, alive: () => true, onChange: (c) => seen.push(c) });
  watch.poll();
  assert.equal(seen.length, 1);
  assert.equal(seen[0].reset, true);
  assert.deepEqual(seen[0].lines, ['start: sharp', '[1/971] sharp cv a1']);
  watch.poll();
  assert.equal(seen.length, 1);   // nothing changed
  fs.appendFileSync(where.log, '71] sharp letter a1\n');
  watch.poll();
  assert.deepEqual(seen[1].lines, ['[2/971] sharp letter a1']);
  assert.equal(seen[1].reset, false);
  const size = fs.statSync(where.log).size;
  fs.appendFileSync(where.log, 'start: partsharp\n');
  fs.writeFileSync(where.status, JSON.stringify({ ...STATUS, started_at: '2026-10-14T01:00:00+04:00', log_offset: size }));
  watch.poll();
  assert.equal(seen[2].reset, true);
  assert.deepEqual(seen[2].lines, ['start: partsharp']);
});

test('the batch starts detached, for a valid identity only', () => {
  const calls = [];
  const pid = startBatch({
    root: '/repo', python: '/repo/.venv/Scripts/python.exe', identity: 'sharp', env: {},
    spawn: (command, args, options) => { calls.push({ command, args, options }); return { pid: 7, unref() {} }; },
  });
  assert.equal(pid, 7);
  assert.deepEqual(calls[0].args, [path.join('tools', 'cv_batch.py'), 'sharp']);
  assert.equal(calls[0].options.detached, true);
  assert.equal(calls[0].options.cwd, '/repo');
  assert.throws(() => startBatch({ root: '/repo', python: 'p', identity: '../x', spawn: () => ({}) }), /invalid identity/);
});

test('stop and hold are files the batch reads', () => {
  const root = tempRoot();
  const where = batchPaths(root);
  stopBatch(root);
  assert.equal(fs.existsSync(where.stop), true);
  holdBatch(root, true, 1234);
  assert.equal(fs.readFileSync(where.hold, 'utf8'), '1234');
  holdBatch(root, false);
  assert.equal(fs.existsSync(where.hold), false);
});
