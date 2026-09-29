'use strict';
// Every interface text comes from the locale file: each key the renderer uses
// exists there, and the file holds nothing the renderer no longer uses.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const RENDERER = path.join(__dirname, '..', '..', 'renderer');
const locale = require('../../renderer/locales/ru.js');

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
  assert.deepEqual(Object.entries(locale).filter(([, v]) => !String(v).trim()).map(([k]) => k), []);
});

test('the markup carries no interface text of its own', () => {
  const html = fs.readFileSync(path.join(RENDERER, 'index.html'), 'utf8');
  const body = html.slice(html.indexOf('<body'));
  const text = body.replace(/<script[\s\S]*?<\/script>/g, '').replace(/<[^>]+>/g, '').trim();
  assert.equal(text, '');
});

test('t() substitutes parameters and leaves unknown ones visible', () => {
  global.self = { LOCALE_RU: { 'x.y': 'Review ({n}) {missing}' } };
  delete require.cache[require.resolve('../../renderer/i18n.js')];
  require('../../renderer/i18n.js');
  assert.equal(global.self.t('x.y', { n: 3 }), 'Review (3) {missing}');
  assert.equal(global.self.t('nope.nope'), 'nope.nope');
  delete global.self;
});
