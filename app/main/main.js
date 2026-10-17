'use strict';
// The Electron main process: one window, and the IPC behind window.api
// (main/preload.js). All data access and process control lives here; the
// renderer only asks.
const fs = require('node:fs');
const path = require('node:path');
const { app, BrowserWindow, clipboard, ipcMain, shell } = require('electron');
const { repoRoot, schemaDir, pythonExecutable } = require('./paths');
const { runCleanup } = require('./cleanup');
const { Store } = require('./store');
const { StoreThread } = require('./store-thread');
const { Runner, killTree } = require('./runner');
const { startRest: spawnRest } = require('./rest');
const { startReputation: spawnReputation } = require('./reputation');
const { CvGenerator, INSTRUCTIONS_LIMIT } = require('./cv');
const { TaskQueue, EXTERNAL } = require('./tasks');
const { BatchWatch, startBatch, stopBatch, holdBatch } = require('./batch');
const { documentsState, resolveRoot, vacancyDir } = require('./documents');
const { listIdentities } = require('./identities');
const { codeStamp, refreshAction } = require('./code-stamp');

const startedWithCode = codeStamp();

// A separate profile folder for test instances. Two Electron processes on one
// profile collide — the smoke test failed at random while the owner had the
// real app open (2026-09-30).
if (process.env.WORK_IDE_USER_DATA) app.setPath('userData', process.env.WORK_IDE_USER_DATA);

const root = repoRoot();
const UI_ZOOM = 1.2;
let identities = [];

function databaseOf(prefix) {
  const entry = identities.find((e) => e.prefix === prefix);
  return entry ? entry.database : null;
}

// The data calls run on a thread of their own (store-thread.js), so a slow
// query never freezes the window. The pipeline indicator stays here: one
// small query, and it checks a pid, which the main thread does.
const data = new StoreThread({
  schemaDir: schemaDir(root),
  databases: () => Object.fromEntries(identities.map((e) => [e.prefix, e.database])),
});
const store = new Store({ schemaDir: schemaDir(root), databasePathOf: databaseOf });

// The folder of generated documents (tools/documents.py): asked of Python
// once; WORK_IDE_DOCUMENTS_DIR sets it in tests.
let documentsRootPromise = null;
function documentsRoot() {
  if (!documentsRootPromise) {
    documentsRootPromise = resolveRoot({ root, python: pythonExecutable(root) })
      .catch((error) => {
        documentsRootPromise = null;
        throw error;
      });
  }
  return documentsRootPromise;
}

let cvGenerator = null;
function cv() {
  if (!cvGenerator) {
    cvGenerator = new CvGenerator({ root, python: pythonExecutable(root), documentsDir: documentsRoot });
  }
  return cvGenerator;
}

const fake = process.env.WORK_IDE_FAKE_RUNNER === '1' ? require('./fake-runner') : null;
const runner = new Runner({
  root,
  logDirOf: (prefix) => {
    const entry = identities.find((e) => e.prefix === prefix);
    return path.join(entry ? entry.dataDir : path.join(root, 'data', 'identities', prefix), 'runs');
  },
  ...(fake ? { spawn: fake.fakeSpawn, kill: fake.fakeKill } : {}),
});

// A collection as a task: the runner's lines go to the task's log, its exit
// ends the task.
let collectSink = null;
function startCollect(task, onLine) {
  // The agent may create or rebuild the database; do not hold it open.
  store.closeAll();
  data.call('closeAll').catch(() => {});
  let resolve;
  const done = new Promise((r) => { resolve = r; });
  collectSink = { onLine, resolve };
  const reply = runner.start('collect', task.identity);
  if (!reply.ok) {
    collectSink = null;
    return { done: Promise.resolve({ ok: false, error: reply.error }), stop() {} };
  }
  return { done, stop: () => runner.stop() };
}

runner.onEvent((event) => {
  if (event.type === 'exit') {
    store.closeAll();
    data.call('closeAll').catch(() => {});
  }
  if (!collectSink) return;
  if (event.type === 'output') collectSink.onLine(event.text);
  if (event.type === 'exit') {
    const sink = collectSink;
    collectSink = null;
    sink.resolve(event.error ? { ok: false, error: event.error } : { ok: event.code === 0, code: event.code });
  }
});

// The CVs and cover letters after a collection: one batch, a process of its
// own (tools/cv_batch.py, main/batch.js), which picks what the identity's
// cv.auto filters match. A batch already running takes the identity on.
const dataRoot = process.env.WORK_IDE_DATA_ROOT || path.join(root, 'data');

