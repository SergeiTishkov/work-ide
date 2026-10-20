'use strict';
// The real interface in a headless browser, with window.api mocked: each test
// clicks what a person clicks and checks what the UI asked the rest of the
// world to do. No agent runs, no tokens are spent.
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { test, expect } = require('@playwright/test');
const {
  choose, check, settled, STATUSES, VIEW, BOTH, view,
} = require('../helpers/dropdown');
const { installMockApi, standardFixture, row } = require('./mock-api');
const en = require('../../renderer/locales/en.js');

const PAGE = pathToFileURL(path.join(__dirname, '..', '..', 'renderer', 'index.html')).href;

async function open(page, fixture = standardFixture()) {
  await page.addInitScript(installMockApi, fixture);
  await page.goto(PAGE);
  await expect(page.getByTestId('identity-tab-sharp')).toBeVisible();
}

function calls(page, name) {
  return page.evaluate((n) => window.__calls.filter((c) => c.name === n).map((c) => c.args), name);
}

const byId = (page, id) => page.getByTestId(`vacancy-${id}`);
// An item of the commands menu (renderMenu), the menu opened first when closed.
// A click on an item closes it again.
async function command(page, testid) {
  if (!(await page.getByTestId('menu').isVisible())) await page.getByTestId('menu-button').click();
  return page.getByTestId(testid);
}
const lastListing = async (page) => { await settled(page); return (await calls(page, 'loadListing')).at(-1); };
// "Show" closed: every status and both freshness rows checked; the start
const SHOW_ALL = [en['filter.new'], en['filter.group.applications'], en['filter.group.denied']].join(' · ');
const SHOW_DEFAULT = `${en['filter.fresh']} · ${en['filter.new']}`;

test('opens on the first identity, every market, fresh vacancies not applied or denied', async ({ page }) => {
  await open(page);
  await expect(page.getByTestId('identity-tab-sharp')).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByTestId('segment-filter-value')).toHaveText('Everything');
  await expect(page.getByTestId('filter-value')).toHaveText(SHOW_DEFAULT);
  expect((await calls(page, 'loadListing'))[0]).toEqual(['sharp', VIEW]);
  await expect(page.getByTestId('list').locator('article')).toHaveCount(3);   // a1, a2r, b1
  await expect(byId(page, 'a3')).toHaveCount(0);   // not fresh
  await expect(byId(page, 'x1')).toHaveCount(0);   // has feedback
  await expect(page).toHaveTitle(en['app.title']);
});

test('sections follow the class order, with their titles from the locale', async ({ page }) => {
  await open(page);
  const titles = await page.locator('.class-section h2 .section-title').allTextContents();
  expect(titles).toEqual([en['class.hot_lead'], en['class.worth_a_look']]);
});

test('"Collect vacancies" queues a collection; the bottom panel lists it with its log', async ({ page }) => {
  await open(page);
  await expect(page.getByTestId('task-panel')).toBeHidden();
  await (await command(page, 'run-collect')).click();
  await expect(page.getByTestId('menu')).toHaveCount(0);   // an item closes the menu
  expect(await calls(page, 'enqueueTask')).toEqual([[{ kind: 'collect', identity: 'sharp' }]]);
  await expect(page.getByTestId('menu-button').getByTestId('menu-busy')).toBeVisible();   // seen with the menu closed
  const button = await command(page, 'run-collect');
  await expect(button.getByTestId('collect-indicator')).toBeVisible();
  await expect(button).toBeDisabled();
  await expect(page.getByTestId('run-stop')).toBeVisible();
  await expect(page.getByTestId('task-panel')).toBeVisible();
  await expect(page.getByTestId('task-1')).toHaveAttribute('data-state', 'running');
  await expect(page.getByTestId('task-1')).toContainText(`${en['task.kind.collect']} · sharp`);

  await page.evaluate(() => window.__taskLine('fetching sources'));
  await expect(page.getByTestId('task-log')).toContainText('fetching sources');
  await expect(page.getByTestId('task-log-title')).toContainText(en['task.state.running']);

  await page.evaluate(() => window.__finishCollect({ ok: true, code: 0 }));
  await expect(page.getByTestId('task-1')).toHaveAttribute('data-state', 'done');
  await expect(button).toBeEnabled();   // the menu stays open across the redraws
  await expect(page.getByTestId('collect-indicator')).toHaveCount(0);
  await expect(page.getByTestId('menu-busy')).toHaveCount(0);
  await expect(page.getByTestId('task-log')).toContainText('fetching sources');   // the log stays
  await expect.poll(async () => (await calls(page, 'listIdentities')).length).toBe(2);   // reloaded after the run
});

test('"Stop" and the panel\'s cross cancel a collection', async ({ page }) => {
  await open(page);
  await (await command(page, 'run-collect')).click();
  await (await command(page, 'run-stop')).click();
  expect(await calls(page, 'cancelTask')).toEqual([[1]]);
  await expect(page.getByTestId('task-1')).toHaveAttribute('data-state', 'stopped');
  await command(page, 'run-collect');
  await expect(page.getByTestId('run-stop')).toHaveCount(0);
  await (await command(page, 'run-collect')).click();
  await page.getByTestId('task-2').hover();
  await page.getByTestId('task-2').getByTestId('task-cancel').click();
  await page.getByTestId('stop-yes').click();
  await expect(page.getByTestId('task-2')).toHaveAttribute('data-state', 'stopped');
});

test('the panel\'s cross asks before it stops a task; "Cancel", Escape and a click outside stop nothing', async ({ page }) => {
  await open(page);
  await (await command(page, 'run-collect')).click();
  const cross = async () => {
    await page.getByTestId('task-1').hover();
    await page.getByTestId('task-1').getByTestId('task-cancel').click();
    await expect(page.getByTestId('stop-dialog')).toContainText(en['task.stop_confirm']);
    await expect(page.getByTestId('stop-dialog')).toContainText(`${en['task.kind.collect']} · sharp`);
  };
  await cross();
  await page.getByTestId('stop-no').click();
  await expect(page.getByTestId('stop-dialog')).toHaveCount(0);
  await cross();
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('stop-dialog')).toHaveCount(0);
  await cross();
  await page.getByTestId('stop-overlay').click({ position: { x: 5, y: 5 } });
  await expect(page.getByTestId('stop-dialog')).toHaveCount(0);
  expect(await calls(page, 'cancelTask')).toEqual([]);
  await expect(page.getByTestId('task-1')).toHaveAttribute('data-state', 'running');
  await cross();
  await page.getByTestId('stop-yes').click();
  expect(await calls(page, 'cancelTask')).toEqual([[1]]);
  await expect(page.getByTestId('task-1')).toHaveAttribute('data-state', 'stopped');
});

test('the panel folds into a tab at the bottom edge, opens from it, and stays folded after a restart', async ({ page }) => {
  await open(page);
  await expect(page.getByTestId('task-tab')).toBeHidden();
  await (await command(page, 'run-collect')).click();
  const panel = page.getByTestId('task-panel');
  const tab = page.getByTestId('task-tab');
  await expect(panel).toBeVisible();
  await expect(tab).toBeHidden();
  await page.evaluate(() => window.__taskLine('fetching sources'));
  await page.getByTestId('task-panel-fold').click();
  await expect(panel).toBeHidden();
  await expect(tab).toBeVisible();
  await expect(tab).toContainText(en['task.list_title'].replace('{n}', '1'));
  await expect(tab.locator('.spinner')).toBeVisible();   // something runs
  const box = await tab.boundingBox();
  const height = await page.evaluate(() => window.innerHeight);
  expect(Math.round(box.y + box.height)).toBe(height);   // on the bottom edge
  await expect(tab).toHaveCSS('clip-path', /polygon/);
  // folded, the task runs on: nothing was stopped
  expect(await calls(page, 'cancelTask')).toEqual([]);
  await page.evaluate(() => window.__taskLine('still fetching'));
  await tab.click();
  await expect(panel).toBeVisible();
  await expect(tab).toBeHidden();
  await expect(page.getByTestId('task-log')).toContainText('fetching sources\nstill fetching');

  await page.getByTestId('task-panel-fold').click();
  await page.reload();
  await (await command(page, 'run-collect')).click();
  await expect(tab).toBeVisible();
  await expect(panel).toBeHidden();
  await tab.click();
  await page.reload();
  await (await command(page, 'run-collect')).click();
  await expect(panel).toBeVisible();
});

test('"Settings…" hides the task list: no panel and no tab, the tasks run on; kept after a restart', async ({ page }) => {
  await open(page);
  await (await command(page, 'run-collect')).click();
  await expect(page.getByTestId('task-panel')).toBeVisible();
  await (await command(page, 'open-settings')).click();
  const show = page.getByTestId('setting-show-tasks');
  await expect(page.getByTestId('settings-dialog')).toContainText(en['settings.show_tasks']);
  await expect(show).toBeChecked();
  await show.uncheck();
  await expect(page.getByTestId('task-panel')).toBeHidden();
  await expect(page.getByTestId('task-tab')).toBeHidden();
  await page.getByTestId('settings-close').click();
  await expect(page.getByTestId('settings-dialog')).toHaveCount(0);
  expect(await calls(page, 'cancelTask')).toEqual([]);
  await expect(page.getByTestId('run-collect')).toHaveCount(0);
  await expect(page.getByTestId('menu-button').getByTestId('menu-busy')).toBeVisible();   // it runs on

  await page.reload();
  await (await command(page, 'run-collect')).click();
  await expect(page.getByTestId('menu-button').getByTestId('menu-busy')).toBeVisible();
  await expect(page.getByTestId('task-panel')).toBeHidden();
  await (await command(page, 'open-settings')).click();
  await expect(page.getByTestId('setting-show-tasks')).not.toBeChecked();
  await page.getByTestId('setting-show-tasks').check();
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('settings-dialog')).toHaveCount(0);
  await expect(page.getByTestId('task-panel')).toBeVisible();
});

test('collections of several identities queue: the first runs, the others wait their turn', async ({ page }) => {
  await open(page);
  await (await command(page, 'run-collect')).click();
  await page.getByTestId('identity-tab-partsharp').click();
  await expect(page.getByTestId('identity-name')).toHaveText('Part-time side work');
  const button = await command(page, 'run-collect');
  await expect(button).toBeEnabled();
  await button.click();
  await command(page, 'run-collect');
  await expect(button).toHaveText(en['run.queued']);
  await expect(button).toBeDisabled();
  await expect(page.getByTestId('task-2')).toHaveAttribute('data-state', 'queued');
  await expect(page.getByTestId('task-list-title')).toContainText(en['task.list_title'].replace('{n}', '2'));

  await page.evaluate(() => window.__finishCollect({ ok: true, code: 0 }));
  await expect(page.getByTestId('task-2')).toHaveAttribute('data-state', 'running');
  await expect(page.getByTestId('run-stop')).toBeVisible();
  await page.keyboard.press('Escape');
  // the running one is the one whose log shows, until a click chooses another
  await expect(page.getByTestId('task-2')).toHaveClass(/chosen/);
  await page.getByTestId('task-1').click();
  await expect(page.getByTestId('task-1')).toHaveClass(/chosen/);
  await expect(page.getByTestId('task-log-title')).toContainText(en['task.state.done']);
});

// The owner, 2026-10-07: the review is started from an agent session, where
// the person follows and steers it; the button only says so.
test('"Review feedback" shows the pending count and starts nothing', async ({ page }) => {
  await open(page);
  const label = await command(page, 'run-feedback');
  await expect(label).toHaveText(en['run.feedback'].replace('{n}', '1'));
  await expect(page.getByTestId('menu').locator('[aria-disabled="true"]')).toContainText(en['run.feedback'].replace('{n}', '1'));
  // the item says how the review starts, with the menu open
  await expect(page.getByTestId('run-feedback-tip')).toHaveText(en['run.feedback_hint'].replace('{identity}', 'sharp'));
  await label.click();
  await expect(page.getByTestId('menu')).toBeVisible();   // nothing to choose: the menu stays
  expect(await calls(page, 'startRun')).toEqual([]);
  expect(await calls(page, 'enqueueTask')).toEqual([]);
});

test('"Review feedback" names the identity of the open tab', async ({ page }) => {
  await open(page);
  await page.getByTestId('identity-tab-partsharp').click();
  await expect(await command(page, 'run-feedback')).toHaveText(en['run.feedback'].replace('{n}', '0'));
  await expect(page.getByTestId('run-feedback-tip'))
    .toHaveText(en['run.feedback_hint'].replace('{identity}', 'partsharp'));
});

test('"Wrong pick" asks for a reason, saves it, and leaves an undoable stub', async ({ page }) => {
  await open(page);
  const row = byId(page, 'a1');
  await row.getByTestId('btn-bugged').click();
  expect(await calls(page, 'setFeedback')).toEqual([]);   // nothing saved before "Save"
  await expect(row.getByTestId('reason-input')).toHaveAttribute('placeholder', en['reason.bugged']);
  await row.getByTestId('reason-input').fill('A Java role, .NET only in the company blurb');
  await row.getByTestId('reason-save').click();

  expect(await calls(page, 'setFeedback')).toEqual([
    ['sharp', 'a1', 'bugged', 'A Java role, .NET only in the company blurb']]);
  await expect(byId(page, 'a1')).toHaveCount(0);
  const stub = page.getByTestId('stub-a1');
  await expect(stub).toContainText(en['stub.marked'].replace('{status}', en['status.bugged']));
  await expect(await command(page, 'run-feedback')).toHaveText(en['run.feedback'].replace('{n}', '2'));

  await stub.getByTestId('btn-undo').click();
  expect((await calls(page, 'stepBack')).at(-1)).toEqual(['sharp', 'a1']);
  await expect(byId(page, 'a1')).toBeVisible();
  await expect(page.getByTestId('stub-a1')).toHaveCount(0);
});

test('"Not for me" with an empty reason is saved without one', async ({ page }) => {
  await open(page);
  await byId(page, 'a2r').getByTestId('btn-rejected').click();
  await byId(page, 'a2r').getByTestId('reason-save').click();
  expect(await calls(page, 'setFeedback')).toEqual([['sharp', 'a2r', 'rejected', '']]);
});

