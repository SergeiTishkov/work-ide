'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { DatabaseSync } = require('node:sqlite');
const { Store, SchemaMismatchError, nowIso } = require('../../main/store');
const { SCHEMA_DIR, standardDatabase, tempDir } = require('../helpers/fixture-db');

function setup() {
  const file = standardDatabase(path.join(tempDir(), 'test.sqlite'));
  const store = new Store({ schemaDir: SCHEMA_DIR, databasePathOf: (p) => (p === 'test' ? file : null) });
  return { store, file };
}

test('segments of the latest selection, default marked', () => {
  const { store } = setup();
  const data = store.segments('test');
  assert.equal(data.selection.id, 2);
  assert.equal(data.displayName, 'Test search');
  assert.deepEqual(data.segments.map((s) => [s.slug, s.isDefault]),
    [['worldwide', false], ['uk', false], ['full', true]]);
  store.closeAll();
});

test('an identity never collected has no selection and lists nothing', () => {
  const { store } = setup();
  assert.deepEqual(store.segments('other'), { selection: null, displayName: null, segments: [] });
  assert.deepEqual(store.listing('other', 'full', 'all'), []);
  assert.equal(store.counts('other', 'full').all, 0);
  assert.deepEqual(store.pendingFeedback('other'), { bugged: 0, rejected: 0 });
});

test('listing: fresh ones by default, the per-class limit on "all"', () => {
  const { store } = setup();
  assert.deepEqual(store.listing('test', 'full', 'fresh_new').map((r) => r.id), ['new0', 'new1', 'new2']);
  const all = store.listing('test', 'full', 'all');
  assert.equal(all.filter((r) => r.class === 'hot_lead').length, 15);
  assert.equal(all[0].view.title, 'Senior .NET Developer old00');
  assert.equal(all[0].fresh, false);
  assert.deepEqual(store.listing('test', 'uk', 'fresh').map((r) => r.id), ['new0', 'new1', 'new2']);
  store.closeAll();
});

test('feedback writes only the feedback columns, and the next one moves up', () => {
  const { store, file } = setup();
  store.setFeedback('test', 'old00', 'bugged', '  Java, not .NET  ');
  const all = store.listing('test', 'full', 'all');
  const hot = all.filter((r) => r.class === 'hot_lead');
  assert.equal(hot.filter((r) => r.feedback.status === 'new').length, 15);
  assert.ok(hot.some((r) => r.id === 'old15'), 'the 16th moved up');
  const [bugged] = store.listing('test', 'full', 'bugged');
  assert.equal(bugged.id, 'old00');
  assert.equal(bugged.feedback.buggedReason, 'Java, not .NET');
  assert.equal(bugged.feedback.rejectedReason, null);
  store.closeAll();

  const db = new DatabaseSync(file);
  const row = db.prepare('SELECT d.data, v.view, v.feedback_selection_id FROM vacancy_identity v '
    + "JOIN vacancies d ON d.id = v.vacancy_id WHERE v.identity_id = 'test' AND v.vacancy_id = ?").get('old00');
  assert.equal(JSON.parse(row.data).title, 'data old00', 'data untouched');
  assert.equal(JSON.parse(row.view).id, 'old00', 'view untouched');
  assert.equal(row.feedback_selection_id, 2, 'remembers the selection it was given in');
  db.close();
});

test('undo returns a vacancy to new and erases its reason', () => {
  const { store } = setup();
  store.setFeedback('test', 'new0', 'rejected', 'too much travel');
  assert.deepEqual(store.pendingFeedback('test'), { bugged: 0, rejected: 1 });
  store.setFeedback('test', 'new0', 'new');
  const [row] = store.listing('test', 'full', 'fresh_new');
  assert.equal(row.id, 'new0');
  assert.equal(row.feedback.rejectedReason, null);
  assert.deepEqual(store.pendingFeedback('test'), { bugged: 0, rejected: 0 });
  store.closeAll();
});

test('counts agree with the fully expanded listing for every filter', () => {
  const { store } = setup();
  store.setFeedback('test', 'old00', 'applied');
  store.setFeedback('test', 'new1', 'rejected');
  for (const segment of ['full', 'uk', 'worldwide']) {
    const counts = store.counts('test', segment);
    for (const filter of Object.keys(counts)) {
      const all = store.listing('test', segment, filter, ['hot_lead', 'worth_a_look']);
      assert.equal(counts[filter], all.length, `${segment}/${filter}`);
    }
  }
  store.closeAll();
});

