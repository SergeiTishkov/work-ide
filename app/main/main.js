'use strict';
// The Electron main process: one window, and the IPC behind window.api
// (main/preload.js). All data access and process control lives here; the
// renderer only asks.
const fs = require('node:fs');
const path = require('node:path');
const { execFile } = require('node:child_process');
const { app, BrowserWindow, clipboard, ipcMain, shell } = require('electron');
const { repoRoot, schemaDir, pythonExecutable } = require('./paths');
const { runCleanup } = require('./cleanup');
const { Store } = require('./store');
const { StoreThread } = require('./store-thread');
const { QueueClient } = require('./queue');
const { WorkerKeeper } = require('./workers');
const { documentsState, resolveRoot, vacancyDir } = require('./documents');
const { listIdentities } = require('./identities');
const { readSourceState, sourceHealth } = require('./source-health');
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

// The task queue (task 0056): tools/taskq.py adds and stops, the workers
// (tools/taskd.py) run, the app reads (queue.js). The tools are always the
// app's own repository's: in the smoke test the data is a fixture's
// (WORK_IDE_ROOT, WORK_IDE_DATA_ROOT), the code is not.
const dataRoot = process.env.WORK_IDE_DATA_ROOT || path.join(root, 'data');
const toolsRoot = path.resolve(__dirname, '..', '..');
const toolsPython = pythonExecutable(toolsRoot);
const toolsEnv = { ...process.env, PYTHONIOENCODING: 'utf-8', WORK_IDE_DATA_ROOT: dataRoot };

function runTaskq(args) {
  return new Promise((resolve, reject) => {
    execFile(toolsPython, [path.join('tools', 'taskq.py'), ...args], {
      cwd: toolsRoot, env: toolsEnv, windowsHide: true, maxBuffer: 4 << 20,
    }, (error, stdout, stderr) => {
      if (error && !String(stdout).trim()) {
        reject(new Error(`tools/taskq.py: ${String(stderr || error.message).trim().split(/\r?\n/).pop()}`));
      } else {
        resolve(stdout);
      }
    });
  });
}

function readBatch() {
  try {
    return JSON.parse(fs.readFileSync(path.join(dataRoot, 'cv_batch.json'), 'utf8'));
  } catch {
    return null;
  }
}

const tasks = new QueueClient({ dataRoot, schemaDir: schemaDir(root), runTaskq, readBatch });
const workers = new WorkerKeeper({
  root: toolsRoot, python: toolsPython, dataRoot,
  live: () => tasks.liveWorkers(),
  pending: () => tasks.list().some((task) => task.state === 'queued'),
  log: (line) => console.log(`workers: ${line}`),
});

// A run that ended may have created the database, recorded a selection or
// changed the base: the connections open again on the next read.
tasks.onEvent((event) => {
  if (event.type === 'finished' && ['collect', 'rest', 'linkedin', 'pipeline', 'clean', 'links', 'ai'].includes(event.task.kind)) {
    store.closeAll();
    data.call('closeAll').catch(() => {});
  }
});

const IDENTITY_PATTERN = /^[a-z][a-z0-9]{2,9}$/;

async function enqueueTask(request) {
  const r = request || {};
  if (['collect', 'rest', 'linkedin'].includes(r.kind)) {
    // the pipeline would skip it too (tools/identity.py skip_if_inactive)
    const entry = identities.find((e) => e.prefix === r.identity);
    if (entry && entry.active === false) throw new Error(`${r.identity} is inactive: it is not collected`);
  }
  if (['cv', 'letter', 'reputation'].includes(r.kind)) vacancyDir('x', r.identity, r.vacancyId);   // validates the id
  const reply = await tasks.enqueue(r);
  workers.check().catch(() => {});
  return reply;
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
    return identities.map(({ prefix, displayName, hasDatabase, active }) => ({ prefix, displayName, hasDatabase, active }));
  });
  handle('set-identity-active', async (identity, active) => {
    if (!IDENTITY_PATTERN.test(String(identity))) throw new Error(`invalid identity: ${identity}`);
    const now = await data.call('setIdentityActive', identity, Boolean(active));
    const entry = identities.find((e) => e.prefix === identity);
    if (entry) entry.active = now;
    return now;
  });
  handle('segments', (identity) => data.call('segments', identity));
  handle('listing', (identity, view, page) => data.call('listing', identity, view || {}, page || {}));
  handle('class-totals', (identity, view) => data.call('classTotals', identity, view || {}));
  handle('counts', (identity, view) => data.call('counts', identity, view || {}));
  handle('sources', (identity, view) => data.call('sources', identity, view || {}));
  handle('companies', (identity, view) => data.call('companies', identity, view || {}));
  handle('ages', (identity, view) => data.call('ages', identity, view || {}));
  handle('roles', (identity, view) => data.call('roles', identity, view || {}));
  handle('source-health', async (identity) => {
    const entry = identities.find((e) => e.prefix === identity);
    if (!entry) throw new Error(`unknown identity: ${identity}`);
    return sourceHealth(readSourceState(entry.dataDir, identity), await data.call('sourceYield', identity));
  });
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
  handle('task-log', (id) => tasks.log(Number(id)));
  handle('enqueue-task', (request) => enqueueTask(request));
  handle('cancel-task', (id) => tasks.cancel(Number(id)));
  handle('cancel-queued', (identity) => tasks.cancelQueued(identity || null));
  handle('clear-tasks', () => tasks.clearFinished());
  handle('schedules', () => tasks.schedules());
  handle('save-schedule', (schedule) => tasks.saveSchedule(schedule));
  handle('enable-schedule', (id, on) => tasks.enableSchedule(id, Boolean(on)));
  handle('remove-schedule', (id) => tasks.removeSchedule(id));
  handle('next-runs', (cron) => tasks.nextRuns(cron));
  handle('documents-state', async (identity, ids) =>
    documentsState(await documentsRoot(), identity, Array.isArray(ids) ? ids.slice(0, 5000) : []));
  handle('open-documents-dir', async (identity, vacancyId) => {
    const dir = vacancyDir(await documentsRoot(), identity, vacancyId);
    if (!fs.existsSync(dir)) throw new Error(`${dir} does not exist`);
    const problem = await shell.openPath(dir);
    if (problem) throw new Error(problem);
  });
  // "Refresh": the page reloads itself; when the main process's own code
  // changed since start, the whole app restarts instead. The tasks run in
  // the queue's workers (task 0056), so a restart cuts nothing off.
  handle('refresh', () => {
    const action = refreshAction({
      startedWith: startedWithCode, now: codeStamp(), agentRunning: false,
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
  // After a copy, when the setting asks for it (task 0070): Windows brings
  // forward the window under the app, where the link is pasted.
  handle('minimize-window', () => window.minimize());
  handle('open-cv-file', async (file) => {
    const problem = await shell.openPath(tasks.checkProduced(file));
    if (problem) throw new Error(problem);
  });
  handle('show-cv-file', (file) => shell.showItemInFolder(tasks.checkProduced(file)));

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

app.whenReady().then(() => {
  tasks.start();
  workers.start();
  createWindow();
});
// Closing the window stops no task: they run in the queue's workers.
app.on('window-all-closed', () => {
  workers.stop();
  tasks.close();
  store.closeAll();
  data.close();
  app.quit();
});
