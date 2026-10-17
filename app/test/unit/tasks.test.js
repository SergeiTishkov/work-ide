'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { TaskQueue } = require('../../main/tasks');

// A piece of work the test finishes by hand.
function work() {
  const started = [];
  const start = (task, onLine) => {
    let finish;
    const done = new Promise((resolve) => { finish = resolve; });
    const entry = { task, onLine, finish, stopped: false };
    started.push(entry);
    return { done, stop: () => { entry.stopped = true; finish({ ok: false, error: 'stopped' }); } };
  };
  return { started, start };
}

const tick = () => new Promise((resolve) => setImmediate(resolve));

test('collections queue one after another; documents run beside them, one at a time', async () => {
  const collect = work();
  const docs = work();
  const queue = new TaskQueue({ startCollect: collect.start, startDocument: docs.start });
  queue.enqueue({ kind: 'collect', identity: 'sharp' });
  queue.enqueue({ kind: 'collect', identity: 'partsharp' });
  queue.enqueue({ kind: 'cv', identity: 'sharp', vacancyId: 'a1' });
  queue.enqueue({ kind: 'letter', identity: 'sharp', vacancyId: 'a1' });
  await tick();
  assert.deepEqual(collect.started.map((s) => s.task.identity), ['sharp']);
  assert.deepEqual(docs.started.map((s) => s.task.kind), ['cv']);
  assert.deepEqual(queue.list().map((t) => t.state), ['running', 'queued', 'running', 'queued']);
  collect.started[0].finish({ ok: true, code: 0 });
  docs.started[0].finish({ ok: true, pdf: '/x.pdf' });
  await tick();
  assert.deepEqual(collect.started.map((s) => s.task.identity), ['sharp', 'partsharp']);
  assert.deepEqual(docs.started.map((s) => s.task.kind), ['cv', 'letter']);
  assert.deepEqual(queue.list().map((t) => t.state), ['done', 'running', 'done', 'running']);
  assert.equal(queue.list()[2].result.pdf, '/x.pdf');
});

test("a vacancy's reputation runs in a lane of its own, beside a collection and the documents", async () => {
  const collect = work();
  const docs = work();
  const reputation = work();
  const queue = new TaskQueue({
    startCollect: collect.start, startDocument: docs.start, startReputation: reputation.start,
  });
  queue.enqueue({ kind: 'collect', identity: 'sharp' });
  queue.enqueue({ kind: 'cv', identity: 'sharp', vacancyId: 'a1' });
  queue.enqueue({ kind: 'reputation', identity: 'sharp', vacancyId: 'a1', company: 'Acme' });
  queue.enqueue({ kind: 'reputation', identity: 'sharp', vacancyId: 'b2', company: 'Beta' });
  assert.equal(queue.enqueue({ kind: 'reputation', identity: 'sharp', vacancyId: 'a1' }).error, 'already_queued');
  await tick();
  assert.deepEqual(reputation.started.map((s) => s.task.vacancyId), ['a1']);
  assert.deepEqual(queue.list().map((t) => t.state), ['running', 'running', 'running', 'queued']);
  reputation.started[0].finish({ ok: true, code: 0 });
  await tick();
  assert.deepEqual(reputation.started.map((s) => s.task.vacancyId), ['a1', 'b2']);
  assert.equal(queue.list()[2].lane, 'reputation');
  assert.equal(queue.list()[2].steps, undefined, 'no steps: one tool, one line or two');
});

test('a task already queued or going is not queued twice', async () => {
  const docs = work();
  const queue = new TaskQueue({ startCollect: work().start, startDocument: docs.start });
  assert.equal(queue.enqueue({ kind: 'cv', identity: 'sharp', vacancyId: 'a1' }).ok, true);
  assert.equal(queue.enqueue({ kind: 'cv', identity: 'sharp', vacancyId: 'a1' }).error, 'already_queued');
  assert.equal(queue.enqueue({ kind: 'letter', identity: 'sharp', vacancyId: 'a1' }).ok, true);
  assert.equal(queue.enqueue({ kind: 'cv', identity: 'partsharp', vacancyId: 'a1' }).ok, true);
  docs.started[0].finish({ ok: true });
  await tick();
  // done: a new version may be asked for
  assert.equal(queue.enqueue({ kind: 'cv', identity: 'sharp', vacancyId: 'a1' }).ok, true);
  assert.throws(() => queue.enqueue({ kind: 'poem', identity: 'sharp' }), /unknown task kind/);
});