test('bad input is refused', () => {
  const { store } = setup();
  assert.throws(() => store.setFeedback('test', 'old00', 'maybe'));
  assert.throws(() => store.setFeedback('test', 'nope', 'applied'));
  assert.throws(() => store.listing('test', 'full', 'whatever'));
  store.closeAll();
});

test('a database of another schema version is refused', () => {
  const { store, file } = setup();
  const db = new DatabaseSync(file);
  db.prepare("UPDATE meta SET value = '999' WHERE key = 'schema_version'").run();
  db.close();
  assert.throws(() => store.segments('test'), SchemaMismatchError);
});

test('timestamps in the format tools/db.py writes', () => {
  assert.equal(nowIso(new Date('2026-09-29T10:11:12.345Z')), '2026-09-29T10:11:12+00:00');
});

function insertRun(file, {
  heartbeat, pid, host, stage = 'check links', status = 'running', identity = 'test',
}) {
  const db = new DatabaseSync(file);
  db.prepare('INSERT INTO pipeline_runs (identity_id, started_at, heartbeat_at, status, stage, pid, host) '
    + 'VALUES (?, ?, ?, ?, ?, ?, ?)')
    .run(identity, '2026-09-30T00:23:41+00:00', heartbeat, status, stage, pid, host);
  db.close();
}

test('a live pipeline run is reported with its stage', () => {
  const { file } = setup();
  insertRun(file, { heartbeat: nowIso(), pid: process.pid, host: 'here' });
  const store = new Store({ schemaDir: SCHEMA_DIR, databasePathOf: () => file, hostname: 'here' });
  assert.deepEqual(store.pipelineStatus('test'), {
    running: true, stage: 'check links', startedAt: '2026-09-30T00:23:41+00:00',
    pid: process.pid, host: 'here',
  });
  store.closeAll();
});

test('a run that stopped beating is not running, whatever its row says', () => {
  const { file } = setup();
  insertRun(file, { heartbeat: nowIso(new Date(Date.now() - 60000)), pid: process.pid, host: 'here' });
  const store = new Store({ schemaDir: SCHEMA_DIR, databasePathOf: () => file, hostname: 'here' });
  assert.deepEqual(store.pipelineStatus('test'), { running: false });
  store.closeAll();
});

test('a run on this machine whose process is gone is not running at once', () => {
  const { file } = setup();
  insertRun(file, { heartbeat: nowIso(), pid: 4242, host: 'here' });
  const alive = new Set();
  const store = new Store({
    schemaDir: SCHEMA_DIR, databasePathOf: () => file, hostname: 'here', isPidAlive: (p) => alive.has(p),
  });
  assert.equal(store.pipelineStatus('test').running, false);
  const elsewhere = new Store({
    schemaDir: SCHEMA_DIR, databasePathOf: () => file, hostname: 'another-machine', isPidAlive: () => false,
  });
  assert.equal(elsewhere.pipelineStatus('test').running, true, 'a pid on another host cannot be checked');
  store.closeAll();
  elsewhere.closeAll();
});

test('a run of another identity is not this one, but it holds the shared base', () => {
  const { file } = setup();
  insertRun(file, { heartbeat: nowIso(), pid: process.pid, host: 'here', identity: 'other' });
  const store = new Store({ schemaDir: SCHEMA_DIR, databasePathOf: () => file, hostname: 'here' });
  assert.deepEqual(store.pipelineStatus('test'), { running: false, busyWith: 'other' });
  assert.equal(store.pipelineStatus('other').running, true);
  store.closeAll();
});

test('one base, two identities: each sees its own selections and answers', () => {
  const { file } = setup();
  const store = new Store({ schemaDir: SCHEMA_DIR, databasePathOf: () => file });
  const db = new DatabaseSync(file);
  db.prepare("INSERT INTO identities (id, display_name, created_at) VALUES ('other', 'Other', '2026-10-05')").run();
  db.prepare("INSERT INTO vacancy_identity (identity_id, vacancy_id, score, class) VALUES ('other', 'old00', 10, 'long_shot')").run();
  db.close();
  store.setFeedback('test', 'old00', 'applied');
  assert.equal(store.segments('other').selection, null, 'never collected for other');
  assert.equal(store.segments('other').displayName, 'Other');
  store.setFeedback('other', 'old00', 'rejected', 'not for this one');
  store.closeAll();
  const check = new DatabaseSync(file);
  const rows = check.prepare('SELECT identity_id, feedback_status FROM vacancy_identity '
    + "WHERE vacancy_id = 'old00' ORDER BY identity_id").all();
  check.close();
  assert.deepEqual(rows.map((r) => [r.identity_id, r.feedback_status]),
    [['other', 'rejected'], ['test', 'applied']]);
});

