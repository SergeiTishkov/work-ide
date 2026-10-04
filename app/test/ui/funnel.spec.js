'use strict';
// The application funnel in the real interface, window.api mocked: the step
// buttons, the comment at the bottom of the card, and the timeline of steps.
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { test, expect } = require('@playwright/test');
const { installMockApi, standardFixture, row } = require('./mock-api');
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

function inFunnel(fixture, id, feedback) {
  const r = row(id, { status: feedback.status, fresh: false });
  r.feedback = {
    rejectedReason: null, buggedReason: null, interviewComments: [], interviewAt: [], ...feedback,
  };
  fixture.rows.kisel.full.push(r);
  return r;
}

const APPLIED_AT = '2026-09-30T09:00:00+00:00';
const CONTACT_AT = '2026-10-01T09:00:00+00:00';

test('an application moves on: "Contact happened" opens a large optional comment at the bottom', async ({ page }) => {
  const fixture = standardFixture();
  inFunnel(fixture, 'p1', { status: 'applied', at: APPLIED_AT, appliedAt: APPLIED_AT });
  await open(page, fixture);
  await page.getByTestId('filter').selectOption('applied');
  const card = byId(page, 'p1');
  await expect(card.getByTestId('btn-step-contacted')).toHaveText(ru['step.contacted']);
  await expect(card.getByTestId('btn-step-interview')).toHaveCount(0);

  await card.getByTestId('btn-step-contacted').click();
  expect(await calls(page, 'advance')).toEqual([]);   // nothing saved yet
  const input = card.getByTestId('step-input');
  await expect(input).toHaveAttribute('rows', '6');
  await expect(input).toHaveAttribute('placeholder', ru['step.hint.contacted']);
  const lastChild = await card.evaluate((el) => el.lastElementChild.dataset.testid);
  expect(lastChild).toBe('step-form');   // at the bottom of the card
  await input.fill('HR called, a call with the team lead next week');
  await card.getByTestId('step-save').click();

  expect(await calls(page, 'advance')).toEqual(
    [['kisel', 'p1', 'contacted', 'HR called, a call with the team lead next week']]);
  await expect(page.getByTestId('stub-p1'))
    .toContainText(ru['stub.marked'].replace('{status}', ru['status.contacted']));
  await page.getByTestId('stub-p1').getByTestId('btn-undo').click();
  expect((await calls(page, 'stepBack')).at(-1)).toEqual(['kisel', 'p1']);
});

test('a step saved without a comment sends an empty string, never null', async ({ page }) => {
  const fixture = standardFixture();
  inFunnel(fixture, 'p1', {
    status: 'contacted', at: CONTACT_AT, appliedAt: APPLIED_AT, contactAt: CONTACT_AT, contactComment: '',
  });
  await open(page, fixture);
  await page.getByTestId('filter').selectOption('contacted');
  const card = byId(page, 'p1');
  await expect(card.getByTestId('btn-step-interview')).toHaveText(ru['step.interview']);
  await expect(card.getByTestId('btn-step-awaiting_final')).toHaveText(ru['step.awaiting_final']);
  await card.getByTestId('btn-step-interview').click();
  await card.getByTestId('step-save').click();
  expect(await calls(page, 'advance')).toEqual([['kisel', 'p1', 'interview', '']]);
});

test('after an interview: another interview, or waiting for the final word', async ({ page }) => {
  const fixture = standardFixture();
  inFunnel(fixture, 'p1', {
    status: 'interview', at: CONTACT_AT, appliedAt: APPLIED_AT, contactAt: CONTACT_AT, contactComment: '',
    interviewComments: [''], interviewAt: [CONTACT_AT],
  });
  await open(page, fixture);
  await page.getByTestId('filter').selectOption('interview');
  const card = byId(page, 'p1');
  await expect(card.getByTestId('btn-step-interview')).toBeVisible();
  await card.getByTestId('btn-step-awaiting_final').click();
  await expect(card.getByTestId('step-input')).toHaveAttribute('placeholder', ru['step.hint.awaiting_final']);
  await card.getByTestId('step-cancel').click();
  await expect(card.getByTestId('step-form')).toHaveCount(0);
  expect(await calls(page, 'advance')).toEqual([]);
});