test('a double click on "Not for me" or "Wrong pick" saves without "Save"', async ({ page }) => {
  await open(page);
  await byId(page, 'a2r').getByTestId('btn-rejected').dblclick();
  expect(await calls(page, 'setFeedback')).toEqual([['sharp', 'a2r', 'rejected', '']]);
  await byId(page, 'a1').getByTestId('btn-bugged').dblclick();
  expect((await calls(page, 'setFeedback')).at(-1)).toEqual(['sharp', 'a1', 'bugged', '']);
});

test('two slow clicks only open the reason, and a typed reason survives', async ({ page }) => {
  await open(page);
  const row = byId(page, 'a1');
  await row.getByTestId('btn-rejected').click();
  await row.getByTestId('reason-input').fill('Too far');
  await page.waitForTimeout(600);
  await row.getByTestId('btn-rejected').click();
  expect(await calls(page, 'setFeedback')).toEqual([]);
  await expect(row.getByTestId('reason-input')).toHaveValue('Too far');
});

test('cancelling the reason form saves nothing', async ({ page }) => {
  await open(page);
  await byId(page, 'a1').getByTestId('btn-rejected').click();
  await byId(page, 'a1').getByTestId('reason-cancel').click();
  await expect(byId(page, 'a1').getByTestId('reason-form')).toHaveCount(0);
  expect(await calls(page, 'setFeedback')).toEqual([]);
});

test('"Applied" is recorded at once, with no reason form', async ({ page }) => {
  await open(page);
  await byId(page, 'a1').getByTestId('btn-applied').click();
  expect(await calls(page, 'setFeedback')).toEqual([['sharp', 'a1', 'applied', null]]);
  await expect(page.getByTestId('reason-form')).toHaveCount(0);
  await expect(page.getByTestId('stub-a1')).toBeVisible();
});

test('an answer and its undo change the card at once, before the list loads again', async ({ page }) => {
  await open(page);
  // the reload after the click is held: what changes, changes without it
  await page.evaluate(() => window.__holdListing());
  await byId(page, 'a1').getByTestId('btn-applied').click();
  await expect(page.getByTestId('stub-a1')).toBeVisible();
  await expect(byId(page, 'a2r')).toBeVisible();
  await page.evaluate(() => window.__releaseListing());
  await expect(page.getByTestId('stub-a1')).toBeVisible();

  await page.evaluate(() => window.__holdListing());
  await page.getByTestId('stub-a1').getByTestId('btn-undo').click();
  await expect(page.getByTestId('stub-a1')).toHaveCount(0);
  await expect(byId(page, 'a1').getByTestId('btn-applied')).toBeVisible();
  await page.evaluate(() => window.__releaseListing());
  await expect(byId(page, 'a1')).toBeVisible();
  expect((await calls(page, 'stepBack')).at(-1)).toEqual(['sharp', 'a1']);
});

test('"Show" counts the statuses under the freshness chosen, the freshness under the statuses', async ({ page }) => {
  await open(page);
  await expect(page.getByTestId('filter-option-new')).toContainText('(3)');   // a1, a2r, b1
  await expect(page.getByTestId('filter-option-bugged')).toContainText('(1)');   // x1
  await expect(page.getByTestId('filter-master-denied')).toContainText('(1)');
  await expect(page.getByTestId('filter-option-earlier')).toContainText('(1)');   // a3
  await expect(page.getByTestId('filter-master-fresh')).toContainText('(4)');
  await choose(page, 'filter', 'bugged');
  expect(await lastListing(page)).toEqual(['sharp', view({ statuses: ['bugged'], fresh: BOTH })]);
  await expect(byId(page, 'x1')).toBeVisible();
  await expect(byId(page, 'x1').getByTestId('status-badge')).toHaveText(en['status.bugged']);

  await byId(page, 'x1').getByTestId('btn-undo').click();
  expect((await calls(page, 'stepBack')).at(-1)).toEqual(['sharp', 'x1']);
});

test('each identity keeps its own view', async ({ page }) => {
  await open(page);
  await choose(page, 'filter', 'all');
  await choose(page, 'segment-filter', 'uk');
  expect(await lastListing(page)).toEqual(['sharp', view({ segments: ['uk'], statuses: STATUSES, fresh: BOTH })]);
  await expect(page.getByTestId('segment-filter-value')).toHaveText('United Kingdom');

  await page.getByTestId('identity-tab-partsharp').click();
  await expect(page.getByTestId('filter-value')).toHaveText(SHOW_DEFAULT);
  await expect(page.getByTestId('segment-filter-value')).toHaveText('Everything');   // its one market
  await choose(page, 'filter', 'applied');

  await page.getByTestId('identity-tab-sharp').click();
  await expect(page.getByTestId('segment-filter-value')).toHaveText('United Kingdom');
  await expect(page.getByTestId('filter-value')).toHaveText(SHOW_ALL);
  await page.getByTestId('identity-tab-partsharp').click();
  await expect(page.getByTestId('filter-value')).toHaveText(en['filter.applied']);
});

// The owner, 2026-10-07: check boxes in the four drop-downs.
test('a check list takes several rows; its master row is on, partly on or off', async ({ page }) => {
  await open(page);
  await page.getByTestId('segment-filter').click();
  const master = page.getByTestId('segment-option-all');
  await expect(master).toHaveText('Everything');
  await expect(master).toHaveAttribute('data-state', 'on');
  await page.getByTestId('segment-option-uk').click();
  await expect(master).toHaveAttribute('data-state', 'partial');
  await expect(page.getByTestId('segment-filter-menu')).toBeVisible();   // open for the next click
  expect(await lastListing(page)).toEqual(['sharp', view({ segments: ['worldwide'] })]);
  await expect(page.getByTestId('segment-filter-value')).toHaveText('Worldwide');

  await master.click();   // partly on: on
  await expect(master).toHaveAttribute('data-state', 'on');
  expect(await lastListing(page)).toEqual(['sharp', VIEW]);
  await master.click();   // on: off
  await expect(master).toHaveAttribute('data-state', 'off');
  expect(await lastListing(page)).toEqual(['sharp', view({ segments: [] })]);
  await expect(page.getByTestId('segment-filter-value')).toHaveText(en['filter.none']);
  await expect(page.getByTestId('list-empty')).toBeVisible();
  await master.click();   // off: on
  await expect(master).toHaveAttribute('data-state', 'on');

  await page.getByTestId('segment-option-uk').click();
  await expect(master).toHaveAttribute('data-state', 'partial');
  await page.getByTestId('segment-option-worldwide').click();
  await expect(master).toHaveAttribute('data-state', 'off');
  await page.getByTestId('segment-option-uk').click();
  await expect(master).toHaveAttribute('data-state', 'partial');
  await page.getByTestId('segment-option-worldwide').click();
  await expect(master).toHaveAttribute('data-state', 'on');
  expect(await lastListing(page)).toEqual(['sharp', VIEW]);   // every market: also one a later run adds
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('segment-filter-menu')).toBeHidden();
});

test('"Show": freshness, not applied or denied, applications, denied; "All" checks a group', async ({ page }) => {
  await open(page);
  await page.getByTestId('filter').click();
  const menu = page.getByTestId('filter-menu');
  await expect(menu.locator('.dropdown-group-label'))
    .toHaveText([en['filter.group.freshness'], en['filter.group.applications'], en['filter.group.denied']]);
  const groups = await menu.locator('[role="group"]').evaluateAll((nodes) => nodes.map((group) => [
    ...group.querySelectorAll('[role="option"]')].map((o) => o.dataset.value || o.dataset.testid)));
  expect(groups).toEqual([
    ['filter-master-fresh', 'fresh', 'earlier'],
    ['new'],
    ['filter-master-applications', 'applied', 'contacted', 'interview', 'awaiting_final', 'awaiting_offer',
      'offered', 'started', 'declined'],
    ['filter-master-denied', 'rejected', 'bugged', 'expired'],
  ]);
  await expect(page.getByTestId('filter-master-fresh')).toHaveAttribute('data-state', 'partial');
  await expect(page.getByTestId('filter-master-denied')).toHaveText(`${en['filter.all']} (1)`);

  await page.getByTestId('filter-master-denied').click();
  await expect(page.getByTestId('filter-option-bugged')).toHaveAttribute('data-state', 'on');
  expect(await lastListing(page)).toEqual(['sharp', view({ statuses: ['new', 'rejected', 'bugged', 'expired'] })]);
  await expect(byId(page, 'x1')).toBeVisible();
  await expect(page.getByTestId('filter-value'))
    .toHaveText(`${en['filter.fresh']} · ${en['filter.new']} · ${en['filter.group.denied']}`);

  await page.getByTestId('filter-option-new').click();
  await expect(page.getByTestId('filter-option-new')).toHaveAttribute('data-state', 'off');
  await page.getByTestId('filter-option-expired').click();
  await expect(page.getByTestId('filter-master-denied')).toHaveAttribute('data-state', 'partial');
  await expect(page.getByTestId('filter-value'))
    .toHaveText([en['filter.fresh'], en['filter.rejected'], en['filter.bugged']].join(' · '));
  await page.getByTestId('filter-master-fresh').click();   // partly on: on
  await expect(page.getByTestId('filter-master-fresh')).toHaveAttribute('data-state', 'on');
  expect(await lastListing(page)).toEqual(['sharp', view({ statuses: ['rejected', 'bugged'], fresh: BOTH })]);
  await page.getByTestId('filter-master-fresh').click();   // on: off
  await expect(page.getByTestId('filter-value')).toHaveText(en['filter.none']);
  await expect(page.getByTestId('list-empty')).toBeVisible();
});

test('the keyboard: Enter or Space checks the row under the cursor and keeps the list open', async ({ page }) => {
  await open(page);
  await page.getByTestId('fit-filter').focus();
  await page.keyboard.press('ArrowDown');
  await expect(page.getByTestId('fit-filter-menu')).toBeVisible();
  await expect(page.getByTestId('fit-option-all')).toHaveClass(/cursor/);
  await page.keyboard.press('ArrowDown');   // the master row, then "Hot leads"
  await page.keyboard.press('Enter');
  await expect(page.getByTestId('fit-option-hot_lead')).toHaveAttribute('data-state', 'off');
  expect(await lastListing(page)).toEqual(['sharp', view({ fits: ['worth_a_look', 'long_shot', 'remote_unconfirmed'] })]);
  await expect(page.getByTestId('fit-filter-menu')).toBeVisible();
  await expect(page.getByTestId('fit-option-hot_lead')).toHaveClass(/cursor/);
  await page.keyboard.press(' ');
  await expect(page.getByTestId('fit-option-hot_lead')).toHaveAttribute('data-state', 'on');
  expect(await lastListing(page)).toEqual(['sharp', VIEW]);
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('fit-filter-menu')).toBeHidden();
});

test('marked vacancies keep their places, whatever order they are marked in', async ({ page }) => {
  const order = () => page.getByTestId('section-hot_lead').locator('article, .stub')
    .evaluateAll((nodes) => nodes.map((n) => n.dataset.testid));
  await open(page);
  expect(await order()).toEqual(['vacancy-a1', 'vacancy-a2r']);
  await byId(page, 'a1').getByTestId('btn-applied').click();
  await expect(page.getByTestId('stub-a1')).toBeVisible();
  await byId(page, 'a2r').getByTestId('btn-expired').click();
  await expect(page.getByTestId('stub-a2r')).toBeVisible();
  expect(await order()).toEqual(['stub-a1', 'stub-a2r']);

  await page.getByTestId('stub-a1').getByTestId('btn-undo').click();
  await page.getByTestId('stub-a2r').getByTestId('btn-undo').click();
  await byId(page, 'a2r').getByTestId('btn-expired').click();
  await expect(page.getByTestId('stub-a2r')).toBeVisible();
  await byId(page, 'a1').getByTestId('btn-applied').click();
  await expect(page.getByTestId('stub-a1')).toBeVisible();
  expect(await order()).toEqual(['stub-a1', 'stub-a2r']);
});

test('a stub drains for 30 seconds, counts down on hover, then goes', async ({ page }) => {
  await page.clock.install();
  await open(page);
  await byId(page, 'a1').getByTestId('btn-applied').click();
  const stub = page.getByTestId('stub-a1');
  await expect(stub).toBeVisible();
  const tip = stub.getByTestId('stub-timer-tip');
  await expect(tip).toBeHidden();
  await stub.getByTestId('stub-timer').hover();
  await expect(tip).toBeVisible();
  await expect(tip).toHaveText(en['stub.removed_in'].replace('{n}', '30'));
  await page.clock.runFor(10000);
  await expect(tip).toHaveText(en['stub.removed_in'].replace('{n}', '20'));
  await page.clock.runFor(20000);
  await expect(stub).toHaveCount(0);
});

test('"Hide" removes a stub at once and keeps the answer', async ({ page }) => {
  await page.clock.install();
  await open(page);
  await byId(page, 'a1').getByTestId('btn-applied').click();
  const stub = page.getByTestId('stub-a1');
  await expect(stub).toBeVisible();
  await stub.getByTestId('btn-hide').click();
  await expect(stub).toHaveCount(0);
  await expect(byId(page, 'a1')).toHaveCount(0);
});

test('a stub that goes lets the ones below keep their order', async ({ page }) => {
  await page.clock.install();
  const order = () => page.getByTestId('section-hot_lead').locator('article, .stub')
    .evaluateAll((nodes) => nodes.map((n) => n.dataset.testid));
  await open(page);
  await byId(page, 'a1').getByTestId('btn-applied').click();
  await expect(page.getByTestId('stub-a1')).toBeVisible();
  await page.clock.runFor(15000);
  await byId(page, 'a2r').getByTestId('btn-expired').click();
  await expect(page.getByTestId('stub-a2r')).toBeVisible();
  await page.clock.runFor(15000);
  await expect(page.getByTestId('stub-a1')).toHaveCount(0);
  expect(await order()).toEqual(['stub-a2r']);
  await page.clock.runFor(15000);
  await expect(page.getByTestId('stub-a2r')).toHaveCount(0);
});

