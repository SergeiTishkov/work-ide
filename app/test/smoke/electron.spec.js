'use strict';
// The real Electron window over a fixture repository: real IPC, real SQLite,
// the agent replaced by a fake command (WORK_IDE_FAKE_RUNNER=1).
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { DatabaseSync } = require('node:sqlite');
const { test, expect, _electron: electron } = require('@playwright/test');
const { check } = require('../helpers/dropdown');
const { SCHEMA_DIR, standardDatabase, tempDir } = require('../helpers/fixture-db');
const en = require('../../renderer/locales/en.js');

function fixtureRepo() {
  const root = tempDir('work-ide-smoke-');
  fs.cpSync(SCHEMA_DIR, path.join(root, 'schemas'), { recursive: true });
  const database = standardDatabase(path.join(root, 'data', 'workide.sqlite'),
    { identity: 'sharp' });
  const identities = path.join(root, 'identities.json');
  fs.writeFileSync(identities, JSON.stringify([
    { prefix: 'sharp', display_name: 'Senior .NET/C# remote engineering', database: 'data/workide.sqlite' },
    { prefix: 'partsharp', display_name: 'Part-time', database: 'data/workide.sqlite' },
  ]));
  return { root, database, identities };
}

// Editors built on Electron (VS Code among them) export ELECTRON_RUN_AS_NODE
// to their child processes; inherited, it would start Electron as plain Node.
function cleanEnv() {
  const env = { ...process.env };
  delete env.ELECTRON_RUN_AS_NODE;
  return env;
}

test('the real window lists, records feedback, and runs the (fake) agent', async () => {
  // A click in the hidden window takes about 2 s (Playwright waits for frames
  // the hidden window seldom draws); the run took 20 s alone and over 30 s
  // beside the UI tests once the filters became clicks (2026-10-06).
  test.setTimeout(60000);
  const repo = fixtureRepo();
  const app = await electron.launch({
    args: [path.join(__dirname, '..', '..')],
    env: {
      ...cleanEnv(),
      WORK_IDE_ROOT: repo.root,
      WORK_IDE_IDENTITIES_JSON: repo.identities,
      WORK_IDE_FAKE_RUNNER: '1',
      WORK_IDE_DOCUMENTS_DIR: path.join(repo.root, 'documents'),
      WORK_IDE_HIDDEN_WINDOW: '1',
      // Its own profile: the real app may be open on the owner's desktop.
      WORK_IDE_USER_DATA: path.join(repo.root, 'electron-profile'),
    },
  });
  try {
    const window = await app.firstWindow();
    await expect(window.getByTestId('identity-tab-sharp')).toBeVisible();
    await expect(window.getByTestId('identity-name')).toHaveText('Test search');
    await expect(window.getByTestId('segment-filter-value')).toHaveText('Everything');   // the market holding everything
    await expect(window.getByTestId('list').locator('article')).toHaveCount(3);   // new0..new2

    await window.getByTestId('vacancy-new0').getByTestId('btn-bugged').click();
    await window.getByTestId('vacancy-new0').getByTestId('reason-input').fill('onsite in fact');
    await window.getByTestId('vacancy-new0').getByTestId('reason-save').click();
    await expect(window.getByTestId('stub-new0')).toBeVisible();
    await expect(window.getByTestId('filter-option-bugged')).toContainText('(1)');

    const db = new DatabaseSync(repo.database);
    const row = db.prepare('SELECT feedback_status, bugged_reason FROM vacancy_identity '
      + "WHERE identity_id = 'sharp' AND vacancy_id = ?").get('new0');
    db.close();
    expect({ ...row }).toEqual({ feedback_status: 'bugged', bugged_reason: 'onsite in fact' });

    await window.getByTestId('menu-button').click();
    await window.getByTestId('run-collect').click();
    await expect(window.getByTestId('task-1')).toHaveAttribute('data-state', 'done', { timeout: 15000 });
    // a collection that ends well queues the rest of the base: the panel
    // goes on to its log, the collection's is a click away
    await expect(window.getByTestId('task-2')).toHaveAttribute('data-state', 'done', { timeout: 15000 });
    await expect(window.getByTestId('task-log')).toContainText('fake rest: sharp');
    await window.getByTestId('task-1').click();
    await expect(window.getByTestId('task-log')).toContainText('fake run: /top sharp');
    await expect(window.getByTestId('task-log-title')).toContainText(en['task.state.done']);
    await expect(window.getByTestId('run-status')).toHaveCount(0);
    expect(fs.readdirSync(path.join(repo.root, 'data', 'identities', 'sharp', 'runs'))).toHaveLength(1);

    // The indicator reads tools/runstate.py's row: a live one (this test's own
    // pid, fresh heartbeat) shows, a finished one clears within a poll.
    const runs = new DatabaseSync(repo.database);
    const now = new Date().toISOString().replace(/\.\d{3}Z$/, '+00:00');
    const { lastInsertRowid } = runs.prepare(
      "INSERT INTO pipeline_runs (identity_id, started_at, heartbeat_at, status, stage, pid, host) "
      + "VALUES ('sharp', ?, ?, 'running', 'check links', ?, ?)").run(now, now, process.pid, os.hostname());
    await expect(window.getByTestId('collect-indicator')).toBeVisible({ timeout: 10000 });
    await expect(window.getByTestId('run-status')).toContainText('check links');
    runs.prepare("UPDATE pipeline_runs SET status = 'finished' WHERE id = ?").run(lastInsertRowid);
    runs.close();
    await expect(window.getByTestId('collect-indicator')).toHaveCount(0, { timeout: 10000 });

    // Refresh through the real IPC: the main process's code has not changed
    // since start, so the page reloads, keeps the view and works. One click:
    // in the hidden window each takes about 2 s, and a row redrawn under it
    // (the check box, then the spinner, then the list) makes Playwright retry.
    await check(window, 'filter', ['fresh', 'earlier', 'new']);
    await window.evaluate(() => { window.__beforeRefresh = true; });
    await window.getByTestId('refresh').click();
    await expect.poll(() => window.evaluate(() => window.__beforeRefresh)).toBeUndefined();
    await expect(window.getByTestId('filter-option-earlier')).toHaveAttribute('data-state', 'on');
    await expect(window.getByTestId('error')).toBeHidden();

    // "Identities" through the real IPC: the switch lands in the base
    await window.getByTestId('menu-button').click();
    await window.getByTestId('open-identities').click();
    await window.getByTestId('identity-active-partsharp').uncheck();
    await expect(window.getByTestId('identity-tab-partsharp')).toHaveClass(/inactive/);
    const flags = new DatabaseSync(repo.database);
    expect(flags.prepare("SELECT active FROM identities WHERE id = 'partsharp'").get().active).toBe(0);
    flags.close();
    await window.getByTestId('identities-close').click();

    await window.getByTestId('identity-tab-partsharp').click();
    await expect(window.getByTestId('never-collected')).toBeVisible();
  } finally {
    await app.close();
  }
});
