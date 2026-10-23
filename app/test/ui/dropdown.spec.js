'use strict';
// The filters (2026-10-06; eight since task 0090, 2026-10-23; in a card
// under the search field since task 0091): one width for all, a long option wraps onto a
// second line inside the open list, and the keyboard works as on a <select>.
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { test, expect } = require('@playwright/test');
const { installMockApi, standardFixture } = require('./mock-api');
const { settled } = require('../helpers/dropdown');
const en = require('../../renderer/locales/en.js');

const PAGE = pathToFileURL(path.join(__dirname, '..', '..', 'renderer', 'index.html')).href;
const BOXES = ['segment-filter', 'fresh-filter', 'filter', 'age-filter', 'source-filter', 'company-filter',
  'fit-filter', 'role-filter'];

async function open(page, fixture = standardFixture()) {
  await page.addInitScript(installMockApi, fixture);
  await page.goto(PAGE);
  await expect(page.getByTestId('text-filter')).toBeVisible();
}

const calls = (page, name) =>
  page.evaluate((n) => window.__calls.filter((c) => c.name === n).map((c) => c.args), name);

test('the eight boxes are one width, four columns of two, in a card as wide as the search field', async ({ page }) => {
  await page.setViewportSize({ width: 1400, height: 700 });
  await open(page);
  const boxes = await Promise.all(BOXES.map((id) => page.getByTestId(id).boundingBox()));
  expect(new Set(boxes.map((b) => Math.round(b.width))).size).toBe(1);
  const rows = [...new Set(boxes.map((b) => Math.round(b.y)))];
  expect(rows).toHaveLength(2);
  expect(boxes.filter((b) => Math.round(b.y) === rows[0])).toHaveLength(4);
  const card = await page.getByTestId('filters').boundingBox();
  const search = await page.getByTestId('text-filter').boundingBox();
  expect(Math.round(search.width)).toBe(Math.round(card.width));
  expect(Math.round(search.x)).toBe(Math.round(card.x));
  await expect(page.getByTestId('filters-legend')).toHaveText(en['filter.card_legend']);
});

test('the filters are hidden at the start; the button in the search field shows them, pressed', async ({ page }) => {
  await open(page, { ...standardFixture(), filtersHidden: true });
  const toggle = page.getByTestId('filters-toggle');
  await expect(page.getByTestId('filters')).toHaveCount(0);
  await expect(toggle).toHaveAttribute('aria-pressed', 'false');
  await expect(toggle).toHaveAttribute('title', en['filter.show']);
  // the button sits inside the field, at its right edge
  const field = await page.getByTestId('text-filter').boundingBox();
  const button = await toggle.boundingBox();
  expect(button.x + button.width).toBeLessThanOrEqual(field.x + field.width);
  expect(button.x + button.width).toBeGreaterThan(field.x + field.width - 16);
  expect(button.y).toBeGreaterThan(field.y);
  expect(button.y + button.height).toBeLessThan(field.y + field.height);

  await toggle.click();
  await expect(page.getByTestId('filters')).toBeVisible();
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  await expect(toggle).toHaveClass(/pressed/);
  await expect(toggle).toHaveAttribute('title', en['filter.hide']);

  // kept across a reload, shown or hidden
  await page.reload();
  await expect(page.getByTestId('filters')).toBeVisible();
  await page.getByTestId('filters-toggle').click();
  await expect(page.getByTestId('filters')).toHaveCount(0);
  await page.reload();
  await expect(page.getByTestId('text-filter')).toBeVisible();
  await expect(page.getByTestId('filters')).toHaveCount(0);
  await expect(page.getByTestId('filters-toggle')).toHaveAttribute('aria-pressed', 'false');
});

test('hiding the filters keeps what they chose; the search field works with them hidden', async ({ page }) => {
  await open(page);
  await page.getByTestId('fit-filter').click();
  await expect(page.getByTestId('fit-filter-menu')).toBeVisible();
  await page.getByTestId('filters-toggle').click();   // an open list closes with its card
  await expect(page.getByTestId('fit-filter-menu')).toHaveCount(0);
  const before = (await calls(page, 'loadListing')).length;
  await page.getByTestId('text-filter').fill('company b');
  await expect.poll(async () => (await calls(page, 'loadListing')).length).toBeGreaterThan(before);
  expect((await calls(page, 'loadListing')).at(-1)[1].text).toBe('company b');
  await page.getByTestId('filters-toggle').click();
  await expect(page.getByTestId('fit-filter')).toBeVisible();
});