test('an undone stub is not removed again by its timer', async ({ page }) => {
  await page.clock.install();
  await open(page);
  await byId(page, 'a1').getByTestId('btn-applied').click();
  await page.getByTestId('stub-a1').getByTestId('btn-undo').click();
  await expect(byId(page, 'a1')).toBeVisible();
  await byId(page, 'a1').getByTestId('btn-applied').click();
  await page.clock.runFor(29000);
  await expect(page.getByTestId('stub-a1')).toBeVisible();
});

test('in "All", a vacancy turned down folds into a stub and goes; an applied one stays', async ({ page }) => {
  await page.clock.install();
  await open(page);
  await choose(page, 'filter', 'all');
  await byId(page, 'a1').getByTestId('btn-expired').click();
  await expect(page.getByTestId('stub-a1')).toBeVisible();
  await expect(byId(page, 'a1')).toHaveCount(0);
  await byId(page, 'a2r').getByTestId('btn-rejected').dblclick();
  await expect(page.getByTestId('stub-a2r')).toBeVisible();
  await byId(page, 'a3').getByTestId('btn-applied').click();
  await expect(byId(page, 'a3').getByTestId('status-badge')).toBeVisible();
  await expect(page.getByTestId('stub-a3')).toHaveCount(0);
  await page.clock.runFor(30000);
  await expect(page.getByTestId('stub-a1')).toHaveCount(0);
  await expect(page.getByTestId('stub-a2r')).toHaveCount(0);
  await expect(byId(page, 'a1')).toHaveCount(0);
  await expect(byId(page, 'a2r')).toHaveCount(0);
  await expect(byId(page, 'a3')).toBeVisible();
});

test('changing the filter clears stubs', async ({ page }) => {
  await open(page);
  await byId(page, 'a1').getByTestId('btn-applied').click();
  await expect(page.getByTestId('stub-a1')).toBeVisible();
  await choose(page, 'filter', 'all');
  await expect(page.getByTestId('stub-a1')).toHaveCount(0);
  await expect(byId(page, 'a1').getByTestId('status-badge')).toHaveText(en['status.applied']);
});

test('an identity never collected says so and offers to collect', async ({ page }) => {
  await open(page);
  await page.getByTestId('identity-tab-newbie').click();
  await expect(page.getByTestId('never-collected')).toHaveText(en['identity.never_collected']);
  await (await command(page, 'run-collect')).click();
  expect(await calls(page, 'enqueueTask')).toEqual([[{ kind: 'collect', identity: 'newbie' }]]);
});

test('"Copy URL" beside "Open" copies the link and says so', async ({ page }) => {
  await open(page);
  const row = byId(page, 'a1');
  const buttons = row.locator('.answers button');
  await expect(buttons.nth(0)).toHaveAttribute('data-testid', 'btn-open');
  await expect(buttons.nth(1)).toHaveAttribute('data-testid', 'btn-copy-url');
  await row.getByTestId('btn-copy-url').click();
  expect(await calls(page, 'copyText')).toEqual([['https://example.test/a1']]);
  expect(await calls(page, 'openExternal')).toEqual([]);
  await expect(row.getByTestId('btn-copy-url')).toHaveText(en['action.copied']);
  await expect(row.getByTestId('btn-copy-url')).toHaveText(en['action.copy_url']);
});

test('a vacancy title opens in the browser, not in the app', async ({ page }) => {
  await open(page);
  await byId(page, 'a1').getByTestId('title').click();
  expect(await calls(page, 'openExternal')).toEqual([['https://example.test/a1']]);
});

test('badges: fresh and needs a manual check', async ({ page }) => {
  await open(page);
  await expect(byId(page, 'a2r').getByTestId('badge-review')).toHaveText(en['badge.manual_review']);
  await expect(byId(page, 'a1').getByTestId('badge-fresh')).toHaveText(en['badge.fresh']);
  await expect(byId(page, 'a1').getByTestId('badge-review')).toHaveCount(0);
});

test('a role off the stack the model let through is marked, with its reason on hover', async ({ page }) => {
  await open(page);
  const stretch = byId(page, 'b1').getByTestId('badge-stretch');
  await expect(stretch).toHaveText(en['badge.stretch']);
  await expect(stretch).toHaveAttribute('title', 'RAG on model APIs; the backend carries');
  await expect(byId(page, 'a2r').getByTestId('badge-stretch')).toHaveText(en['badge.off_stack']);
  await expect(byId(page, 'a1').getByTestId('badge-stretch')).toHaveCount(0);
});

test('a missing claude is explained', async ({ page }) => {
  const fixture = standardFixture();
  fixture.collectReply = { ok: false, error: 'claude_not_found' };
  await open(page, fixture);
  await (await command(page, 'run-collect')).click();
  await expect(page.getByTestId('error')).toContainText(en['run.claude_not_found']);
  await expect(await command(page, 'run-collect')).toBeEnabled();
  await expect(page.getByTestId('task-1')).toHaveAttribute('data-state', 'failed');
});

test('data text is shown as text, never as markup', async ({ page }) => {
  const fixture = standardFixture();
  fixture.rows.sharp.full[0].view.highlights = ['<img src=x onerror="window.__xss=1"> _fine_'];
  await open(page, fixture);
  await expect(byId(page, 'a1').locator('.highlights em')).toHaveText('fine');
  expect(await page.evaluate(() => window.__xss)).toBeUndefined();
});

test('every row shows when it was posted and when we first downloaded it', async ({ page }) => {
  await open(page);
  const row = byId(page, 'a1');
  await expect(row.getByTestId('posted-on')).toHaveText(en['row.posted_on'].replace('{date}', '20 Sep 2026'));
  await expect(row.getByTestId('first-seen-on'))
    .toHaveText(en['row.first_seen_on'].replace('{date}', '28 Sep 2026'));
  await expect(byId(page, 'a2r').getByTestId('posted-on'))
    .toHaveText(en['row.posted_on'].replace('{date}', en['row.date_unknown']));
});

test('"Open the vacancy link" hands the URL to the system browser, marked or not', async ({ page }) => {
  await open(page);
  const button = byId(page, 'a1').getByTestId('btn-open');
  await expect(button).toHaveText(en['action.open']);
  await button.click();
  expect(await calls(page, 'openExternal')).toEqual([['https://example.test/a1']]);
  expect(await calls(page, 'setFeedback')).toEqual([]);   // opening is not an answer

  await choose(page, 'filter', 'bugged');
  await byId(page, 'x1').getByTestId('btn-open').click();
  expect((await calls(page, 'openExternal')).at(-1)).toEqual(['https://example.test/x1']);
});

test('a pipeline run going anywhere spins the menu button, shows in the menu and on the tab, then clears', async ({ page }) => {
  await open(page);
  await page.evaluate(() => window.__setPipeline('sharp',
    { running: true, stage: 'check links', startedAt: '2026-09-30T00:23:41+00:00' }));
  const menuButton = page.getByTestId('menu-button');
  await expect(menuButton.getByTestId('menu-busy')).toBeVisible();
  await expect(menuButton).toHaveAttribute('title',
    `${en['run.collecting_stage'].replace('{stage}', 'check links')} · sharp`);
  const button = await command(page, 'run-collect');
  await expect(button).toContainText(en['run.collecting_stage'].replace('{stage}', 'check links'));
  await expect(button.getByTestId('collect-indicator')).toBeVisible();
  await expect(button).toBeDisabled();
  await expect(page.getByTestId('run-stop')).toHaveCount(0);   // started elsewhere: shown, not stopped here
  await expect(page.getByTestId('identity-tab-sharp').getByTestId('tab-collecting')).toBeVisible();
  await expect(page.getByTestId('identity-tab-partsharp').getByTestId('tab-collecting')).toHaveCount(0);

  const loadsBefore = (await calls(page, 'loadSegments')).length;
  await page.evaluate(() => window.__setPipeline('sharp', { running: false }));
  await expect(button).toHaveText(en['run.collect']);
  await expect(button).toBeEnabled();
  await expect(page.getByTestId('menu-busy')).toHaveCount(0);
  await expect(page.getByTestId('tab-collecting')).toHaveCount(0);
  await expect.poll(async () => (await calls(page, 'loadSegments')).length).toBeGreaterThan(loadsBefore);
});

test('a reason being typed survives the indicator re-rendering the list', async ({ page }) => {
  await open(page);
  await byId(page, 'a1').getByTestId('btn-bugged').click();
  await byId(page, 'a1').getByTestId('reason-input').fill('half typed');
  await page.evaluate(() => window.__setPipeline('sharp', { running: true, stage: 'rescore' }));
  await expect(page.getByTestId('menu-busy')).toBeVisible();
  await expect(byId(page, 'a1').getByTestId('reason-input')).toHaveValue('half typed');
});

test('"Refresh" reloads the interface and keeps the tab and the view', async ({ page }) => {
  await open(page);
  await page.getByTestId('identity-tab-sharp').click();
  await choose(page, 'segment-filter', 'uk');
  await choose(page, 'filter', 'all');
  await expect(page.getByTestId('refresh')).toHaveAttribute('aria-label', en['app.refresh']);
  await page.evaluate(() => { window.__beforeRefresh = true; });

  await page.getByTestId('refresh').click();
  await expect(page.getByTestId('segment-filter-value')).toHaveText('United Kingdom');
  expect(await page.evaluate(() => window.__beforeRefresh)).toBeUndefined();   // a new page
  await expect(page.getByTestId('filter-value')).toHaveText(SHOW_ALL);
  expect((await calls(page, 'loadListing'))[0])
    .toEqual(['sharp', view({ segments: ['uk'], statuses: STATUSES, fresh: BOTH })]);
});

// n fresh hot leads h00..h<n-1>, best first, and the worth-a-look b1
function manyHotLeads(n) {
  const fixture = standardFixture();
  fixture.limit = 15;   // section_limit
  fixture.rows.sharp.full = [
    ...Array.from({ length: n }, (_, i) => row(`h${String(i).padStart(2, '0')}`, { score: 99 - i })),
    row('b1', { cls: 'worth_a_look', score: 45, source: 'devitjobs' }),
  ];
  return fixture;
}

const fill = (text, values) => Object.entries(values)
  .reduce((s, [k, v]) => s.split(`{${k}}`).join(String(v)), text);

test('an answer and its undo change the class count at once, and the list that catches up agrees', async ({ page }) => {
  await open(page, manyHotLeads(30));
  const count = page.getByTestId('section-count-hot_lead');
  const shownOf = (total) => fill(en['list.shown_of'],
    { shown: 15, total, n: 10, button: en['list.show_more'].replace('{n}', '10') });
  await expect(count).toHaveText(shownOf(30));

  await page.evaluate(() => window.__holdListing());
  await byId(page, 'h00').getByTestId('btn-applied').click();
  await expect(page.getByTestId('stub-h00')).toBeVisible();
  await expect(count).toHaveText(shownOf(29));
  await page.evaluate(() => window.__releaseListing());
  await expect(byId(page, 'h15')).toBeVisible();   // the next one moved up
  await expect(count).toHaveText(shownOf(29));

  await page.evaluate(() => window.__holdListing());
  await page.getByTestId('stub-h00').getByTestId('btn-undo').click();
  await expect(byId(page, 'h00')).toBeVisible();
  await expect(byId(page, 'h15')).toHaveCount(0);
  await expect(count).toHaveText(shownOf(30));
  await page.evaluate(() => window.__releaseListing());
  await expect(count).toHaveText(shownOf(30));
  await expect(page.getByTestId('section-hot_lead').locator('article')).toHaveCount(15);
});

test('in a class shown whole, an answer takes one off its count at once', async ({ page }) => {
  await open(page);
  const count = page.getByTestId('section-count-hot_lead');
  await expect(count).toHaveText(en['list.shown_all'].replace('{n}', '2'));   // a1, a2r
  await page.evaluate(() => window.__holdListing());
  await byId(page, 'a1').getByTestId('btn-applied').click();
  await expect(count).toHaveText(en['list.shown_all'].replace('{n}', '1'));
  await page.evaluate(() => window.__releaseListing());
  await expect(count).toHaveText(en['list.shown_all'].replace('{n}', '1'));
});

test('"Not applied or denied" from every run lists every unanswered vacancy, fresh or not', async ({ page }) => {
  await open(page);
  await expect(page.getByTestId('filter-option-new')).toHaveText(`${en['filter.new']} (3)`);   // fresh ones
  await check(page, 'filter', ['fresh', 'earlier', 'new']);
  expect(await lastListing(page)).toEqual(['sharp', view({ fresh: BOTH })]);
  await expect(page.getByTestId('filter-option-new')).toHaveText(`${en['filter.new']} (4)`);   // a1, a2r, a3, b1
  await expect(page.getByTestId('filter-value')).toHaveText(en['filter.new']);
  await expect(page.getByTestId('list').locator('article')).toHaveCount(4);
  await expect(byId(page, 'a3')).toBeVisible();   // not fresh
  await expect(byId(page, 'x1')).toHaveCount(0);   // has feedback
});