test('finished runs and a missing database mean not running', () => {
  const { store, file } = setup();
  insertRun(file, { heartbeat: nowIso(), pid: process.pid, host: 'x', status: 'finished' });
  assert.deepEqual(store.pipelineStatus('test'), { running: false });
  assert.deepEqual(store.pipelineStatus('other'), { running: false });
  store.closeAll();
});

test('counts are whole numbers; the list is capped unless a class is expanded', () => {
  const { store } = setup();
  const counts = store.counts('test', 'full');
  assert.equal(counts.all, 23, 'every vacancy, not the 15 + 3 on screen');
  assert.deepEqual(store.classTotals('test', 'full', 'all'), { hot_lead: 20, worth_a_look: 3 });
  assert.equal(store.listing('test', 'full', 'all').length, 18);
  assert.equal(store.listing('test', 'full', 'all', ['hot_lead']).length, 23);
  const byMarket = store.counts('test', 'uk').all + store.counts('test', 'worldwide').all;
  assert.equal(byMarket, counts.all, 'markets add up to everything');
  store.closeAll();
});

test('"shown" raises one class\'s limit; "fit" narrows the list, the counts and the sources', () => {
  const { store } = setup();
  const hot = (rows) => rows.filter((r) => r.class === 'hot_lead').length;
  assert.equal(hot(store.listing('test', 'full', 'all', [], '', { shown: { hot_lead: 17 } })), 17);
  assert.equal(hot(store.listing('test', 'full', 'all', [], '', { shown: { worth_a_look: 17 } })), 15);

  const worth = store.listing('test', 'full', 'all', [], '', { fit: 'worth_a_look' });
  assert.deepEqual(worth.map((r) => r.class), ['worth_a_look', 'worth_a_look', 'worth_a_look']);
  assert.equal(store.counts('test', 'full', '', 'worth_a_look').all, 3);
  assert.deepEqual(store.sources('test', 'full', 'all', 'worth_a_look').map((s) => [s.source, s.total]),
    [['devitjobs', 3]]);
  assert.deepEqual(store.classTotals('test', 'full', 'all'), { hot_lead: 20, worth_a_look: 3 });

  // the funnel reads the class from the view
  store.setFeedback('test', 'old00', 'applied');
  assert.equal(store.listing('test', 'full', 'applied', [], '', { fit: 'hot_lead' }).length, 1);
  assert.equal(store.listing('test', 'full', 'applied', [], '', { fit: 'worth_a_look' }).length, 0);
  assert.equal(store.counts('test', 'full', '', 'worth_a_look').applied, 0);
  assert.equal(store.counts('test', 'full', '', 'hot_lead').applied, 1);
  assert.deepEqual(store.sources('test', 'full', 'applied', 'worth_a_look'), []);
  store.closeAll();
});

test('"expired" is a status of its own: no reason, out of the list, not pending review', () => {
  const { store } = setup();
  store.setFeedback('test', 'new0', 'expired', 'ignored');
  assert.deepEqual(store.listing('test', 'full', 'fresh_new').map((r) => r.id), ['new1', 'new2']);
  const [row] = store.listing('test', 'full', 'expired');
  assert.equal(row.id, 'new0');
  assert.equal(row.feedback.rejectedReason, null);
  assert.equal(row.feedback.buggedReason, null);
  assert.equal(store.counts('test', 'full').expired, 1);
  assert.deepEqual(store.pendingFeedback('test'), { bugged: 0, rejected: 0 });
  store.closeAll();
});