test('each task keeps its own log, and the lines go out as events', async () => {
  const docs = work();
  const queue = new TaskQueue({ startCollect: work().start, startDocument: docs.start });
  const events = [];
  queue.onEvent((e) => events.push(e));
  const { task } = queue.enqueue({ kind: 'cv', identity: 'sharp', vacancyId: 'a1' });
  docs.started[0].onLine('CV V1: Dev\nasking the model');
  assert.deepEqual(queue.log(task.id), ['CV V1: Dev', 'asking the model']);
  assert.deepEqual(events.filter((e) => e.type === 'log').map((e) => e.text), ['CV V1: Dev', 'asking the model']);
  docs.started[0].finish({ ok: false, error: 'Vacancy not found, possibly outdated: the link is dead.' });
  await tick();
  const finished = events.find((e) => e.type === 'finished');
  assert.equal(finished.task.state, 'failed');
  assert.match(finished.task.error, /Vacancy not found/);
  assert.equal(queue.list()[0].logLines, 2);
});

test('cancel: a queued task never starts, a running one is stopped', async () => {
  const docs = work();
  const queue = new TaskQueue({ startCollect: work().start, startDocument: docs.start });
  const first = queue.enqueue({ kind: 'cv', identity: 'sharp', vacancyId: 'a1' }).task;
  const second = queue.enqueue({ kind: 'cv', identity: 'sharp', vacancyId: 'a2' }).task;
  queue.enqueue({ kind: 'cv', identity: 'sharp', vacancyId: 'a3' });
  assert.equal(queue.cancel(second.id).ok, true);
  assert.equal(queue.cancel(first.id).ok, true);
  await tick();
  assert.equal(docs.started[0].stopped, true);
  assert.deepEqual(queue.list().map((t) => t.state), ['stopped', 'stopped', 'running']);
  assert.deepEqual(docs.started.map((s) => s.task.vacancyId), ['a1', 'a3']);
  queue.clearFinished();
  assert.deepEqual(queue.list().map((t) => t.vacancyId), ['a3']);
  queue.enqueue({ kind: 'cv', identity: 'sharp', vacancyId: 'a4' });
  queue.enqueue({ kind: 'cv', identity: 'partsharp', vacancyId: 'a5' });
  assert.equal(queue.cancelQueued('sharp').cancelled, 1);
  assert.deepEqual(queue.list().map((t) => t.state), ['running', 'stopped', 'queued']);
});

test('a collection waits while a run started elsewhere holds the base', async () => {
  const collect = work();
  let holder = 'partsharp';
  const queue = new TaskQueue({
    startCollect: collect.start, startDocument: work().start,
    externalBusy: async () => holder, retryMs: 10,
  });
  queue.enqueue({ kind: 'collect', identity: 'sharp' });
  await tick();
  assert.equal(collect.started.length, 0);
  assert.equal(queue.list()[0].waitingFor, 'partsharp');
  holder = null;
  await new Promise((resolve) => setTimeout(resolve, 40));
  assert.equal(collect.started.length, 1);
  assert.equal(queue.list()[0].waitingFor, null);
});

test('a collection that ends well starts the CV/CL batch, and says so in its log', async () => {
  const collect = work();
  const asked = [];
  const queue = new TaskQueue({
    startCollect: collect.start, startDocument: work().start,
    startAuto: async (identity) => { asked.push(identity); return 'CV/CL batch started (pid 7)'; },
  });
  const { task } = queue.enqueue({ kind: 'collect', identity: 'sharp' });
  collect.started[0].finish({ ok: true, code: 0 });
  await tick();
  await tick();
  assert.deepEqual(asked, ['sharp']);
  assert.equal(queue.list()[0].state, 'done');
  assert.equal(queue.log(task.id).pop(), 'CV/CL batch started (pid 7)');
});

test('a failed or stopped collection starts no batch', async () => {
  const collect = work();
  let asked = 0;
  const queue = new TaskQueue({
    startCollect: collect.start, startDocument: work().start, startAuto: async () => { asked += 1; return ''; },
  });
  queue.enqueue({ kind: 'collect', identity: 'sharp' });
  collect.started[0].finish({ ok: false, code: 1 });
  await tick();
  const stopped = queue.enqueue({ kind: 'collect', identity: 'sharp' }).task;
  await tick();
  queue.cancel(stopped.id);
  await tick();
  assert.equal(asked, 0);
  assert.deepEqual(queue.list().map((t) => [t.state, t.error]), [['failed', 'exit 1'], ['stopped', 'stopped']]);
  assert.equal(queue.active(), false);
});