test('the timeline: dated steps, empty ones plain, commented ones accordions', async ({ page }) => {
  const fixture = standardFixture();
  inFunnel(fixture, 'p1', {
    status: 'interview', at: '2026-10-05T09:00:00+00:00', appliedAt: APPLIED_AT,
    contactAt: CONTACT_AT, contactComment: '',
    interviewComments: ['system design, 1 hour', ''],
    interviewAt: ['2026-10-03T09:00:00+00:00', '2026-10-05T09:00:00+00:00'],
  });
  await open(page, fixture);
  await page.getByTestId('filter').selectOption('interview');
  const card = byId(page, 'p1');

  const applied = card.getByTestId('entry-applied');
  await expect(applied.getByTestId('entry-date')).toHaveText('30.09.2026');
  await expect(applied.getByTestId('entry-label')).toHaveText(ru['timeline.applied']);
  await expect(applied.getByTestId('entry-edit')).toHaveCount(0);

  const contact = card.getByTestId('entry-contact');
  await expect(contact.getByTestId('entry-date')).toHaveText('01.10.2026');
  await expect(contact.getByTestId('entry-label')).toHaveText(ru['timeline.contact']);
  await expect(contact.getByTestId('entry-toggle')).toHaveCount(0);   // empty: a plain line
  await expect(contact.getByTestId('entry-edit')).toBeVisible();

  const first = card.getByTestId('entry-interview-0');
  await expect(first.getByTestId('entry-label')).toHaveText(ru['timeline.interview'].replace('{n}', '1'));
  await expect(first.getByTestId('entry-comment')).toHaveCount(0);   // closed at first
  await first.getByTestId('entry-toggle').click();
  await expect(first.getByTestId('entry-comment')).toHaveText('system design, 1 hour');
  await first.getByTestId('entry-toggle').click();
  await expect(first.getByTestId('entry-comment')).toHaveCount(0);

  const second = card.getByTestId('entry-interview-1');
  await expect(second.getByTestId('entry-label')).toHaveText(ru['timeline.interview'].replace('{n}', '2'));
  await expect(second.getByTestId('entry-toggle')).toHaveCount(0);
});

test('Ctrl+Enter saves a step comment and an edited one, as "Save" does', async ({ page }) => {
  const fixture = standardFixture();
  inFunnel(fixture, 'p1', {
    status: 'contacted', at: CONTACT_AT, appliedAt: APPLIED_AT, contactAt: CONTACT_AT, contactComment: '',
  });
  await open(page, fixture);
  await page.getByTestId('filter').selectOption('contacted');
  const card = byId(page, 'p1');
  await card.getByTestId('entry-contact').getByTestId('entry-edit').click();
  await card.getByTestId('entry-input').fill('recruiter wrote on LinkedIn');
  await card.getByTestId('entry-input').press('Control+Enter');
  expect(await calls(page, 'editComment')).toEqual(
    [['kisel', 'p1', 'contact', null, 'recruiter wrote on LinkedIn']]);

  await card.getByTestId('btn-step-interview').click();
  await card.getByTestId('step-input').fill('a call with the team lead');
  await card.getByTestId('step-input').press('Control+Enter');
  expect(await calls(page, 'advance')).toEqual([['kisel', 'p1', 'interview', 'a call with the team lead']]);
});

test('the pencil edits in place: an empty step becomes an open accordion', async ({ page }) => {
  const fixture = standardFixture();
  inFunnel(fixture, 'p1', {
    status: 'contacted', at: CONTACT_AT, appliedAt: APPLIED_AT, contactAt: CONTACT_AT, contactComment: '',
  });
  await open(page, fixture);
  await page.getByTestId('filter').selectOption('contacted');
  const contact = byId(page, 'p1').getByTestId('entry-contact');
  await contact.getByTestId('entry-edit').click();
  await expect(contact.getByTestId('entry-input')).toHaveValue('');
  await contact.getByTestId('entry-input').fill('recruiter wrote on LinkedIn');
  await contact.getByTestId('entry-save').click();

  expect(await calls(page, 'editComment')).toEqual(
    [['kisel', 'p1', 'contact', null, 'recruiter wrote on LinkedIn']]);
  await expect(contact.getByTestId('entry-toggle')).toHaveAttribute('aria-expanded', 'true');
  await expect(contact.getByTestId('entry-comment')).toHaveText('recruiter wrote on LinkedIn');
});