test('a capped class says how much is shown and brings ten more at a time', async ({ page }) => {
  await open(page, manyHotLeads(30));
  const section = page.getByTestId('section-hot_lead');
  const count = page.getByTestId('section-count-hot_lead');
  const more = en['list.show_more'].replace('{n}', '10');
  await expect(count).toHaveText(fill(en['list.shown_of'], { shown: 15, total: 30, n: 10, button: more }));
  await expect(page.getByTestId('show-more-hot_lead')).toHaveText(more);
  await expect(section.locator('article')).toHaveCount(15);
  await expect(page.getByTestId('scroll-more-hot_lead')).toHaveCount(0);   // every class: buttons only

  await page.getByTestId('show-more-hot_lead').click();
  expect(await lastListing(page)).toEqual(['sharp', VIEW, { shown: { hot_lead: 25 } }]);
  await expect(section.locator('article')).toHaveCount(25);
  const five = en['list.show_more'].replace('{n}', '5');
  await expect(count).toHaveText(fill(en['list.shown_of'], { shown: 25, total: 30, n: 5, button: five }));

  await page.getByTestId('show-more-hot_lead').click();
  await expect(section.locator('article')).toHaveCount(30);
  await expect(count).toHaveText(fill(en['list.shown_all'], { n: 30 }));
  await expect(page.getByTestId('show-more-hot_lead')).toHaveCount(0);

  await page.getByTestId('show-less-hot_lead').click();
  await expect(section.locator('article')).toHaveCount(15);
  await expect(page.getByTestId('show-less-hot_lead')).toHaveCount(0);
  await expect(page.getByTestId('section-count-worth_a_look')).toHaveText(fill(en['list.shown_all'], { n: 1 }));
});

test('"Fit" narrows the list to one class, and the other filters count within it', async ({ page }) => {
  await open(page);
  await expect(page.getByTestId('fit-label')).toHaveText(en['filter.fit_legend']);
  await expect(page.getByTestId('fit-filter-value')).toHaveText(en['filter.fit_all']);
  await expect(page.getByTestId('fit-option-all')).toHaveText(`${en['filter.fit_all']} (3)`);
  await expect(page.getByTestId('fit-option-hot_lead')).toHaveText(`${en['class.hot_lead']} (2)`);
  await expect(page.getByTestId('fit-option-worth_a_look')).toHaveText(`${en['class.worth_a_look']} (1)`);

  await choose(page, 'fit-filter', 'hot_lead');
  await expect(page.getByTestId('section-worth_a_look')).toHaveCount(0);
  await expect(page.getByTestId('section-hot_lead').locator('article')).toHaveCount(2);
  const hot = ['sharp', view({ fits: ['hot_lead'] })];
  expect(await lastListing(page)).toEqual(hot);
  expect((await calls(page, 'listingCounts')).at(-1)).toEqual(hot);
  expect((await calls(page, 'listSources')).at(-1)).toEqual(hot);
  await expect(page.getByTestId('filter-option-new')).toContainText('(2)');
  await expect(page.getByTestId('source-option-devitjobs')).toHaveCount(0);   // b1 is worth a look
  await expect(page.getByTestId('fit-option-worth_a_look')).toHaveText(`${en['class.worth_a_look']} (1)`);

  // with the status filter: "All" adds a3 (not fresh) and x1 (a wrong pick)
  await choose(page, 'filter', 'all');
  await expect(page.getByTestId('fit-filter-value')).toHaveText(en['class.hot_lead']);
  await expect(page.getByTestId('section-hot_lead').locator('article')).toHaveCount(4);
  // and with the source
  await choose(page, 'source-filter', 'devitjobs');
  await expect(page.getByTestId('list').locator('article')).toHaveCount(1);   // x1
  await expect(byId(page, 'x1')).toBeVisible();

  await page.getByTestId('refresh').click();
  await expect(page.getByTestId('fit-filter-value')).toHaveText(en['class.hot_lead']);
});

test('a class with nothing left stays listed and keeps its tick', async ({ page }) => {
  await open(page);
  await choose(page, 'source-filter', 'devitjobs');   // b1, worth a look, alone
  await expect(page.getByTestId('fit-option-hot_lead')).toHaveText(`${en['class.hot_lead']} (0)`);
  await expect(page.getByTestId('fit-option-long_shot')).toHaveText(`${en['class.long_shot']} (0)`);
  await expect(page.getByTestId('fit-option-remote_unconfirmed'))
    .toHaveText(`${en['class.remote_unconfirmed']} (0)`);
  await expect(page.getByTestId('fit-option-engagement_unconfirmed')).toHaveCount(0);

  await check(page, 'fit-filter', ['hot_lead', 'worth_a_look', 'long_shot']);
  // the empty hot leads stay chosen
  expect((await lastListing(page))[1].fits).toEqual(['hot_lead', 'worth_a_look', 'long_shot']);
  await page.getByTestId('fit-filter').click();
  await expect(page.getByTestId('fit-option-hot_lead')).toHaveAttribute('data-state', 'on');
  await expect(page.getByTestId('fit-option-remote_unconfirmed')).toHaveAttribute('data-state', 'off');
});

test('one class chosen: the scroll brings ten more at a time', async ({ page }) => {
  await page.setViewportSize({ width: 1000, height: 700 });
  await open(page, manyHotLeads(40));
  await choose(page, 'fit-filter', 'hot_lead');
  const section = page.getByTestId('section-hot_lead');
  await expect(section.locator('article')).toHaveCount(15);
  await expect(page.getByTestId('section-count-hot_lead'))
    .toHaveText(fill(en['list.shown_scroll'], { shown: 15, total: 40, n: 10 }));
  await expect(page.getByTestId('show-more-hot_lead')).toBeVisible();   // the button still works

  for (const shown of [25, 35, 40]) {
    await page.getByTestId('scroll-more-hot_lead').scrollIntoViewIfNeeded();
    await expect(section.locator('article')).toHaveCount(shown);
  }
  await expect(page.getByTestId('scroll-more-hot_lead')).toHaveCount(0);
  await expect(page.getByTestId('section-count-hot_lead')).toHaveText(fill(en['list.shown_all'], { n: 40 }));
  const asked = (await calls(page, 'loadListing')).map((args) => args[2] && args[2].shown)
    .filter(Boolean).map((shown) => shown.hot_lead);
  expect(asked).toEqual([25, 35, 45]);
});

test('Ctrl+Enter in a reason saves it, as "Save" does', async ({ page }) => {
  await open(page);
  const row = byId(page, 'a1');
  await row.getByTestId('btn-bugged').click();
  await row.getByTestId('reason-input').fill('Java, not .NET');
  await row.getByTestId('reason-input').press('Enter');   // a new line, not a save
  expect(await calls(page, 'setFeedback')).toEqual([]);
  await row.getByTestId('reason-input').press('Control+Enter');
  expect(await calls(page, 'setFeedback')).toEqual([['sharp', 'a1', 'bugged', 'Java, not .NET\n']]);
  await expect(page.getByTestId('stub-a1')).toBeVisible();
});

test('a failing request shows the error over the real screen, not the start one', async ({ page }) => {
  const fixture = standardFixture();
  fixture.failClassTotals = true;   // what an outdated main process answered
  await open(page, fixture);
  await expect(page.getByTestId('error')).toContainText("No handler registered for 'class-totals'");
  await expect(page.getByTestId('identity-tab-sharp')).toBeVisible();
  await expect(page.getByTestId('identity-tab-partsharp')).toBeVisible();
  await expect(page.getByTestId('no-identities')).toHaveCount(0);
  await expect(page.getByTestId('menu-button')).toBeVisible();
});

test('until the identities arrive the window shows a spinner, not "no identities"', async ({ page }) => {
  // Reported 2026-10-03: after a reload the start screen ("No identities yet,
  // see docs/ONBOARDING.md") flashed for a second before the tabs appeared.
  const fixture = standardFixture();
  fixture.holdIdentities = true;
  await page.addInitScript(installMockApi, fixture);
  await page.goto(PAGE);
  await expect(page.getByTestId('loading')).toBeVisible();
  await expect(page.getByTestId('loading')).toContainText(en['app.loading']);
  await expect(page.getByTestId('no-identities')).toHaveCount(0);
  await page.evaluate(() => window.__releaseIdentities());
  await expect(page.getByTestId('identity-tab-sharp')).toBeVisible();
  await expect(page.getByTestId('loading')).toHaveCount(0);
  await expect(page.getByTestId('no-identities')).toHaveCount(0);
});

test('with no identities the start screen comes once the answer says so', async ({ page }) => {
  const fixture = standardFixture();
  fixture.identities = [];
  fixture.holdIdentities = true;
  await page.addInitScript(installMockApi, fixture);
  await page.goto(PAGE);
  await expect(page.getByTestId('loading')).toBeVisible();
  await page.evaluate(() => window.__releaseIdentities());
  await expect(page.getByTestId('no-identities')).toBeVisible();
  await expect(page.getByTestId('loading')).toHaveCount(0);
});

test('a failed first load shows its error, not a spinner that never stops', async ({ page }) => {
  const fixture = standardFixture();
  fixture.failIdentities = true;
  await page.addInitScript(installMockApi, fixture);
  await page.goto(PAGE);
  await expect(page.getByTestId('error')).toContainText('listIdentities failed');
  await expect(page.getByTestId('loading')).toHaveCount(0);
});

test('"Refresh" leaves the reload to the app when the app restarts itself', async ({ page }) => {
  const fixture = standardFixture();
  fixture.refreshReply = 'relaunch';
  await open(page, fixture);
  await choose(page, 'filter', 'all');
  await page.evaluate(() => { window.__beforeRefresh = true; });
  await page.getByTestId('refresh').click();
  await expect.poll(() => calls(page, 'refresh')).toHaveLength(1);
  expect(await page.evaluate(() => window.__beforeRefresh)).toBe(true);   // not reloaded here
  const saved = await page.evaluate(() => JSON.parse(localStorage.getItem('work-ide-view')));
  expect(saved.views.sharp.statuses).toEqual(STATUSES);   // the restarted app picks the view up
});

test('"Refresh" still reloads against an older main process without the channel', async ({ page }) => {
  const fixture = standardFixture();
  fixture.withoutRefresh = true;
  await open(page, fixture);
  await page.evaluate(() => { window.__beforeRefresh = true; });
  await page.getByTestId('refresh').click();
  await expect(page.getByTestId('identity-tab-sharp')).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.__beforeRefresh)).toBeUndefined();
});

test('"Vacancy expired" is recorded at once, with no reason, and has its own filter', async ({ page }) => {
  await open(page);
  const button = byId(page, 'a1').getByTestId('btn-expired');
  await expect(button).toHaveText(en['action.expired']);
  await button.click();
  expect(await calls(page, 'setFeedback')).toEqual([['sharp', 'a1', 'expired', null]]);
  await expect(page.getByTestId('reason-form')).toHaveCount(0);
  await expect(page.getByTestId('stub-a1'))
    .toContainText(en['stub.marked'].replace('{status}', en['status.expired']));
  await expect(page.getByTestId('filter-option-expired')).toContainText('(1)');

  await choose(page, 'filter', 'expired');
  expect(await lastListing(page)).toEqual(['sharp', view({ statuses: ['expired'], fresh: BOTH })]);
  await expect(byId(page, 'a1').getByTestId('status-badge')).toHaveText(en['status.expired']);
  await byId(page, 'a1').getByTestId('btn-undo').click();
  expect((await calls(page, 'stepBack')).at(-1)).toEqual(['sharp', 'a1']);
});

// --- the source filter (the owner, 2026-10-04) --------------------------------

test('"Source" lists the boards of the current filter, each with its count', async ({ page }) => {
  await open(page);
  await expect(page.getByTestId('source-label')).toHaveText(en['filter.source_legend']);
  await expect(page.getByTestId('source-filter-value')).toHaveText(en['filter.source_all']);
  await expect(page.getByTestId('source-option-all')).toHaveText(`${en['filter.source_all']} (3)`);
  await expect(page.getByTestId('source-option-linkedin')).toHaveText('linkedin.com (2)');
  await expect(page.getByTestId('source-option-devitjobs')).toHaveText('devitjobs.uk, devitjobs.com (1)');
  expect(await calls(page, 'listSources')).toContainEqual(['sharp', VIEW]);
});

test('the details open with the website the vacancy came from', async ({ page }) => {
  await open(page);
  const details = byId(page, 'b1').locator('details');
  await details.locator('summary').click();
  await expect(details.locator('li').first()).toHaveText(`${en['row.source']}: devitjobs.uk, devitjobs.com`);
  await expect(byId(page, 'a1').getByTestId('details-source')).toHaveText(`${en['row.source']}: linkedin.com`);
});

test('an exclusivity clause is a line in the details, not a refusal', async ({ page }) => {
  await open(page);
  await byId(page, 'b1').locator('details summary').click();
  await expect(byId(page, 'b1').getByTestId('details-exclusivity'))
    .toHaveText(`${en['row.exclusivity']}: moonlighting prohibited`);
  await expect(byId(page, 'a1').getByTestId('details-exclusivity')).toHaveCount(0);
});

test('choosing a source lists only its vacancies, and the filter counts follow it', async ({ page }) => {
  await open(page);
  await choose(page, 'source-filter', 'devitjobs');
  await expect(page.getByTestId('list').locator('article')).toHaveCount(1);
  await expect(byId(page, 'b1')).toBeVisible();
  const devitjobs = ['sharp', view({ sources: ['devitjobs'] })];
  expect(await lastListing(page)).toEqual(devitjobs);
  expect((await calls(page, 'listingCounts')).at(-1)).toEqual(devitjobs);
  await expect(page.getByTestId('filter-option-bugged')).toContainText('(1)');   // x1
  await expect(page.getByTestId('filter-option-new')).toContainText('(1)');   // b1
});

test('"Identities" turns one off: it cannot be collected, its tab goes once another is open, on again it is back', async ({ page }) => {
  await open(page);
  await page.getByTestId('identity-tab-partsharp').click();
  await (await command(page, 'open-identities')).click();
  const dialog = page.getByTestId('identities-dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText(en['identities.explain']);
  await expect(page.getByTestId('identity-active-sharp')).toBeChecked();
  await expect(page.getByTestId('identity-active-partsharp')).toBeChecked();
  await expect(page.getByTestId('identity-active-newbie')).toBeDisabled();   // no base yet

  await page.getByTestId('identity-active-partsharp').uncheck();
  expect(await calls(page, 'setIdentityActive')).toEqual([['partsharp', false]]);
  await expect(page.getByTestId('identity-state-partsharp')).toHaveText(en['identities.inactive']);
  await page.getByTestId('identities-close').click();
  await expect(dialog).toHaveCount(0);

  // the one open keeps its tab, dimmed, and cannot be collected
  await expect(page.getByTestId('identity-tab-partsharp')).toHaveClass(/inactive/);
  const collect = await command(page, 'run-collect');
  await expect(collect).toBeDisabled();
  await expect(collect).toHaveAttribute('title', en['run.inactive']);
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('menu')).toHaveCount(0);

  await page.getByTestId('identity-tab-sharp').click();
  await expect(page.getByTestId('identity-tab-partsharp')).toHaveCount(0);

  await (await command(page, 'open-identities')).click();
  await page.getByTestId('identity-active-partsharp').check();
  await page.getByTestId('identities-close').click();
  await expect(page.getByTestId('identity-tab-partsharp')).not.toHaveClass(/inactive/);
  await page.getByTestId('identity-tab-partsharp').click();
  await expect(await command(page, 'run-collect')).toBeEnabled();
});