test('the funnel is written step by step, arrays and dates included', () => {
  const { file } = setup();
  let tick = 0;
  const clock = () => `2026-10-0${++tick}T10:00:00+00:00`;
  const store = new Store({ schemaDir: SCHEMA_DIR, databasePathOf: () => file, clock });
  store.setFeedback('test', 'new0', 'applied');
  store.advance('test', 'new0', 'contacted', '');
  store.advance('test', 'new0', 'interview', 'tech round');
  store.advance('test', 'new0', 'interview', '');
  store.advance('test', 'new0', 'awaiting_final', 'answer by Friday');
  assert.throws(() => store.advance('test', 'new0', 'contacted', ''), /cannot go/);
  store.advance('test', 'new0', 'awaiting_offer', 'within two weeks');
  store.advance('test', 'new0', 'declined', '');
  store.closeAll();

  const db = new DatabaseSync(file);
  const row = db.prepare("SELECT * FROM vacancy_identity WHERE identity_id = 'test' AND vacancy_id = ?").get('new0');
  db.close();
  assert.equal(row.feedback_status, 'declined');
  assert.equal(row.applied_at, '2026-10-01T10:00:00+00:00');
  assert.equal(row.contact_comment, '', 'an empty comment is "", not NULL');
  assert.equal(row.interview_comments, '["tech round",""]');
  assert.equal(row.interview_at, '["2026-10-03T10:00:00+00:00","2026-10-04T10:00:00+00:00"]');
  assert.equal(row.final_comment, 'answer by Friday');
  assert.equal(row.awaiting_offer_comment, 'within two weeks');
  assert.equal(row.awaiting_offer_at, '2026-10-07T10:00:00+00:00');   // the refused step took a tick too
  assert.equal(row.declined_comment, '', 'the employer\'s no, nothing written: "" not NULL');
  assert.equal(row.declined_at, '2026-10-08T10:00:00+00:00');
});

test('the new funnel filters count and list applications across markets', () => {
  const { store } = setup();
  store.setFeedback('test', 'old00', 'applied');
  store.advance('test', 'old00', 'declined', 'not enough Azure');
  store.setFeedback('test', 'old01', 'applied');
  store.advance('test', 'old01', 'contacted', '');
  store.advance('test', 'old01', 'awaiting_final', '');
  store.advance('test', 'old01', 'awaiting_offer', '');
  const counts = store.counts('test', 'uk');
  assert.equal(counts.declined, 1);
  assert.equal(counts.awaiting_offer, 1);
  const [declined] = store.listing('test', 'uk', 'declined');
  assert.equal(declined.feedback.declinedComment, 'not enough Azure');
  assert.deepEqual(store.listing('test', 'uk', 'awaiting_offer').map((r) => r.id), ['old01']);
  store.stepBack('test', 'old00');
  assert.equal(store.listing('test', 'uk', 'applied')[0].id, 'old00', 'undo returns to applied');
  store.closeAll();
});

test('funnel filters list applications in every market, and undo steps back', () => {
  const { store } = setup();
  store.setFeedback('test', 'old00', 'applied');       // an old01..: worldwide / old00: worldwide
  store.advance('test', 'old00', 'contacted', 'hr');
  for (const segment of ['full', 'uk', 'worldwide']) {
    assert.deepEqual(store.listing('test', segment, 'contacted').map((r) => r.id), ['old00'], segment);
    assert.equal(store.counts('test', segment).contacted, 1);
  }
  const [row] = store.listing('test', 'full', 'contacted');
  assert.equal(row.feedback.contactComment, 'hr');
  assert.deepEqual(row.feedback.interviewComments, []);

  store.stepBack('test', 'old00');
  assert.deepEqual(store.listing('test', 'full', 'applied').map((r) => r.id), ['old00']);
  store.stepBack('test', 'old00');
  assert.equal(store.counts('test', 'full').applied, 0);
  store.closeAll();
});

test('comments are edited in place', () => {
  const { store } = setup();
  store.setFeedback('test', 'new1', 'applied');
  store.advance('test', 'new1', 'contacted', '');
  store.advance('test', 'new1', 'interview', '');
  store.editComment('test', 'new1', 'interview', 0, 'system design, went fine');
  store.editComment('test', 'new1', 'contact', null, 'recruiter on LinkedIn');
  const [row] = store.listing('test', 'full', 'interview');
  assert.deepEqual(row.feedback.interviewComments, ['system design, went fine']);
  assert.equal(row.feedback.contactComment, 'recruiter on LinkedIn');

  store.setFeedback('test', 'new2', 'rejected', 'travel');
  store.editComment('test', 'new2', 'rejected', null, 'travel 50%');
  assert.equal(store.listing('test', 'full', 'rejected')[0].feedback.rejectedReason, 'travel 50%');
  store.closeAll();
});

