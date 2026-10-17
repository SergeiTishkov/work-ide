'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { EventEmitter } = require('node:events');
const { PassThrough } = require('node:stream');
const { CvGenerator, buildCvCommand, parseResult, INSTRUCTIONS_LIMIT } = require('../../main/cv');

const OPTIONS = { root: '/repo', python: '/repo/.venv/Scripts/python.exe', documentsDir: '/home/me/Work IDE CVs and CLs' };

test('the command runs tools/cv_tailor.py for one identity and vacancy, with a JSON result', () => {
  const cmd = buildCvCommand('sharp', '35bf096fae2ac0e4b101', OPTIONS);
  assert.equal(cmd.command, OPTIONS.python);
  assert.equal(cmd.cwd, '/repo');
  assert.deepEqual(cmd.args, [path.join('tools', 'cv_tailor.py'), '--identity', 'sharp',
    '--vacancy', '35bf096fae2ac0e4b101', '--documents-dir', '/home/me/Work IDE CVs and CLs', '--json']);
});

test('instructions go last, trimmed; empty ones add nothing', () => {
  const cmd = buildCvCommand('sharp', 'a1', OPTIONS, '  Stress Azure.' + String.fromCharCode(10) + 'Write it in German. ');
  assert.deepEqual(cmd.args.slice(-2), ['--instructions', 'Stress Azure.' + String.fromCharCode(10) + 'Write it in German.']);
  for (const empty of [undefined, null, '', '   ']) {
    assert.equal(buildCvCommand('sharp', 'a1', OPTIONS, empty).args.includes('--instructions'), false);
  }
});

test('instructions that are not text, or too long for a command line, are refused', () => {
  assert.throws(() => buildCvCommand('sharp', 'a1', OPTIONS, { text: 'x' }), /must be text/);
  assert.throws(() => buildCvCommand('sharp', 'a1', OPTIONS, 'x'.repeat(INSTRUCTIONS_LIMIT + 1)), /more than/);
  assert.ok(buildCvCommand('sharp', 'a1', OPTIONS, 'x'.repeat(INSTRUCTIONS_LIMIT)));
});

test('malformed identities and vacancy ids are refused', () => {
  assert.throws(() => buildCvCommand('SHARP', 'a1', OPTIONS));
  assert.throws(() => buildCvCommand('sharp; rm', 'a1', OPTIONS));
  assert.throws(() => buildCvCommand('sharp', '../a1', OPTIONS));
  assert.throws(() => buildCvCommand('sharp', '', OPTIONS));
});

test('the result is the last JSON line; without one, the end of stderr', () => {
  assert.deepEqual(parseResult('loading\n{"ok": true, "pages": 3}\n', '', 0), { ok: true, pages: 3 });
  assert.deepEqual(parseResult('', 'Traceback\nValueError: bad\n', 1), { ok: false, error: 'Traceback\nValueError: bad' });
  assert.deepEqual(parseResult('', '', 2), { ok: false, error: 'cv_tailor.py exited with 2' });
});

test('a cover letter runs tools/cover_letter.py; an unknown kind is refused', () => {
  const cmd = buildCvCommand('sharp', 'a1', OPTIONS, 'Mention Azure.', 'letter');
  assert.equal(cmd.args[0], path.join('tools', 'cover_letter.py'));
  assert.deepEqual(cmd.args.slice(-2), ['--instructions', 'Mention Azure.']);
  assert.throws(() => buildCvCommand('sharp', 'a1', OPTIONS, '', 'poem'), /invalid kind/);
  assert.throws(() => buildCvCommand('sharp', 'a1', OPTIONS, '', 'toString'), /invalid kind/);
  assert.deepEqual(parseResult('', '', 3, 'cover_letter.py'), { ok: false, error: 'cover_letter.py exited with 3' });
});

function fakeChild() {
  const child = new EventEmitter();
  child.stdout = new PassThrough();
  child.stderr = new PassThrough();
  child.kill = () => child.emit('close', null);
  return child;
}

test('one generation at a time; only the files it produced may be opened', async () => {
  const spawned = [];
  const child = fakeChild();
  const cv = new CvGenerator({ ...OPTIONS, spawn: (command, args, options) => {
    spawned.push({ command, args, options }); return child;
  } });
  const running = cv.generate('sharp', 'a1');
  assert.deepEqual(cv.state(), { running: true, identity: 'sharp', vacancyId: 'a1', kind: 'cv' });
  assert.equal((await cv.generate('sharp', 'a2')).error, 'busy');
  assert.equal((await cv.generate('sharp', 'a1', '', 'letter')).error, 'busy');   // either kind waits
  assert.equal(spawned.length, 1);
  assert.equal(spawned[0].options.cwd, '/repo');
  assert.equal(spawned[0].options.env.PYTHONIOENCODING, 'utf-8');
  assert.throws(() => cv.checkProduced('/home/me/Downloads/CV.pdf'), /not a generated CV file/);

  child.stdout.write(`${JSON.stringify({ ok: true, docx: '/home/me/Downloads/CV.docx', pdf: '/home/me/Downloads/CV.pdf' })}\n`);
  child.emit('close', 0);
  const result = await running;
  assert.equal(result.ok, true);
  assert.deepEqual(cv.state(), { running: false });
  assert.equal(cv.checkProduced('/home/me/Downloads/CV.pdf'), path.resolve('/home/me/Downloads/CV.pdf'));
  assert.throws(() => cv.checkProduced('/home/me/Downloads/other.pdf'));
});

test('a failed generation reports its error and frees the generator', async () => {
  const child = fakeChild();
  const cv = new CvGenerator({ ...OPTIONS, spawn: () => child });
  const running = cv.generate('sharp', 'a1');
  child.stdout.write('{"ok": false, "error": "vacancy a1 is not in the database"}\n');
  child.emit('close', 1);
  assert.deepEqual(await running, { ok: false, error: 'vacancy a1 is not in the database' });
  assert.deepEqual(cv.state(), { running: false });
});

test('the progress lines go out as they come; a stopped generation says it was stopped', async () => {
  const child = fakeChild();
  const killed = [];
  const lines = [];
  const cv = new CvGenerator({
    ...OPTIONS,
    documentsDir: async () => '/docs',
    spawn: (command, args) => {
      lines.push(`args ${args.join(' ')}`);
      return child;
    },
    kill: (c) => { killed.push(c); c.emit('close', null); },
  });
  const handle = cv.start('sharp', 'a1', '', 'cv', (line) => lines.push(line));
  await new Promise((resolve) => setImmediate(resolve));
  assert.match(lines[0], /--documents-dir \/docs/);
  child.stderr.write('CV V1: Dev — Acme\nasking the mo');
  child.stderr.write('del\n');
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(lines.slice(1), ['CV V1: Dev — Acme', 'asking the model']);
  handle.stop();
  assert.deepEqual(await handle.done, { ok: false, error: 'stopped' });
  assert.equal(killed.length, 1);
  assert.deepEqual(cv.state(), { running: false });
});

test('a generation with no answer in time is stopped', async () => {
  const child = fakeChild();
  const cv = new CvGenerator({ ...OPTIONS, spawn: () => child, timeoutMs: 20 });
  const result = await cv.generate('sharp', 'a1');
  assert.equal(result.ok, false);
  assert.match(result.error, /no result/);
  assert.deepEqual(cv.state(), { running: false });
});
