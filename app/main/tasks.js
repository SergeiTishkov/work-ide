'use strict';
// The task queue behind the bottom panel (the owner, 2026-10-13): what the
// app was asked to do, in order — collections, CVs, cover letters — and the
// log of each.
//
// Lanes, each one task at a time, side by side (and "reputation", below):
//   collect    the agent runs (runner.js): one at a time, since an agent
//              edits shared code; and a run started anywhere else (the
//              pipeline's own lock, tools/runstate.py) makes the next one wait.
//   documents  CVs and cover letters (cv.js): one at a time, since each
//              drives Word through COM.
// "Collect vacancies" on three identities queues three runs; "Generate CV" on
// ten vacancies queues ten CVs. A task already queued or going is not queued
// twice.
//
// A collection shows its steps (steps.js): the agent's preparation, each
// stage of the pipeline, the agent's review.
//
// After a collection ends well, the identity's CVs and cover letters are made
// by ONE batch (tools/cv_batch.py, batch.js): a process of its own, shown here
// as the task "batch" (setExternal). While the app has documents of its own
// to make, the batch waits between documents (holdExternal) — a CV the person
// asked for does not wait hours behind it; the app's document waits only for
// the batch's current one.
//
// A vacancy's "Collect reputation" is the task "reputation" (reputation.js),
// in a lane of its own: a lookup of a minute or two does not wait hours
// behind a collection (the owner, 2026-10-17).
//
// The fast collection (/top) is followed by the rest of the base: the task
// "rest" (rest.js), queued in the collect lane when the collection ends well,
// so it runs after every collection queued before it — the top vacancies of
// each identity first, the rest afterwards (the owner, 2026-10-17).
//
// LinkedIn is the task "linkedin" (`pipeline.py --linkedin`, rest.js), in a
// lane of its own (the owner, 2026-10-20): its fetch takes hours, the other
// sources half an hour, and the vacancies of those are not to wait for it.
// "Collect" queues both. The run fetches without holding the base and waits
// for it to merge (tools/runstate.py), so the lane does not ask externalBusy.
// The rest of the base waits for both: it is queued when the later of the
// two ends, if the collection ended well. A LinkedIn run that ends well
// starts the CV/CL batch too, for what it brought.
//
// The work itself is injected (start*, startAuto, externalBusy, ...), so
// tests run the queue without processes.

const { StepTracker } = require('./steps');

const LANES = {
  collect: 'collect', rest: 'collect', cv: 'documents', letter: 'documents', reputation: 'reputation',
  linkedin: 'linkedin',
};
const ACTIVE = new Set(['queued', 'running']);
const LOG_LIMIT = 3000;
const EXTERNAL = 'batch';

class TaskQueue {
  // startCollect(task, onLine) / startRest(task, onLine) / startLinkedIn(task, onLine) /
  // startReputation(task, onLine) / startDocument(task, onLine):
  //   -> { done: Promise<{ ok, code?, error?, ...result }>, stop() }
  // startAuto(identity) -> Promise<string>: starts the CV/CL batch; a line
  //   for the collection's log
  // externalBusy(identity) -> Promise<string|null>: who holds the pipeline
  // stopExternal() / holdExternal(on): the batch's stop and hold files
  constructor({ startCollect, startDocument, startRest = null, startLinkedIn = null, startReputation = null,
    startAuto = null, externalBusy = null,
    stopExternal = () => {}, holdExternal = () => {},
    retryMs = 5000, now = () => new Date().toISOString(), clock = () => Date.now() }) {
    this.startCollect = startCollect;
    this.startRest = startRest;
    this.startLinkedIn = startLinkedIn;
    this.startReputation = startReputation;
    this.startDocument = startDocument;
    this.startAuto = startAuto;
    this.externalBusy = externalBusy;
    this.stopExternal = stopExternal;
    this.holdExternal = holdExternal;
    this.retryMs = retryMs;
    this.now = now;
    this.clock = clock;
    this.tasks = [];
    this.handles = new Map();   // id -> { stop }
    this.trackers = new Map();  // collection id -> StepTracker
    this.checking = new Set();  // lanes asking externalBusy right now
    this.retry = null;
    this.nextId = 1;
    this.listeners = new Set();
    this.external = null;       // the batch, as batch.batchTask() describes it
    this.externalLines = [];
    this.dismissed = null;      // a finished batch cleared from the panel
    this.holding = false;
  }

