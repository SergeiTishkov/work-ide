'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { PassThrough } = require('node:stream');
const { startRest, restArgs, restLine } = require('../../main/rest');
const { reputationArgs } = require('../../main/reputation');

test('the rest of the base runs the pipeline in its rest mode; a malformed identity is refused', () => {
  assert.deepEqual(restArgs('sharp').slice(1), ['--identity', 'sharp', '--rest']);
  assert.match(restArgs('sharp')[0], /pipeline\.py$/);
  assert.throws(() => restArgs('../x'), /invalid identity/);
});

test("the pipeline's progress lines are prefixed as the collection's log has them", () => {
  assert.equal(restLine('[04:14:11] >> check links'), '  | [04:14:11] >> check links');
  assert.equal(restLine('Pipeline finished:'), 'Pipeline finished:');
});

test('lines of both streams reach the task; the exit code ends it', async () => {
  const child = new EventEmitter();
  child.stdout = new PassThrough();
  child.stderr = new PassThrough();
  const calls = [];
  const lines = [];
  const handle = startRest({
    root: '/repo', python: 'py', identity: 'sharp', onLine: (l) => lines.push(l),
    spawn: (cmd, args, opts) => { calls.push([cmd, args, opts.cwd]); return child; },
    kill: () => calls.push('kill'),
  });
  child.stderr.write('[10:00:00] >> load the knowledge base\n[10:00:06] ok load');
  child.stdout.write('Pipeline finished:\n');
  child.stderr.end(' the knowledge base - 6 s\n');
  child.stdout.end();
  await new Promise((r) => setImmediate(r));
  child.emit('close', 0);
  assert.deepEqual(await handle.done, { ok: true, code: 0 });
  assert.deepEqual(lines.sort(), ['  | [10:00:00] >> load the knowledge base',
    '  | [10:00:06] ok load the knowledge base - 6 s', 'Pipeline finished:'].sort());
  assert.equal(calls[0][0], 'py');
  assert.equal(calls[0][2], '/repo');
  handle.stop();
  assert.equal(calls.at(-1), 'kill');
});

test("a vacancy's reputation runs the lookup for it; a malformed identity or id is refused", () => {
  assert.deepEqual(reputationArgs('sharp', 'li-123').slice(1), ['--identity', 'sharp', '--vacancy', 'li-123']);
  assert.match(reputationArgs('sharp', 'li-123')[0], /reputation_lookup\.py$/);
  assert.throws(() => reputationArgs('../x', 'a1'), /invalid identity/);
  assert.throws(() => reputationArgs('sharp', '../a1'), /invalid vacancy id/);
});
