'use strict';
// The interface language: a flag in the top bar opens a drop-down of flags;
// the choice re-draws everything at once and survives a reload.
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { test, expect } = require('@playwright/test');
const { installMockApi, standardFixture } = require('./mock-api');
const ru = require('../../renderer/locales/ru.js');
const en = require('../../renderer/locales/en.js');

const PAGE = pathToFileURL(path.join(__dirname, '..', '..', 'renderer', 'index.html')).href;

async function open(page) {
  await page.addInitScript(installMockApi, standardFixture());
  await page.goto(PAGE);
  await expect(page.getByTestId('identity-tab-kisel')).toBeVisible();
}

// A flag is an image that actually loaded, not a broken icon.
async function flagOf(locator) {
  return locator.locator('img.flag').evaluate((img) => ({
    src: img.getAttribute('src'), loaded: img.complete && img.naturalWidth > 0,
  }));
}

test('Russian by default; the button shows its flag and the menu is closed', async ({ page }) => {
  await open(page);
  await expect(page.getByTestId('run-collect')).toHaveText(ru['run.collect']);
  await expect(page.locator('html')).toHaveAttribute('lang', 'ru');
  const button = page.getByTestId('language-button');
  await expect(button).toHaveAttribute('title', ru['language.choose']);
  await expect(button).toHaveAttribute('aria-expanded', 'false');
  expect(await flagOf(button)).toEqual({ src: 'flags/ru.svg', loaded: true });
  await expect(page.getByTestId('language-menu')).toHaveCount(0);
});

test('the drop-down lists every language with its flag and its own name', async ({ page }) => {
  await open(page);
  await page.getByTestId('language-button').click();
  await expect(page.getByTestId('language-button')).toHaveAttribute('aria-expanded', 'true');
  const russian = page.getByTestId('language-option-ru');
  const english = page.getByTestId('language-option-en');
  await expect(russian).toHaveText(ru['language.name']);
  await expect(english).toHaveText(en['language.name']);
  await expect(russian).toHaveAttribute('aria-selected', 'true');
  expect(await flagOf(russian)).toEqual({ src: 'flags/ru.svg', loaded: true });
  expect(await flagOf(english)).toEqual({ src: 'flags/en.svg', loaded: true });
});

test('choosing English re-draws the whole interface in English', async ({ page }) => {
  await open(page);
  await page.getByTestId('language-button').click();
  await page.getByTestId('language-option-en').click();

  await expect(page.getByTestId('language-menu')).toHaveCount(0);
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  expect(await flagOf(page.getByTestId('language-button'))).toEqual({ src: 'flags/en.svg', loaded: true });
  await expect(page.getByTestId('run-collect')).toHaveText(en['run.collect']);
  await expect(page.getByTestId('refresh')).toHaveText(en['app.refresh']);
  await expect(page.getByTestId('filter-label')).toHaveText(en['filter.legend']);
  await expect(page.locator('[data-testid^="vacancy-"]').first().getByTestId('btn-applied'))
    .toHaveText(en['action.applied']);
  // Dates are written the English way.
  await expect(page.getByTestId('posted-on').first()).toContainText(/\d{2} [A-Z][a-z]{2} \d{4}/);
});

test('the choice survives a reload, and Russian comes back the same way', async ({ page }) => {
  await open(page);
  await page.getByTestId('language-button').click();
  await page.getByTestId('language-option-en').click();
  await page.reload();
  await expect(page.getByTestId('run-collect')).toHaveText(en['run.collect']);

  await page.getByTestId('language-button').click();
  await page.getByTestId('language-option-ru').click();
  await expect(page.getByTestId('run-collect')).toHaveText(ru['run.collect']);
  await expect(page.getByTestId('posted-on').first()).toContainText(/\d{2}\.\d{2}\.\d{4}/);
});

test('a click elsewhere or Escape closes the drop-down without a change', async ({ page }) => {
  await open(page);
  await page.getByTestId('language-button').click();
  await page.getByTestId('panel').click({ position: { x: 5, y: 5 } });
  await expect(page.getByTestId('language-menu')).toHaveCount(0);
  await page.getByTestId('language-button').click();
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('language-menu')).toHaveCount(0);
  await expect(page.getByTestId('run-collect')).toHaveText(ru['run.collect']);
});

test("a vacancy's own lines follow the language, a row without them keeps its one", async ({ page }) => {
  const fixture = standardFixture();
  const [withViews, without] = fixture.rows.kisel.full;
  withViews.views = {
    ru: { ...withViews.view, highlights: ['nizkaya nagruzka'], salary: 'ne ukazana' },
    en: { ...withViews.view, highlights: ['low intensity'], salary: 'not stated' },
  };
  without.view.highlights = ['only one language'];
  await page.addInitScript(installMockApi, fixture);
  await page.goto(PAGE);
  const card = page.getByTestId(`vacancy-${withViews.id}`);
  await expect(card.locator('.highlights')).toHaveText('nizkaya nagruzka');
  await expect(card).toContainText('ne ukazana');

  await page.getByTestId('language-button').click();
  await page.getByTestId('language-option-en').click();
  await expect(card.locator('.highlights')).toHaveText('low intensity');
  await expect(card).toContainText('not stated');
  await expect(page.getByTestId(`vacancy-${without.id}`).locator('.highlights')).toHaveText('only one language');
});
