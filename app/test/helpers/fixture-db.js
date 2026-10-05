'use strict';
// A small database built from the real schemas/db.sql, so the app's tests
// run against exactly the schema the Python side writes.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { DatabaseSync } = require('node:sqlite');

const REPO = path.resolve(__dirname, '..', '..', '..');
const SCHEMA_DIR = path.join(REPO, 'schemas');

function view(id, overrides = {}) {
  return {
    id,
    title: `Senior .NET Developer ${id}`,
    company: `Company ${id}`,
    url: `https://example.test/${id}`,
    score: 60,
    classification: 'hot_lead',
    highlights: ['legacy/enterprise: insurance'],
    salary: 'not stated _(source: no data)_',
    to_confirm: [],
    company_url: null,
    eligibility: { level: 'likely', label: 'eligibility: likely', reason: 'says anywhere' },
    apply_channels: [],
    technologies: ['C#', '.NET'],
    reputation: 'not checked',
    hiring_country: 'without a country',
    company_age: null,
    needs_manual_review: false,
    first_seen: '2026-09-01T00:00:00+00:00',
    posted_on: '2026-08-30',
    first_seen_on: '2026-09-01',
    ...overrides,
  };
}

// One identity's work in a fresh shared base.
// vacancies: [{ id, score, class, segments: ['full', ...] }]
// selections: [{ kind, run, items: [id, ...] }] — later ones are newer
function createDatabase(file, {
  vacancies, selections, segments, identity = 'test', displayName = 'Test search',
}) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const db = new DatabaseSync(file);
  db.exec(fs.readFileSync(path.join(SCHEMA_DIR, 'db.sql'), 'utf8'));
  db.prepare("INSERT INTO meta (key, value) VALUES ('schema_version', '8')").run();
  db.prepare("INSERT INTO identities (id, display_name, created_at) VALUES (?, ?, '2026-09-01')")
    .run(identity, displayName);
  const classOrder = ['hot_lead', 'worth_a_look', 'long_shot',
    'remote_unconfirmed', 'engagement_unconfirmed'];
  const insertVacancy = db.prepare('INSERT INTO vacancies (id, data) VALUES (?, ?)');
  const insertVerdict = db.prepare(
    'INSERT INTO vacancy_identity (identity_id, vacancy_id, score, class, view) VALUES (?, ?, ?, ?, ?)');
  for (const v of vacancies) {
    insertVacancy.run(v.id, JSON.stringify({ id: v.id, title: `data ${v.id}`, source: v.source || 'linkedin' }));
    insertVerdict.run(identity, v.id, v.score, v.class || 'hot_lead',
      JSON.stringify(view(v.id, { score: v.score, classification: v.class })));
  }
  for (const [index, selection] of selections.entries()) {
    const id = index + 1;
    db.prepare('INSERT INTO selections (id, identity_id, run, created_at, kind) VALUES (?, ?, ?, ?, ?)')
      .run(id, identity, selection.run || id, `2026-09-2${id}T10:00:00+00:00`, selection.kind || 'run');
    for (const [position, s] of segments.entries()) {
      db.prepare('INSERT INTO selection_segments VALUES (?, ?, ?, ?, ?)')
        .run(id, s.slug, s.name, position, s.isDefault ? 1 : 0);
    }
    for (const vid of selection.items) {
      const v = vacancies.find((x) => x.id === vid);
      for (const segment of v.segments || ['full']) {
        db.prepare('INSERT INTO selection_items VALUES (?, ?, ?, ?, ?, ?, ?, ?)')
          .run(id, segment, vid, v.class || 'hot_lead',
            classOrder.indexOf(v.class || 'hot_lead'), 15, v.score, 1);
      }
    }
  }
  db.close();
  return file;
}

function tempDir(prefix = 'work-ide-app-') {
  return fs.mkdtempSync(path.join(os.tmpdir(), prefix));
}

// A standard two-run fixture: 20 hot leads seen in run 1, plus fresh ones in
// run 2 (hot and worth_a_look), split over two markets. The old ones came from
// linkedin, the new ones from devitjobs.
function standardDatabase(file, options = {}) {
  const vacancies = [];
  for (let i = 0; i < 20; i += 1) {
    vacancies.push({ id: `old${String(i).padStart(2, '0')}`, score: 90 - i, class: 'hot_lead',
      segments: ['full', i % 2 ? 'uk' : 'worldwide'] });
  }
  for (let i = 0; i < 3; i += 1) {
    vacancies.push({ id: `new${i}`, score: 40 - i, class: 'worth_a_look', segments: ['full', 'uk'],
      source: 'devitjobs' });
  }
  const old = vacancies.filter((v) => v.id.startsWith('old')).map((v) => v.id);
  return createDatabase(file, {
    ...options,
    vacancies,
    segments: [
      { slug: 'worldwide', name: 'Worldwide' },
      { slug: 'uk', name: 'United Kingdom' },
      { slug: 'full', name: 'Everything', isDefault: true },
    ],
    selections: [
      { kind: 'run', items: old },
      { kind: 'run', items: vacancies.map((v) => v.id) },
    ],
  });
}

module.exports = { REPO, SCHEMA_DIR, createDatabase, standardDatabase, tempDir, view };