test('editing an open comment turns its text into a text area', async ({ page }) => {
  const fixture = standardFixture();
  inFunnel(fixture, 'p1', {
    status: 'interview', at: CONTACT_AT, appliedAt: APPLIED_AT, contactAt: CONTACT_AT, contactComment: '',
    interviewComments: ['went well'], interviewAt: ['2026-10-03T09:00:00+00:00'],
  });
  await open(page, fixture);
  await page.getByTestId('filter').selectOption('interview');
  const entry = byId(page, 'p1').getByTestId('entry-interview-0');
  await entry.getByTestId('entry-toggle').click();
  await expect(entry.getByTestId('entry-comment')).toHaveText('went well');
  await entry.getByTestId('entry-edit').click();
  await expect(entry.getByTestId('entry-comment')).toHaveCount(0);
  await expect(entry.getByTestId('entry-input')).toHaveValue('went well');
  await entry.getByTestId('entry-input').fill('went well; a second round on Monday');
  await entry.getByTestId('entry-save').click();
  expect((await calls(page, 'editComment')).at(-1)).toEqual(
    ['kisel', 'p1', 'interview', 0, 'went well; a second round on Monday']);
  await expect(entry.getByTestId('entry-comment')).toHaveText('went well; a second round on Monday');
});

test('the pencil opens a closed accordion straight into editing', async ({ page }) => {
  const fixture = standardFixture();
  inFunnel(fixture, 'p1', {
    status: 'interview', at: CONTACT_AT, appliedAt: APPLIED_AT, contactAt: CONTACT_AT, contactComment: '',
    interviewComments: ['went well'], interviewAt: ['2026-10-03T09:00:00+00:00'],
  });
  await open(page, fixture);
  await page.getByTestId('filter').selectOption('interview');
  const entry = byId(page, 'p1').getByTestId('entry-interview-0');
  await entry.getByTestId('entry-edit').click();
  await expect(entry.getByTestId('entry-toggle')).toHaveAttribute('aria-expanded', 'true');
  await expect(entry.getByTestId('entry-input')).toHaveValue('went well');
  await entry.getByTestId('entry-cancel').click();
  await expect(entry.getByTestId('entry-input')).toHaveCount(0);
  expect(await calls(page, 'editComment')).toEqual([]);
});

test('a negative answer shows in the timeline, its reason editable', async ({ page }) => {
  await open(page);
  await page.getByTestId('filter').selectOption('bugged');
  const card = byId(page, 'x1');
  const entry = card.getByTestId('entry-bugged');
  await expect(entry.getByTestId('entry-label')).toHaveText(ru['timeline.bugged']);
  await expect(entry.getByTestId('entry-edit')).toBeVisible();
  await expect(card.getByTestId('btn-step-contacted')).toHaveCount(0);   // no funnel from here
});

test('funnel filters are among the filters, with their counts', async ({ page }) => {
  const fixture = standardFixture();
  inFunnel(fixture, 'p1', { status: 'awaiting_final', at: CONTACT_AT, appliedAt: APPLIED_AT,
    contactAt: CONTACT_AT, contactComment: '', finalAt: CONTACT_AT, finalComment: '' });
  await open(page, fixture);
  await expect(page.getByTestId('filter-option-awaiting_final')).toContainText('(1)');
  await page.getByTestId('filter').selectOption('awaiting_final');
  expect((await calls(page, 'loadListing')).at(-1)).toEqual(['kisel', 'full', 'awaiting_final']);
  await expect(byId(page, 'p1').getByTestId('entry-final').getByTestId('entry-label'))
    .toHaveText(ru['timeline.final']);
  // After the final resolution: the offer, or a no.
  await expect(byId(page, 'p1').getByTestId('btn-step-awaiting_offer')).toHaveText(ru['step.awaiting_offer']);
  await expect(byId(page, 'p1').getByTestId('btn-step-declined')).toHaveText(ru['step.declined']);
});