test('the fast cycle ends with the summary by the agent instead of the checklist', async () => {
  const collect = work();
  const queue = new TaskQueue({ startCollect: collect.start, startDocument: work().start });
  queue.enqueue({ kind: 'collect', identity: 'sharp' });
  const say = (text) => collect.started[0].onLine(text);
  say('> Bash: python tools/pipeline.py --identity sharp --top --skip-contracts');
  say('  | [04:14:11] >> fetch 19 sources (LinkedIn: posted in the last 1 day)');
  say('  | [04:40:11] ok fetch 19 sources (LinkedIn: posted in the last 1 day) - 26:00 (3 000 records, 900 new)');
  say('  | [04:40:12] >> remote check by the descriptions');
  say('  | [04:52:12] ok remote check by the descriptions - 12:00 (considered 300, fetched 290)');
  say('  | [04:52:13] >> rescore the top, with the descriptions (3 400 vacancies)');
  say('  | [04:52:43] ok rescore the top, with the descriptions (3 400 vacancies) - 30 s');
  say('  | [04:52:44] >> AI brief');
  say('  | [04:52:44] ok AI brief - 0 s (current)');
  say('  | [05:00:00] pipeline finished in 45:49');
  assert.deepEqual(queue.list()[0].steps.map((s) => [s.key, s.state]), [
    ['prepare', 'done'], ['fetch', 'done'], ['remote_check', 'done'], ['rescore_top', 'done'],
    ['ai_brief', 'done'], ['summary', 'running']]);
});

test('a collection shows its steps as its log comes', async () => {
  const collect = work();
  let ms = 0;
  const queue = new TaskQueue({ startCollect: collect.start, startDocument: work().start, clock: () => ms });
  queue.enqueue({ kind: 'collect', identity: 'sharp' });
  const say = (text) => collect.started[0].onLine(text);
  say('> Bash: python tools/identity.py which');
  ms = 65000;
  say('> Bash: python tools/pipeline.py --identity sharp --skip-contracts');
  say('  | [04:14:11] >> fetch 19 sources: weworkremotely, remoteok');
  say('  | [04:19:48]    linkedin pairs: 1/168 (0%), ~12:44:56 left - 100 pages');
  let steps = queue.list()[0].steps;
  assert.deepEqual(steps.map((s) => [s.key, s.state]), [['prepare', 'done'], ['fetch', 'running']]);
  assert.equal(steps[0].duration, '1:05');
  assert.match(steps[1].progress, /^linkedin pairs: 1\/168/);
  assert.equal(steps[1].began, 65000);
  say('  | [06:53:16] ok fetch - 2:39:05 (17 906 records, 12 381 new)');
  say('  | [06:53:17] >> rescore the base, current criteria (58 984 vacancies)');
  say('  | [06:58:51] !! rescore the base, current criteria (58 984 vacancies) - failed after 5:34: MemoryError');
  say('  | [08:38:08] pipeline finished in 4:24:03');
  say('> Bash: python tools/kb.py --identity sharp dump --min-class long_shot');
  steps = queue.list()[0].steps;
  assert.deepEqual(steps.map((s) => [s.key, s.state, s.duration]), [
    ['prepare', 'done', '1:05'], ['fetch', 'done', '2:39:05'], ['rescore', 'failed', '5:34'],
    ['checklist', 'running', null]]);
  assert.equal(steps[1].note, '17 906 records, 12 381 new');
  assert.equal(steps[2].note, 'MemoryError');
  collect.started[0].finish({ ok: true, code: 0 });
  await tick();
  assert.equal(queue.list()[0].steps[3].state, 'done');
});