test('an inactive identity has no tab, and the app opens on an active one', async ({ page }) => {
  const fixture = standardFixture();
  fixture.identities[1].active = false;   // partsharp
  await page.addInitScript(() => {
    localStorage.setItem('work-ide-view', JSON.stringify({ active: 'partsharp', views: {} }));
  });
  await open(page, fixture);
  await expect(page.getByTestId('identity-tab-sharp')).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByTestId('identity-tab-partsharp')).toHaveCount(0);
  await expect(page.getByTestId('identity-tab-newbie')).toBeVisible();   // no base yet, not turned off
});

test('the menu closes on a click elsewhere', async ({ page }) => {
  await open(page);
  await command(page, 'cleanup');
  await page.getByTestId('panel').click({ position: { x: 5, y: 5 } });
  await expect(page.getByTestId('menu')).toHaveCount(0);
});

test('the text field after the drop-downs narrows the list by words, together with them', async ({ page }) => {
  await open(page);
  const order = await page.getByTestId('filters').locator('[data-dropdown], [data-testid="text-filter"]')
    .evaluateAll((nodes) => nodes.map((n) => n.dataset.dropdown || n.dataset.testid));
  expect(order.at(-1)).toBe('text-filter');
  await expect(page.getByTestId('filters')).toContainText(en['filter.text_legend']);
  await expect(page.getByTestId('list').locator('article')).toHaveCount(3);   // a1, a2r, b1

  // typed key by key: each key redraws the panel, the field keeps the focus and the caret
  const field = page.getByTestId('text-filter');
  await field.pressSequentially('COMPANY b', { delay: 40 });
  await expect(field).toHaveValue('COMPANY b');
  await expect(field).toBeFocused();
  await settled(page);
  await expect(page.getByTestId('list').locator('article')).toHaveCount(1);
  await expect(byId(page, 'b1')).toBeVisible();
  const typed = ['sharp', view({ text: 'COMPANY b' })];
  expect(await lastListing(page)).toEqual(typed);
  expect((await calls(page, 'listingCounts')).at(-1)).toEqual(typed);
  await expect(page.getByTestId('filter-option-new')).toContainText('(1)');

  await field.fill('');
  await settled(page);
  await expect(page.getByTestId('list').locator('article')).toHaveCount(3);
  expect(await lastListing(page)).toEqual(['sharp', view()]);

  // a drop-down and the words: both apply
  await choose(page, 'source-filter', 'linkedin');
  await expect(page.getByTestId('list').locator('article')).toHaveCount(2);   // a1, a2r
  await field.fill('a2r');
  await settled(page);
  await expect(page.getByTestId('list').locator('article')).toHaveCount(1);
  await expect(byId(page, 'a2r')).toBeVisible();
  expect(await lastListing(page)).toEqual(['sharp', view({ sources: ['linkedin'], text: 'a2r' })]);
  await field.fill('devitjobs');
  await settled(page);
  await expect(page.getByTestId('list').locator('article')).toHaveCount(0);
  await expect(field).toHaveValue('devitjobs');
});

test('the status filter and the source apply together', async ({ page }) => {
  await open(page);
  await choose(page, 'source-filter', 'linkedin');
  await choose(page, 'filter', 'bugged');
  await expect(page.getByTestId('list').locator('article')).toHaveCount(0);
  expect(await lastListing(page))
    .toEqual(['sharp', view({ statuses: ['bugged'], fresh: BOTH, sources: ['linkedin'] })]);
  // the chosen board stays on the list with nothing in it; the others follow the filter
  await expect(page.getByTestId('source-filter-value')).toHaveText('linkedin.com');
  await expect(page.getByTestId('source-option-linkedin')).toHaveText('linkedin.com (0)');
  await expect(page.getByTestId('source-option-devitjobs')).toHaveText('devitjobs.uk, devitjobs.com (1)');
  await choose(page, 'source-filter', 'devitjobs');
  await expect(byId(page, 'x1')).toBeVisible();
  await choose(page, 'source-filter', '');
  expect(await lastListing(page)).toEqual(['sharp', view({ statuses: ['bugged'], fresh: BOTH })]);
});

test('the chosen boards stay across markets, and a refresh brings them back', async ({ page }) => {
  await open(page);
  await choose(page, 'source-filter', 'devitjobs');
  await choose(page, 'segment-filter', 'uk');
  await expect(page.getByTestId('source-filter-value')).toHaveText('devitjobs.uk, devitjobs.com');
  await choose(page, 'segment-filter', '');
  await page.getByTestId('refresh').click();
  await expect(page.getByTestId('source-filter-value')).toHaveText('devitjobs.uk, devitjobs.com');
  await expect(byId(page, 'b1')).toBeVisible();
  await expect(byId(page, 'a1')).toHaveCount(0);
});

// --- the company filter (the owner, 2026-10-14) -------------------------------
// All companies; under it the kinds of intermediary, each one by name under
// its kind; every other company one row. a1 and a2r are freelance
// marketplaces, b1 an employer; no agency and no reposter in the view.

const ALL4 = ['marketplace', 'agency', 'reposter', 'other'];

function companyFixture() {
  const fixture = standardFixture();
  fixture.companyKinds = {
    'Company a1': { kind: 'marketplace', name: 'Proxify' },
    'Company a2r': { kind: 'marketplace', name: 'Toptal' },
  };
  return fixture;
}

async function openCompanies(page) {
  await open(page, companyFixture());
  await page.getByTestId('company-filter').click();
  await expect(page.getByTestId('company-filter-menu')).toBeVisible();
}

async function click(page, testid) {
  await page.getByTestId(testid).click();
  await settled(page);
}

test('"Company" sits between "Source" and "Category": all, the kinds, the intermediaries, the rest', async ({ page }) => {
  await openCompanies(page);
  const order = await page.getByTestId('filters').locator('[data-dropdown]')
    .evaluateAll((nodes) => nodes.map((n) => n.dataset.dropdown));
  expect(order).toEqual(['segment-filter', 'filter', 'age-filter', 'source-filter', 'company-filter', 'fit-filter']);
  await expect(page.getByTestId('company-label')).toHaveText(en['filter.company_legend']);
  await expect(page.getByTestId('company-filter-value')).toHaveText(en['filter.company_all']);
  const rows = await page.getByTestId('company-filter-menu').locator('[role="option"]')
    .evaluateAll((nodes) => nodes.map((n) => [n.textContent, n.dataset.state]));
  expect(rows).toEqual([
    [`${en['filter.company_all']} (3)`, 'on'],
    [`${en['filter.company_kind.marketplace']} (2)`, 'on'],
    ['Proxify (1)', 'on'],
    ['Toptal (1)', 'on'],
    [`${en['filter.company_kind.other']} (1)`, 'on'],
  ]);
  expect(await calls(page, 'listCompanies')).toContainEqual(['sharp', VIEW]);
});

test('unticking one intermediary hides it alone, and the closed box says what is hidden', async ({ page }) => {
  await openCompanies(page);
  await click(page, 'company-option-Proxify');
  expect(await lastListing(page)).toEqual(['sharp', view({ companies: { kinds: ALL4, hidden: ['Proxify'] } })]);
  await expect(byId(page, 'a1')).toHaveCount(0);
  await expect(byId(page, 'a2r')).toBeVisible();
  await expect(byId(page, 'b1')).toBeVisible();
  // its own numbers leave the company choice aside: Proxify stays, unticked
  await expect(page.getByTestId('company-option-Proxify')).toHaveAttribute('data-state', 'off');
  await expect(page.getByTestId('company-option-Proxify')).toHaveText('Proxify (1)');
  await expect(page.getByTestId('company-kind-marketplace')).toHaveAttribute('data-state', 'partial');
  await expect(page.getByTestId('company-option-all')).toHaveAttribute('data-state', 'partial');
  await expect(page.getByTestId('company-filter-value'))
    .toHaveText(en['filter.company_except'].replace('{list}', 'Proxify'));
  // the other drop-downs count under it
  await expect(page.getByTestId('source-option-linkedin')).toHaveText('linkedin.com (1)');
  await click(page, 'company-option-Proxify');
  expect(await lastListing(page)).toEqual(['sharp', VIEW]);
});

test('a kind goes as a whole, and one of it ticked back brings that one alone', async ({ page }) => {
  await openCompanies(page);
  await click(page, 'company-kind-marketplace');
  expect(await lastListing(page))
    .toEqual(['sharp', view({ companies: { kinds: ['agency', 'reposter', 'other'], hidden: [] } })]);
  await expect(page.getByTestId('list').locator('article')).toHaveCount(1);   // b1
  await expect(page.getByTestId('company-option-Proxify')).toHaveAttribute('data-state', 'off');
  await expect(page.getByTestId('company-option-Toptal')).toHaveAttribute('data-state', 'off');
  await expect(page.getByTestId('company-filter-value'))
    .toHaveText(en['filter.company_except'].replace('{list}', en['filter.company_kind.marketplace']));

  await click(page, 'company-option-Toptal');
  expect(await lastListing(page)).toEqual(['sharp', view({ companies: { kinds: ALL4, hidden: ['Proxify'] } })]);
  await expect(byId(page, 'a2r')).toBeVisible();
  await expect(byId(page, 'a1')).toHaveCount(0);

  // a partly ticked kind: a click ticks all of it
  await click(page, 'company-kind-marketplace');
  expect(await lastListing(page)).toEqual(['sharp', VIEW]);
});

test('"Other companies" leaves only the intermediaries; "All companies" turns everything off and on', async ({ page }) => {
  await openCompanies(page);
  await click(page, 'company-kind-other');
  expect(await lastListing(page))
    .toEqual(['sharp', view({ companies: { kinds: ['marketplace', 'agency', 'reposter'], hidden: [] } })]);
  await expect(byId(page, 'b1')).toHaveCount(0);
  await expect(page.getByTestId('company-kind-other')).toHaveAttribute('data-state', 'off');
  await expect(page.getByTestId('company-option-all')).toHaveAttribute('data-state', 'partial');

  await click(page, 'company-option-all');   // partly on: everything
  expect(await lastListing(page)).toEqual(['sharp', VIEW]);
  await click(page, 'company-option-all');   // on: nothing
  expect(await lastListing(page)).toEqual(['sharp', view({ companies: { kinds: [], hidden: [] } })]);
  await expect(page.getByTestId('list').locator('article')).toHaveCount(0);
  await expect(page.getByTestId('company-filter-value')).toHaveText(en['filter.none']);
  for (const testid of ['company-kind-marketplace', 'company-option-Proxify', 'company-kind-other']) {
    await expect(page.getByTestId(testid)).toHaveAttribute('data-state', 'off');
  }
});

test('the hidden companies survive a refresh and a change of market', async ({ page }) => {
  await openCompanies(page);
  await click(page, 'company-option-Proxify');
  await page.keyboard.press('Escape');
  await choose(page, 'segment-filter', 'uk');
  await choose(page, 'segment-filter', '');
  await page.getByTestId('refresh').click();
  await expect(page.getByTestId('company-filter-value'))
    .toHaveText(en['filter.company_except'].replace('{list}', 'Proxify'));
  await expect(byId(page, 'a2r')).toBeVisible();
  await expect(byId(page, 'a1')).toHaveCount(0);
});

test('a base without company kinds: every company is one "Other companies" row', async ({ page }) => {
  await open(page);
  await page.getByTestId('company-filter').click();
  const rows = await page.getByTestId('company-filter-menu').locator('[role="option"]')
    .evaluateAll((nodes) => nodes.map((n) => n.textContent));
  expect(rows).toEqual([`${en['filter.company_all']} (3)`, `${en['filter.company_kind.other']} (3)`]);
});

test('the company list stands in by level: all, the kinds, the companies', async ({ page }) => {
  await openCompanies(page);
  const pad = (testid) => page.getByTestId(testid)
    .evaluate((node) => parseFloat(getComputedStyle(node).paddingLeft));
  const top = await pad('company-option-all');
  const kind = await pad('company-kind-marketplace');
  const company = await pad('company-option-Proxify');
  expect(kind).toBeGreaterThan(top);
  expect(company).toBeGreaterThan(kind);
  expect(await pad('company-kind-other')).toBe(kind);
});

