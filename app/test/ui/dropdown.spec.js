'use strict';
// The four filters (2026-10-06): one width for all, a long option wraps onto a
// second line inside the open list, and the keyboard works as on a <select>.
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { test, expect } = require('@playwright/test');
const { installMockApi, standardFixture } = require('./mock-api');

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

test('the keyboard: arrows move, Enter picks, Escape closes', async ({ page }) => {
  await open(page);
  await page.getByTestId('filter').focus();
  await page.keyboard.press('ArrowDown');
  await expect(page.getByTestId('filter-menu')).toBeVisible();
  await page.keyboard.press('ArrowDown');   // fresh_new -> no_feedback
  await page.keyboard.press('Enter');
  await expect(page.getByTestId('filter-menu')).toBeHidden();
  expect((await calls(page, 'loadListing')).at(-1)).toEqual(['sharp', 'full', 'no_feedback']);
  await expect(page.getByTestId('filter')).toHaveAttribute('data-value', 'no_feedback');

  await page.getByTestId('fit-filter').click();
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('fit-filter-menu')).toBeHidden();
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