test('a fast collection that ends well queues the rest of the base after the collections queued before it', async () => {
  const collect = work();
  const rest = work();
  const queue = new TaskQueue({ startCollect: collect.start, startRest: rest.start, startDocument: work().start });
  queue.enqueue({ kind: 'collect', identity: 'sharp' });
  queue.enqueue({ kind: 'collect', identity: 'partsharp' });
  await tick();
  collect.started[0].finish({ ok: true, code: 0 });
  await tick();
  assert.deepEqual(queue.list().map((t) => [t.kind, t.identity, t.state]), [
    ['collect', 'sharp', 'done'], ['collect', 'partsharp', 'running'], ['rest', 'sharp', 'queued']]);
  assert.match(queue.log(1).at(-1), /the rest of the base is queued: task #3/);
  assert.equal(queue.list()[2].origin, 'auto');
  collect.started[1].finish({ ok: false, code: 1 });
  await tick();
  assert.deepEqual(rest.started.map((s) => s.task.identity), ['sharp']);
  // a failed collection queues no rest
  assert.equal(queue.list().filter((t) => t.kind === 'rest').length, 1);
});

test('the rest of the base shows the pipeline stages, with no agent steps', async () => {
  const rest = work();
  const queue = new TaskQueue({ startCollect: work().start, startRest: rest.start, startDocument: work().start });
  queue.enqueue({ kind: 'rest', identity: 'sharp' });
  await tick();
  const say = (text) => rest.started[0].onLine(text);
  say("  | [10:00:00] >> fetch LinkedIn's missed days (posted in the last 6 days)");
  say("  | [11:40:00] ok fetch LinkedIn's missed days (posted in the last 6 days) - 1:40:00 (8 000 records, 5 000 new)");
  say('  | [11:40:01] >> AI check of the top');
  say('  | [11:50:01] ok AI check of the top - 10:00 (screened 120, rejected 30)');
  say('  | [11:51:00] pipeline finished in 1:51:00');
  const steps = queue.list()[0].steps;
  assert.deepEqual(steps.map((s) => [s.key, s.state, s.duration]), [
    ['backfill', 'done', '1:40:00'], ['ai_check', 'done', '10:00']]);
});

const BATCH = {
  id: 'batch', kind: 'batch', lane: 'documents', identity: 'sharp', origin: 'external',
  state: 'running', holding: false, queuedAt: '2026-10-13T03:30:54+04:00', startedAt: '2026-10-13T03:30:54+04:00',
  progress: { index: 3, total: 10, made: 2, failed: 0, gone: 0 }, current: null, error: null,
};

test('the batch is listed with its log; the ✕ asks it to stop; Clear finished hides it once done', () => {
  const stops = [];
  const queue = new TaskQueue({ startCollect: work().start, startDocument: work().start,
    stopExternal: () => stops.push(1), now: () => '2026-10-12T20:00:00.000Z' });
  queue.enqueue({ kind: 'collect', identity: 'sharp' });   // came before the batch
  const events = [];
  queue.onEvent((e) => events.push(e));
  queue.setExternal({ task: BATCH, lines: ['start: sharp', '[1/10] sharp cv a1'], reset: true });
  assert.deepEqual(queue.list().map((t) => t.id), [1, 'batch']);
  assert.deepEqual(queue.log('batch'), ['start: sharp', '[1/10] sharp cv a1']);
  assert.deepEqual(events.filter((e) => e.type === 'log').map((e) => e.id), ['batch', 'batch']);
  assert.equal(queue.cancel('batch').ok, true);
  assert.equal(stops.length, 1);
  assert.equal(queue.list()[1].stopping, true);
  queue.setExternal({ task: { ...BATCH, state: 'stopped' }, lines: ['stopped before 4/10'] });
  assert.equal(events.filter((e) => e.type === 'finished').length, 1);
  queue.clearFinished();
  assert.deepEqual(queue.list().map((t) => t.id), [1]);
  queue.setExternal({ task: { ...BATCH, state: 'stopped' } });   // the next poll: still hidden
  assert.deepEqual(queue.list().map((t) => t.id), [1]);
  assert.equal(queue.active(), true);   // the batch does not hold a refresh back
});

test("the app's documents make the batch pause, and wait only for its current document", async () => {
  const docs = work();
  const holds = [];
  const queue = new TaskQueue({ startCollect: work().start, startDocument: docs.start,
    holdExternal: (on) => holds.push(on) });
  queue.setExternal({ task: BATCH, reset: true });
  queue.enqueue({ kind: 'cv', identity: 'sharp', vacancyId: 'a1' });
  await tick();
  assert.deepEqual(holds, [true]);
  assert.equal(docs.started.length, 0);
  assert.equal(queue.list().find((t) => t.kind === 'cv').waitingFor, 'batch');
  queue.setExternal({ task: { ...BATCH, holding: true } });   // between two documents
  await tick();
  assert.equal(docs.started.length, 1);
  docs.started[0].finish({ ok: true });
  await tick();
  assert.deepEqual(holds, [true, false]);
});
