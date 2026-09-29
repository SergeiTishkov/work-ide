'use strict';
// The real interface in a headless browser, with window.api mocked: each test
// clicks what a person clicks and checks what the UI asked the rest of the
// world to do. No agent runs, no tokens are spent.
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { test, expect } = require('@playwright/test');
const { installMockApi, standardFixture } = require('./mock-api');
const ru = require('../../renderer/locales/ru.js');

const PAGE = pathToFileURL(path.join(__dirname, '..', '..', 'renderer', 'index.html')).href;

async function open(page, fixture = standardFixture()) {
  await page.addInitScript(installMockApi, fixture);
  await page.goto(PAGE);
  await expect(page.getByTestId('identity-tab-kisel')).toBeVisible();
}

function calls(page, name) {
  return page.evaluate((n) => window.__calls.filter((c) => c.name === n).map((c) => c.args), name);
}

const byId = (page, id) => page.getByTestId(`vacancy-${id}`);

test('opens on the first identity, its default market, fresh without feedback', async ({ page }) => {
  await open(page);
  await expect(page.getByTestId('identity-tab-kisel')).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByTestId('segment-tab-full')).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByTestId('filter-fresh_new')).toBeChecked();
  expect((await calls(page, 'loadListing'))[0]).toEqual(['kisel', 'full', 'fresh_new']);
  await expect(page.getByTestId('list').locator('article')).toHaveCount(3);   // a1, a2r, b1
  await expect(byId(page, 'a3')).toHaveCount(0);   // not fresh
  await expect(byId(page, 'x1')).toHaveCount(0);   // has feedback
  await expect(page).toHaveTitle(ru['app.title']);
});

test('sections follow the class order, with their titles from the locale', async ({ page }) => {
  await open(page);
  const titles = await page.locator('.class-section h2').allTextContents();
  expect(titles).toEqual([ru['class.hot_lead'], ru['class.worth_a_look']]);
});

test('"Collect vacancies" starts the agent for this identity and locks the buttons', async ({ page }) => {
  await open(page);
  await page.getByTestId('run-collect').click();
  expect(await calls(page, 'startRun')).toEqual([[{ identity: 'kisel', kind: 'collect' }]]);
  await expect(page.getByTestId('run-collect')).toBeDisabled();
  await expect(page.getByTestId('run-feedback')).toBeDisabled();
  await expect(page.getByTestId('run-stop')).toBeVisible();

  await page.evaluate(() => window.__emitRunEvent({ type: 'output', text: 'fetching sources' }));
  await expect(page.getByTestId('run-log')).toContainText('fetching sources');

  await page.getByTestId('run-stop').click();
  expect(await calls(page, 'stopRun')).toHaveLength(1);

  await page.evaluate(() => window.__emitRunEvent({ type: 'exit', code: 0, identity: 'kisel', kind: 'collect' }));
  await expect(page.getByTestId('run-collect')).toBeEnabled();
  await expect(page.getByTestId('run-status')).toContainText(ru['run.finished']);
  expect((await calls(page, 'listIdentities')).length).toBe(2);   // reloaded after the run
});

test('buttons are locked on every identity while any run is going', async ({ page }) => {
  await open(page);
  await page.getByTestId('run-collect').click();
  await page.getByTestId('identity-tab-pjoice').click();
  await expect(page.getByTestId('identity-name')).toHaveText('Part-time side work');
  await expect(page.getByTestId('run-collect')).toBeDisabled();
});

test('"Review feedback" shows the pending count and starts the feedback run', async ({ page }) => {
  await open(page);
  await expect(page.getByTestId('run-feedback')).toHaveText(ru['run.feedback'].replace('{n}', '1'));
  await page.getByTestId('run-feedback').click();
  expect(await calls(page, 'startRun')).toEqual([[{ identity: 'kisel', kind: 'feedback' }]]);
});

test('"Review feedback" is disabled when nothing is pending', async ({ page }) => {
  await open(page);
  await page.getByTestId('identity-tab-pjoice').click();
  await expect(page.getByTestId('run-feedback')).toBeDisabled();
});