test('the open list is the box\'s width, and a long option takes a second line', async ({ page }) => {
  await open(page);
  await page.getByTestId('source-filter').click();
  const menu = page.getByTestId('source-filter-menu');
  await expect(menu).toBeVisible();
  const box = await page.getByTestId('source-filter').boundingBox();
  expect(Math.round((await menu.boundingBox()).width)).toBe(Math.round(box.width));
  const long = page.getByTestId('source-option-devitjobs');   // "devitjobs.uk, devitjobs.com (1)"
  await long.evaluate((node) => { node.textContent = 'a much longer name of a board, for one line too many (1)'; });
  const short = await page.getByTestId('source-option-all').boundingBox();
  expect((await long.boundingBox()).height).toBeGreaterThan(short.height * 1.5);
  expect((await long.boundingBox()).width).toBeLessThanOrEqual(box.width);
});

test('the keyboard: arrows move, Enter checks and leaves the list open, Escape closes', async ({ page }) => {
  await open(page);
  await page.getByTestId('fresh-filter').focus();
  await page.keyboard.press('ArrowDown');
  await expect(page.getByTestId('fresh-filter-menu')).toBeVisible();
  await expect(page.getByTestId('fresh-option-fresh')).toHaveClass(/cursor/);   // the first row on
  await page.keyboard.press('ArrowDown');   // fresh -> earlier
  await page.keyboard.press('Enter');
  await expect(page.getByTestId('fresh-option-earlier')).toHaveAttribute('data-state', 'on');
  await expect(page.getByTestId('fresh-filter-menu')).toBeVisible();
  await expect(page.getByTestId('fresh-option-earlier')).toHaveClass(/cursor/);
  await settled(page);
  expect((await calls(page, 'loadListing')).at(-1)).toEqual(['sharp', {
    segments: null, statuses: ['new'], fresh: ['fresh', 'earlier'], sources: null, fits: null, companies: null, ages: null,
    roles: null, text: '',
  }]);
  await expect(page.getByTestId('fresh-filter-value')).toHaveText(en['filter.fresh_all']);
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('fresh-filter-menu')).toBeHidden();

  await page.getByTestId('fit-filter').click();
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('fit-filter-menu')).toBeHidden();
});

// The owner, 2026-10-12: a click on a filter froze the window. The check box
// changes at once; the list is asked for once the clicks stop for 200 ms, and
// a spinner stands in for the vacancies until it comes.
test('quick clicks ask for one list, and a spinner stands in for it until it comes', async ({ page }) => {
  await open(page);
  await expect(page.locator('article').first()).toBeVisible();
  const before = (await calls(page, 'loadListing')).length;
  await page.evaluate(() => window.__holdListing());
  await page.getByTestId('filter').click();
  await page.getByTestId('filter-option-contacted').click();
  await page.getByTestId('filter-option-applied').click();
  await expect(page.getByTestId('filter-option-contacted')).toHaveAttribute('data-state', 'on');
  await expect(page.getByTestId('filter-option-applied')).toHaveAttribute('data-state', 'on');
  await expect(page.getByTestId('list-loading')).toBeVisible();
  await expect(page.locator('article')).toHaveCount(0);
  await expect(page.getByTestId('filter-menu')).toBeVisible();   // the open list stays
  const asked = (await calls(page, 'loadListing')).slice(before);
  expect(asked).toEqual([['sharp', {
    segments: null, statuses: ['new', 'applied', 'contacted'], fresh: ['fresh'], sources: null, fits: null, companies: null, ages: null,
    roles: null, text: '',
  }]]);
  await page.evaluate(() => window.__releaseListing());
  await settled(page);
  await expect(page.getByTestId('list-loading')).toHaveCount(0);
  await expect(page.locator('article').first()).toBeVisible();
});

test("the rows under a group's master row stand in from it", async ({ page }) => {
  await open(page);
  await page.getByTestId('filter').click();
  const left = async (id) => (await page.getByTestId(id).locator('.check').boundingBox()).x;
  expect(await left('filter-option-applied')).toBeGreaterThan(await left('filter-master-applications') + 8);
  expect(await left('filter-option-new')).toBe(await left('filter-master-applications'));   // a group of one row
});

test('one list open at a time; a click elsewhere closes it', async ({ page }) => {
  await open(page);
  await page.getByTestId('filter').click();
  await page.getByTestId('source-filter').click();
  await expect(page.getByTestId('filter-menu')).toBeHidden();
  await expect(page.getByTestId('source-filter-menu')).toBeVisible();
  await page.getByTestId('panel').click({ position: { x: 5, y: 5 } });
  await expect(page.getByTestId('source-filter-menu')).toBeHidden();
});