test('"Generate CV" sits between "Copy URL" and "Generate Cover Letter" and opens what it made', async ({ page }) => {
  const fixture = standardFixture();
  fixture.holdCv = true;
  fixture.cvReply = {
    ok: true, pages: 3, docx: '/docs/sharp/a1/CV.docx', pdf: '/docs/sharp/a1/CV.pdf',
    findings: [{ kind: 'term', text: 'Kafka', where: 'Skills', message: 'not found in either CV' }],
    warnings: [], removed_for_length: ['Contoso: Fixed flaky tests.'],
    report: { gaps: ['Kubernetes'], from_parent: ['interviewed Go developers'], notes: [] },
  };
  await open(page, fixture);
  const row = byId(page, 'a1');
  const ids = await row.locator('.answers button').evaluateAll((b) => b.map((x) => x.dataset.testid));
  expect(ids.slice(0, 6)).toEqual(['btn-open', 'btn-copy-url', 'btn-generate-cv', 'btn-generate-letter',
    'btn-collect-reputation', 'btn-applied']);

  await row.getByTestId('btn-generate-cv').click();
  await expect(row.getByTestId('cv-form')).toBeVisible();
  expect(await calls(page, 'enqueueTask')).toEqual([]);
  await row.getByTestId('btn-generate-cv').click();
  await expect(row.getByTestId('cv-form')).toHaveCount(0);
  await expect(row.getByTestId('btn-generate-cv')).toHaveText(en['action.generating_cv']);
  await expect(row.getByTestId('btn-generate-cv')).toBeDisabled();
  expect(await calls(page, 'enqueueTask')).toEqual([[{
    kind: 'cv', identity: 'sharp', vacancyId: 'a1', title: 'Senior .NET Developer a1', company: 'Company a1',
    instructions: '',
  }]]);
  // another card is not locked: its CV queues behind this one
  const other = byId(page, 'a2r').getByTestId('btn-generate-cv');
  await other.dblclick();
  await expect(other).toHaveText(en['action.queued']);
  await expect(other).toBeDisabled();

  await page.evaluate(() => window.__releaseCv());
  await expect(row.getByTestId('btn-generate-cv')).toHaveText(en['action.cv_generated']);
  await expect(row.getByTestId('btn-generate-cv')).toBeEnabled();
  await expect(other).toHaveText(en['action.generating_cv']);
  await expect(row.getByTestId('cv-summary')).toHaveText(en['cv.ready_pages'].replace('{pages}', '3'));
  await expect(row.getByTestId('cv-findings')).toContainText('Kafka');
  await expect(row.getByTestId('cv-gaps')).toContainText('Kubernetes');
  await expect(row.getByTestId('cv-from-parent')).toContainText('interviewed Go developers');
  await expect(row.getByTestId('cv-removed')).toContainText('Contoso: Fixed flaky tests.');
  await expect(row.getByTestId('cv-notes')).toHaveCount(0);   // empty lists are not shown

  await row.getByTestId('cv-open-pdf').click();
  await row.getByTestId('cv-show-folder').click();
  expect(await calls(page, 'openCvFile')).toEqual([['/docs/sharp/a1/CV.pdf']]);
  expect(await calls(page, 'showCvFile')).toEqual([['/docs/sharp/a1/CV.pdf']]);
  await row.getByTestId('cv-close').click();
  await expect(row.getByTestId('cv-result')).toHaveCount(0);
});

test('"Collect reputation" queues a lookup for the vacancy and is gone once the company has a result', async ({ page }) => {
  const fixture = standardFixture();
  fixture.holdReputation = true;
  for (const rows of Object.values(fixture.rows.sharp)) {
    for (const r of rows) if (r.id === 'a3') r.view.reputation_collected = true;
  }
  await open(page, fixture);
  await expect(byId(page, 'a3').getByTestId('btn-collect-reputation')).toHaveCount(0);
  const row = byId(page, 'a1');
  const button = row.getByTestId('btn-collect-reputation');
  await expect(button).toHaveText(en['action.collect_reputation']);
  await button.click();
  await expect(button).toHaveText(en['action.collecting_reputation']);
  await expect(button).toBeDisabled();
  expect(await calls(page, 'enqueueTask')).toEqual([[{
    kind: 'reputation', identity: 'sharp', vacancyId: 'a1', title: 'Senior .NET Developer a1', company: 'Company a1',
  }]]);
  // its own lane: a second lookup queues behind it
  const other = byId(page, 'a2r').getByTestId('btn-collect-reputation');
  await other.click();
  await expect(other).toHaveText(en['action.queued']);
  await expect(page.getByTestId('task-1')).toContainText(en['task.kind.reputation']);
  await page.evaluate(() => window.__finishReputation());
  await expect(button).toHaveCount(0);
  await expect(row).toContainText('4.1/5 (Glassdoor)');
  await expect(other).toHaveText(en['action.collecting_reputation']);
});

test('the vacancy\'s folder: opened, or its path copied, once it has a CV or a cover letter', async ({ page }) => {
  await open(page);
  const row = byId(page, 'a1');
  await expect(row.getByTestId('btn-open-docs')).toHaveCount(0);
  await row.getByTestId('btn-generate-cv').dblclick();
  await expect(row.getByTestId('btn-generate-cv')).toHaveText(en['action.cv_generated']);
  const ids = await row.locator('.answers button').evaluateAll((b) => b.map((x) => x.dataset.testid));
  expect(ids.slice(0, 8)).toEqual(['btn-open', 'btn-copy-url', 'btn-generate-cv', 'btn-generate-letter',
    'btn-collect-reputation', 'btn-open-docs', 'btn-copy-docs-path', 'btn-applied']);
  await expect(row.getByTestId('btn-open-docs')).toHaveText(en['action.open_docs']);
  await row.getByTestId('btn-open-docs').click();
  expect(await calls(page, 'openDocumentsDir')).toEqual([['sharp', 'a1']]);
  await row.getByTestId('btn-copy-docs-path').click();
  expect(await calls(page, 'copyText')).toEqual([['/docs/sharp/a1']]);
  await expect(row.getByTestId('btn-copy-docs-path')).toHaveText(en['action.copied']);
  await expect(row.getByTestId('btn-copy-docs-path')).toHaveText(en['action.copy_docs_path']);
  await expect(byId(page, 'a2r').getByTestId('btn-open-docs')).toHaveCount(0);
});

test('a generated CV stays generated whatever is generated after it, and makes a new version when pressed', async ({ page }) => {
  const fixture = standardFixture();
  fixture.holdCv = true;
  // made before this session: the folder says so
  fixture.docs = { sharp: { b1: { dir: "/docs/sharp/b1", cv: 2, letter: 0, errors: {} } } };
  await open(page, fixture);
  const first = byId(page, 'a1').getByTestId('btn-generate-cv');
  const second = byId(page, 'a2r').getByTestId('btn-generate-cv');
  await expect(byId(page, "b1").getByTestId("btn-generate-cv")).toHaveText(en['action.cv_generated']);
  await expect(byId(page, "b1").getByTestId("btn-open-docs")).toBeVisible();

  await first.dblclick();
  await page.evaluate(() => window.__releaseCv());
  await expect(first).toHaveText(en['action.cv_generated']);
  await expect(first).toHaveClass(/done/);
  await expect(second).toHaveText(en['action.generate_cv']);

  await second.dblclick();
  await page.evaluate(() => window.__releaseCv());
  await expect(second).toHaveText(en['action.cv_generated']);
  await expect(first).toHaveText(en['action.cv_generated']);

  // pressed again: the instructions, then a new version
  await first.click();
  await expect(byId(page, 'a1').getByTestId('cv-form')).toBeVisible();
  await first.click();
  await expect(first).toHaveText(en['action.generating_cv']);
  await page.evaluate(() => window.__releaseCv());
  await expect(first).toHaveText(en['action.cv_generated']);
  expect((await calls(page, 'enqueueTask')).map(([r]) => r.vacancyId)).toEqual(['a1', 'a2r', 'a1']);
});

test('"Generate Cover Letter" works as "Generate CV" does, apart from it, and queues behind it', async ({ page }) => {
  const fixture = standardFixture();
  fixture.holdCv = true;
  fixture.letterReply = {
    ok: true, pages: 1, docx: '/docs/sharp/a1/Cover Letter.docx', pdf: '/docs/sharp/a1/Cover Letter.pdf',
    findings: [{ kind: 'term', text: 'Kafka', where: 'letter', message: 'not found in either CV' }],
    warnings: [], report: { gaps: ['Kubernetes'], from_parent: [], notes: ['the recipient is guessed'] },
  };
  await open(page, fixture);
  const row = byId(page, 'a1');
  const cv = row.getByTestId('btn-generate-cv');
  const letter = row.getByTestId('btn-generate-letter');
  await expect(letter).toHaveText(en['action.generate_letter']);

  // the first click opens the letter's own instructions; the second sends them
  await letter.click();
  await expect(row.getByTestId('letter-instructions')).toHaveAttribute('placeholder', en['letter.instructions_hint']);
  await expect(row.getByTestId('cv-form')).toHaveCount(0);
  await expect(letter).toHaveClass(/pressed/);
  await row.getByTestId('letter-instructions').fill('Mention Azure.');
  await letter.click();
  await expect(letter).toHaveText(en['action.generating_letter']);
  expect((await calls(page, 'enqueueTask')).map(([r]) => [r.kind, r.vacancyId, r.instructions]))
    .toEqual([['letter', 'a1', 'Mention Azure.']]);

  // a CV meanwhile: queued, one document at a time
  await expect(cv).toBeEnabled();
  await cv.dblclick();
  await expect(cv).toHaveText(en['action.queued']);
  await expect(page.getByTestId('task-2')).toContainText(`${en['task.kind.cv']} · Senior .NET Developer a1 — Company a1 · sharp`);

  await page.evaluate(() => window.__releaseCv());
  await expect(letter).toHaveText(en['action.letter_generated']);
  await expect(cv).toHaveText(en['action.generating_cv']);
  await expect(row.getByTestId('letter-summary')).toHaveText(en['letter.ready_pages'].replace('{pages}', '1'));
  await expect(row.getByTestId('letter-findings')).toContainText('Kafka');
  await expect(row.getByTestId('letter-notes')).toContainText('the recipient is guessed');
  await row.getByTestId('letter-open-pdf').click();
  expect(await calls(page, 'openCvFile')).toEqual([['/docs/sharp/a1/Cover Letter.pdf']]);

  await page.evaluate(() => window.__releaseCv());
  await expect(cv).toHaveText(en['action.cv_generated']);
  await expect(letter).toHaveText(en['action.letter_generated']);
  await expect(row.getByTestId('cv-result')).toBeVisible();
  await expect(row.getByTestId('letter-result')).toBeVisible();

  // a letter for another vacancy leaves this card's letter generated
  const other = byId(page, 'a2r').getByTestId('btn-generate-letter');
  await other.dblclick();
  await page.evaluate(() => window.__releaseCv());
  await expect(other).toHaveText(en['action.letter_generated']);
  await expect(letter).toHaveText(en['action.letter_generated']);
  await row.getByTestId('letter-close').click();
  await expect(row.getByTestId('letter-result')).toHaveCount(0);
  await expect(row.getByTestId('cv-result')).toBeVisible();
});

test('a failed generation does not say the CV is generated', async ({ page }) => {
  const fixture = standardFixture();
  fixture.failCv = true;
  await open(page, fixture);
  const row = byId(page, 'a1');
  await row.getByTestId('btn-generate-cv').click();
  await row.getByTestId('btn-generate-cv').click();
  await expect(row.getByTestId('cv-result')).toHaveClass(/failed/);
  await expect(row.getByTestId('btn-generate-cv')).toHaveText(en['action.generate_cv']);
  await expect(page.getByTestId('task-1')).toHaveAttribute('data-state', 'failed');
});

test('a vacancy found gone says so on its button, and offers no folder', async ({ page }) => {
  const fixture = standardFixture();
  const gone = 'Vacancy not found, possibly outdated: the link is dead.';
  fixture.docs = { sharp: { a1: { dir: '/docs/sharp/a1', cv: 0, letter: 0, errors: { cv: gone } } } };
  await open(page, fixture);
  const row = byId(page, 'a1');
  await expect(row.getByTestId('btn-generate-cv')).toHaveText(en['action.generate_cv']);
  await expect(row.getByTestId('btn-generate-cv')).toHaveAttribute('title', gone);
  await expect(row.getByTestId('btn-open-docs')).toHaveCount(0);
});

test('documents the app queued itself show on their cards and in the panel, marked auto', async ({ page }) => {
  const fixture = standardFixture();
  fixture.holdCv = true;
  await open(page, fixture);
  await page.evaluate(() => {
    window.__addTask({ kind: 'cv', identity: 'sharp', vacancyId: 'a1', title: 'Senior .NET Developer a1', company: 'Company a1' });
    window.__addTask({ kind: 'letter', identity: 'sharp', vacancyId: 'a1', title: 'Senior .NET Developer a1', company: 'Company a1' });
  });
  const row = byId(page, 'a1');
  await expect(row.getByTestId('btn-generate-cv')).toHaveText(en['action.generating_cv']);
  await expect(row.getByTestId('btn-generate-letter')).toHaveText(en['action.queued']);
  await expect(page.getByTestId('task-1')).toContainText(en['task.origin.auto']);
  await page.getByTestId('tasks-cancel-queued').click();
  expect(await calls(page, 'cancelQueued')).toEqual([[null]]);
  await expect(row.getByTestId('btn-generate-letter')).toHaveText(en['action.generate_letter']);
  await page.evaluate(() => window.__releaseCv());
  await expect(row.getByTestId('btn-generate-cv')).toHaveText(en['action.cv_generated']);
  // what the app queued itself shows no result on the card: the folder has it
  await expect(row.getByTestId('cv-result')).toHaveCount(0);
  await page.getByTestId('tasks-clear').click();
  await expect(page.getByTestId('task-panel')).toBeHidden();
});