test('a row carries its lines in every language, and in funnel filters too', () => {
  const { store, file } = setup();
  const db = new DatabaseSync(file);
  const views = { en: { title: 'in English' }, ru: { title: 'in Russian' } };
  db.prepare("UPDATE vacancy_identity SET views = ? WHERE identity_id = 'test' AND vacancy_id = ?")
    .run(JSON.stringify(views), 'old00');
  db.close();
  const all = store.listing('test', 'full', 'all');
  assert.deepEqual(all.find((r) => r.id === 'old00').views, views);
  assert.equal(all.find((r) => r.id === 'old01').views, null, 'a row from before has only its view');
  store.setFeedback('test', 'old00', 'applied', null);
  assert.deepEqual(store.listing('test', 'full', 'applied')[0].views, views);
  store.closeAll();
});

test('an offer and the first day are written to their own columns', () => {
  const { store, file } = setup();
  store.setFeedback('test', 'new1', 'applied');
  for (const step of ['contacted', 'awaiting_final', 'awaiting_offer']) store.advance('test', 'new1', step, '');
  store.advance('test', 'new1', 'offered', 'from November');
  store.advance('test', 'new1', 'started', '');
  assert.deepEqual(store.listing('test', 'uk', 'started').map((r) => r.id), ['new1']);
  assert.equal(store.counts('test', 'uk').started, 1);
  store.closeAll();
  const db = new DatabaseSync(file);
  const row = db.prepare("SELECT * FROM vacancy_identity WHERE identity_id = 'test' AND vacancy_id = ?").get('new1');
  db.close();
  assert.equal(row.feedback_status, 'started');
  assert.equal(row.offered_comment, 'from November');
  assert.equal(row.started_comment, '');
  assert.ok(row.offered_at && row.started_at);
});

// The owner, 2026-10-04: a "Source" drop-down next to the filter, both applied
// at once.
test('the source narrows the listing, the counts and the class totals', () => {
  const { store } = setup();
  assert.deepEqual(store.listing('test', 'full', 'all', [], 'devitjobs').map((r) => r.id),
    ['new0', 'new1', 'new2']);
  assert.equal(store.listing('test', 'full', 'all', [], 'linkedin').length, 15, 'still capped per class');
  assert.equal(store.counts('test', 'full', 'linkedin').all, 20);
  assert.equal(store.counts('test', 'full', 'devitjobs').fresh_new, 3);
  assert.equal(store.counts('test', 'full', 'linkedin').fresh_new, 0);
  assert.deepEqual(store.classTotals('test', 'full', 'all', 'devitjobs'), { worth_a_look: 3 });
  assert.equal(store.counts('test', 'full').all, 23, 'no source: every board');
  store.closeAll();
});

test('the source list counts each board under the status filter', () => {
  const { store } = setup();
  assert.deepEqual(store.sources('test', 'full', 'all'),
    [{ source: 'linkedin', site: null, total: 20 }, { source: 'devitjobs', site: null, total: 3 }]);
  assert.deepEqual(store.sources('test', 'full', 'fresh_new'), [{ source: 'devitjobs', site: null, total: 3 }]);
  store.setFeedback('test', 'old00', 'applied');
  assert.deepEqual(store.sources('test', 'full', 'applied'), [{ source: 'linkedin', site: null, total: 1 }]);
  assert.deepEqual(store.listing('test', 'full', 'applied', [], 'devitjobs'), []);
  assert.equal(store.counts('test', 'full', 'linkedin').applied, 1);
  assert.equal(store.counts('test', 'full', 'devitjobs').applied, 0);
  assert.deepEqual(store.sources('other', 'full', 'all'), []);
  store.closeAll();
});

test('each board comes with its website when the selection recorded them', () => {
  const { store, file } = setup();
  const db = new DatabaseSync(file);
  db.prepare("INSERT INTO meta (key, value) VALUES ('source_sites', ?)")
    .run(JSON.stringify({ linkedin: 'linkedin.com' }));
  db.close();
  assert.deepEqual(store.sources('test', 'full', 'all'),
    [{ source: 'linkedin', site: 'linkedin.com', total: 20 }, { source: 'devitjobs', site: null, total: 3 }]);
  store.closeAll();
});
