'use strict';
// The bottom panel's tasks, from the task queue (task 0056): data/tasks.sqlite,
// tools/taskq.py. The app is a client of it: it adds tasks and asks for
// stops through tools/taskq.py (the queue's rules live there, in one place),
// reads the rows and the log files itself, and runs nothing. The workers
// (tools/taskd.py, started by Windows Task Scheduler) run the tasks, so
// closing or collapsing the window stops nothing, and a task the agent, a
// terminal or a schedule added is listed beside the app's own.
//
// Until 2026-10-21 the queue lived here, in memory (tasks.js): closing the
// window stopped every task, and the panel showed only the app's own — for
// weeks one old CV/CL batch and nothing else.
//
// What the panel gets is the shape tasks.js gave it: camelCase fields, the
// steps of a collection (steps.js, read from its log), a CV/CL batch as the
// kind "batch" with its progress (tools/cv_batch.py's status file).
const fs = require('node:fs');
const path = require('node:path');
const { DatabaseSync } = require('node:sqlite');
const { StepTracker, OUTLINES } = require('./steps');

const ACTIVE = new Set(['queued', 'running']);
const LOG_LIMIT = 3000;
// The first read of a long log: its tail is what the panel shows, the whole
// of it is what the step list needs (a collection logs a few MB at most).
const STEP_KINDS = { collect: true, rest: false, linkedin: false, pipeline: false };
const PROGRESS_LINE = /^\[\d\d:\d\d:\d\d\] /;
const KINDS = new Set(['collect', 'rest', 'linkedin', 'clean', 'cv', 'letter', 'cv_batch', 'reputation']);
const IDENTITY_PATTERN = /^[a-z][a-z0-9]{2,9}$/;
const VACANCY_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;
// The person's instructions for one CV go on the command line, whose limit on
// Windows is 32767 characters for the whole of it (tools/taskd.py).
const INSTRUCTIONS_LIMIT = 8000;
const NO_WORKER = 'no worker is running';
const BATCH_STATES = { running: 'running', finished: 'done', stopped: 'stopped', crashed: 'failed' };

// A pipeline run started by hand logs without the prefix the worker adds.
function logLine(line) {
  return PROGRESS_LINE.test(line) ? `  | ${line}` : line;
}

function parseJson(text, fallback) {
  if (!text) return fallback;
  try {
    return JSON.parse(text);
  } catch {
    return fallback;
  }
}

class QueueClient {
  // runTaskq(args) -> Promise<stdout> of `python tools/taskq.py <args>`;
  // readBatch() -> tools/cv_batch.py's status, or null
  constructor({ dataRoot, schemaDir, runTaskq, readBatch = () => null, pollMs = 1000,
    clock = () => Date.now() }) {
    this.file = path.join(dataRoot, 'tasks.sqlite');
    this.schemaDir = schemaDir;
    this.runTaskq = runTaskq;
    this.readBatch = readBatch;
    this.pollMs = pollMs;
    this.clock = clock;
    this.db = null;
    this.logs = new Map();      // id -> { file, offset, rest, lines, tracker }
    this.current = [];          // the panel's list
    this.snapshot = '';
    this.workers = [];
    this.listeners = new Set();
    this.produced = new Set();  // documents a task reported: the only ones the renderer may open
    this.timer = null;
  }

  onEvent(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  emit(event) {
    for (const listener of this.listeners) listener(event);
  }

  open() {
    if (this.db) return this.db;
    fs.mkdirSync(path.dirname(this.file), { recursive: true });
    const db = new DatabaseSync(this.file, { timeout: 5000 });
    db.exec(fs.readFileSync(path.join(this.schemaDir, 'tasks.sql'), 'utf8'));
    this.db = db;
    return db;
  }

  close() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    if (this.db) this.db.close();
    this.db = null;
  }

  start() {
    this.poll();
    this.timer = setInterval(() => this.poll(), this.pollMs);
    if (this.timer.unref) this.timer.unref();
  }

