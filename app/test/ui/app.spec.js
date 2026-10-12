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
const ru = require('../../renderer/locales/ru.js');

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
const lastListing = async (page) => { await settled(page); return (await calls(page, 'loadListing')).at(-1); };
// "Show" closed: every status and both freshness rows checked; the start
const SHOW_ALL = [ru['filter.new'], ru['filter.group.applications'], ru['filter.group.denied']].join(' · ');
const SHOW_DEFAULT = `${ru['filter.fresh']} · ${ru['filter.new']}`;

test('opens on the first identity, every market, fresh vacancies not applied or denied', async ({ page }) => {
  await open(page);
  await expect(page.getByTestId('identity-tab-sharp')).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByTestId('segment-filter-value')).toHaveText('Everything');
  await expect(page.getByTestId('filter-value')).toHaveText(SHOW_DEFAULT);
  expect((await calls(page, 'loadListing'))[0]).toEqual(['sharp', VIEW]);
  await expect(page.getByTestId('list').locator('article')).toHaveCount(3);   // a1, a2r, b1
  await expect(byId(page, 'a3')).toHaveCount(0);   // not fresh
  await expect(byId(page, 'x1')).toHaveCount(0);   // has feedback
  await expect(page).toHaveTitle(ru['app.title']);
});

test('sections follow the class order, with their titles from the locale', async ({ page }) => {
  await open(page);
  const titles = await page.locator('.class-section h2 .section-title').allTextContents();
  expect(titles).toEqual([ru['class.hot_lead'], ru['class.worth_a_look']]);
});

test('"Collect vacancies" starts the agent for this identity and locks the buttons', async ({ page }) => {
  await open(page);
  await page.getByTestId('run-collect').click();
  expect(await calls(page, 'startRun')).toEqual([[{ identity: 'sharp', kind: 'collect' }]]);
  await expect(page.getByTestId('run-collect')).toBeDisabled();
  await expect(page.getByTestId('run-stop')).toBeVisible();

  await page.evaluate(() => window.__emitRunEvent({ type: 'output', text: 'fetching sources' }));
  await expect(page.getByTestId('run-log')).toContainText('fetching sources');

  await page.getByTestId('run-stop').click();
  expect(await calls(page, 'stopRun')).toHaveLength(1);

  await page.evaluate(() => window.__emitRunEvent({ type: 'exit', code: 0, identity: 'sharp', kind: 'collect' }));
  await expect(page.getByTestId('run-collect')).toBeEnabled();
  await expect(page.getByTestId('run-status')).toContainText(ru['run.finished']);
  expect((await calls(page, 'listIdentities')).length).toBe(2);   // reloaded after the run
});

test('buttons are locked on every identity while any run is going', async ({ page }) => {
  await open(page);
  await page.getByTestId('run-collect').click();
  await page.getByTestId('identity-tab-partsharp').click();
  await expect(page.getByTestId('identity-name')).toHaveText('Part-time side work');
  await expect(page.getByTestId('run-collect')).toBeDisabled();
});

// The owner, 2026-10-07: the review is started from an agent session, where
// the person follows and steers it; the button only says so.
test('"Review feedback" shows the pending count and starts nothing', async ({ page }) => {
  await open(page);
  const button = page.getByTestId('run-feedback');
  const tip = page.getByTestId('run-feedback-tip');
  const hint = ru['run.feedback_hint'].replace('{identity}', 'sharp');
  await expect(button).toHaveText(ru['run.feedback'].replace('{n}', '1'));
  await expect(button).toHaveAttribute('aria-disabled', 'true');
  await expect(tip).toBeHidden();

  await button.hover();
  await expect(tip).toBeVisible();
  await expect(tip).toHaveText(hint);

  // A click opens it without the hover: the mouse stays away. Playwright's own
  // click refuses an aria-disabled button, so the event is sent.
  await page.mouse.move(0, 0);
  await expect(tip).toBeHidden();
  await button.dispatchEvent('click');
  await expect(tip).toBeVisible();
  await button.hover();
  await page.mouse.move(0, 0);
  await expect(tip).toBeHidden();
  expect(await calls(page, 'startRun')).toEqual([]);
});

