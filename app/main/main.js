'use strict';
// The Electron main process: one window, and the IPC behind window.api
// (main/preload.js). All data access and process control lives here; the
// renderer only asks.
const path = require('node:path');
const { app, BrowserWindow, clipboard, ipcMain, shell } = require('electron');
const { repoRoot, schemaDir } = require('./paths');
const { Store } = require('./store');
const { Runner } = require('./runner');
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

const store = new Store({
  schemaDir: schemaDir(root),
  databasePathOf: (prefix) => {
    const entry = identities.find((e) => e.prefix === prefix);
    return entry ? entry.database : null;
  },
});

const fake = process.env.WORK_IDE_FAKE_RUNNER === '1' ? require('./fake-runner') : null;
const runner = new Runner({
  root,
  logDirOf: (prefix) => {
    const entry = identities.find((e) => e.prefix === prefix);
    return path.join(entry ? path.dirname(entry.database) : path.join(root, 'data', prefix), 'runs');
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
  handle('segments', (identity) => store.segments(identity));
  handle('listing', (identity, segment, filter, expanded, source) =>
    store.listing(identity, segment, filter, expanded || [], source || ''));
  handle('class-totals', (identity, segment, filter, source) =>
    store.classTotals(identity, segment, filter, source || ''));
  handle('counts', (identity, segment, source) => store.counts(identity, segment, source || ''));
  handle('sources', (identity, segment, filter) => store.sources(identity, segment, filter));
  handle('set-feedback', (identity, id, status, reason) => store.setFeedback(identity, id, status, reason));
  handle('advance', (identity, id, step, comment) => store.advance(identity, id, step, comment));
  handle('step-back', (identity, id) => store.stepBack(identity, id));
  handle('edit-comment', (identity, id, kind, index, text) =>
    store.editComment(identity, id, kind, index, text));
  handle('pending-feedback', (identity) => store.pendingFeedback(identity));
  handle('pipeline-status', (identity) => store.pipelineStatus(identity));
  handle('run-state', () => runner.state());
  handle('start-run', ({ identity, kind }) => {
    // The agent may create or rebuild the database; do not hold it open.
    store.closeAll();
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

  runner.onEvent((event) => {
    if (event.type === 'exit') store.closeAll();
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
  app.quit();
});