  // One look at the queue: new lines go out as 'log' events, a changed list
  // as 'tasks', each task that ended as 'finished'.
  poll() {
    let rows;
    try {
      const db = this.open();
      rows = db.prepare('SELECT * FROM tasks WHERE hidden = 0 ORDER BY id').all();
      this.workers = db.prepare('SELECT role, pid, capabilities, heartbeat_at, note FROM workers').all();
    } catch (error) {
      // the file is being created or locked for a moment: the next poll reads it
      return false;
    }
    const before = new Map(this.current.map((task) => [task.id, task]));
    // the workers write why a task waits; with none alive nobody does
    const nobody = this.liveWorkers().length === 0;
    const list = rows.map((row) => this.publicTask(row, nobody));
    this.current = list;
    const snapshot = JSON.stringify(list);
    if (snapshot !== this.snapshot) {
      this.snapshot = snapshot;
      this.emit({ type: 'tasks', tasks: list });
    }
    for (const task of list) {
      const was = before.get(task.id);
      if (was && ACTIVE.has(was.state) && !ACTIVE.has(task.state)) this.emit({ type: 'finished', task });
    }
    for (const id of [...this.logs.keys()]) if (!list.some((task) => task.id === id)) this.logs.delete(id);
    return true;
  }

  publicTask(row, nobody = false) {
    const result = parseJson(row.result, null);
    const log = this.readLog(row);
    const task = {
      id: row.id,
      kind: row.kind === 'cv_batch' ? 'batch' : row.kind,
      lane: row.slot,
      identity: row.identity || '',
      vacancyId: row.vacancy_id || null,
      title: row.title || '',
      company: row.company || '',
      origin: row.origin,
      state: row.state,
      waitingFor: row.state === 'queued' ? (nobody ? NO_WORKER : row.waiting_for || null) : null,
      queuedAt: row.queued_at,
      startedAt: row.started_at,
      endedAt: row.ended_at,
      result,
      error: row.error || null,
      stopping: row.state === 'running' && !!row.stop_requested,
      worker: row.worker || null,
      groupId: row.group_id || null,
      logLines: log ? log.lines.length : 0,
    };
    if (log && log.tracker) task.steps = log.tracker.steps();
    if ((row.kind === 'cv' || row.kind === 'letter') && result && result.ok) {
      for (const key of ['docx', 'pdf']) if (result[key]) this.produced.add(path.resolve(result[key]));
    }
    if (row.kind === 'cv_batch') Object.assign(task, this.batchProgress(task));
    return task;
  }

  // The batch's own status file says how far it is, and what it is making.
  batchProgress(task) {
    const status = task.state === 'running' ? this.readBatch() : null;
    const number = (value) => (Number.isFinite(value) ? value : 0);
    if (!status || BATCH_STATES[status.state] !== 'running') {
      return { progress: null, holding: false, current: null };
    }
    return {
      progress: {
        index: number(status.index), total: number(status.total),
        made: number(status.made), failed: number(status.failed), gone: number(status.gone),
      },
      holding: !!status.holding,
      current: status.current ? {
        identity: status.current.identity, vacancyId: status.current.vacancy_id, kind: status.current.kind,
        title: status.current.title || '', company: status.current.company || '',
      } : null,
    };
  }

  // The new part of a task's log file: to the panel, and to its steps.
  readLog(row) {
    if (!row.log_path) return null;
    let entry = this.logs.get(row.id);
    if (!entry || entry.file !== row.log_path) {
      const agent = STEP_KINDS[row.kind];
      entry = {
        file: row.log_path, offset: 0, rest: '', lines: [],
        tracker: agent === undefined ? null
          : new StepTracker({ now: this.clock, agent, outline: OUTLINES[row.kind] || [] }),
        ended: false,
      };
      this.logs.set(row.id, entry);
    }
    let size = 0;
    try {
      size = fs.statSync(entry.file).size;
    } catch {
      size = 0;
    }
    if (size > entry.offset) {
      const fd = fs.openSync(entry.file, 'r');
      const buffer = Buffer.alloc(size - entry.offset);
      fs.readSync(fd, buffer, 0, buffer.length, entry.offset);
      fs.closeSync(fd);
      entry.offset = size;
      const parts = (entry.rest + buffer.toString('utf8')).split(/\r?\n/);
      entry.rest = parts.pop();
      const fresh = [];
      for (const raw of parts) {
        if (!raw.trim()) continue;
        const line = logLine(raw);
        entry.lines.push(line);
        fresh.push(line);
        if (entry.tracker) entry.tracker.feed(line);
      }
      if (entry.lines.length > LOG_LIMIT) entry.lines.splice(0, entry.lines.length - LOG_LIMIT);
      if (this.snapshot) for (const line of fresh) this.emit({ type: 'log', id: row.id, text: line });
    }
    if (entry.tracker && !ACTIVE.has(row.state) && !entry.ended) {
      entry.ended = true;
      entry.tracker.finish(row.state);
    }
    return entry;
  }