  onEvent(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  emit(event) {
    for (const listener of this.listeners) listener(event);
  }

  changed() {
    const hold = this.tasks.some((t) => t.lane === 'documents' && ACTIVE.has(t.state));
    if (hold !== this.holding) {
      this.holding = hold;
      this.holdExternal(hold);
    }
    this.emit({ type: 'tasks', tasks: this.list() });
  }

  // The tasks without their logs: the panel's list, in the order they came.
  list() {
    const own = this.tasks.map((task) => this.publicTask(task));
    if (!this.shownExternal()) return own;
    const batch = { ...this.external, logLines: this.externalLines.length };
    const at = Date.parse(batch.queuedAt);
    const index = own.findIndex((t) => Date.parse(t.queuedAt) > at);
    if (index < 0) own.push(batch);
    else own.splice(index, 0, batch);
    return own;
  }

  shownExternal() {
    return this.external && this.external.startedAt !== this.dismissed ? this.external : null;
  }

  log(id) {
    if (id === EXTERNAL) return [...this.externalLines];
    const task = this.tasks.find((t) => t.id === id);
    return task ? [...task.log] : [];
  }

  active() {
    return this.tasks.some((t) => ACTIVE.has(t.state));
  }

  same(a, b) {
    return a.kind === b.kind && a.identity === b.identity && (a.vacancyId || null) === (b.vacancyId || null);
  }

  // request: { kind: 'collect'|'rest'|'linkedin'|'cv'|'letter'|'reputation', identity, vacancyId?, title?,
  // company?, instructions?, origin? }
  enqueue(request) {
    if (!Object.hasOwn(LANES, request.kind)) throw new Error(`unknown task kind: ${request.kind}`);
    const existing = this.tasks.find((t) => ACTIVE.has(t.state) && this.same(t, request));
    if (existing) return { ok: false, error: 'already_queued', task: this.publicTask(existing) };
    const task = {
      id: this.nextId++,
      kind: request.kind,
      lane: LANES[request.kind],
      identity: request.identity,
      vacancyId: request.vacancyId || null,
      title: request.title || '',
      company: request.company || '',
      instructions: (request.instructions || '').trim(),
      origin: request.origin || 'manual',
      state: 'queued',
      waitingFor: null,
      queuedAt: this.now(),
      startedAt: null,
      endedAt: null,
      result: null,
      error: null,
      log: [],
    };
    if (task.kind === 'collect') this.trackers.set(task.id, new StepTracker({ now: this.clock }));
    if (task.kind === 'rest' || task.kind === 'linkedin') {
      this.trackers.set(task.id, new StepTracker({ now: this.clock, agent: false }));
    }
    this.tasks.push(task);
    this.changed();
    this.pump();
    return { ok: true, task: this.publicTask(task) };
  }

  publicTask(task) {
    const { log, ...rest } = task;
    const tracker = this.trackers.get(task.id);
    return { ...rest, logLines: log.length, ...(tracker ? { steps: tracker.steps() } : {}) };
  }

  append(task, text) {
    const tracker = this.trackers.get(task.id);
    let stepsChanged = false;
    for (const line of String(text).split(/\r?\n/)) {
      if (!line.trim()) continue;
      task.log.push(line);
      this.emit({ type: 'log', id: task.id, text: line });
      if (tracker && tracker.feed(line)) stepsChanged = true;
    }
    if (task.log.length > LOG_LIMIT) task.log.splice(0, task.log.length - LOG_LIMIT);
    if (stepsChanged) this.changed();
  }

  pump() {
    for (const lane of new Set(Object.values(LANES))) this.pumpLane(lane);
  }

  async pumpLane(lane) {
    if (this.tasks.some((t) => t.lane === lane && t.state === 'running')) return;
    if (this.checking.has(lane)) return;
    const task = this.tasks.find((t) => t.lane === lane && t.state === 'queued');
    if (!task) return;
    if (lane === 'documents') {
      // the batch makes one document at a time too, through the same Word:
      // the app's document waits until the batch has paused between two
      const batch = this.external;
      const busy = batch && batch.state === 'running' && !batch.holding;
      if (busy) {
        if (task.waitingFor !== EXTERNAL) {
          task.waitingFor = EXTERNAL;
          this.changed();
        }
        return;   // setExternal pumps again when the batch pauses or ends
      }
      if (task.waitingFor) task.waitingFor = null;
    }
    if (lane === 'collect' && this.externalBusy) {
      this.checking.add(lane);
      let holder = null;
      try {
        holder = await this.externalBusy(task.identity);
      } catch {
        holder = null;
      } finally {
        this.checking.delete(lane);
      }
      if (task.state !== 'queued') {
        this.pumpLane(lane);
        return;
      }
      if (holder) {
        if (task.waitingFor !== holder) {
          task.waitingFor = holder;
          this.changed();
        }
        this.scheduleRetry();
        return;
      }
      task.waitingFor = null;
    }
    this.run(task);
  }

  scheduleRetry() {
    if (this.retry) return;
    this.retry = setTimeout(() => {
      this.retry = null;
      this.pump();
    }, this.retryMs);
    if (this.retry.unref) this.retry.unref();
  }

  run(task) {
    task.state = 'running';
    task.startedAt = this.now();
    const onLine = (text) => this.append(task, text);
    let handle;
    try {
      if (task.kind === 'collect') handle = this.startCollect(task, onLine);
      else if (task.kind === 'rest') handle = this.startRest(task, onLine);
      else if (task.kind === 'linkedin') handle = this.startLinkedIn(task, onLine);
      else if (task.kind === 'reputation') handle = this.startReputation(task, onLine);
      else handle = this.startDocument(task, onLine);
    } catch (error) {
      this.finish(task, { ok: false, error: error.message });
      return;
    }
    this.handles.set(task.id, handle);
    this.changed();
    Promise.resolve(handle.done)
      .then((result) => this.completed(task, result || { ok: false, error: 'no result' }))
      .catch((error) => this.completed(task, { ok: false, error: error.message }));
  }

  async completed(task, result) {
    const ok = result.ok && !task.stopping;
    if ((task.kind === 'collect' || task.kind === 'linkedin') && ok && this.startAuto) {
      try {
        const line = await this.startAuto(task.identity);
        if (line) this.append(task, line);
      } catch (error) {
        this.append(task, `CV/CL batch: ${error.message}`);
      }
    }
    if (task.kind === 'collect' && ok && this.startRest) {
      const linkedin = this.tasks.find((t) => t.kind === 'linkedin' && t.identity === task.identity
        && ACTIVE.has(t.state));
      if (linkedin) {
        linkedin.restAfter = true;
        this.append(task, `the rest of the base is queued when LinkedIn ends: task #${linkedin.id}`);
      } else {
        this.queueRest(task);
      }
    }
    if (task.kind === 'linkedin' && task.restAfter && this.startRest) this.queueRest(task);
    this.finish(task, result);
  }

  queueRest(after) {
    const queued = this.enqueue({ kind: 'rest', identity: after.identity, origin: 'auto' });
    if (queued.ok) this.append(after, `the rest of the base is queued: task #${queued.task.id}`);
  }

  finish(task, result) {
    this.handles.delete(task.id);
    task.endedAt = this.now();
    task.result = result;
    task.error = result.ok ? null : (result.error || (result.code != null ? `exit ${result.code}` : 'failed'));
    task.state = task.stopping ? 'stopped' : result.ok ? 'done' : 'failed';
    delete task.stopping;
    const tracker = this.trackers.get(task.id);
    if (tracker) tracker.finish(task.state);
    this.changed();
    this.emit({ type: 'finished', task: this.publicTask(task) });
    this.pump();
  }

  // The batch as batch.BatchWatch reads it: { task, lines, reset }.
  setExternal({ task, lines = [], reset = false }) {
    const before = this.external;
    this.external = task;
    if (reset) this.externalLines = [];
    for (const line of lines) {
      this.externalLines.push(line);
      if (this.shownExternal()) this.emit({ type: 'log', id: EXTERNAL, text: line });
    }
    if (this.externalLines.length > LOG_LIMIT) this.externalLines.splice(0, this.externalLines.length - LOG_LIMIT);
    this.changed();
    const wasBusy = before && before.state === 'running' && !before.holding;
    const isBusy = task && task.state === 'running' && !task.holding;
    if (wasBusy && !isBusy) this.pump();
    if (before && before.state === 'running' && task && task.state !== 'running') {
      this.emit({ type: 'finished', task: { ...task, logLines: this.externalLines.length } });
    }
  }

  cancel(id) {
    if (id === EXTERNAL) {
      if (!this.external || this.external.state !== 'running') return { ok: false };
      this.stopExternal();
      this.external = { ...this.external, stopping: true };
      this.changed();
      return { ok: true };
    }
    const task = this.tasks.find((t) => t.id === id);
    if (!task || !ACTIVE.has(task.state)) return { ok: false };
    if (task.state === 'queued') {
      task.state = 'stopped';
      task.endedAt = this.now();
      this.changed();
      this.pump();
      return { ok: true };
    }
    task.stopping = true;
    const handle = this.handles.get(id);
    if (handle && handle.stop) handle.stop();
    return { ok: true };
  }

  // Every queued task, of one identity or of all; the running ones go on.
  cancelQueued(identity = null) {
    let n = 0;
    for (const task of this.tasks) {
      if (task.state === 'queued' && (!identity || task.identity === identity)) {
        task.state = 'stopped';
        task.endedAt = this.now();
        n += 1;
      }
    }
    if (n) this.changed();
    return { ok: true, cancelled: n };
  }

  clearFinished() {
    const before = this.tasks.length;
    this.tasks = this.tasks.filter((t) => ACTIVE.has(t.state));
    for (const id of [...this.trackers.keys()]) if (!this.tasks.some((t) => t.id === id)) this.trackers.delete(id);
    const batch = this.shownExternal();
    const batchCleared = batch && batch.state !== 'running';
    if (batchCleared) this.dismissed = batch.startedAt;
    if (this.tasks.length !== before || batchCleared) this.changed();
    return { ok: true };
  }

  // The window closes: the app's own tasks end; the batch goes on.
  stopAll() {
    this.cancelQueued();
    for (const task of this.tasks) if (task.state === 'running') this.cancel(task.id);
    if (this.holding) {
      this.holding = false;
      this.holdExternal(false);
    }
  }
}

module.exports = { TaskQueue, LANES, EXTERNAL };
