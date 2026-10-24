'use strict';
// main/workers.js: the app starts a queue worker that is not beating.
const test = require('node:test');
const assert = require('node:assert/strict');
const { WorkerKeeper, TASK_NAMES } = require('../../main/workers');

function keeper({ registered = {}, live = [], pending = true, env = {} } = {}) {
  const ran = [];
  const spawned = [];
  let ms = 0;
  const k = new WorkerKeeper({
    root: 'C:/repo', python: 'C:/repo/.venv/Scripts/python.exe', dataRoot: 'C:/repo/data',
    live: () => live, pending: () => pending, env,
    run: async (args) => {
      ran.push(args);
      if (args[0] === '/Query') return { ok: Object.values(TASK_NAMES).includes(args[2]) && registered[args[2]] };
      return { ok: true };
    },
    spawn: (command, args, options) => { spawned.push({ command, args, options }); return { unref() {} }; },
    clock: () => ms,
  });
  return { k, ran, spawned, advance: (by) => { ms += by; } };
}

test('a registered worker that does not beat is started through Task Scheduler, not twice in a row', async () => {
  const { k, ran, advance } = keeper({ registered: { [TASK_NAMES.background]: true, [TASK_NAMES.desktop]: true } });
  assert.deepEqual(await k.check(), ['background: started through Task Scheduler', 'desktop: started through Task Scheduler']);
  assert.deepEqual(ran.filter((a) => a[0] === '/Run'), [['/Run', '/TN', TASK_NAMES.background], ['/Run', '/TN', TASK_NAMES.desktop]]);
  assert.deepEqual(await k.check(), []);
  advance(130000);
  assert.equal((await k.check()).length, 2);
});

test('a live worker is left alone', async () => {
  const { k, ran } = keeper({ registered: { [TASK_NAMES.desktop]: true }, live: [{ role: 'desktop' }] });
  assert.deepEqual(await k.check(), []);
  assert.equal(ran.filter((a) => a[0] === '/Run').length, 0);
});

test('with nothing registered the app starts a desktop worker itself, through taskd.py start, when a task waits', async () => {
  const { k, spawned } = keeper();
  assert.deepEqual(await k.check(), ['desktop: started by the app (not registered with Task Scheduler)']);
  const [{ command, args, options }] = spawned;
  assert.equal(command, 'C:/repo/.venv/Scripts/python.exe');
  assert.deepEqual(args.slice(1), ['start', '--role', 'desktop', '--idle-exit', '600']);
  assert.equal(options.env.WORK_IDE_DATA_ROOT, 'C:/repo/data');
});

test('nothing waiting, or a background worker alive: the app starts nothing', async () => {
  assert.deepEqual(await keeper({ pending: false }).k.check(), []);
  assert.deepEqual(await keeper({ live: [{ role: 'background' }] }).k.check(), []);
});

test("the scheduler's page asks Task Scheduler afresh: the setup script may have just run", async () => {
  const registered = {};
  const { k } = keeper({ registered });
  assert.deepEqual(await k.registration(), { background: false, desktop: false });
  registered[TASK_NAMES.background] = true;
  registered[TASK_NAMES.desktop] = true;
  assert.deepEqual(await k.isRegistered(), { background: false, desktop: false });   // check() keeps its answer
  assert.deepEqual(await k.registration(), { background: true, desktop: true });
});

test('under the fake runner Task Scheduler is not asked', async () => {
  const { k, ran, spawned } = keeper({ env: { WORK_IDE_FAKE_RUNNER: '1' } });
  await k.check();
  assert.deepEqual(ran, []);
  assert.equal(spawned.length, 1);
});
