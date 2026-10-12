'use strict';
// The Electron main process: one window, and the IPC behind window.api
// (main/preload.js). All data access and process control lives here; the
// renderer only asks.
const path = require('node:path');
const { app, BrowserWindow, clipboard, ipcMain, shell } = require('electron');
const { repoRoot, schemaDir, pythonExecutable } = require('./paths');
const { Store } = require('./store');
const { StoreThread } = require('./store-thread');
const { Runner } = require('./runner');
const { CvGenerator } = require('./cv');
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

// The tailored CV goes to Downloads; WORK_IDE_CV_OUT_DIR points it elsewhere
// in tests.
let cvGenerator = null;
function cv() {
  if (!cvGenerator) {
    cvGenerator = new CvGenerator({
      root, python: pythonExecutable(root),
      outDir: process.env.WORK_IDE_CV_OUT_DIR || app.getPath('downloads'),
    });
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
  handle('set-feedback', (identity, id, status, reason) => data.call('setFeedback', identity, id, status, reason));
  handle('advance', (identity, id, step, comment) => data.call('advance', identity, id, step, comment));
  handle('step-back', (identity, id) => data.call('stepBack', identity, id));
  handle('edit-comment', (identity, id, kind, index, text) =>
    data.call('editComment', identity, id, kind, index, text));
  handle('pending-feedback', (identity) => data.call('pendingFeedback', identity));
  handle('pipeline-status', (identity) => store.pipelineStatus(identity));
  handle('run-state', () => runner.state());
  handle('start-run', ({ identity, kind }) => {
    // The agent may create or rebuild the database; do not hold it open.
    store.closeAll();
    data.call('closeAll').catch(() => {});
    return runner.start(kind, identity);
  });
  handle('stop-run', () => runner.stop());
  // "Refresh": the page reloads itself; when the main process's own code
  // changed since start, the whole app restarts instead — unless an agent run
  // started from here is going, which a restart would cut off.
  handle('refresh', () => {
    const action = refreshAction({
      startedWith: startedWithCode, now: codeStamp(), agentRunning: runner.state().running,
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
  handle('generate-cv', (identity, vacancyId, instructions) => cv().generate(identity, vacancyId, instructions));
  handle('generate-cover-letter', (identity, vacancyId, instructions) =>
    cv().generate(identity, vacancyId, instructions, 'letter'));
  handle('cv-state', () => cv().state());
  handle('open-cv-file', async (file) => {
    const problem = await shell.openPath(cv().checkProduced(file));
    if (problem) throw new Error(problem);
  });
  handle('show-cv-file', (file) => shell.showItemInFolder(cv().checkProduced(file)));

  runner.onEvent((event) => {
    if (event.type === 'exit') {
      store.closeAll();
      data.call('closeAll').catch(() => {});
    }
    if (!window.isDestroyed()) window.webContents.send('run-event', event);
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
  if (runner.state().running) runner.stop();
  store.closeAll();
  data.close();
  app.quit();
});