test('the panel\'s height and split are dragged on their sashes and kept', async ({ page }) => {
  await open(page);
  await (await command(page, 'run-collect')).click();
  const panel = page.getByTestId('task-panel');
  await expect(panel).toBeVisible();
  // the panel's edge and its split are 2px lines, as VS Code's; each sash lies over its line
  await expect(panel).toHaveCSS('border-top-width', '2px');
  await expect(page.locator('.log-pane')).toHaveCSS('border-left-width', '2px');
  const before = await panel.boundingBox();
  const sash = await page.getByTestId('task-panel-sash').boundingBox();
  expect(sash.y).toBeLessThanOrEqual(before.y);
  expect(sash.y + sash.height).toBeGreaterThanOrEqual(before.y + 2);
  const log = await page.locator('.log-pane').boundingBox();
  const splitAt = await page.getByTestId('task-split-sash').boundingBox();
  expect(splitAt.x).toBeLessThanOrEqual(log.x);
  expect(splitAt.x + splitAt.width).toBeGreaterThanOrEqual(log.x + 2);
  await expect(page.getByTestId('task-panel-sash')).toHaveCSS('cursor', 'ns-resize');
  await page.mouse.move(sash.x + 50, sash.y + sash.height / 2);
  await page.mouse.down();
  await page.mouse.move(sash.x + 50, sash.y - 80, { steps: 4 });
  await page.mouse.up();
  const after = await panel.boundingBox();
  expect(Math.round(after.height - before.height)).toBeGreaterThan(70);

  const split = await page.getByTestId('task-split-sash').boundingBox();
  await expect(page.getByTestId('task-split-sash')).toHaveCSS('cursor', 'ew-resize');
  const listBefore = await page.locator('.tasks-pane').boundingBox();
  await page.mouse.move(split.x + split.width / 2, split.y + 20);
  await page.mouse.down();
  await page.mouse.move(split.x + 120, split.y + 20, { steps: 4 });
  await page.mouse.up();
  const listAfter = await page.locator('.tasks-pane').boundingBox();
  expect(listAfter.width - listBefore.width).toBeGreaterThan(80);

  await page.reload();
  await (await command(page, 'run-collect')).click();
  await expect(panel).toBeVisible();
  expect(Math.abs((await panel.boundingBox()).height - after.height)).toBeLessThan(3);
  expect(Math.abs((await page.locator('.tasks-pane').boundingBox()).width - listAfter.width)).toBeLessThan(3);
});

test('the first click on "Generate CV" opens instructions; the second sends what they hold', async ({ page }) => {
  await open(page, standardFixture());
  const row = byId(page, 'a1');
  await row.getByTestId('btn-generate-cv').click();
  const input = row.getByTestId('cv-instructions');
  await expect(input).toBeFocused();
  await expect(input).toHaveAttribute('placeholder', en['cv.instructions_hint']);
  await expect(row.getByTestId('btn-generate-cv')).toHaveClass(/pressed/);
  await input.fill('  Stress Azure.\nWrite it in German.  ');
  await row.getByTestId('btn-generate-cv').click();
  await expect(row.getByTestId('cv-summary')).toBeVisible();
  const sent = async () => (await calls(page, 'enqueueTask')).map(([r]) => r.instructions);
  expect(await sent()).toEqual(['Stress Azure.\nWrite it in German.']);
  await expect(row.getByTestId('cv-form')).toHaveCount(0);

  // The form's own button and Ctrl+Enter send too; Cancel sends nothing.
  await row.getByTestId('btn-generate-cv').click();
  await row.getByTestId('cv-instructions').fill('Lead with payments.');
  await row.getByTestId('cv-instructions-generate').click();
  await expect(row.getByTestId('btn-generate-cv')).toHaveText(en['action.cv_generated']);
  await row.getByTestId('btn-generate-cv').click();
  await row.getByTestId('cv-instructions').fill('Short.');
  await row.getByTestId('cv-instructions').press('Control+Enter');
  await expect(row.getByTestId('btn-generate-cv')).toHaveText(en['action.cv_generated']);
  await row.getByTestId('btn-generate-cv').click();
  await row.getByTestId('cv-instructions').fill('Never sent.');
  await row.getByTestId('cv-instructions-cancel').click();
  await expect(row.getByTestId('cv-form')).toHaveCount(0);
  expect(await sent()).toEqual(['Stress Azure.\nWrite it in German.', 'Lead with payments.', 'Short.']);
});

test('instructions half typed outlive a re-render and stay with their card', async ({ page }) => {
  await open(page, standardFixture());
  await byId(page, 'a1').getByTestId('btn-generate-cv').click();
  await byId(page, 'a1').getByTestId('cv-instructions').fill('Stress Azure.');
  await byId(page, 'a2r').getByTestId('btn-copy-url').click();   // re-renders the list
  await expect(byId(page, 'a1').getByTestId('cv-instructions')).toHaveValue('Stress Azure.');
  await expect(byId(page, 'a2r').getByTestId('cv-form')).toHaveCount(0);
});

test('a failed CV generation says why, on its card', async ({ page }) => {
  const fixture = standardFixture();
  fixture.cvReply = { ok: false, error: 'the common CV is missing' };
  await open(page, fixture);
  await byId(page, 'a1').getByTestId('btn-generate-cv').dblclick();
  await expect(byId(page, 'a1').getByTestId('cv-result')).toHaveText(new RegExp(`${en['cv.failed']}: the common CV is missing`));
  await expect(byId(page, 'a2r').getByTestId('cv-result')).toHaveCount(0);
  await expect(byId(page, 'a1').getByTestId('btn-generate-cv')).toBeEnabled();
});

test('a collection shows its steps under it while it runs, folded or opened by its arrow', async ({ page }) => {
  await open(page);
  await (await command(page, 'run-collect')).click();
  await page.evaluate(() => window.__setSteps([
    { key: 'prepare', state: 'done', duration: '1:05', note: null, progress: null },
    { key: 'fetch', name: 'fetch 19 sources', state: 'running', began: Date.now() - 65000,
      progress: 'linkedin pairs: 36/168 (21%)', note: null, duration: null },
    { key: null, name: 'a stage the app has no name for', state: 'done', duration: '0:02', note: null, progress: null },
  ]));
  const step = (i) => page.getByTestId(`task-step-1-${i}`);
  await expect(step(0)).toContainText(en['step.prepare']);
  await expect(step(0)).toContainText('1:05');
  await expect(step(1)).toHaveAttribute('data-state', 'running');
  await expect(step(1)).toContainText(en['step.fetch']);
  await expect(step(1)).toContainText('linkedin pairs: 36/168');
  await expect(step(1)).toContainText(/1:0[5-9]/);   // its time counts on
  await expect(step(2)).toContainText('a stage the app has no name for');
  await page.getByTestId('task-1').getByTestId('task-fold').click();
  await expect(step(0)).toHaveCount(0);
  await page.getByTestId('task-1').getByTestId('task-fold').click();
  await expect(step(0)).toBeVisible();
  await page.evaluate(() => window.__finishCollect({ ok: true, code: 0 }));
  await expect(page.getByTestId('task-1')).toHaveAttribute('data-state', 'done');
  await expect(step(0)).toHaveCount(0);   // an ended collection folds its steps
  await page.getByTestId('task-1').getByTestId('task-fold').click();
  await expect(step(0)).toBeVisible();
});

test('a collection lists the stages still to come: a circle to do, a spinner going, a tick done', async ({ page }) => {
  await open(page);
  await (await command(page, 'run-collect')).click();
  await page.evaluate(() => window.__setSteps([
    { key: 'prepare', state: 'done', duration: '1:05', note: null, progress: null },
    { key: 'fetch', name: 'fetch 19 sources', state: 'running', began: Date.now() - 5000,
      progress: null, note: null, duration: null },
    { key: 'rescore_top', state: 'pending' },
    { key: 'summary', state: 'pending' },
  ]));
  const step = (i) => page.getByTestId(`task-step-1-${i}`);
  await expect(step(0)).toHaveAttribute('data-state', 'done');
  await expect(step(0).locator('.task-icon')).toHaveText('✓');
  await expect(step(0).locator('.task-icon')).toHaveCSS('color', await page.evaluate(() => {
    const probe = document.createElement('span');
    probe.style.color = 'var(--applied)';
    document.body.append(probe);
    const color = getComputedStyle(probe).color;
    probe.remove();
    return color;
  }));
  await expect(step(1).locator('.spinner')).toBeVisible();
  await expect(step(2)).toHaveAttribute('data-state', 'pending');
  await expect(step(2).locator('.task-icon')).toHaveText('○');
  await expect(step(2)).toContainText(en['step.rescore_top']);
  await expect(step(3)).toContainText(en['step.summary']);
  await expect(step(2).locator('.step-time')).toHaveText('');
});

test('the CV/CL batch is one task: its progress, its document on the card, its log, its stop', async ({ page }) => {
  await open(page);
  await page.evaluate(() => window.__setBatch({
    identity: 'sharp, partsharp',
    progress: { index: 8, total: 971, made: 6, failed: 1, gone: 0 },
    current: { identity: 'sharp', kind: 'cv', vacancyId: 'a1', title: 'Senior .NET Developer a1', company: 'Company a1' },
  }, ['start: sharp partsharp', '[8/971] sharp cv a1']));
  const task = page.getByTestId('task-batch');
  await expect(task).toHaveAttribute('data-state', 'running');
  await expect(task).toContainText(`${en['task.kind.batch']} · sharp, partsharp · 8/971`);
  await expect(task).toContainText('Senior .NET Developer a1');
  await expect(task).toContainText(en['batch.summary'].replace('{made}', '6').replace('{gone}', '0').replace('{failed}', '1'));
  const row = byId(page, 'a1');
  await expect(row.getByTestId('btn-generate-cv')).toHaveText(en['action.generating_cv']);
  await expect(row.getByTestId('btn-generate-cv')).toBeDisabled();
  await expect(page.getByTestId('task-log')).toContainText('[8/971] sharp cv a1');
  await expect(page.getByTestId('task-log-title')).toContainText(en['task.kind.batch']);

  await page.evaluate(() => window.__setBatch({
    identity: 'sharp, partsharp', holding: true,
    progress: { index: 8, total: 971, made: 7, failed: 1, gone: 0 }, current: null,
  }, ['paused: the app is generating documents']));
  await expect(task).toContainText(en['batch.holding']);
  await expect.poll(async () => (await calls(page, 'documentsState')).some(([who, ids]) => who === 'sharp'
    && ids.length === 1 && ids[0] === 'a1')).toBe(true);   // the document it made shows on the card
  await expect(row.getByTestId('btn-generate-cv')).toBeEnabled();

  await task.hover();
  await task.getByTestId('task-cancel').click();
  await page.getByTestId('stop-yes').click();
  expect(await calls(page, 'cancelTask')).toEqual([['batch']]);
  await expect(task).toContainText(en['batch.stopping']);
  await page.evaluate(() => window.__setBatch({
    identity: 'sharp, partsharp', state: 'stopped', progress: { index: 9, total: 971, made: 8, failed: 1, gone: 0 },
  }, ['stopped before 10/971']));
  await expect(task).toHaveAttribute('data-state', 'stopped');
  await page.getByTestId('tasks-clear').click();
  await expect(page.getByTestId('task-panel')).toBeHidden();
});

test("a document asked for while the batch runs says it waits for the batch's current document", async ({ page }) => {
  const fixture = standardFixture();
  fixture.holdCv = true;
  await open(page, fixture);
  await page.evaluate(() => window.__setBatch({ progress: { index: 1, total: 3, made: 0, failed: 0, gone: 0 } }));
  await page.evaluate(() => window.__addTask({ kind: 'cv', identity: 'sharp', vacancyId: 'b1', origin: 'app' }));
  await expect(page.getByTestId('task-1')).toHaveAttribute('data-state', 'queued');
  await expect(page.getByTestId('task-1')).toHaveAttribute('title', en['task.waiting_batch']);
  await page.evaluate(() => window.__setBatch({ holding: true, progress: { index: 1, total: 3, made: 1, failed: 0, gone: 0 } }));
  await expect(page.getByTestId('task-1')).toHaveAttribute('data-state', 'running');
});

test('a task held by the AI usage limit says until when, then that the reset is being checked', async ({ page }) => {
  await open(page, standardFixture());
  await page.evaluate(() => window.__addTask({ kind: 'rest', identity: 'sharp', held: true,
    waitingFor: 'the AI usage limit; tried again at 17:05' }));
  await page.evaluate(() => window.__addTask({ kind: 'reputation', identity: 'sharp', vacancyId: 'b1', held: true,
    waitingFor: 'the AI usage limit; checking whether it has reset' }));
  await expect(page.getByTestId('task-1')).toHaveAttribute('title', en['task.wait.ai_limit'].replace('{time}', '17:05'));
  await expect(page.getByTestId('task-2')).toHaveAttribute('title', en['task.wait.ai_checking']);
});

test('"Age" stands after "Status": today, a week, a month, older, each with its count', async ({ page }) => {
  const fixture = standardFixture();
  fixture.rows.sharp.full.find((r) => r.id === 'a2r').age = 'week';
  fixture.rows.sharp.full.find((r) => r.id === 'b1').age = 'older';
  await open(page, fixture);
  await expect(page.getByTestId('filter-label')).toHaveText(en['filter.legend']);
  await expect(page.getByTestId('age-label')).toHaveText(en['filter.age_legend']);
  await expect(page.getByTestId('age-filter-value')).toHaveText(en['filter.age_all']);
  await page.getByTestId('age-filter').click();
  await expect(page.getByTestId('age-option-today')).toHaveText(`${en['filter.age.today']} (1)`);
  await expect(page.getByTestId('age-option-week')).toHaveText(`${en['filter.age.week']} (1)`);
  await expect(page.getByTestId('age-option-older')).toHaveText(`${en['filter.age.older']} (1)`);
  await page.keyboard.press('Escape');
  await check(page, 'age-filter', ['today', 'week']);
  expect(await lastListing(page)).toEqual(['sharp', view({ ages: ['today', 'week'] })]);
  await expect(byId(page, 'b1')).toHaveCount(0);
  await expect(byId(page, 'a1')).toBeVisible();
});

test('the stub\'s text has one width, so the buttons after it stand in one column', async ({ page }) => {
  await open(page);
  await byId(page, 'a1').getByTestId('btn-applied').click();
  await byId(page, 'a2r').getByTestId('btn-rejected').click();
  await byId(page, 'a2r').getByTestId('reason-save').click();
  const lefts = await Promise.all(['stub-a1', 'stub-a2r'].map((id) =>
    page.getByTestId(id).getByTestId('btn-undo').boundingBox().then((b) => Math.round(b.x))));
  expect(new Set(lefts).size).toBe(1);
});

