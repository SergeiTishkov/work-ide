'use strict';
// The colour theme and the top bar's pickers (2026-10-06): theme left of the
// language, each a button with no arrow — an icon or a flag — that opens a
// list; the markets are a drop-down beside the filters.
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { test, expect } = require('@playwright/test');
const { installMockApi, standardFixture } = require('./mock-api');
const ru = require('../../renderer/locales/ru.js');

const PAGE = pathToFileURL(path.join(__dirname, '..', '..', 'renderer', 'index.html')).href;

async function open(page, colorScheme = 'light') {
  await page.emulateMedia({ colorScheme });
  await page.addInitScript(installMockApi, standardFixture());
  await page.goto(PAGE);
  await expect(page.getByTestId('identity-tab-sharp')).toBeVisible();
}

const background = (page) => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
const LIGHT = 'rgb(246, 247, 249)';
const DARK = 'rgb(21, 24, 30)';

test('the theme follows the system until one is chosen', async ({ page }) => {
  await open(page, 'dark');
  const button = page.getByTestId('theme-button');
  await expect(button).toHaveAttribute('title', ru['theme.choose']);
  await expect(button.locator('[data-theme-icon="system"]')).toHaveCount(1);
  expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBeUndefined();
  expect(await background(page)).toBe(DARK);
  await page.emulateMedia({ colorScheme: 'light' });
  expect(await background(page)).toBe(LIGHT);
});

test('light and dark hold whatever the system says, and survive a reload', async ({ page }) => {
  await open(page, 'dark');
  await page.getByTestId('theme-button').click();
  await expect(page.getByTestId('theme-option-system')).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByTestId('theme-option-light')).toHaveText(ru['theme.light']);
  await page.getByTestId('theme-option-light').click();
  await expect(page.getByTestId('theme-menu')).toHaveCount(0);
  expect(await background(page)).toBe(LIGHT);
  await expect(page.getByTestId('theme-button').locator('[data-theme-icon="light"]')).toHaveCount(1);

  await page.reload();
  expect(await background(page)).toBe(LIGHT);
  await page.getByTestId('theme-button').click();
  await page.getByTestId('theme-option-dark').click();
  await page.emulateMedia({ colorScheme: 'light' });
  expect(await background(page)).toBe(DARK);
});

test('theme sits left of the language; neither button has an arrow; one menu at a time', async ({ page }) => {
  await open(page);
  const theme = await page.getByTestId('theme-button').boundingBox();
  const language = await page.getByTestId('language-button').boundingBox();
  expect(theme.x).toBeLessThan(language.x);
  expect(theme.height).toBe(language.height);
  for (const id of ['theme-button', 'language-button']) {
    expect((await page.getByTestId(id).innerText()).trim()).toBe('');   // an icon, no caret
  }
  await page.getByTestId('theme-button').click();
  await page.getByTestId('language-button').click();
  await expect(page.getByTestId('theme-menu')).toHaveCount(0);
  await expect(page.getByTestId('language-menu')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('language-menu')).toHaveCount(0);
});

test('the markets are a drop-down before the filters', async ({ page }) => {
  await open(page);
  await expect(page.getByTestId('segment-label')).toHaveText(ru['filter.segment_legend']);
  const options = await page.getByTestId('segment-filter-menu').locator('[role="option"]').evaluateAll(
    (nodes) => nodes.map((n) => n.dataset.value));
  expect(options.length).toBeGreaterThan(1);
  const segment = await page.getByTestId('segment-filter').boundingBox();
  const filter = await page.getByTestId('filter').boundingBox();
  expect(segment.x).toBeLessThan(filter.x);
});
