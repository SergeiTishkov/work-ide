'use strict';
// Every interface text comes from the locale files: each key the renderer uses
// exists there, the files hold nothing the renderer no longer uses, and every
// language has every text.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const RENDERER = path.join(__dirname, '..', '..', 'renderer');
const locale = require('../../renderer/locales/ru.js');
const LOCALES = { ru: locale, en: require('../../renderer/locales/en.js') };

function usedKeys() {
  const namespaces = new Set(Object.keys(locale).map((k) => k.split('.')[0]));
  const used = new Set();
  for (const file of ['app.js']) {
    const source = fs.readFileSync(path.join(RENDERER, file), 'utf8');
    for (const [, key] of source.matchAll(/['"`]([a-z_]+(?:\.[a-z_0-9]+)+)['"`]/g)) {
      if (namespaces.has(key.split('.')[0])) used.add(key);
    }
  }
  return used;
}

test('every key the renderer uses has a text', () => {
  const missing = [...usedKeys()].filter((k) => !(k in locale));
  assert.deepEqual(missing, []);
});

test('the locale holds no text the renderer no longer uses', () => {
  const used = usedKeys();
  const unused = Object.keys(locale).filter((k) => !used.has(k));
  assert.deepEqual(unused, []);
});

test('no text is empty', () => {
  for (const [language, texts] of Object.entries(LOCALES)) {
    assert.deepEqual(Object.entries(texts).filter(([, v]) => !String(v).trim()).map(([k]) => k), [], language);
  }
});

test('every language has exactly the same texts', () => {
  assert.deepEqual(Object.keys(LOCALES.en).sort(), Object.keys(locale).sort());
});

test('a text takes the same parameters in every language', () => {
  const names = (text) => [...String(text).matchAll(/{(w+)}/g)].map((m) => m[1]).sort();
  for (const key of Object.keys(locale)) {
    if (key === 'date.format') continue;   // each language picks its own parts of a date
    assert.deepEqual(names(LOCALES.en[key]), names(locale[key]), key);
  }
});

test('a date format uses only the parts a date has, and twelve months', () => {
  for (const [language, texts] of Object.entries(LOCALES)) {
    const parts = [...texts['date.format'].matchAll(/{(w+)}/g)].map((m) => m[1]);
    assert.ok(parts.every((p) => ['day', 'mm', 'month', 'year'].includes(p)), language);
    assert.equal(texts['date.months'].split(' ').length, 12, language);
  }
});

test('every language has its flag', () => {
  for (const language of Object.keys(LOCALES)) {
    assert.ok(fs.existsSync(path.join(RENDERER, 'flags', `${language}.svg`)), language);
  }
});

test('the markup carries no interface text of its own', () => {
  const html = fs.readFileSync(path.join(RENDERER, 'index.html'), 'utf8');
  const body = html.slice(html.indexOf('<body'));
  const text = body.replace(/<script[\s\S]*?<\/script>/g, '').replace(/<[^>]+>/g, '').trim();
  assert.equal(text, '');
});

function loadI18n(saved) {
  const storage = new Map(saved ? [['work-ide-language', saved]] : []);
  global.self = {
    LOCALE_RU: { 'x.y': 'Obzor ({n}) {missing}' },
    LOCALE_EN: { 'x.y': 'Review ({n}) {missing}' },
    localStorage: { getItem: (k) => storage.get(k) ?? null, setItem: (k, v) => storage.set(k, v) },
  };
  delete require.cache[require.resolve('../../renderer/i18n.js')];
  require('../../renderer/i18n.js');
  const root = global.self;
  delete global.self;
  return { root, storage };
}

test('t() substitutes parameters and leaves unknown ones visible', () => {
  const { root } = loadI18n();
  assert.equal(root.t('x.y', { n: 3 }), 'Obzor (3) {missing}');
  assert.equal(root.t('nope.nope'), 'nope.nope');
});

test('Russian until another language is chosen; the choice is remembered', () => {
  const { root, storage } = loadI18n();
  assert.equal(root.I18n.language(), 'ru');
  assert.deepEqual(root.I18n.languages, ['ru', 'en']);
  assert.equal(root.I18n.setLanguage('en'), true);
  assert.equal(root.t('x.y', { n: 1 }), 'Review (1) {missing}');
  assert.equal(storage.get('work-ide-language'), 'en');
  assert.equal(loadI18n('en').root.I18n.language(), 'en', 'the next start speaks English');
});

test('an unknown language is refused, a stored one falls back to Russian', () => {
  const { root } = loadI18n('xx');
  assert.equal(root.I18n.language(), 'ru');
  assert.equal(root.I18n.setLanguage('xx'), false);
  assert.equal(root.I18n.language(), 'ru');
  assert.equal(root.t('x.y', { n: 2 }, 'en'), 'Review (2) {missing}', 'one text in another language');
});