test('"Review feedback" names the identity of the open tab', async ({ page }) => {
  await open(page);
  await page.getByTestId('identity-tab-partsharp').click();
  await expect(page.getByTestId('run-feedback')).toHaveText(ru['run.feedback'].replace('{n}', '0'));
  await expect(page.getByTestId('run-feedback-tip'))
    .toHaveText(ru['run.feedback_hint'].replace('{identity}', 'partsharp'));
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
    ['sharp', 'a1', 'bugged', 'A Java role, .NET only in the company blurb']]);
  await expect(byId(page, 'a1')).toHaveCount(0);
  const stub = page.getByTestId('stub-a1');
  await expect(stub).toContainText(ru['stub.marked'].replace('{status}', ru['status.bugged']));
  await expect(page.getByTestId('run-feedback')).toHaveText(ru['run.feedback'].replace('{n}', '2'));

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
  await expect(byId(page, 'x1').getByTestId('status-badge')).toHaveText(ru['status.bugged']);

  await byId(page, 'x1').getByTestId('btn-undo').click();
  expect((await calls(page, 'stepBack')).at(-1)).toEqual(['sharp', 'x1']);
});

test('each identity keeps its own view', async ({ page }) => {
  await open(page);
  await choose(page, 'filter', 'all');
  await choose(page, 'segment-filter', 'uk');
  expect(await lastListing(page)).toEqual(['sharp', view({ segments: ['uk'], statuses: STATUSES, fresh: BOTH })]);
  await expect(page.getByTestId('segment-filter-value')).toHaveText('Velikobritaniya');

  await page.getByTestId('identity-tab-partsharp').click();
  await expect(page.getByTestId('filter-value')).toHaveText(SHOW_DEFAULT);
  await expect(page.getByTestId('segment-filter-value')).toHaveText('Everything');   // its one market
  await choose(page, 'filter', 'applied');

  await page.getByTestId('identity-tab-sharp').click();
  await expect(page.getByTestId('segment-filter-value')).toHaveText('Velikobritaniya');
  await expect(page.getByTestId('filter-value')).toHaveText(SHOW_ALL);
  await page.getByTestId('identity-tab-partsharp').click();
  await expect(page.getByTestId('filter-value')).toHaveText(ru['filter.applied']);
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
  await expect(page.getByTestId('segment-filter-value')).toHaveText(ru['filter.none']);
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
    .toHaveText([ru['filter.group.freshness'], ru['filter.group.applications'], ru['filter.group.denied']]);
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
  await expect(page.getByTestId('filter-master-denied')).toHaveText(`${ru['filter.all']} (1)`);

  await page.getByTestId('filter-master-denied').click();
  await expect(page.getByTestId('filter-option-bugged')).toHaveAttribute('data-state', 'on');
  expect(await lastListing(page)).toEqual(['sharp', view({ statuses: ['new', 'rejected', 'bugged', 'expired'] })]);
  await expect(byId(page, 'x1')).toBeVisible();
  await expect(page.getByTestId('filter-value'))
    .toHaveText(`${ru['filter.fresh']} · ${ru['filter.new']} · ${ru['filter.group.denied']}`);

  await page.getByTestId('filter-option-new').click();
  await expect(page.getByTestId('filter-option-new')).toHaveAttribute('data-state', 'off');
  await page.getByTestId('filter-option-expired').click();
  await expect(page.getByTestId('filter-master-denied')).toHaveAttribute('data-state', 'partial');
  await expect(page.getByTestId('filter-value'))
    .toHaveText([ru['filter.fresh'], ru['filter.rejected'], ru['filter.bugged']].join(' · '));
  await page.getByTestId('filter-master-fresh').click();   // partly on: on
  await expect(page.getByTestId('filter-master-fresh')).toHaveAttribute('data-state', 'on');
  expect(await lastListing(page)).toEqual(['sharp', view({ statuses: ['rejected', 'bugged'], fresh: BOTH })]);
  await page.getByTestId('filter-master-fresh').click();   // on: off
  await expect(page.getByTestId('filter-value')).toHaveText(ru['filter.none']);
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
  expect(await lastListing(page)).toEqual(['sharp', view({ fits: ['worth_a_look'] })]);
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
  await expect(tip).toHaveText(ru['stub.removed_in'].replace('{n}', '30'));
  await page.clock.runFor(10000);
  await expect(tip).toHaveText(ru['stub.removed_in'].replace('{n}', '20'));
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
  await expect(byId(page, 'a1').getByTestId('status-badge')).toHaveText(ru['status.applied']);
});

