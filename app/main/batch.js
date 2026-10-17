'use strict';
// The CV/CL batch (tools/cv_batch.py) as the task panel sees it: a process of
// its own, apart from the app, so it outlives the window — hundreds of
// documents take a day. The app starts it after a collection, shows it from
// its status file and log in data/, stops it with the stop file, and makes it
// wait between documents while the app has documents of its own to make
// (the hold file). The owner, 2026-10-13.
const fs = require('node:fs');
const path = require('node:path');
const { spawn: nodeSpawn } = require('node:child_process');

const LOG_LIMIT = 3000;
const STATES = { running: 'running', finished: 'done', stopped: 'stopped', crashed: 'failed' };

function batchPaths(dataRoot) {
  const at = (ext) => path.join(dataRoot, `cv_batch.${ext}`);
  return { status: at('json'), log: at('log'), stop: at('STOP'), hold: at('HOLD') };
}

function pidAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error.code === 'EPERM';
  }
}

// The status file -> a task of the panel, or null.
function batchTask(status, { alive = pidAlive, stopAsked = false } = {}) {
  if (!status || typeof status !== 'object' || !status.started_at) return null;
  let state = STATES[status.state] || 'failed';
  let error = status.error || null;
  if (state === 'running' && !alive(status.pid)) {
    state = 'failed';
    error = 'the batch process ended without finishing';
  }
  const number = (value) => (Number.isFinite(value) ? value : 0);
  return {
    id: 'batch',
    kind: 'batch',
    lane: 'documents',
    identity: (status.identities || []).join(', '),
    vacancyId: null,
    title: '',
    company: '',
    origin: 'external',
    state,
    holding: state === 'running' && !!status.holding,
    stopping: state === 'running' && stopAsked,
    waitingFor: null,
    queuedAt: status.started_at,
    startedAt: status.started_at,
    endedAt: status.ended_at || null,
    progress: {
      index: number(status.index), total: number(status.total),
      made: number(status.made), failed: number(status.failed), gone: number(status.gone),
    },
    current: state === 'running' && status.current ? {
      identity: status.current.identity, kind: status.current.kind, vacancyId: status.current.vacancy_id,
      title: status.current.title || '', company: status.current.company || '',
    } : null,
    result: null,
    error,
  };
}

// Polls the two files; onChange({ task, lines, reset }) when the task or the
// batch's log changed. `reset`: a new batch, its log starts over.
class BatchWatch {
  constructor({ dataRoot, onChange, interval = 2000, alive = pidAlive }) {
    this.paths = batchPaths(dataRoot);
    this.onChange = onChange;
    this.alive = alive;
    this.key = null;        // the batch's started_at
    this.offset = 0;
    this.rest = '';
    this.last = null;
    this.timer = interval ? setInterval(() => this.poll(), interval) : null;
    if (this.timer && this.timer.unref) this.timer.unref();
  }

  readStatus() {
    try {
      return JSON.parse(fs.readFileSync(this.paths.status, 'utf8'));
    } catch {
      return null;
    }
  }

  readLog() {
    let size;
    try {
      size = fs.statSync(this.paths.log).size;
    } catch {
      return [];
    }
    if (size <= this.offset) return [];
    const fd = fs.openSync(this.paths.log, 'r');
    const buffer = Buffer.alloc(size - this.offset);
    fs.readSync(fd, buffer, 0, buffer.length, this.offset);
    fs.closeSync(fd);
    this.offset = size;
    const lines = (this.rest + buffer.toString('utf8')).split(/\r?\n/);
    this.rest = lines.pop();
    return lines.filter((line) => line.trim());
  }

  poll() {
    const status = this.readStatus();
    const task = batchTask(status, { alive: this.alive, stopAsked: fs.existsSync(this.paths.stop) });
    let reset = false;
    if (task && task.startedAt !== this.key) {
      this.key = task.startedAt;
      this.offset = Number.isFinite(status.log_offset) ? status.log_offset : 0;
      this.rest = '';
      reset = true;
    }
    const lines = task ? this.readLog().slice(-LOG_LIMIT) : [];
    const text = JSON.stringify(task);
    if (!reset && !lines.length && text === this.last) return;
    this.last = text;
    this.onChange({ task, lines, reset });
  }

  stop() {
    if (this.timer) clearInterval(this.timer);
  }
}

// Starts tools/cv_batch.py for one identity, detached: it goes on when the
// app closes. When a batch is running, the script joins it and exits.
function startBatch({ root, python, identity, env = process.env, spawn = nodeSpawn }) {
  if (!/^[a-z][a-z0-9]{2,9}$/.test(String(identity))) throw new Error(`invalid identity: ${identity}`);
  const child = spawn(python, [path.join('tools', 'cv_batch.py'), identity], {
    cwd: root, detached: true, stdio: 'ignore', windowsHide: true,
    env: { ...env, PYTHONIOENCODING: 'utf-8' },
  });
  if (child.unref) child.unref();
  return child.pid;
}

function stopBatch(dataRoot) {
  fs.mkdirSync(dataRoot, { recursive: true });
  fs.writeFileSync(batchPaths(dataRoot).stop, '');
}

// On: the batch waits between documents; off: it goes on.
function holdBatch(dataRoot, on, pid = process.pid) {
  const file = batchPaths(dataRoot).hold;
  if (on) {
    fs.mkdirSync(dataRoot, { recursive: true });
    fs.writeFileSync(file, String(pid));
  } else {
    fs.rmSync(file, { force: true });
  }
}

module.exports = { batchPaths, batchTask, BatchWatch, startBatch, stopBatch, holdBatch, pidAlive };