test('"Wrong pick" asks for a reason, saves it, and leaves an undoable stub', async ({ page }) => {
  await open(page);
  const row = byId(page, 'a1');
  await row.getByTestId('btn-bugged').click();
  expect(await calls(page, 'setFeedback')).toEqual([]);   // nothing saved before "Save"
  await expect(row.getByTestId('reason-input')).toHaveAttribute('placeholder', ru['reason.bugged']);
  await row.getByTestId('reason-input').fill('A Java role, .NET only in the company blurb');
  await row.getByTestId('reason-save').click();

  expect(await calls(page, 'setFeedback')).toEqual([
    ['kisel', 'a1', 'bugged', 'A Java role, .NET only in the company blurb']]);
  await expect(byId(page, 'a1')).toHaveCount(0);
  const stub = page.getByTestId('stub-a1');
  await expect(stub).toContainText(ru['stub.marked'].replace('{status}', ru['status.bugged']));
  await expect(page.getByTestId('run-feedback')).toHaveText(ru['run.feedback'].replace('{n}', '2'));

  await stub.getByTestId('btn-undo').click();
  expect((await calls(page, 'setFeedback')).at(-1)).toEqual(['kisel', 'a1', 'new', null]);
  await expect(byId(page, 'a1')).toBeVisible();
  await expect(page.getByTestId('stub-a1')).toHaveCount(0);
});

test('"Not for me" with an empty reason is saved without one', async ({ page }) => {
  await open(page);
  await byId(page, 'a2r').getByTestId('btn-rejected').click();
  await byId(page, 'a2r').getByTestId('reason-save').click();
  expect(await calls(page, 'setFeedback')).toEqual([['kisel', 'a2r', 'rejected', '']]);
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
  expect(await calls(page, 'setFeedback')).toEqual([['kisel', 'a1', 'applied', null]]);
  await expect(page.getByTestId('reason-form')).toHaveCount(0);
  await expect(page.getByTestId('stub-a1')).toBeVisible();
});

test('filters ask for their own list and show their counts', async ({ page }) => {
  await open(page);
  await expect(page.getByTestId('filter-count-all')).toHaveText('(5)');
  await expect(page.getByTestId('filter-count-bugged')).toHaveText('(1)');
  await page.getByTestId('filter-bugged').check();
  expect((await calls(page, 'loadListing')).at(-1)).toEqual(['kisel', 'full', 'bugged']);
  await expect(byId(page, 'x1')).toBeVisible();
  await expect(byId(page, 'x1').getByTestId('status-badge')).toHaveText(ru['status.bugged']);

  await byId(page, 'x1').getByTestId('btn-undo').click();
  expect((await calls(page, 'setFeedback')).at(-1)).toEqual(['kisel', 'x1', 'new', null]);
});

test('each market of each identity keeps its own filter', async ({ page }) => {
  await open(page);
  await page.getByTestId('filter-all').check();
  await page.getByTestId('segment-tab-uk').click();
  await expect(page.getByTestId('filter-fresh_new')).toBeChecked();
  expect((await calls(page, 'loadListing')).at(-1)).toEqual(['kisel', 'uk', 'fresh_new']);

  await page.getByTestId('segment-tab-full').click();
  await expect(page.getByTestId('filter-all')).toBeChecked();

  await page.getByTestId('identity-tab-pjoice').click();
  await expect(page.getByTestId('filter-fresh_new')).toBeChecked();
  await page.getByTestId('filter-applied').check();

  await page.getByTestId('identity-tab-kisel').click();
  await expect(page.getByTestId('segment-tab-full')).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByTestId('filter-all')).toBeChecked();
  await page.getByTestId('identity-tab-pjoice').click();
  await expect(page.getByTestId('filter-applied')).toBeChecked();
});

test('changing the filter clears stubs', async ({ page }) => {
  await open(page);
  await byId(page, 'a1').getByTestId('btn-applied').click();
  await expect(page.getByTestId('stub-a1')).toBeVisible();
  await page.getByTestId('filter-all').check();
  await expect(page.getByTestId('stub-a1')).toHaveCount(0);
  await expect(byId(page, 'a1').getByTestId('status-badge')).toHaveText(ru['status.applied']);
});

test('an identity never collected says so and offers to collect', async ({ page }) => {
  await open(page);
  await page.getByTestId('identity-tab-newbie').click();
  await expect(page.getByTestId('never-collected')).toHaveText(ru['identity.never_collected']);
  await page.getByTestId('run-collect').click();
  expect(await calls(page, 'startRun')).toEqual([[{ identity: 'newbie', kind: 'collect' }]]);
});

test('a vacancy title opens in the browser, not in the app', async ({ page }) => {
  await open(page);
  await byId(page, 'a1').getByTestId('title').click();
  expect(await calls(page, 'openExternal')).toEqual([['https://example.test/a1']]);
});

test('badges: fresh and needs a manual check', async ({ page }) => {
  await open(page);
  await expect(byId(page, 'a2r').getByTestId('badge-review')).toHaveText(ru['badge.manual_review']);
  await expect(byId(page, 'a1').getByTestId('badge-fresh')).toHaveText(ru['badge.fresh']);
  await expect(byId(page, 'a1').getByTestId('badge-review')).toHaveCount(0);
});