test('an identity never collected says so and offers to collect', async ({ page }) => {
  await open(page);
  await page.getByTestId('identity-tab-newbie').click();
  await expect(page.getByTestId('never-collected')).toHaveText(ru['identity.never_collected']);
  await page.getByTestId('run-collect').click();
  expect(await calls(page, 'startRun')).toEqual([[{ identity: 'newbie', kind: 'collect' }]]);
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
  await expect(row.getByTestId('btn-copy-url')).toHaveText(ru['action.copied']);
  await expect(row.getByTestId('btn-copy-url')).toHaveText(ru['action.copy_url']);
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
  fixture.rows.sharp.full[0].view.highlights = ['<img src=x onerror="window.__xss=1"> _fine_'];
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

  await choose(page, 'filter', 'bugged');
  await byId(page, 'x1').getByTestId('btn-open').click();
  expect((await calls(page, 'openExternal')).at(-1)).toEqual(['https://example.test/x1']);
});

test('a pipeline run going anywhere shows on the button and the tab, then clears', async ({ page }) => {
  await open(page);
  await page.evaluate(() => window.__setPipeline('sharp',
    { running: true, stage: 'check links', startedAt: '2026-09-30T00:23:41+00:00' }));
  const button = page.getByTestId('run-collect');
  await expect(button).toContainText(ru['run.collecting_stage'].replace('{stage}', 'check links'));
  await expect(button).toBeDisabled();
  await expect(button.getByTestId('collect-indicator')).toBeVisible();
  await expect(page.getByTestId('identity-tab-sharp').getByTestId('tab-collecting')).toBeVisible();
  await expect(page.getByTestId('identity-tab-partsharp').getByTestId('tab-collecting')).toHaveCount(0);

  const loadsBefore = (await calls(page, 'loadSegments')).length;
  await page.evaluate(() => window.__setPipeline('sharp', { running: false }));
  await expect(button).toHaveText(ru['run.collect']);
  await expect(button).toBeEnabled();
  await expect(page.getByTestId('tab-collecting')).toHaveCount(0);
  await expect.poll(async () => (await calls(page, 'loadSegments')).length).toBeGreaterThan(loadsBefore);
});

test('a reason being typed survives the indicator re-rendering the list', async ({ page }) => {
  await open(page);
  await byId(page, 'a1').getByTestId('btn-bugged').click();
  await byId(page, 'a1').getByTestId('reason-input').fill('half typed');
  await page.evaluate(() => window.__setPipeline('sharp', { running: true, stage: 'rescore' }));
  await expect(page.getByTestId('run-collect')).toContainText('rescore');
  await expect(byId(page, 'a1').getByTestId('reason-input')).toHaveValue('half typed');
});