test('"Score" in Details: a row per part, a cell per point, earned ones bright, axes in one column', async ({ page }) => {
  const fixture = standardFixture();
  fixture.rows.sharp.full.find((r) => r.id === 'a1').view.score_parts = [
    { key: 'stack', points: 4, min: 0, max: 20 },
    { key: 'extra:calm', label: 'calm domain', points: 0, min: 0, max: 6 },
    { key: 'title', points: -8, min: -24, max: 0 },
  ];
  await open(page, fixture);
  const card = byId(page, 'a1');
  await card.locator('details.details > summary').click();
  await card.getByTestId('score-parts').locator('summary').click();
  await expect(card.getByTestId('score-parts').locator('summary')).toHaveText(en['score.summary']);
  await expect(card.getByTestId('score-label-stack')).toHaveText(`${en['score.part.stack']} (+4/+20)`);
  await expect(card.getByTestId('score-label-extra:calm')).toHaveText('calm domain (0/+6)');
  await expect(card.getByTestId('score-label-title')).toHaveText(`${en['score.part.title']} (-8/-24)`);
  const stack = card.getByTestId('score-bar-stack');
  await expect(stack.locator('.score-cell.plus:not(.off)')).toHaveCount(4);
  await expect(stack.locator('.score-cell.plus.off')).toHaveCount(16);
  const title = card.getByTestId('score-bar-title');
  await expect(title.locator('.score-cell.minus:not(.off)')).toHaveCount(8);
  await expect(title.locator('.score-cell.minus.off')).toHaveCount(16);
  const axes = await card.locator('.score-axis').evaluateAll((nodes) => nodes.map((n) => Math.round(n.getBoundingClientRect().x)));
  expect(new Set(axes).size).toBe(1);
  const widths = await card.locator('.score-cell').evaluateAll((nodes) => nodes.map((n) => n.getBoundingClientRect().width));
  expect(new Set(widths).size).toBe(1);
  // the bright minus cells sit next to the axis
  const lastMinus = await title.locator('.score-cell.minus').last().getAttribute('class');
  expect(lastMinus).not.toContain('off');
});

test('Refresh is a button of its own, left of the theme and the language, the same size and icon', async ({ page }) => {
  await open(page);
  const order = await page.locator('header.topbar > .picker')
    .evaluateAll((nodes) => nodes.map((n) => n.dataset.testid));
  expect(order).toEqual(['refresh-slot', 'theme-picker', 'language-picker']);
  const refresh = page.getByTestId('refresh');
  await expect(refresh).toHaveText('\u27F3');
  await expect(refresh).toHaveAttribute('title', en['app.refresh_hint']);
  const size = async (testid) => {
    const box = await page.getByTestId(testid).boundingBox();
    return [box.width, box.height];
  };
  expect(await size('refresh')).toEqual(await size('theme-button'));
  expect(await size('refresh')).toEqual(await size('language-button'));
  await page.getByTestId('menu-button').click();
  await expect(page.getByTestId('menu').getByTestId('refresh')).toHaveCount(0);
});

test('the menu holds Collect, Review feedback, Clean up, Identities, Settings; "Clean up" filters, counts, deletes', async ({ page }) => {
  await open(page);
  const order = await page.locator('.actions > *').evaluateAll((nodes) => nodes.map((n) => n.dataset.testid || n.className));
  expect(order).toEqual(['commands']);
  await command(page, 'cleanup');
  const items = await page.getByTestId('menu').locator('[role="menuitem"]')
    .evaluateAll((nodes) => nodes.map((n) => n.dataset.testid || n.querySelector('[data-testid]').dataset.testid));
  expect(items).toEqual(['run-collect', 'run-feedback', 'cleanup', 'open-identities', 'open-scheduler', 'open-settings']);
  await page.getByTestId('cleanup').click();
  const dialog = page.getByTestId('cleanup-dialog');
  await expect(dialog).toBeVisible();
  await expect(page.getByTestId('cleanup-ages-older')).toBeChecked();
  await expect(page.getByTestId('cleanup-delete')).toBeDisabled();
  await page.getByTestId('cleanup-statuses-expired').check();
  await page.getByTestId('cleanup-count').click();
  expect((await calls(page, 'cleanup')).at(-1)).toEqual(['sharp', { ages: ['older'], statuses: ['expired'], classes: [] }, true]);
  await expect(page.getByTestId('cleanup-outcome')).toContainText(en['cleanup.would_delete'].replace('{n}', '3'));
  await expect(page.getByTestId('cleanup-delete')).toHaveText(en['cleanup.delete_n'].replace('{n}', '3'));
  // a changed filter needs a new count first
  await page.getByTestId('cleanup-classes-rejected').check();
  await expect(page.getByTestId('cleanup-delete')).toBeDisabled();
  await page.getByTestId('cleanup-count').click();
  const before = (await calls(page, 'loadSegments')).length;
  await page.getByTestId('cleanup-delete').click();
  expect((await calls(page, 'cleanup')).at(-1)[2]).toBe(false);
  await expect(page.getByTestId('cleanup-outcome')).toContainText(en['cleanup.deleted'].replace('{n}', '3'));
  expect((await calls(page, 'loadSegments')).length).toBeGreaterThan(before);
  await page.getByTestId('cleanup-close').click();
  await expect(page.getByTestId('cleanup-overlay')).toHaveCount(0);
});

test('a long stage wraps inside the wider menu, the spinner beside it', async ({ page }) => {
  await open(page);
  const stage = 'rescore the top, with company facts (12 345 vacancies) and a long note after it';
  await page.evaluate((s) => window.__setPipeline('sharp', { running: true, stage: s }), stage);
  const button = await command(page, 'run-collect');
  await expect(button).toContainText(stage);
  const menu = await page.getByTestId('menu').boundingBox();
  expect(menu.width).toBeGreaterThanOrEqual(300);
  expect(menu.width).toBeLessThanOrEqual(400);
  const text = await button.locator('.menu-text').boundingBox();
  expect(text.x + text.width).toBeLessThanOrEqual(menu.x + menu.width);   // wrapped, not cut
  expect(text.height).toBeGreaterThan(25);   // two lines or more
});

test('the menu button spins while a clean-up counts', async ({ page }) => {
  await open(page);
  await (await command(page, 'cleanup')).click();
  await page.evaluate(() => { window.__holdCleanup = true; });
  await page.getByTestId('cleanup-statuses-expired').check();
  await page.getByTestId('cleanup-count').click();
  await expect(page.getByTestId('menu-busy')).toBeVisible();
  await expect(page.getByTestId('menu-button')).toHaveAttribute('title', en['cleanup.button']);
  await page.evaluate(() => window.__releaseCleanup());
  await expect(page.getByTestId('menu-busy')).toHaveCount(0);
});


test.describe('"Task scheduler…"', () => {
  test.use({ timezoneId: 'UTC' });

  const SCHEDULES = [
    { id: 1, name: '', what: 'collect', identities: ['all'], args: {}, cron: '0 7 * * *', enabled: true,
      missed: 'catch_up', next_at: '2026-10-22T07:00:00+00:00', last_run_at: '2026-10-21T07:00:05+00:00',
      last_tasks: [12, 13], last_result: 'done', last_note: 'schedule #1 (collect), the run of 2026-10-21 07:00: queued #12, #13' },
    { id: 2, name: 'weekend', what: 'clean', identities: ['sharp'], args: { ages: ['older'] }, cron: '30 9 * * 0,6',
      enabled: false, missed: 'skip', next_at: null, last_run_at: null, last_tasks: [], last_result: null, last_note: null },
  ];

  async function openScheduler(page, schedules = SCHEDULES) {
    await open(page, { ...standardFixture(), schedules });
    await (await command(page, 'open-scheduler')).click();
    await expect(page.getByTestId('scheduler-dialog')).toBeVisible();
  }

  test('lists the schedules: what, for whom, when, the next and the last run; on/off and delete', async ({ page }) => {
    await openScheduler(page);
    const first = page.getByTestId('schedule-1');
    await expect(first).toContainText(`${en['scheduler.what.collect']} · ${en['scheduler.all']}`);
    await expect(page.getByTestId('schedule-when-1')).toHaveText(
      `every day at 07:00 · next 2026-10-22 07:00 · ${en['scheduler.missed.catch_up']}`);
    await expect(page.getByTestId('schedule-last-1')).toHaveText(`last run 2026-10-21 07:00: ${en['task.state.done']}`);
    await expect(page.getByTestId('schedule-last-1')).toHaveAttribute('title', /queued #12, #13/);
    await expect(page.getByTestId('schedule-2')).toContainText(`weekend · ${en['scheduler.what.clean']} · sharp`);
    await expect(page.getByTestId('schedule-when-2')).toHaveText(`Sat, Sun at 09:30 · ${en['scheduler.missed.skip']}`);
    await expect(page.getByTestId('schedule-last-2')).toHaveText(en['scheduler.never']);
    await expect(page.getByTestId('schedule-on-2')).not.toBeChecked();
    await page.getByTestId('schedule-on-2').check();
    expect(await calls(page, 'enableSchedule')).toEqual([[2, true]]);
    await expect(page.getByTestId('schedule-when-2')).toContainText('next 2026-10-22 07:00');
    await page.getByTestId('schedule-remove-1').click();
    expect(await calls(page, 'removeSchedule')).toEqual([[1]]);
    await expect(page.getByTestId('schedule-1')).toHaveCount(0);
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('scheduler-dialog')).toHaveCount(0);
  });

  test('a new schedule: the time as a preset or a cron line, the next runs before saving', async ({ page }) => {
    await openScheduler(page, []);
    await expect(page.getByTestId('schedule-empty')).toHaveText(en['scheduler.empty']);
    await page.getByTestId('schedule-add').click();
    const next = page.getByTestId('schedule-next');
    await expect(next).toHaveText('Next runs: 2026-10-22 07:00 · 2026-10-23 07:00 · 2026-10-24 07:00');
    await page.getByTestId('schedule-time').fill('06:30');
    await expect(next).toContainText('2026-10-22 06:30');

    await page.getByTestId('schedule-preset').selectOption('weekly');
    for (const day of [1, 2, 3, 4, 5]) await page.getByTestId(`schedule-day-${day}`).uncheck();
    await expect(next).toHaveText(en['scheduler.no_days']);
    await expect(page.getByTestId('schedule-save')).toBeDisabled();
    await page.getByTestId('schedule-day-1').check();
    await page.getByTestId('schedule-preset').selectOption('cron');
    const cron = page.getByTestId('schedule-cron');
    await expect(cron).toHaveValue('30 6 * * 1');   // what the preset wrote

    await cron.fill('0 7 * *');
    await expect(next).toContainText('a cron line has 5 fields');
    await expect(page.getByTestId('schedule-save')).toBeDisabled();
    await cron.fill('15 8 * *');
    await cron.press('End');
    await page.keyboard.type(' *');   // the popup redraws with the preview; the field keeps its caret
    await expect(next).toContainText('2026-10-22 08:15');
    await expect(cron).toBeFocused();
    await expect(cron).toHaveValue('15 8 * * *');

    await page.getByTestId('schedule-all').uncheck();
    await expect(page.getByTestId('schedule-problem')).toHaveText(en['scheduler.no_identity']);
    await page.getByTestId('schedule-identity-sharp').check();
    await page.getByTestId('schedule-missed-skip').check();
    await page.getByTestId('schedule-name').fill('mornings');
    await page.getByTestId('schedule-save').click();
    expect(await calls(page, 'saveSchedule')).toEqual([[{
      id: null, what: 'collect', identities: ['sharp'], cron: '15 8 * * *', missed: 'skip', name: 'mornings',
      enabled: true, args: {},
    }]]);
    await expect(page.getByTestId('schedule-1')).toContainText(`mornings · ${en['scheduler.what.collect']} · sharp`);
    await expect(page.getByTestId('schedule-when-1')).toContainText('every day at 08:15');
  });

  test('a clean-up keeps its filters and needs one; a change keeps the schedule off', async ({ page }) => {
    await openScheduler(page);
    await page.getByTestId('schedule-edit-2').click();
    await expect(page.getByTestId('schedule-what')).toHaveValue('clean');
    await expect(page.getByTestId('schedule-preset')).toHaveValue('weekly');
    await expect(page.getByTestId('schedule-day-6')).toBeChecked();
    await expect(page.getByTestId('schedule-day-0')).toBeChecked();
    await expect(page.getByTestId('schedule-day-1')).not.toBeChecked();
    await expect(page.getByTestId('schedule-time')).toHaveValue('09:30');
    await expect(page.getByTestId('schedule-missed-skip')).toBeChecked();
    await expect(page.getByTestId('schedule-identity-sharp')).toBeChecked();
    await expect(page.getByTestId('schedule-ages-older')).toBeChecked();
    await page.getByTestId('schedule-ages-older').uncheck();
    await expect(page.getByTestId('schedule-problem')).toHaveText(en['scheduler.clean_needs_one']);
    await expect(page.getByTestId('schedule-save')).toBeDisabled();
    await page.getByTestId('schedule-statuses-expired').check();
    await page.getByTestId('schedule-save').click();
    expect(await calls(page, 'saveSchedule')).toEqual([[{
      id: 2, what: 'clean', identities: ['sharp'], cron: '30 9 * * 0,6', missed: 'skip', name: 'weekend',
      enabled: false, args: { ages: [], statuses: ['expired'], classes: [] },
    }]]);
    await expect(page.getByTestId('schedule-on-2')).not.toBeChecked();
    // Cancel and Escape leave a form without saving
    await page.getByTestId('schedule-edit-1').click();
    await page.getByTestId('schedule-cancel').click();
    await page.getByTestId('schedule-edit-1').click();
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('schedule-list')).toBeVisible();
    expect((await calls(page, 'saveSchedule')).length).toBe(1);
  });

  test('a save the queue refuses says why, and the form stays', async ({ page }) => {
    await openScheduler(page, []);
    await page.evaluate(() => {
      window.api.saveSchedule = async () => { throw new Error('tools/taskq.py: taskq schedule: invalid identity: X'); };
    });
    await page.getByTestId('schedule-add').click();
    await expect(page.getByTestId('schedule-next')).toContainText('2026-10-22');
    await page.getByTestId('schedule-save').click();
    await expect(page.getByTestId('schedule-error')).toContainText('invalid identity');
    await expect(page.getByTestId('schedule-form')).toBeVisible();
  });
});
