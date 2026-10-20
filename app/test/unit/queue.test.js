'use strict';
// main/queue.js: the panel's tasks read from data/tasks.sqlite and the log
// files, written here the way tools/taskq.py and tools/taskd.py write them.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { DatabaseSync } = require('node:sqlite');
const { QueueClient, logLine, NO_WORKER } = require('../../main/queue');

const SCHEMA_DIR = path.join(__dirname, '..', '..', '..', 'schemas');

function fixture() {
  const dataRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'work-ide-queue-'));
  const calls = [];
  let answer = () => '{}';
  const client = new QueueClient({
    dataRoot, schemaDir: SCHEMA_DIR,
    runTaskq: async (args) => { calls.push(args); return answer(args); },
  });
  client.open();
  const db = new DatabaseSync(path.join(dataRoot, 'tasks.sqlite'));
  const now = new Date().toISOString();
  db.prepare("INSERT INTO workers (role, pid, capabilities, heartbeat_at) VALUES ('background', 1, 'ai', ?)").run(now);
  let next = 1;
  const add = (fields) => {
    const row = {
      kind: 'rest', identity: 'sharp', slot: 'collect', origin: 'app', state: 'queued', queued_at: now,
      log_path: path.join(dataRoot, 'tasks', `${next}.log`), ...fields,
    };
    const cols = Object.keys(row);
    db.prepare(`INSERT INTO tasks (${cols.join(', ')}) VALUES (${cols.map(() => '?').join(', ')})`).run(...Object.values(row));
    return next++;
  };
  const set = (id, fields) => {
    const cols = Object.keys(fields);
    db.prepare(`UPDATE tasks SET ${cols.map((c) => `${c} = ?`).join(', ')} WHERE id = ?`).run(...Object.values(fields), id);
  };
  const write = (id, text) => {
    const file = path.join(dataRoot, 'tasks', `${id}.log`);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.appendFileSync(file, text);
  };
  const events = [];
  client.onEvent((event) => events.push(event));
  return {
    dataRoot, client, db, add, set, write, events, calls, answer: (fn) => { answer = fn; },
    done: () => { client.close(); db.close(); fs.rmSync(dataRoot, { recursive: true, force: true }); },
  };
}

test('the panel lists every task of the queue, whoever added it, in the shape it knows', () => {
  const f = fixture();
  try {
    f.add({ kind: 'collect', origin: 'agent', state: 'running', worker: 'background', group_id: 1 });
    f.add({ kind: 'cv_batch', slot: 'documents', origin: 'terminal', waiting_for: '#1 to end', needs: 'desktop,ai' });
    f.add({ kind: 'cv', slot: 'documents', vacancy_id: 'a1', title: 'Dev', company: 'Acme', state: 'done',
      result: JSON.stringify({ ok: true, pdf: path.join(f.dataRoot, 'cv.pdf') }) });
    f.add({ kind: 'rest', state: 'done', hidden: 1 });
    f.client.poll();
    const list = f.client.list();
    assert.deepEqual(list.map((t) => [t.id, t.kind, t.lane, t.origin, t.state]), [
      [1, 'collect', 'collect', 'agent', 'running'], [2, 'batch', 'documents', 'terminal', 'queued'],
      [3, 'cv', 'documents', 'app', 'done']]);
    assert.equal(list[1].waitingFor, '#1 to end');
    assert.equal(list[2].vacancyId, 'a1');
    assert.equal(list[2].result.pdf, path.join(f.dataRoot, 'cv.pdf'));
    assert.equal(f.client.checkProduced(path.join(f.dataRoot, 'cv.pdf')), path.join(f.dataRoot, 'cv.pdf'));
    assert.throws(() => f.client.checkProduced(path.join(f.dataRoot, 'other.pdf')), /not a generated CV file/);
    assert.deepEqual(f.events.map((e) => e.type), ['tasks']);
  } finally {
    f.done();
  }
});

test('with no worker alive a queued task says so', () => {
  const f = fixture();
  try {
    f.db.prepare('DELETE FROM workers').run();
    f.add({ waiting_for: '#9 to end' });
    f.client.poll();
    assert.equal(f.client.list()[0].waitingFor, NO_WORKER);
    assert.deepEqual(f.client.liveWorkers(), []);
  } finally {
    f.done();
  }
});

test("a task's new log lines go out as events, and its steps follow them", () => {
  const f = fixture();
  try {
    const id = f.add({ kind: 'collect', state: 'running' });
    f.write(id, '> Bash: python tools/pipeline.py --identity sharp --top\n');
    f.client.poll();
    assert.deepEqual(f.client.log(id), ['> Bash: python tools/pipeline.py --identity sharp --top']);
    f.write(id, '  | [04:14:11] >> fetch 19 sources\n  | [04:20:00]    linkedin pairs: 1/168');
    f.client.poll();
    // a line without its end waits for the rest
    assert.deepEqual(f.events.filter((e) => e.type === 'log').map((e) => e.text), ['  | [04:14:11] >> fetch 19 sources']);
    f.write(id, '\n  | [04:40:00] ok fetch 19 sources - 26:00 (900 new)\n  | [05:00:00] pipeline finished in 45:49\n');
    f.client.poll();
    let steps = f.client.list()[0].steps;
    assert.deepEqual(steps.map((s) => [s.key, s.state]), [['prepare', 'done'], ['fetch', 'done'], ['summary', 'running']]);
    assert.equal(steps[1].note, '900 new');
    f.set(id, { state: 'done', ended_at: new Date().toISOString() });
    f.client.poll();
    steps = f.client.list()[0].steps;
    assert.equal(steps[2].state, 'done');
    const finished = f.events.filter((e) => e.type === 'finished');
    assert.deepEqual(finished.map((e) => [e.task.id, e.task.state]), [[id, 'done']]);
  } finally {
    f.done();
  }
});

