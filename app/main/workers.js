'use strict';
// Keeps the queue's workers (tools/taskd.py) alive from the app's side (task
// 0056): Task Scheduler starts them at boot and sign-in and restarts them on
// failure; the app adds a look every half minute. A registered worker that
// is not beating is started through Task Scheduler (`schtasks /run`). With
// no desktop worker registered — `taskd.py install` not run yet — the app
// starts one itself through `taskd.py start`, which detaches it from the
// app and its handles, so it outlives the window; it ends after ten minutes
// with nothing to do.
const path = require('node:path');
const { execFile, spawn: nodeSpawn } = require('node:child_process');

const TASK_NAMES = {
  background: 'WorkIDE\\Task worker (background)',
  desktop: 'WorkIDE\\Task worker (desktop)',
};
const CHECK_MS = 30000;
// A start takes a few seconds before the first beat: no second start sooner.
const RESTART_AFTER_MS = 120000;
const IDLE_EXIT_SECONDS = 600;

function schtasks(args) {
  return new Promise((resolve) => {
    execFile('schtasks', args, { windowsHide: true }, (error, stdout) => resolve({ ok: !error, stdout }));
  });
}

class WorkerKeeper {
  // live() -> [{ role }]; pending() -> whether anything is queued
  constructor({ root, python, dataRoot, live, pending, run = schtasks, spawn = nodeSpawn,
    clock = () => Date.now(), env = process.env, idleExit = IDLE_EXIT_SECONDS, log = () => {} }) {
    Object.assign(this, { root, python, dataRoot, live, pending, run, spawn, clock, env, idleExit, log });
    this.registered = null;    // { background, desktop }, asked once
    this.startedAt = {};       // role -> when the app last started it
    this.timer = null;
  }

  async isRegistered() {
    if (this.registered) return this.registered;
    const out = {};
    for (const [role, name] of Object.entries(TASK_NAMES)) {
      out[role] = (await this.run(['/Query', '/TN', name])).ok;
    }
    this.registered = out;
    return out;
  }

  recently(role) {
    return this.startedAt[role] != null && this.clock() - this.startedAt[role] < RESTART_AFTER_MS;
  }

  // -> what it did: [`${role}: ${how}`]
  async check() {
    const did = [];
    const alive = new Set(this.live().map((w) => w.role));
    const fake = this.env.WORK_IDE_FAKE_RUNNER === '1';
    const registered = fake ? { background: false, desktop: false } : await this.isRegistered();
    for (const role of ['background', 'desktop']) {
      if (alive.has(role) || this.recently(role)) continue;
      if (registered[role]) {
        this.startedAt[role] = this.clock();
        await this.run(['/Run', '/TN', TASK_NAMES[role]]);
        did.push(`${role}: started through Task Scheduler`);
      } else if (role === 'desktop' && !alive.has('background') && this.pending()) {
        this.startedAt[role] = this.clock();
        this.spawnDesktop();
        did.push('desktop: started by the app (not registered with Task Scheduler)');
      }
    }
    for (const line of did) this.log(line);
    return did;
  }

  // Not spawned from here directly: a child of Electron inherits its stdio
  // pipes, and a terminal or Playwright waiting on them waited for the
  // worker's end (tools/taskd.py start).
  spawnDesktop() {
    return this.spawn(this.python, [path.join('tools', 'taskd.py'), 'start', '--role', 'desktop',
      '--idle-exit', String(this.idleExit)], {
      cwd: this.root,
      stdio: 'ignore',
      windowsHide: true,
      env: { ...this.env, PYTHONIOENCODING: 'utf-8', WORK_IDE_DATA_ROOT: this.dataRoot },
    });
  }

  start() {
    const tick = () => this.check().catch((error) => this.log(`workers: ${error.message}`));
    tick();
    this.timer = setInterval(tick, CHECK_MS);
    if (this.timer.unref) this.timer.unref();
  }

  // The window closes; the workers go on.
  stop() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }
}

module.exports = { WorkerKeeper, TASK_NAMES };
