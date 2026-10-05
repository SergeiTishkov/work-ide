'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const { EventEmitter } = require('node:events');
const { PassThrough } = require('node:stream');
const { Runner, buildCommand, describeEvent, ALLOWED_TOOLS } = require('../../main/runner');
const { tempDir } = require('../helpers/fixture-db');

test('collect runs /run for the identity, headless, with the allowed tools', () => {
  const cmd = buildCommand('collect', 'sharp', { root: '/repo' });
  assert.equal(cmd.command, 'claude');
  assert.equal(cmd.cwd, '/repo');
  assert.deepEqual(cmd.args, ['-p', '/run sharp', '--output-format', 'stream-json', '--verbose',
    '--allowedTools', ALLOWED_TOOLS.join(',')]);
});

test('feedback runs /feedback for the identity', () => {
  assert.equal(buildCommand('feedback', 'pjoice', { root: '/repo' }).args[1], '/feedback pjoice');
});

test('the agent may not commit', () => {
  assert.ok(!ALLOWED_TOOLS.some((tool) => /git (commit|push)|Bash\(git:\*\)|^Bash$/.test(tool)));
});

test('unknown kinds and malformed identities are refused', () => {
  assert.throws(() => buildCommand('deploy', 'sharp', { root: '/r' }));
  assert.throws(() => buildCommand('collect', 'sharp; rm -rf /', { root: '/r' }));
  assert.throws(() => buildCommand('collect', 'SHARP', { root: '/r' }));
});

function fakeChild() {
  const child = new EventEmitter();
  child.pid = 1;
  child.stdout = new PassThrough();
  child.stderr = new PassThrough();
  return child;
}

test('one run at a time; output is described and logged; exit is reported', async () => {
  const logs = tempDir();
  const spawned = [];
  const child = fakeChild();
  const runner = new Runner({
    root: '/repo',
    logDirOf: (identity) => path.join(logs, identity, 'runs'),
    spawn: (command, args, options) => { spawned.push({ command, args, options }); return child; },
    kill: () => child.emit('close', null),
  });
  const events = [];
  runner.onEvent((e) => events.push(e));

  assert.deepEqual(runner.start('collect', 'sharp'), { ok: true });
  assert.equal(spawned[0].args[1], '/run sharp');
  assert.equal(spawned[0].options.cwd, '/repo');
  assert.deepEqual(runner.state(), { running: true, identity: 'sharp', kind: 'collect' });
  assert.equal(runner.start('feedback', 'sharp').error, 'busy');

  child.stdout.write(`${JSON.stringify({ type: 'assistant', message: { content: [
    { type: 'text', text: 'Running the pipeline' },
    { type: 'tool_use', name: 'Bash', input: { command: 'python tools/pipeline.py --identity sharp' } },
  ] } })}\n`);
  await new Promise((r) => setImmediate(r));
  child.emit('close', 0);

  assert.deepEqual(events.map((e) => e.type), ['start', 'output', 'exit']);
  assert.match(events[1].text, /Running the pipeline\n> Bash: python tools\/pipeline.py/);
  assert.equal(events[2].code, 0);
  assert.equal(runner.state().running, false);
  await new Promise((r) => setTimeout(r, 50));
  const [logFile] = fs.readdirSync(path.join(logs, 'sharp', 'runs'));
  assert.match(logFile, /_collect\.log$/);
});

test('stop kills the running agent', () => {
  const child = fakeChild();
  let killed = null;
  const runner = new Runner({
    root: '/repo', logDirOf: () => tempDir(),
    spawn: () => child, kill: (c) => { killed = c; c.emit('close', null); },
  });
  const events = [];
  runner.onEvent((e) => events.push(e));
  assert.deepEqual(runner.stop(), { ok: false });
  runner.start('collect', 'sharp');
  assert.deepEqual(runner.stop(), { ok: true });
  assert.equal(killed, child);
  assert.equal(events.at(-1).code, null);
});

test('a missing claude is reported as such', () => {
  const runner = new Runner({
    root: '/repo', logDirOf: () => tempDir(),
    spawn: () => { const e = new Error('spawn claude ENOENT'); e.code = 'ENOENT'; throw e; },
  });
  assert.deepEqual(runner.start('collect', 'sharp'), { ok: false, error: 'claude_not_found' });
  assert.equal(runner.state().running, false);
});

test('stream-json lines are described for the log panel', () => {
  assert.equal(describeEvent('{"type":"system","subtype":"init"}'), null);
  assert.equal(describeEvent('{"type":"result","subtype":"success","total_cost_usd":1.234,"result":"ok"}'),
    '= success ($1.23)\nok');
  assert.equal(describeEvent('not json'), 'not json');
});

test('the pipeline log of this run is followed line by line; older logs are not', async () => {
  const { PipelineLogFollower } = require('../../main/runner');
  const dir = tempDir();
  const old = path.join(dir, 'pipeline_2026-01-01_000000.log');
  fs.writeFileSync(old, 'an older run\n');
  fs.utimesSync(old, new Date('2026-01-01'), new Date('2026-01-01'));

  const lines = [];
  const follower = new PipelineLogFollower({
    dir, since: Date.now() - 1000, onLine: (l) => lines.push(l), interval: 10,
  });
  const current = path.join(dir, 'pipeline_2026-09-30_002341.log');
  fs.writeFileSync(current, '[00:23:41] >> load the knowledge base\n[00:23:42] ok load');
  await new Promise((r) => setTimeout(r, 60));
  assert.deepEqual(lines, ['[00:23:41] >> load the knowledge base']);   // the half line waits
  fs.appendFileSync(current, ' - 0 s\n');
  follower.stop();
  assert.deepEqual(lines, ['[00:23:41] >> load the knowledge base', '[00:23:42] ok load - 0 s']);
});
