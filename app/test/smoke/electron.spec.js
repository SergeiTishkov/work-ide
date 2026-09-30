'use strict';
// The real Electron window over a fixture repository: real IPC, real SQLite,
// the agent replaced by a fake command (WORK_IDE_FAKE_RUNNER=1).
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { DatabaseSync } = require('node:sqlite');
const { test, expect, _electron: electron } = require('@playwright/test');
const { SCHEMA_DIR, standardDatabase, tempDir } = require('../helpers/fixture-db');
const ru = require('../../renderer/locales/ru.js');

function fixtureRepo() {
  const root = tempDir('work-ide-smoke-');
  fs.cpSync(SCHEMA_DIR, path.join(root, 'schemas'), { recursive: true });
  const database = standardDatabase(path.join(root, 'data', 'kisel', 'kisel.sqlite'));
  const identities = path.join(root, 'identities.json');
  fs.writeFileSync(identities, JSON.stringify([
    { prefix: 'kisel', display_name: 'Calm legacy work', database: 'data/kisel/kisel.sqlite' },
    { prefix: 'pjoice', display_name: 'Part-time', database: 'data/pjoice/pjoice.sqlite' },
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
  const repo = fixtureRepo();
  const app = await electron.launch({
    args: [path.join(__dirname, '..', '..')],
    env: {
      ...cleanEnv(),
      WORK_IDE_ROOT: repo.root,
      WORK_IDE_IDENTITIES_JSON: repo.identities,
      WORK_IDE_FAKE_RUNNER: '1',
      WORK_IDE_HIDDEN_WINDOW: '1',
      // Its own profile: the real app may be open on the owner's desktop.
      WORK_IDE_USER_DATA: path.join(repo.root, 'electron-profile'),
    },
  });
  try {
    const window = await app.firstWindow();
    await expect(window.getByTestId('identity-tab-kisel')).toBeVisible();
    await expect(window.getByTestId('identity-name')).toHaveText('Test search');
    await expect(window.getByTestId('segment-tab-full')).toHaveAttribute('aria-selected', 'true');
    await expect(window.getByTestId('list').locator('article')).toHaveCount(3);   // new0..new2

    await window.getByTestId('vacancy-new0').getByTestId('btn-bugged').click();
    await window.getByTestId('vacancy-new0').getByTestId('reason-input').fill('onsite in fact');
    await window.getByTestId('vacancy-new0').getByTestId('reason-save').click();
    await expect(window.getByTestId('stub-new0')).toBeVisible();
    await expect(window.getByTestId('filter-count-bugged')).toHaveText('(1)');

    const db = new DatabaseSync(repo.database);
    const row = db.prepare('SELECT feedback_status, bugged_reason FROM vacancies WHERE id = ?').get('new0');
    db.close();
    expect({ ...row }).toEqual({ feedback_status: 'bugged', bugged_reason: 'onsite in fact' });

    await window.getByTestId('run-collect').click();
    await expect(window.getByTestId('run-log')).toContainText('fake run: /run kisel');
    await expect(window.getByTestId('run-status')).toContainText(ru['run.finished']);
    await expect(window.getByTestId('run-collect')).toBeEnabled();
    expect(fs.readdirSync(path.join(repo.root, 'data', 'kisel', 'runs'))).toHaveLength(1);

    // The indicator reads tools/runstate.py's row: a live one (this test's own
    // pid, fresh heartbeat) shows, a finished one clears within a poll.
    const runs = new DatabaseSync(repo.database);
    const now = new Date().toISOString().replace(/\.\d{3}Z$/, '+00:00');
    const { lastInsertRowid } = runs.prepare(
      "INSERT INTO pipeline_runs (started_at, heartbeat_at, status, stage, pid, host) "
      + "VALUES (?, ?, 'running', 'check links', ?, ?)").run(now, now, process.pid, os.hostname());
    await expect(window.getByTestId('collect-indicator')).toBeVisible({ timeout: 10000 });
    await expect(window.getByTestId('run-collect')).toContainText('check links');
    runs.prepare("UPDATE pipeline_runs SET status = 'finished' WHERE id = ?").run(lastInsertRowid);
    runs.close();
    await expect(window.getByTestId('collect-indicator')).toHaveCount(0, { timeout: 10000 });
    await expect(window.getByTestId('run-collect')).toBeEnabled();

    // Refresh through the real IPC: the main process's code has not changed
    // since start, so the page reloads, keeps the view and works.
    await window.getByTestId('filter-all').check();
    await window.evaluate(() => { window.__beforeRefresh = true; });
    await window.getByTestId('refresh').click();
    await expect.poll(() => window.evaluate(() => window.__beforeRefresh)).toBeUndefined();
    await expect(window.getByTestId('filter-all')).toBeChecked();
    await expect(window.getByTestId('error')).toBeHidden();

    await window.getByTestId('identity-tab-pjoice').click();
    await expect(window.getByTestId('never-collected')).toBeVisible();
  } finally {
    await app.close();
  }
});