test('"Rejected" can close an application at any step, with an optional comment', async ({ page }) => {
  const fixture = standardFixture();
  inFunnel(fixture, 'p1', { status: 'applied', at: APPLIED_AT, appliedAt: APPLIED_AT });
  await open(page, fixture);
  await page.getByTestId('filter').selectOption('applied');
  const card = byId(page, 'p1');
  await expect(card.getByTestId('btn-step-declined')).toHaveText(ru['step.declined']);
  await card.getByTestId('btn-step-declined').click();
  await expect(card.getByTestId('step-input')).toHaveAttribute('placeholder', ru['step.hint.declined']);
  await card.getByTestId('step-input').fill('not enough Azure');
  await card.getByTestId('step-save').click();
  expect(await calls(page, 'advance')).toEqual([['kisel', 'p1', 'declined', 'not enough Azure']]);

  await page.getByTestId('filter').selectOption('declined');
  expect((await calls(page, 'loadListing')).at(-1)).toEqual(['kisel', 'full', 'declined']);
  const closed = byId(page, 'p1');
  await expect(closed.getByTestId('status-badge')).toHaveText(ru['status.declined']);
  await expect(closed.getByTestId('entry-declined').getByTestId('entry-label'))
    .toHaveText(ru['timeline.declined']);
  await expect(closed.locator('[data-testid^="btn-step-"]')).toHaveCount(0);   // nothing follows a no
});

test('waiting for the offer comes after the final resolution and shows in the timeline', async ({ page }) => {
  const fixture = standardFixture();
  inFunnel(fixture, 'p1', {
    status: 'awaiting_offer', at: CONTACT_AT, appliedAt: APPLIED_AT, contactAt: CONTACT_AT,
    contactComment: '', finalAt: CONTACT_AT, finalComment: '', offerAt: CONTACT_AT,
    offerComment: 'within two weeks',
  });
  await open(page, fixture);
  await expect(page.getByTestId('filter-option-awaiting_offer')).toContainText('(1)');
  await page.getByTestId('filter').selectOption('awaiting_offer');
  const card = byId(page, 'p1');
  await expect(card.getByTestId('entry-offer').getByTestId('entry-label')).toHaveText(ru['timeline.offer']);
  await card.getByTestId('entry-offer').getByTestId('entry-toggle').click();
  await expect(card.getByTestId('entry-offer').getByTestId('entry-comment')).toHaveText('within two weeks');
  await expect(card.getByTestId('btn-step-declined')).toBeVisible();
  await expect(card.getByTestId('btn-step-awaiting_offer')).toHaveCount(0);
  await expect(card.getByTestId('btn-step-offered')).toHaveText(ru['step.offered']);
  await expect(card.getByTestId('btn-step-started')).toHaveCount(0);   // only after the offer
});

test('"Started working" follows only the offer, and closes the funnel', async ({ page }) => {
  const fixture = standardFixture();
  inFunnel(fixture, 'p1', {
    status: 'offered', at: CONTACT_AT, appliedAt: APPLIED_AT, contactAt: CONTACT_AT,
    contactComment: '', finalAt: CONTACT_AT, finalComment: '', offerAt: CONTACT_AT, offerComment: '',
    offeredAt: CONTACT_AT, offeredComment: '$7k a month',
  });
  await open(page, fixture);
  await expect(page.getByTestId('filter-option-offered')).toContainText('(1)');
  await page.getByTestId('filter').selectOption('offered');
  const card = byId(page, 'p1');
  await expect(card.getByTestId('entry-offered').getByTestId('entry-label')).toHaveText(ru['timeline.offered']);
  await expect(card.locator('[data-testid^="btn-step-"]')).toHaveCount(1);
  await card.getByTestId('btn-step-started').click();
  await expect(card.getByTestId('step-input')).toHaveAttribute('placeholder', ru['step.hint.started']);
  await card.getByTestId('step-save').click();
  expect(await calls(page, 'advance')).toEqual([['kisel', 'p1', 'started', '']]);
  await page.getByTestId('filter').selectOption('started');
  await expect(byId(page, 'p1').getByTestId('status-badge')).toHaveText(ru['status.started']);
  await expect(byId(page, 'p1').locator('[data-testid^="btn-step-"]')).toHaveCount(0);
});
