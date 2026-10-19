'use strict';
// The filters are check lists of the app's own (renderer/app.js, checklist()),
// not <select>: a person opens the box and clicks rows, each click a reload
// of the list under the open box once the clicks stop (body[data-list-pending]
// meanwhile). A row's value is its data-value, its
// check box its data-state (on, partial, off); master rows have no value.
const { expect } = require('@playwright/test');

const STATUSES = ['new', 'applied', 'contacted', 'interview', 'awaiting_final', 'awaiting_offer', 'offered',
  'started', 'declined', 'rejected', 'bugged', 'expired'];
// The single filters the app had before 2026-10-07, as rows of "Show".
function showRows(name) {
  const fresh = ['fresh_new', 'fresh'].includes(name) ? ['fresh'] : ['fresh', 'earlier'];
  const statuses = { fresh_new: ['new'], no_feedback: ['new'], all: STATUSES, fresh: STATUSES }[name] || [name];
  return [...fresh, ...statuses];
}

// Leaves exactly `values` checked in the check list (null: every row), and
// closes it.
async function check(page, testid, values) {
  const menu = page.getByTestId(`${testid}-menu`);
  if (await menu.isHidden()) await page.getByTestId(testid).click();
  for (let guard = 0; guard < 40; guard += 1) {
    const rows = await menu.locator('[role="option"][data-value]')
      .evaluateAll((nodes) => nodes.map((n) => [n.dataset.value, n.dataset.state]));
    const wrong = rows.find(([value, state]) => (!values || values.includes(value)) !== (state === 'on'));
    if (!wrong) break;
    const row = menu.locator(`[role="option"][data-value="${wrong[0]}"]`);
    await row.click();
    await expect(menu.locator(`[role="option"][data-value="${wrong[0]}"]`))
      .toHaveAttribute('data-state', wrong[1] === 'on' ? 'off' : 'on');
  }
  await page.keyboard.press('Escape');
  await expect(menu).toBeHidden();
  await settled(page);
}

// Waits for the list a drop-down change asked for.
async function settled(page) {
  await expect(page.locator('body')).not.toHaveAttribute('data-list-pending', /.*/);
}

// The old one-choice drop-downs: `value` alone ('' for every row; in "Show",
// a filter name of before).
async function choose(page, testid, value) {
  if (testid === 'filter') return check(page, testid, showRows(value));
  return check(page, testid, value === '' ? null : [value]);
}

// The view the app starts with, and one changed from it (renderer/app.js,
// DEFAULT_VIEW): what the listing calls carry.
const VIEW = {
  segments: null, statuses: ['new'], fresh: ['fresh'], sources: null, fits: null, companies: null, ages: null, text: '',
};
const BOTH = ['fresh', 'earlier'];
const view = (change = {}) => ({ ...VIEW, ...change });

module.exports = { choose, check, settled, showRows, STATUSES, VIEW, BOTH, view };