  list() {
    return this.current;
  }

  log(id) {
    const entry = this.logs.get(Number(id));
    return entry ? [...entry.lines] : [];
  }

  active() {
    return this.current.some((task) => ACTIVE.has(task.state));
  }

  // The workers alive now: { role, capabilities, note }.
  liveWorkers(staleMs = 45000) {
    const now = this.clock();
    return this.workers.filter((w) => w.heartbeat_at && now - Date.parse(w.heartbeat_at) <= staleMs);
  }

  async taskq(args) {
    const out = await this.runTaskq(args);
    const reply = parseJson(String(out).trim(), null);
    if (reply === null) throw new Error(`tools/taskq.py answered: ${String(out).slice(0, 300)}`);
    // read now: the caller looks at the list next (the app starts a worker
    // when something is queued)
    this.poll();
    return reply;
  }

  // request: { kind, identity, vacancyId?, title?, company?, instructions?, args? }
  // -> { ok, error?, task }
  async enqueue(request) {
    const r = request || {};
    if (!KINDS.has(r.kind)) throw new Error(`unknown task kind: ${r.kind}`);
    if (!IDENTITY_PATTERN.test(String(r.identity))) throw new Error(`invalid identity: ${r.identity}`);
    const text = (value, limit) => String(value == null ? '' : value).slice(0, limit);
    if (r.kind === 'collect') {
      const reply = await this.taskq(['collect', r.identity, '--origin', 'app', '--json']);
      const made = reply[0];
      return { ok: made.added, error: made.added ? null : 'already_queued', task: this.shape(made.task) };
    }
    const args = ['add', r.kind, '--identity', r.identity, '--origin', 'app', '--json'];
    if (['cv', 'letter', 'reputation'].includes(r.kind)) {
      if (!VACANCY_PATTERN.test(String(r.vacancyId))) throw new Error(`invalid vacancy id: ${r.vacancyId}`);
      args.push('--vacancy', r.vacancyId, '--title', text(r.title, 300), '--company', text(r.company, 300));
    }
    if (r.instructions != null && typeof r.instructions !== 'string') throw new Error('instructions must be text');
    const instructions = (r.instructions || '').trim();
    if (instructions.length > INSTRUCTIONS_LIMIT) {
      throw new Error(`the instructions are longer than ${INSTRUCTIONS_LIMIT} characters`);
    }
    if (instructions) args.push('--instructions', instructions);
    if (r.args) args.push('--args', JSON.stringify(r.args));
    const reply = await this.taskq(args);
    return { ok: reply.added, error: reply.added ? null : 'already_queued', task: this.shape(reply.task) };
  }

  // A task as taskq.py prints it -> the panel's shape.
  shape(task) {
    return this.publicTask({
      ...task,
      args: JSON.stringify(task.args || {}),
      result: task.result == null ? null : JSON.stringify(task.result),
      needs: (task.needs || []).join(','),
    });
  }

  async cancel(id) {
    const reply = await this.taskq(['stop', String(Number(id)), '--json']).catch((error) => ({ ok: false, error: error.message }));
    return { ok: !!reply.ok };
  }

  // Every queued task, of one identity or of all; the running ones go on.
  async cancelQueued(identity = null) {
    let cancelled = 0;
    for (const task of this.current) {
      if (task.state !== 'queued' || (identity && task.identity !== identity)) continue;
      const reply = await this.cancel(task.id);
      if (reply.ok) cancelled += 1;
    }
    return { ok: true, cancelled };
  }

  // Cleared for good: a restart does not bring them back (task 0060).
  async clearFinished() {
    await this.taskq(['hide', '--json']);
    return { ok: true };
  }

  // A file the renderer asks to open must be one a task produced.
  checkProduced(file) {
    const resolved = path.resolve(String(file || ''));
    if (!this.produced.has(resolved)) throw new Error('not a generated CV file');
    return resolved;
  }
}

module.exports = { QueueClient, logLine, INSTRUCTIONS_LIMIT, NO_WORKER };