test('a missing claude is explained', async ({ page }) => {
  const fixture = standardFixture();
  fixture.startRunReply = { ok: false, error: 'claude_not_found' };
  await open(page, fixture);
  await page.getByTestId('run-collect').click();
  await expect(page.getByTestId('error')).toContainText(ru['run.claude_not_found']);
  await expect(page.getByTestId('run-collect')).toBeEnabled();
});

test('data text is shown as text, never as markup', async ({ page }) => {
  const fixture = standardFixture();
  fixture.rows.kisel.full[0].view.highlights = ['<img src=x onerror="window.__xss=1"> _fine_'];
  await open(page, fixture);
  await expect(byId(page, 'a1').locator('.highlights em')).toHaveText('fine');
  expect(await page.evaluate(() => window.__xss)).toBeUndefined();
});

test('every row shows when it was posted and when we first downloaded it', async ({ page }) => {
  await open(page);
  const row = byId(page, 'a1');
  await expect(row.getByTestId('posted-on')).toHaveText(ru['row.posted_on'].replace('{date}', '20.09.2026'));
  await expect(row.getByTestId('first-seen-on'))
    .toHaveText(ru['row.first_seen_on'].replace('{date}', '28.09.2026'));
  await expect(byId(page, 'a2r').getByTestId('posted-on'))
    .toHaveText(ru['row.posted_on'].replace('{date}', ru['row.date_unknown']));
});

test('"Open the vacancy link" hands the URL to the system browser, marked or not', async ({ page }) => {
  await open(page);
  const button = byId(page, 'a1').getByTestId('btn-open');
  await expect(button).toHaveText(ru['action.open']);
  await button.click();
  expect(await calls(page, 'openExternal')).toEqual([['https://example.test/a1']]);
  expect(await calls(page, 'setFeedback')).toEqual([]);   // opening is not an answer

  await page.getByTestId('filter-bugged').check();
  await byId(page, 'x1').getByTestId('btn-open').click();
  expect((await calls(page, 'openExternal')).at(-1)).toEqual(['https://example.test/x1']);
});

test('a pipeline run going anywhere shows on the button and the tab, then clears', async ({ page }) => {
  await open(page);
  await page.evaluate(() => window.__setPipeline('kisel',
    { running: true, stage: 'check links', startedAt: '2026-09-30T00:23:41+00:00' }));
  const button = page.getByTestId('run-collect');
  await expect(button).toContainText(ru['run.collecting_stage'].replace('{stage}', 'check links'));
  await expect(button).toBeDisabled();
  await expect(button.getByTestId('collect-indicator')).toBeVisible();
  await expect(page.getByTestId('identity-tab-kisel').getByTestId('tab-collecting')).toBeVisible();
  await expect(page.getByTestId('identity-tab-pjoice').getByTestId('tab-collecting')).toHaveCount(0);

  const loadsBefore = (await calls(page, 'loadSegments')).length;
  await page.evaluate(() => window.__setPipeline('kisel', { running: false }));
  await expect(button).toHaveText(ru['run.collect']);
  await expect(button).toBeEnabled();
  await expect(page.getByTestId('tab-collecting')).toHaveCount(0);
  await expect.poll(async () => (await calls(page, 'loadSegments')).length).toBeGreaterThan(loadsBefore);
});

test('a reason being typed survives the indicator re-rendering the list', async ({ page }) => {
  await open(page);
  await byId(page, 'a1').getByTestId('btn-bugged').click();
  await byId(page, 'a1').getByTestId('reason-input').fill('half typed');
  await page.evaluate(() => window.__setPipeline('kisel', { running: true, stage: 'rescore' }));
  await expect(page.getByTestId('run-collect')).toContainText('rescore');
  await expect(byId(page, 'a1').getByTestId('reason-input')).toHaveValue('half typed');
});

test('"Refresh" reloads the interface and keeps the tab, market and filter', async ({ page }) => {
  await open(page);
  await page.getByTestId('identity-tab-kisel').click();
  await page.getByTestId('segment-tab-uk').click();
  await page.getByTestId('filter-all').check();
  await expect(page.getByTestId('refresh')).toHaveText(ru['app.refresh']);
  await page.evaluate(() => { window.__beforeRefresh = true; });

  await page.getByTestId('refresh').click();
  await expect(page.getByTestId('segment-tab-uk')).toHaveAttribute('aria-selected', 'true');
  expect(await page.evaluate(() => window.__beforeRefresh)).toBeUndefined();   // a new page
  await expect(page.getByTestId('filter-all')).toBeChecked();
  expect((await calls(page, 'loadListing'))[0]).toEqual(['kisel', 'uk', 'all']);
});