test('a pipeline run started by hand: its own log, read with the prefix the steps need', () => {
  const f = fixture();
  try {
    const own = path.join(f.dataRoot, 'pipeline_2026.log');
    fs.writeFileSync(own, '[04:14:11] >> check links\n[04:15:00] ok check links - 49 s\n');
    const id = f.add({ kind: 'pipeline', origin: 'terminal', worker: 'external', state: 'running', log_path: own });
    f.client.poll();
    assert.deepEqual(f.client.log(id), ['  | [04:14:11] >> check links', '  | [04:15:00] ok check links - 49 s']);
    assert.deepEqual(f.client.list()[0].steps.map((s) => [s.key, s.state]), [['links', 'done']]);
    assert.equal(logLine('Pipeline finished:'), 'Pipeline finished:');
  } finally {
    f.done();
  }
});

test('a running CV/CL batch shows its progress and the document it makes', () => {
  const f = fixture();
  try {
    f.client.readBatch = () => ({
      state: 'running', holding: true, index: 3, total: 10, made: 2, failed: 0, gone: 1,
      current: { identity: 'sharp', vacancy_id: 'v1', kind: 'cv', title: 'Dev', company: 'Acme' },
    });
    f.add({ kind: 'cv_batch', slot: 'documents', state: 'running' });
    f.add({ kind: 'cv_batch', slot: 'documents', state: 'queued' });
    f.client.poll();
    const [running, queued] = f.client.list();
    assert.deepEqual(running.progress, { index: 3, total: 10, made: 2, failed: 0, gone: 1 });
    assert.equal(running.holding, true);
    assert.deepEqual(running.current, { identity: 'sharp', vacancyId: 'v1', kind: 'cv', title: 'Dev', company: 'Acme' });
    assert.equal(queued.progress, null);
  } finally {
    f.done();
  }
});

test('adding, stopping and clearing go through tools/taskq.py, as the app', async () => {
  const f = fixture();
  try {
    f.answer((args) => {
      if (args[0] === 'collect') {
        f.add({ kind: 'collect' });
        return JSON.stringify([{ added: true, task: { id: 1, kind: 'collect', identity: 'sharp', slot: 'collect',
          origin: 'app', state: 'queued', queued_at: 'x', needs: ['ai'], args: {} } }]);
      }
      if (args[0] === 'add') {
        return JSON.stringify({ added: false, task: { id: 2, kind: 'cv', identity: 'sharp', vacancy_id: 'a1',
          slot: 'documents', origin: 'app', state: 'running', queued_at: 'x', needs: [], args: {} } });
      }
      return JSON.stringify({ ok: true, hidden: 0 });
    });
    const collected = await f.client.enqueue({ kind: 'collect', identity: 'sharp' });
    assert.equal(collected.ok, true);
    assert.equal(collected.task.kind, 'collect');
    // the list holds the new row by the time the reply comes back
    assert.deepEqual(f.client.list().map((t) => [t.kind, t.state]), [['collect', 'queued']]);
    const again = await f.client.enqueue({ kind: 'cv', identity: 'sharp', vacancyId: 'a1', title: 'Dev',
      instructions: '  shorter  ' });
    assert.deepEqual([again.ok, again.error, again.task.id], [false, 'already_queued', 2]);
    await f.client.cancel(2);
    await f.client.clearFinished();
    assert.deepEqual(f.calls, [
      ['collect', 'sharp', '--origin', 'app', '--json'],
      ['add', 'cv', '--identity', 'sharp', '--origin', 'app', '--json', '--vacancy', 'a1', '--title', 'Dev',
        '--company', '', '--instructions', 'shorter'],
      ['stop', '2', '--json'],
      ['hide', '--json']]);
  } finally {
    f.done();
  }
});

test('what does not fit is refused before it reaches Python', async () => {
  const f = fixture();
  try {
    await assert.rejects(f.client.enqueue({ kind: 'dance', identity: 'sharp' }), /unknown task kind/);
    await assert.rejects(f.client.enqueue({ kind: 'rest', identity: '../x' }), /invalid identity/);
    await assert.rejects(f.client.enqueue({ kind: 'cv', identity: 'sharp', vacancyId: 'a b' }), /invalid vacancy id/);
    await assert.rejects(f.client.enqueue({ kind: 'cv', identity: 'sharp', vacancyId: 'a1', instructions: 'x'.repeat(9000) }),
      /longer than/);
    assert.deepEqual(f.calls, []);
  } finally {
    f.done();
  }
});

test('cancel queued stops each queued task of the identity, and only those', async () => {
  const f = fixture();
  try {
    f.answer(() => JSON.stringify({ ok: true }));
    f.add({ identity: 'sharp' });
    f.add({ identity: 'partsharp' });
    f.add({ identity: 'sharp', state: 'running' });
    f.client.poll();
    const reply = await f.client.cancelQueued('sharp');
    assert.deepEqual(reply, { ok: true, cancelled: 1 });
    assert.deepEqual(f.calls, [['stop', '1', '--json']]);
  } finally {
    f.done();
  }
});