async function startAuto(identity) {
  if (fake) return 'CV/CL batch: not started (fake runner)';
  const pid = startBatch({ root, python: pythonExecutable(root), identity });
  return `CV/CL batch started for ${identity} (pid ${pid}): see the task "CV/CL batch"`;
}

// The rest of the base after a collection (rest.js): the pipeline alone.
function startRest(task, onLine) {
  if (fake) {
    onLine(`fake rest: ${task.identity}`);
    return { done: Promise.resolve({ ok: true, code: 0 }), stop() {} };
  }
  store.closeAll();
  data.call('closeAll').catch(() => {});
  const handle = spawnRest({ root, python: pythonExecutable(root), identity: task.identity, onLine, kill: killTree });
  return {
    done: handle.done.then((result) => {
      store.closeAll();
      data.call('closeAll').catch(() => {});
      return result;
    }),
    stop: handle.stop,
  };
}

// A vacancy's "Collect reputation" (reputation.js). It only writes rows of
// the shared base, which a running collection allows: the connections stay.
function startReputation(task, onLine) {
  if (fake) {
    onLine(`reputation of ${task.company || task.vacancyId}: not looked up (fake runner)`);
    return { done: Promise.resolve({ ok: true, code: 0 }), stop() {} };
  }
  return spawnReputation({
    root, python: pythonExecutable(root), identity: task.identity, vacancyId: task.vacancyId,
    onLine, kill: killTree,
  });
}

const tasks = new TaskQueue({
  startCollect,
  startRest,
  startReputation,
  startDocument: (task, onLine) => cv().start(task.identity, task.vacancyId, task.instructions, task.kind, onLine),
  startAuto,
  // A pipeline run started anywhere else holds the shared base: the next
  // collection waits for it.
  externalBusy: async (identity) => {
    const status = store.pipelineStatus(identity);
    return status.running ? identity : status.busyWith || null;
  },
  stopExternal: () => stopBatch(dataRoot),
  holdExternal: (on) => {
    try {
      holdBatch(dataRoot, on);
    } catch (error) {
      console.warn(`cv_batch hold: ${error.message}`);
    }
  },
});

const batchWatch = new BatchWatch({ dataRoot, onChange: (change) => tasks.setExternal(change) });
batchWatch.poll();

// A task id from the renderer: a number, or the batch's.
const taskId = (id) => (id === EXTERNAL ? EXTERNAL : Number(id));

const TASK_KINDS = new Set(['collect', 'rest', 'cv', 'letter', 'reputation']);
const IDENTITY_PATTERN = /^[a-z][a-z0-9]{2,9}$/;

function enqueueTask(request) {
  const r = request || {};
  if (!TASK_KINDS.has(r.kind)) throw new Error(`unknown task kind: ${r.kind}`);
  if (!IDENTITY_PATTERN.test(String(r.identity))) throw new Error(`invalid identity: ${r.identity}`);
  const text = (value, limit) => String(value == null ? '' : value).slice(0, limit);
  if (r.kind === 'collect' || r.kind === 'rest') return tasks.enqueue({ kind: r.kind, identity: r.identity });
  if (r.kind === 'reputation') {
    vacancyDir('x', r.identity, r.vacancyId);   // validates the id
    return tasks.enqueue({
      kind: r.kind, identity: r.identity, vacancyId: r.vacancyId,
      title: text(r.title, 300), company: text(r.company, 300),
    });
  }
  if (r.instructions != null && typeof r.instructions !== 'string') throw new Error('instructions must be text');
  if ((r.instructions || '').trim().length > INSTRUCTIONS_LIMIT) {
    throw new Error(`the instructions are longer than ${INSTRUCTIONS_LIMIT} characters`);
  }
  vacancyDir('x', r.identity, r.vacancyId);   // validates the id
  return tasks.enqueue({
    kind: r.kind, identity: r.identity, vacancyId: r.vacancyId,
    title: text(r.title, 300), company: text(r.company, 300), instructions: r.instructions || '',
  });
}

// Errors cross IPC as values, not exceptions: the renderer shows them.
function handle(channel, fn) {
  ipcMain.handle(channel, async (_event, ...args) => {
    try {
      return { ok: true, value: await fn(...args) };
    } catch (error) {
      return { ok: false, error: error.message };
    }
  });
}

