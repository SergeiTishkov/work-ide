'use strict';
// The four filters (2026-10-06): one width for all, a long option wraps onto a
// second line inside the open list, and the keyboard works as on a <select>.
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { test, expect } = require('@playwright/test');
const { installMockApi, standardFixture } = require('./mock-api');
const { settled } = require('../helpers/dropdown');
const ru = require('../../renderer/locales/ru.js');

const PAGE = pathToFileURL(path.join(__dirname, '..', '..', 'renderer', 'index.html')).href;
const BOXES = ['segment-filter', 'filter', 'source-filter', 'fit-filter'];

async function open(page) {
  await page.addInitScript(installMockApi, standardFixture());
  await page.goto(PAGE);
  await expect(page.getByTestId('filter')).toBeVisible();
}

const calls = (page, name) =>
  page.evaluate((n) => window.__calls.filter((c) => c.name === n).map((c) => c.args), name);

test('the four boxes are one width, in one row', async ({ page }) => {
  await page.setViewportSize({ width: 1400, height: 600 });
  await open(page);
  const boxes = await Promise.all(BOXES.map((id) => page.getByTestId(id).boundingBox()));
  expect(new Set(boxes.map((b) => Math.round(b.width))).size).toBe(1);
  expect(new Set(boxes.map((b) => Math.round(b.y))).size).toBe(1);
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
  await page.getByTestId('filter').focus();
  await page.keyboard.press('ArrowDown');
  await expect(page.getByTestId('filter-menu')).toBeVisible();
  await expect(page.getByTestId('filter-option-fresh')).toHaveClass(/cursor/);   // the first row on
  await page.keyboard.press('ArrowDown');   // fresh -> earlier
  await page.keyboard.press('Enter');
  await expect(page.getByTestId('filter-option-earlier')).toHaveAttribute('data-state', 'on');
  await expect(page.getByTestId('filter-menu')).toBeVisible();
  await expect(page.getByTestId('filter-option-earlier')).toHaveClass(/cursor/);
  await settled(page);
  expect((await calls(page, 'loadListing')).at(-1)).toEqual(['sharp', {
    segments: null, statuses: ['new'], fresh: ['fresh', 'earlier'], sources: null, fits: null,
  }]);
  await expect(page.getByTestId('filter-value')).toHaveText(ru['filter.new']);
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('filter-menu')).toBeHidden();

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
  await page.getByTestId('filter-option-earlier').click();
  await page.getByTestId('filter-option-applied').click();
  await expect(page.getByTestId('filter-option-earlier')).toHaveAttribute('data-state', 'on');
  await expect(page.getByTestId('filter-option-applied')).toHaveAttribute('data-state', 'on');
  await expect(page.getByTestId('list-loading')).toBeVisible();
  await expect(page.locator('article')).toHaveCount(0);
  await expect(page.getByTestId('filter-menu')).toBeVisible();   // the open list stays
  const asked = (await calls(page, 'loadListing')).slice(before);
  expect(asked).toEqual([['sharp', {
    segments: null, statuses: ['new', 'applied'], fresh: ['fresh', 'earlier'], sources: null, fits: null,
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
  expect(await left('filter-option-earlier')).toBeGreaterThan(await left('filter-master-fresh') + 8);
  expect(await left('filter-option-new')).toBe(await left('filter-master-fresh'));   // a group of one row
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