test('"Refresh" reloads the interface and keeps the tab and the view', async ({ page }) => {
  await open(page);
  await page.getByTestId('identity-tab-sharp').click();
  await choose(page, 'segment-filter', 'uk');
  await choose(page, 'filter', 'all');
  await expect(page.getByTestId('refresh')).toHaveText(ru['app.refresh']);
  await page.evaluate(() => { window.__beforeRefresh = true; });

  await page.getByTestId('refresh').click();
  await expect(page.getByTestId('segment-filter-value')).toHaveText('Velikobritaniya');
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

test('"Not applied or denied" from every run lists every unanswered vacancy, fresh or not', async ({ page }) => {
  await open(page);
  await expect(page.getByTestId('filter-option-new')).toHaveText(`${ru['filter.new']} (3)`);   // fresh ones
  await check(page, 'filter', ['fresh', 'earlier', 'new']);
  expect(await lastListing(page)).toEqual(['sharp', view({ fresh: BOTH })]);
  await expect(page.getByTestId('filter-option-new')).toHaveText(`${ru['filter.new']} (4)`);   // a1, a2r, a3, b1
  await expect(page.getByTestId('filter-value')).toHaveText(ru['filter.new']);
  await expect(page.getByTestId('list').locator('article')).toHaveCount(4);
  await expect(byId(page, 'a3')).toBeVisible();   // not fresh
  await expect(byId(page, 'x1')).toHaveCount(0);   // has feedback
});

test('a capped class says how much is shown and brings ten more at a time', async ({ page }) => {
  await open(page, manyHotLeads(30));
  const section = page.getByTestId('section-hot_lead');
  const count = page.getByTestId('section-count-hot_lead');
  const more = ru['list.show_more'].replace('{n}', '10');
  await expect(count).toHaveText(fill(ru['list.shown_of'], { shown: 15, total: 30, n: 10, button: more }));
  await expect(page.getByTestId('show-more-hot_lead')).toHaveText(more);
  await expect(section.locator('article')).toHaveCount(15);
  await expect(page.getByTestId('scroll-more-hot_lead')).toHaveCount(0);   // every class: buttons only

  await page.getByTestId('show-more-hot_lead').click();
  expect(await lastListing(page)).toEqual(['sharp', VIEW, { shown: { hot_lead: 25 } }]);
  await expect(section.locator('article')).toHaveCount(25);
  const five = ru['list.show_more'].replace('{n}', '5');
  await expect(count).toHaveText(fill(ru['list.shown_of'], { shown: 25, total: 30, n: 5, button: five }));

  await page.getByTestId('show-more-hot_lead').click();
  await expect(section.locator('article')).toHaveCount(30);
  await expect(count).toHaveText(fill(ru['list.shown_all'], { n: 30 }));
  await expect(page.getByTestId('show-more-hot_lead')).toHaveCount(0);

  await page.getByTestId('show-less-hot_lead').click();
  await expect(section.locator('article')).toHaveCount(15);
  await expect(page.getByTestId('show-less-hot_lead')).toHaveCount(0);
  await expect(page.getByTestId('section-count-worth_a_look')).toHaveText(fill(ru['list.shown_all'], { n: 1 }));
});

test('"Fit" narrows the list to one class, and the other filters count within it', async ({ page }) => {
  await open(page);
  await expect(page.getByTestId('fit-label')).toHaveText(ru['filter.fit_legend']);
  await expect(page.getByTestId('fit-filter-value')).toHaveText(ru['filter.fit_all']);
  await expect(page.getByTestId('fit-option-all')).toHaveText(`${ru['filter.fit_all']} (3)`);
  await expect(page.getByTestId('fit-option-hot_lead')).toHaveText(`${ru['class.hot_lead']} (2)`);
  await expect(page.getByTestId('fit-option-worth_a_look')).toHaveText(`${ru['class.worth_a_look']} (1)`);

  await choose(page, 'fit-filter', 'hot_lead');
  await expect(page.getByTestId('section-worth_a_look')).toHaveCount(0);
  await expect(page.getByTestId('section-hot_lead').locator('article')).toHaveCount(2);
  const hot = ['sharp', view({ fits: ['hot_lead'] })];
  expect(await lastListing(page)).toEqual(hot);
  expect((await calls(page, 'listingCounts')).at(-1)).toEqual(hot);
  expect((await calls(page, 'listSources')).at(-1)).toEqual(hot);
  await expect(page.getByTestId('filter-option-new')).toContainText('(2)');
  await expect(page.getByTestId('source-option-devitjobs')).toHaveCount(0);   // b1 is worth a look
  await expect(page.getByTestId('fit-option-worth_a_look')).toHaveText(`${ru['class.worth_a_look']} (1)`);

  // with the status filter: "All" adds a3 (not fresh) and x1 (a wrong pick)
  await choose(page, 'filter', 'all');
  await expect(page.getByTestId('fit-filter-value')).toHaveText(ru['class.hot_lead']);
  await expect(page.getByTestId('section-hot_lead').locator('article')).toHaveCount(4);
  // and with the source
  await choose(page, 'source-filter', 'devitjobs');
  await expect(page.getByTestId('list').locator('article')).toHaveCount(1);   // x1
  await expect(byId(page, 'x1')).toBeVisible();

  await page.getByTestId('refresh').click();
  await expect(page.getByTestId('fit-filter-value')).toHaveText(ru['class.hot_lead']);
});

test('one class chosen: the scroll brings ten more at a time', async ({ page }) => {
  await page.setViewportSize({ width: 1000, height: 700 });
  await open(page, manyHotLeads(40));
  await choose(page, 'fit-filter', 'hot_lead');
  const section = page.getByTestId('section-hot_lead');
  await expect(section.locator('article')).toHaveCount(15);
  await expect(page.getByTestId('section-count-hot_lead'))
    .toHaveText(fill(ru['list.shown_scroll'], { shown: 15, total: 40, n: 10 }));
  await expect(page.getByTestId('show-more-hot_lead')).toBeVisible();   // the button still works

  for (const shown of [25, 35, 40]) {
    await page.getByTestId('scroll-more-hot_lead').scrollIntoViewIfNeeded();
    await expect(section.locator('article')).toHaveCount(shown);
  }
  await expect(page.getByTestId('scroll-more-hot_lead')).toHaveCount(0);
  await expect(page.getByTestId('section-count-hot_lead')).toHaveText(fill(ru['list.shown_all'], { n: 40 }));
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
  await expect(page.getByTestId('run-collect')).toBeVisible();
});

test('until the identities arrive the window shows a spinner, not "no identities"', async ({ page }) => {
  // Reported 2026-10-03: after a reload the start screen ("No identities yet,
  // see docs/ONBOARDING.md") flashed for a second before the tabs appeared.
  const fixture = standardFixture();
  fixture.holdIdentities = true;
  await page.addInitScript(installMockApi, fixture);
  await page.goto(PAGE);
  await expect(page.getByTestId('loading')).toBeVisible();
  await expect(page.getByTestId('loading')).toContainText(ru['app.loading']);
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
  await expect(button).toHaveText(ru['action.expired']);
  await button.click();
  expect(await calls(page, 'setFeedback')).toEqual([['sharp', 'a1', 'expired', null]]);
  await expect(page.getByTestId('reason-form')).toHaveCount(0);
  await expect(page.getByTestId('stub-a1'))
    .toContainText(ru['stub.marked'].replace('{status}', ru['status.expired']));
  await expect(page.getByTestId('filter-option-expired')).toContainText('(1)');

  await choose(page, 'filter', 'expired');
  expect(await lastListing(page)).toEqual(['sharp', view({ statuses: ['expired'], fresh: BOTH })]);
  await expect(byId(page, 'a1').getByTestId('status-badge')).toHaveText(ru['status.expired']);
  await byId(page, 'a1').getByTestId('btn-undo').click();
  expect((await calls(page, 'stepBack')).at(-1)).toEqual(['sharp', 'a1']);
});

// --- the source filter (the owner, 2026-10-04) --------------------------------

test('"Source" lists the boards of the current filter, each with its count', async ({ page }) => {
  await open(page);
  await expect(page.getByTestId('source-label')).toHaveText(ru['filter.source_legend']);
  await expect(page.getByTestId('source-filter-value')).toHaveText(ru['filter.source_all']);
  await expect(page.getByTestId('source-option-all')).toHaveText(`${ru['filter.source_all']} (3)`);
  await expect(page.getByTestId('source-option-linkedin')).toHaveText('linkedin.com (2)');
  await expect(page.getByTestId('source-option-devitjobs')).toHaveText('devitjobs.uk, devitjobs.com (1)');
  expect(await calls(page, 'listSources')).toContainEqual(['sharp', VIEW]);
});

test('the details open with the website the vacancy came from', async ({ page }) => {
  await open(page);
  const details = byId(page, 'b1').locator('details');
  await details.locator('summary').click();
  await expect(details.locator('li').first()).toHaveText(`${ru['row.source']}: devitjobs.uk, devitjobs.com`);
  await expect(byId(page, 'a1').getByTestId('details-source')).toHaveText(`${ru['row.source']}: linkedin.com`);
});

test('an exclusivity clause is a line in the details, not a refusal', async ({ page }) => {
  await open(page);
  await byId(page, 'b1').locator('details summary').click();
  await expect(byId(page, 'b1').getByTestId('details-exclusivity'))
    .toHaveText(`${ru['row.exclusivity']}: moonlighting prohibited`);
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

test('"Generate CV" sits between "Copy URL" and "Generate Cover Letter" and opens what it made', async ({ page }) => {
  const fixture = standardFixture();
  fixture.holdCv = true;
  fixture.cvReply = {
    ok: true, pages: 3, docx: '/home/me/Downloads/CV.docx', pdf: '/home/me/Downloads/CV.pdf',
    findings: [{ kind: 'term', text: 'Kafka', where: 'Skills', message: 'not found in either CV' }],
    warnings: [], removed_for_length: ['Contoso: Fixed flaky tests.'],
    report: { gaps: ['Kubernetes'], from_parent: ['interviewed Go developers'], notes: [] },
  };
  await open(page, fixture);
  const row = byId(page, 'a1');
  const ids = await row.locator('.answers button').evaluateAll((b) => b.map((x) => x.dataset.testid));
  expect(ids.slice(0, 5)).toEqual(['btn-open', 'btn-copy-url', 'btn-generate-cv', 'btn-generate-letter', 'btn-applied']);

  await row.getByTestId('btn-generate-cv').click();
  await expect(row.getByTestId('cv-form')).toBeVisible();
  expect(await calls(page, 'generateCv')).toEqual([]);
  await row.getByTestId('btn-generate-cv').click();
  await expect(row.getByTestId('cv-form')).toHaveCount(0);
  await expect(row.getByTestId('btn-generate-cv')).toHaveText(ru['action.generating_cv']);
  await expect(row.getByTestId('btn-generate-cv')).toBeDisabled();
  // one at a time: the other cards wait too
  await expect(byId(page, 'a2r').getByTestId('btn-generate-cv')).toBeDisabled();
  expect(await calls(page, 'generateCv')).toEqual([['sharp', 'a1', '']]);

  await page.evaluate(() => window.__releaseCv());
  await expect(row.getByTestId('btn-generate-cv')).toHaveText(ru['action.cv_generated']);
  await expect(row.getByTestId('btn-generate-cv')).toBeEnabled();
  await expect(row.getByTestId('cv-summary')).toHaveText(ru['cv.ready_pages'].replace('{pages}', '3'));
  await expect(row.getByTestId('cv-findings')).toContainText('Kafka');
  await expect(row.getByTestId('cv-gaps')).toContainText('Kubernetes');
  await expect(row.getByTestId('cv-from-parent')).toContainText('interviewed Go developers');
  await expect(row.getByTestId('cv-removed')).toContainText('Contoso: Fixed flaky tests.');
  await expect(row.getByTestId('cv-notes')).toHaveCount(0);   // empty lists are not shown

  await row.getByTestId('cv-open-pdf').click();
  await row.getByTestId('cv-show-folder').click();
  expect(await calls(page, 'openCvFile')).toEqual([['/home/me/Downloads/CV.pdf']]);
  expect(await calls(page, 'showCvFile')).toEqual([['/home/me/Downloads/CV.pdf']]);
  await row.getByTestId('cv-close').click();
  await expect(row.getByTestId('cv-result')).toHaveCount(0);
});

test('the button of the last CV says it is generated, still makes another, and resets on the next', async ({ page }) => {
  const fixture = standardFixture();
  fixture.holdCv = true;
  await open(page, fixture);
  const first = byId(page, 'a1').getByTestId('btn-generate-cv');
  const second = byId(page, 'a2r').getByTestId('btn-generate-cv');

  await first.click();
  await first.click();
  await page.evaluate(() => window.__releaseCv());
  await expect(first).toHaveText(ru['action.cv_generated']);
  await expect(first).toHaveClass(/done/);
  await expect(second).toHaveText(ru['action.generate_cv']);

  // pressed again: the instructions, then another generation
  await first.click();
  await expect(byId(page, 'a1').getByTestId('cv-form')).toBeVisible();
  await first.click();
  await expect(first).toHaveText(ru['action.generating_cv']);
  await page.evaluate(() => window.__releaseCv());
  await expect(first).toHaveText(ru['action.cv_generated']);
  expect(await calls(page, 'generateCv')).toEqual([['sharp', 'a1', ''], ['sharp', 'a1', '']]);

  // the next CV starts: the first button is back to "Generate CV"
  await second.click();
  await second.click();
  await expect(first).toHaveText(ru['action.generate_cv']);
  await expect(first).not.toHaveClass(/done/);
  await page.evaluate(() => window.__releaseCv());
  await expect(second).toHaveText(ru['action.cv_generated']);
  await expect(first).toHaveText(ru['action.generate_cv']);
});

test('"Generate Cover Letter" works as "Generate CV" does, apart from it, and waits its turn', async ({ page }) => {
  const fixture = standardFixture();
  fixture.holdCv = true;
  fixture.letterReply = {
    ok: true, pages: 1, docx: '/home/me/Downloads/Cover Letter.docx', pdf: '/home/me/Downloads/Cover Letter.pdf',
    findings: [{ kind: 'term', text: 'Kafka', where: 'letter', message: 'not found in either CV' }],
    warnings: [], report: { gaps: ['Kubernetes'], from_parent: [], notes: ['the recipient is guessed'] },
  };
  await open(page, fixture);
  const row = byId(page, 'a1');
  const cv = row.getByTestId('btn-generate-cv');
  const letter = row.getByTestId('btn-generate-letter');
  await expect(letter).toHaveText(ru['action.generate_letter']);

  // the first click opens the letter's own instructions; the second sends them
  await letter.click();
  await expect(row.getByTestId('letter-instructions')).toHaveAttribute('placeholder', ru['letter.instructions_hint']);
  await expect(row.getByTestId('cv-form')).toHaveCount(0);
  await expect(letter).toHaveClass(/pressed/);
  await row.getByTestId('letter-instructions').fill('Mention Azure.');
  await letter.click();
  await expect(letter).toHaveText(ru['action.generating_letter']);
  // one at a time, of either kind
  await expect(cv).toBeDisabled();
  await expect(cv).toHaveText(ru['action.generate_cv']);
  expect(await calls(page, 'generateCoverLetter')).toEqual([['sharp', 'a1', 'Mention Azure.']]);
  expect(await calls(page, 'generateCv')).toEqual([]);

  await page.evaluate(() => window.__releaseCv());
  await expect(letter).toHaveText(ru['action.letter_generated']);
  await expect(row.getByTestId('letter-summary')).toHaveText(ru['letter.ready_pages'].replace('{pages}', '1'));
  await expect(row.getByTestId('letter-findings')).toContainText('Kafka');
  await expect(row.getByTestId('letter-notes')).toContainText('the recipient is guessed');
  await row.getByTestId('letter-open-pdf').click();
  expect(await calls(page, 'openCvFile')).toEqual([['/home/me/Downloads/Cover Letter.pdf']]);

  // a CV after it: the letter keeps saying it is generated; both results show
  await cv.click();
  await cv.click();
  await expect(letter).toBeDisabled();
  await page.evaluate(() => window.__releaseCv());
  await expect(cv).toHaveText(ru['action.cv_generated']);
  await expect(letter).toHaveText(ru['action.letter_generated']);
  await expect(row.getByTestId('cv-result')).toBeVisible();
  await expect(row.getByTestId('letter-result')).toBeVisible();

  // the next letter, for another vacancy: this card's letter button resets, its CV button does not
  const other = byId(page, 'a2r').getByTestId('btn-generate-letter');
  await other.click();
  await other.click();
  await expect(letter).toHaveText(ru['action.generate_letter']);
  await page.evaluate(() => window.__releaseCv());
  await expect(other).toHaveText(ru['action.letter_generated']);
  await expect(cv).toHaveText(ru['action.cv_generated']);
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
  await expect(row.getByTestId('btn-generate-cv')).toHaveText(ru['action.generate_cv']);
});

test('the first click on "Generate CV" opens instructions; the second sends what they hold', async ({ page }) => {
  await open(page, standardFixture());
  const row = byId(page, 'a1');
  await row.getByTestId('btn-generate-cv').click();
  const input = row.getByTestId('cv-instructions');
  await expect(input).toBeFocused();
  await expect(input).toHaveAttribute('placeholder', ru['cv.instructions_hint']);
  await expect(row.getByTestId('btn-generate-cv')).toHaveClass(/pressed/);
  await input.fill('  Stress Azure.\nWrite it in German.  ');
  await row.getByTestId('btn-generate-cv').click();
  await expect(row.getByTestId('cv-summary')).toBeVisible();
  expect(await calls(page, 'generateCv')).toEqual([['sharp', 'a1', 'Stress Azure.\nWrite it in German.']]);
  await expect(row.getByTestId('cv-form')).toHaveCount(0);

  // The form's own button and Ctrl+Enter send too; Cancel sends nothing.
  await row.getByTestId('btn-generate-cv').click();
  await row.getByTestId('cv-instructions').fill('Lead with payments.');
  await row.getByTestId('cv-instructions-generate').click();
  await row.getByTestId('btn-generate-cv').click();
  await row.getByTestId('cv-instructions').fill('Short.');
  await row.getByTestId('cv-instructions').press('Control+Enter');
  await row.getByTestId('btn-generate-cv').click();
  await row.getByTestId('cv-instructions').fill('Never sent.');
  await row.getByTestId('cv-instructions-cancel').click();
  await expect(row.getByTestId('cv-form')).toHaveCount(0);
  expect((await calls(page, 'generateCv')).map((c) => c[2]))
    .toEqual(['Stress Azure.\nWrite it in German.', 'Lead with payments.', 'Short.']);
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
  await expect(byId(page, 'a1').getByTestId('cv-result')).toHaveText(new RegExp(`${ru['cv.failed']}: the common CV is missing`));
  await expect(byId(page, 'a2r').getByTestId('cv-result')).toHaveCount(0);
  await expect(byId(page, 'a1').getByTestId('btn-generate-cv')).toBeEnabled();
});