function registerIpc(window) {
  handle('identities', async () => {
    identities = await listIdentities({ root });
    return identities.map(({ prefix, displayName, hasDatabase }) => ({ prefix, displayName, hasDatabase }));
  });
  handle('segments', (identity) => data.call('segments', identity));
  handle('listing', (identity, view, page) => data.call('listing', identity, view || {}, page || {}));
  handle('class-totals', (identity, view) => data.call('classTotals', identity, view || {}));
  handle('counts', (identity, view) => data.call('counts', identity, view || {}));
  handle('sources', (identity, view) => data.call('sources', identity, view || {}));
  handle('companies', (identity, view) => data.call('companies', identity, view || {}));
  handle('ages', (identity, view) => data.call('ages', identity, view || {}));
  // Deleting compacts the file (VACUUM), which an open connection can hold
  // up: both close first and open again on the next read.
  handle('cleanup', async (identity, filters, dryRun) => {
    if (!dryRun) {
      await data.call('closeAll');
      store.closeAll();
    }
    return runCleanup({ root, python: pythonExecutable(root), identity, filters, dryRun: Boolean(dryRun) });
  });
  handle('set-feedback', (identity, id, status, reason) => data.call('setFeedback', identity, id, status, reason));
  handle('advance', (identity, id, step, comment) => data.call('advance', identity, id, step, comment));
  handle('step-back', (identity, id) => data.call('stepBack', identity, id));
  handle('edit-comment', (identity, id, kind, index, text) =>
    data.call('editComment', identity, id, kind, index, text));
  handle('pending-feedback', (identity) => data.call('pendingFeedback', identity));
  handle('pipeline-status', (identity) => store.pipelineStatus(identity));
  handle('tasks', () => tasks.list());
  handle('task-log', (id) => tasks.log(taskId(id)));
  handle('enqueue-task', (request) => enqueueTask(request));
  handle('cancel-task', (id) => tasks.cancel(taskId(id)));
  handle('cancel-queued', (identity) => tasks.cancelQueued(identity || null));
  handle('clear-tasks', () => tasks.clearFinished());
  handle('documents-state', async (identity, ids) =>
    documentsState(await documentsRoot(), identity, Array.isArray(ids) ? ids.slice(0, 5000) : []));
  handle('open-documents-dir', async (identity, vacancyId) => {
    const dir = vacancyDir(await documentsRoot(), identity, vacancyId);
    if (!fs.existsSync(dir)) throw new Error(`${dir} does not exist`);
    const problem = await shell.openPath(dir);
    if (problem) throw new Error(problem);
  });
  // "Refresh": the page reloads itself; when the main process's own code
  // changed since start, the whole app restarts instead — unless an agent run
  // started from here is going, which a restart would cut off.
  handle('refresh', () => {
    const action = refreshAction({
      startedWith: startedWithCode, now: codeStamp(), agentRunning: tasks.active(),
    });
    if (action !== 'relaunch') return action;
    setTimeout(() => {
      app.relaunch();
      app.exit(0);
    }, 50);
    return 'relaunch';
  });
  handle('open-external', (url) => {
    if (!/^https?:\/\//i.test(url)) throw new Error('only http(s) links open');
    return shell.openExternal(url);
  });
  handle('copy-text', (text) => {
    clipboard.writeText(String(text));
  });
  handle('open-cv-file', async (file) => {
    const problem = await shell.openPath(cv().checkProduced(file));
    if (problem) throw new Error(problem);
  });
  handle('show-cv-file', (file) => shell.showItemInFolder(cv().checkProduced(file)));

  tasks.onEvent((event) => {
    if (!window.isDestroyed()) window.webContents.send('task-event', event);
  });
}

function createWindow() {
  // WORK_IDE_HIDDEN_WINDOW=1: the window is never shown, though its page still
  // renders and responds. The smoke test drives the real app this way, so
  // running the tests does not flash a window on the desktop.
  const hidden = process.env.WORK_IDE_HIDDEN_WINDOW === '1';
  const window = new BrowserWindow({
    width: 1280,
    height: 900,
    show: !hidden,
    paintWhenInitiallyHidden: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      backgroundThrottling: !hidden,
      // The whole interface 20% larger — text, buttons and spacing alike, so
      // the proportions stay as designed. Read on a laptop screen (the owner,
      // 2026-09-30); it survives Refresh.
      zoomFactor: UI_ZOOM,
    },
  });
  window.removeMenu();
  registerIpc(window);
  window.loadFile(path.join(__dirname, '..', 'renderer', 'index.html'));
  return window;
}

app.whenReady().then(createWindow);
app.on('window-all-closed', () => {
  tasks.stopAll();
  batchWatch.stop();
  store.closeAll();
  data.close();
  app.quit();
});
