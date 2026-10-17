'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { buildCleanupArgs, runCleanup } = require('../../main/cleanup');

test('the cleanup command carries the chosen filters, and a dry run says so', () => {
  const args = buildCleanupArgs('sharp', { ages: ['older'], statuses: [], classes: ['rejected', 'low_priority'] }, true);
  assert.deepEqual(args.slice(1), ['--identity', 'sharp', '--json', '--ages', 'older',
    '--classes', 'rejected', 'low_priority', '--dry-run']);
  assert.ok(!buildCleanupArgs('sharp', { statuses: ['expired'] }, false).includes('--dry-run'));
});

test('no filter, an unknown value or a malformed identity is refused', () => {
  assert.throws(() => buildCleanupArgs('sharp', {}, true), /at least one filter/);
  assert.throws(() => buildCleanupArgs('sharp', { ages: [], statuses: [] }, true), /at least one filter/);
  assert.throws(() => buildCleanupArgs('sharp', { ages: ['ancient'] }, true), /unknown ages/);
  assert.throws(() => buildCleanupArgs('sharp', { statuses: 'new' }, true), /unknown statuses/);
  assert.throws(() => buildCleanupArgs('../x', { ages: ['older'] }, true), /invalid identity/);
});

test('the answer is the last JSON line; an error in it is an error', async () => {
  const fake = (stdout, stderr = '') => (_cmd, _args, _opts, done) => done(null, stdout, stderr);
  const ok = await runCleanup({ root: '.', python: 'py', identity: 'sharp', filters: { ages: ['older'] },
    dryRun: true, run: fake('[identity: sharp]\n{"matched": 5, "deleted": 0, "dry_run": true}\n') });
  assert.equal(ok.matched, 5);
  await assert.rejects(runCleanup({ root: '.', python: 'py', identity: 'sharp', filters: { ages: ['older'] },
    run: fake('{"error": "a collection of \'sharp\' is running"}') }), /is running/);
  await assert.rejects(runCleanup({ root: '.', python: 'py', identity: 'sharp', filters: { ages: ['older'] },
    run: fake('', 'Traceback') }), /cleanup.py failed: Traceback/);
});
