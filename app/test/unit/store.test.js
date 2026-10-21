'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { DatabaseSync } = require('node:sqlite');
const {
  Store, SchemaMismatchError, nowIso, NEW, VIEW_STATUSES, FRESHNESS,
} = require('../../main/store');
const { SCHEMA_DIR, standardDatabase, tempDir } = require('../helpers/fixture-db');

function setup() {
  const file = standardDatabase(path.join(tempDir(), 'test.sqlite'));
  const store = new Store({ schemaDir: SCHEMA_DIR, databasePathOf: (p) => (p === 'test' ? file : null) });
  return { store, file };
}

// The single filters the app had before 2026-10-07, as views of the four
// drop-downs (tests/test_selections.py, _view).
const FILTERS = ['fresh_new', 'no_feedback', 'all', 'fresh', ...VIEW_STATUSES.filter((s) => s !== 'new')];
function v(segments = 'full', filter = 'fresh_new', { source, fit } = {}) {
  return {
    segments: segments == null ? null : [].concat(segments),
    statuses: { fresh_new: NEW, no_feedback: NEW, all: VIEW_STATUSES, fresh: VIEW_STATUSES }[filter] || [filter],
    fresh: ['fresh_new', 'fresh'].includes(filter) ? ['fresh'] : FRESHNESS,
    sources: source ? [source] : null,
    fits: fit ? [fit] : null,
  };
}

// The view's size by the "Show" drop-down's numbers; both axes agree.
function count(store, identity, view) {
  const counts = store.counts(identity, view);
  const byStatus = view.statuses.reduce((n, s) => n + counts.statuses[s], 0);
  const byFresh = view.fresh.reduce((n, f) => n + counts.fresh[f], 0);
  assert.equal(byStatus, byFresh, JSON.stringify(view));
  return byStatus;
}

test('segments of the latest selection, default marked', () => {
  const { store } = setup();
  const data = store.segments('test');
  assert.equal(data.selection.id, 2);
  assert.equal(data.displayName, 'Test search');
  assert.deepEqual(data.segments.map((s) => [s.slug, s.isDefault]),
    [['worldwide', false], ['uk', false], ['full', true]]);
  assert.deepEqual(data.segments.map((s) => s.everything), [false, false, true]);
  // Each name in every language the configuration gives; none before version 9.
  assert.deepEqual(data.segments.map((s) => s.names),
    [{}, {}, { en: 'Everything', ru: 'Vsyo vmeste' }]);
  store.closeAll();
});

test('an identity never collected has no selection and lists nothing', () => {
  const { store } = setup();
  assert.deepEqual(store.segments('other'), { selection: null, displayName: null, segments: [] });
  assert.deepEqual(store.listing('other', v('full', 'all')), []);
  assert.equal(count(store, 'other', v('full', 'all')), 0);
  assert.deepEqual(store.pendingFeedback('other'), { bugged: 0, rejected: 0 });
});

test('listing: fresh ones by default, the per-class limit on "all"', () => {
  const { store } = setup();
  assert.deepEqual(store.listing('test', v('full', 'fresh_new')).map((r) => r.id), ['new0', 'new1', 'new2']);
  const all = store.listing('test', v('full', 'all'));
  assert.equal(all.filter((r) => r.class === 'hot_lead').length, 15);
  assert.equal(all[0].view.title, 'Senior .NET Developer old00');
  assert.equal(all[0].fresh, false);
  assert.deepEqual(store.listing('test', v('uk', 'fresh')).map((r) => r.id), ['new0', 'new1', 'new2']);
  store.closeAll();
});

test('feedback writes only the feedback columns, and the next one moves up', () => {
  const { store, file } = setup();
  store.setFeedback('test', 'old00', 'bugged', '  Java, not .NET  ');
  const all = store.listing('test', v('full', 'all'));
  const hot = all.filter((r) => r.class === 'hot_lead');
  assert.equal(hot.filter((r) => r.feedback.status === 'new').length, 15);
  assert.ok(hot.some((r) => r.id === 'old15'), 'the 16th moved up');
  const [bugged] = store.listing('test', v('full', 'bugged'));
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

test('every write answers with the record as the base now holds it', () => {
  const { store } = setup();
  const rejected = store.setFeedback('test', 'new0', 'rejected', '  too much travel ');
  assert.equal(rejected.status, 'rejected');
  assert.equal(rejected.rejectedReason, 'too much travel');
  const applied = store.setFeedback('test', 'new1', 'applied');
  assert.equal(applied.status, 'applied');
  const contacted = store.advance('test', 'new1', 'contacted', 'a call on Monday');
  assert.equal(contacted.status, 'contacted');
  assert.equal(contacted.contactComment, 'a call on Monday');
  assert.equal(store.editComment('test', 'new1', 'contact', null, 'a call on Tuesday').contactComment,
    'a call on Tuesday');
  const back = store.stepBack('test', 'new1');
  assert.equal(back.status, 'applied');
  const [row] = store.listing('test', v('full', 'applied'));
  assert.deepEqual(back, row.feedback, 'the same record the list reads');
  store.closeAll();
});

test('undo returns a vacancy to new and erases its reason', () => {
  const { store } = setup();
  store.setFeedback('test', 'new0', 'rejected', 'too much travel');
  assert.deepEqual(store.pendingFeedback('test'), { bugged: 0, rejected: 1 });
  store.setFeedback('test', 'new0', 'new');
  const [row] = store.listing('test', v('full', 'fresh_new'));
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
    for (const filter of FILTERS) {
      const all = store.listing('test', v(segment, filter), { expanded: ['hot_lead', 'worth_a_look'] });
      assert.equal(count(store, 'test', v(segment, filter)), all.length, `${segment}/${filter}`);
    }
  }
  store.closeAll();
});

test('bad input is refused', () => {
  const { store } = setup();
  assert.throws(() => store.setFeedback('test', 'old00', 'maybe'));
  assert.throws(() => store.setFeedback('test', 'nope', 'applied'));
  assert.throws(() => store.listing('test', v('full', 'whatever')), /unknown status/);
  assert.throws(() => store.counts('test', { ...v('full'), fresh: ['stale'] }), /unknown status, freshness, age or role/);
  assert.throws(() => store.ages('test', { ...v('full'), ages: ['ancient'] }), /unknown status, freshness, age or role/);
  assert.throws(() => store.roles('test', { ...v('full'), roles: ['sideways'] }), /unknown status, freshness, age or role/);
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
  const all = count(store, 'test', v('full', 'all'));
  assert.equal(all, 23, 'every vacancy, not the 15 + 3 on screen');
  assert.deepEqual(store.classTotals('test', v('full', 'all')), { hot_lead: 20, worth_a_look: 3 });
  assert.equal(store.listing('test', v('full', 'all')).length, 18);
  assert.equal(store.listing('test', v('full', 'all'), { expanded: ['hot_lead'] }).length, 23);
  const byMarket = count(store, 'test', v('uk', 'all')) + count(store, 'test', v('worldwide', 'all'));
  assert.equal(byMarket, all, 'markets add up to everything');
  store.closeAll();
});

test('"shown" raises one class\'s limit; "fit" narrows the list, the counts and the sources', () => {
  const { store } = setup();
  const hot = (rows) => rows.filter((r) => r.class === 'hot_lead').length;
  assert.equal(hot(store.listing('test', v('full', 'all'), { shown: { hot_lead: 17 } })), 17);
  assert.equal(hot(store.listing('test', v('full', 'all'), { shown: { worth_a_look: 17 } })), 15);

  const worth = store.listing('test', v('full', 'all', { fit: 'worth_a_look' }));
  assert.deepEqual(worth.map((r) => r.class), ['worth_a_look', 'worth_a_look', 'worth_a_look']);
  assert.equal(count(store, 'test', v('full', 'all', { fit: 'worth_a_look' })), 3);
  assert.deepEqual(store.sources('test', v('full', 'all', { fit: 'worth_a_look' })).map((s) => [s.source, s.total]),
    [['devitjobs', 3]]);
  assert.deepEqual(store.classTotals('test', v('full', 'all')), { hot_lead: 20, worth_a_look: 3 });
  assert.deepEqual(store.classTotals('test', v('full', 'all', { fit: 'worth_a_look' })),
    { hot_lead: 20, worth_a_look: 3 }, 'the "Fit" drop-down counts each class whatever is chosen in it');

  // the funnel reads the class from the view
  store.setFeedback('test', 'old00', 'applied');
  assert.equal(store.listing('test', v('full', 'applied', { fit: 'hot_lead' })).length, 1);
  assert.equal(store.listing('test', v('full', 'applied', { fit: 'worth_a_look' })).length, 0);
  assert.equal(count(store, 'test', v('full', 'applied', { fit: 'worth_a_look' })), 0);
  assert.equal(count(store, 'test', v('full', 'applied', { fit: 'hot_lead' })), 1);
  assert.deepEqual(store.sources('test', v('full', 'applied', { fit: 'worth_a_look' })), []);
  store.closeAll();
});

test('"expired" is a status of its own: no reason, out of the list, not pending review', () => {
  const { store } = setup();
  store.setFeedback('test', 'new0', 'expired', 'ignored');
  assert.deepEqual(store.listing('test', v('full', 'fresh_new')).map((r) => r.id), ['new1', 'new2']);
  const [row] = store.listing('test', v('full', 'expired'));
  assert.equal(row.id, 'new0');
  assert.equal(row.feedback.rejectedReason, null);
  assert.equal(row.feedback.buggedReason, null);
  assert.equal(count(store, 'test', v('full', 'expired')), 1);
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
  const counts = store.counts('test', v('uk', 'all')).statuses;
  assert.equal(counts.declined, 1);
  assert.equal(counts.awaiting_offer, 1);
  const [declined] = store.listing('test', v('uk', 'declined'));
  assert.equal(declined.feedback.declinedComment, 'not enough Azure');
  assert.deepEqual(store.listing('test', v('uk', 'awaiting_offer')).map((r) => r.id), ['old01']);
  store.stepBack('test', 'old00');
  assert.equal(store.listing('test', v('uk', 'applied'))[0].id, 'old00', 'undo returns to applied');
  store.closeAll();
});

test('funnel filters list applications in every market, and undo steps back', () => {
  const { store } = setup();
  store.setFeedback('test', 'old00', 'applied');       // an old01..: worldwide / old00: worldwide
  store.advance('test', 'old00', 'contacted', 'hr');
  for (const segment of ['full', 'uk', 'worldwide']) {
    assert.deepEqual(store.listing('test', v(segment, 'contacted')).map((r) => r.id), ['old00'], segment);
    assert.equal(count(store, 'test', v(segment, 'contacted')), 1);
  }
  const [row] = store.listing('test', v('full', 'contacted'));
  assert.equal(row.feedback.contactComment, 'hr');
  assert.deepEqual(row.feedback.interviewComments, []);

  store.stepBack('test', 'old00');
  assert.deepEqual(store.listing('test', v('full', 'applied')).map((r) => r.id), ['old00']);
  store.stepBack('test', 'old00');
  assert.equal(count(store, 'test', v('full', 'applied')), 0);
  store.closeAll();
});

test('comments are edited in place', () => {
  const { store } = setup();
  store.setFeedback('test', 'new1', 'applied');
  store.advance('test', 'new1', 'contacted', '');
  store.advance('test', 'new1', 'interview', '');
  store.editComment('test', 'new1', 'interview', 0, 'system design, went fine');
  store.editComment('test', 'new1', 'contact', null, 'recruiter on LinkedIn');
  const [row] = store.listing('test', v('full', 'interview'));
  assert.deepEqual(row.feedback.interviewComments, ['system design, went fine']);
  assert.equal(row.feedback.contactComment, 'recruiter on LinkedIn');

  store.setFeedback('test', 'new2', 'rejected', 'travel');
  store.editComment('test', 'new2', 'rejected', null, 'travel 50%');
  assert.equal(store.listing('test', v('full', 'rejected'))[0].feedback.rejectedReason, 'travel 50%');
  store.closeAll();
});

test('a row carries its lines in every language, and in funnel filters too', () => {
  const { store, file } = setup();
  const db = new DatabaseSync(file);
  const views = { en: { title: 'in English' }, ru: { title: 'in Russian' } };
  db.prepare("UPDATE vacancy_identity SET views = ? WHERE identity_id = 'test' AND vacancy_id = ?")
    .run(JSON.stringify(views), 'old00');
  db.close();
  const all = store.listing('test', v('full', 'all'));
  assert.deepEqual(all.find((r) => r.id === 'old00').views, views);
  assert.equal(all.find((r) => r.id === 'old01').views, null, 'a row from before has only its view');
  store.setFeedback('test', 'old00', 'applied', null);
  assert.deepEqual(store.listing('test', v('full', 'applied'))[0].views, views);
  store.closeAll();
});

test('an offer and the first day are written to their own columns', () => {
  const { store, file } = setup();
  store.setFeedback('test', 'new1', 'applied');
  for (const step of ['contacted', 'awaiting_final', 'awaiting_offer']) store.advance('test', 'new1', step, '');
  store.advance('test', 'new1', 'offered', 'from November');
  store.advance('test', 'new1', 'started', '');
  assert.deepEqual(store.listing('test', v('uk', 'started')).map((r) => r.id), ['new1']);
  assert.equal(count(store, 'test', v('uk', 'started')), 1);
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
  assert.deepEqual(store.listing('test', v('full', 'all', { source: 'devitjobs' })).map((r) => r.id),
    ['new0', 'new1', 'new2']);
  assert.equal(store.listing('test', v('full', 'all', { source: 'linkedin' })).length, 15, 'still capped per class');
  assert.equal(count(store, 'test', v('full', 'all', { source: 'linkedin' })), 20);
  assert.equal(count(store, 'test', v('full', 'fresh_new', { source: 'devitjobs' })), 3);
  assert.equal(count(store, 'test', v('full', 'fresh_new', { source: 'linkedin' })), 0);
  assert.deepEqual(store.classTotals('test', v('full', 'all', { source: 'devitjobs' })), { worth_a_look: 3 });
  assert.equal(count(store, 'test', v('full', 'all')), 23, 'no source: every board');
  store.closeAll();
});

test('the source list counts each board under the status filter', () => {
  const { store } = setup();
  assert.deepEqual(store.sources('test', v('full', 'all')),
    [{ source: 'linkedin', site: null, total: 20 }, { source: 'devitjobs', site: null, total: 3 }]);
  assert.deepEqual(store.sources('test', v('full', 'fresh_new')), [{ source: 'devitjobs', site: null, total: 3 }]);
  store.setFeedback('test', 'old00', 'applied');
  assert.deepEqual(store.sources('test', v('full', 'applied')), [{ source: 'linkedin', site: null, total: 1 }]);
  assert.deepEqual(store.listing('test', v('full', 'applied', { source: 'devitjobs' })), []);
  assert.equal(count(store, 'test', v('full', 'applied', { source: 'linkedin' })), 1);
  assert.equal(count(store, 'test', v('full', 'applied', { source: 'devitjobs' })), 0);
  assert.deepEqual(store.sources('other', v('full', 'all')), []);
  store.closeAll();
});

test("each board's yield: every vacancy it brought, shortlisted now and applied to (task 0054)", () => {
  const { store, file } = setup();
  const db = new DatabaseSync(file);
  db.prepare("INSERT INTO meta (key, value) VALUES ('source_sites', ?)").run(JSON.stringify({ linkedin: 'linkedin.com' }));
  db.prepare("UPDATE vacancy_identity SET class = 'not_a_fit' WHERE vacancy_id IN ('old00', 'old01')").run();
  db.prepare("UPDATE vacancy_identity SET duplicate_of = 'old03' WHERE vacancy_id = 'old02'").run();
  db.close();
  store.setFeedback('test', 'new0', 'applied');
  store.setFeedback('test', 'old05', 'rejected', 'not for me');
  const rows = Object.fromEntries(store.sourceYield('test').map((r) => [r.source, r]));
  assert.deepEqual(rows.linkedin, { source: 'linkedin', site: 'linkedin.com', total: 19, shortlisted: 17, applied: 0 });
  assert.deepEqual(rows.devitjobs, { source: 'devitjobs', site: null, total: 3, shortlisted: 3, applied: 1 });
  assert.deepEqual(store.sourceYield('other'), []);
  store.closeAll();
});

test('each board comes with its website when the selection recorded them', () => {
  const { store, file } = setup();
  const db = new DatabaseSync(file);
  db.prepare("INSERT INTO meta (key, value) VALUES ('source_sites', ?)")
    .run(JSON.stringify({ linkedin: 'linkedin.com' }));
  db.close();
  assert.deepEqual(store.sources('test', v('full', 'all')),
    [{ source: 'linkedin', site: 'linkedin.com', total: 20 }, { source: 'devitjobs', site: null, total: 3 }]);
  store.closeAll();
});

// The owner, 2026-10-07: check boxes in the four drop-downs, several rows at once.
test('several markets, statuses, boards and classes at once; an empty choice lists nothing', () => {
  const { store } = setup();
  store.setFeedback('test', 'old00', 'applied');
  store.setFeedback('test', 'new1', 'rejected');
  const view = {
    segments: ['uk', 'worldwide'], statuses: ['new', 'applied', 'rejected'], fresh: FRESHNESS,
    sources: ['linkedin', 'devitjobs'], fits: null,
  };
  const every = ['hot_lead', 'worth_a_look'];
  assert.equal(store.listing('test', view, { expanded: every }).length, 23, 'each vacancy once');
  assert.equal(count(store, 'test', view), 23);
  assert.deepEqual(store.listing('test', { ...view, segments: null }, { expanded: every }).map((r) => r.id).sort(),
    store.listing('test', view, { expanded: every }).map((r) => r.id).sort(), 'no market chosen: everything');
  assert.equal(count(store, 'test', { ...view, sources: [] }), 0);
  assert.deepEqual(store.listing('test', { ...view, fits: [] }), []);
  assert.deepEqual(store.listing('test', { ...view, statuses: [] }), []);

  // each half of "Show" is counted under the other
  const fresh = store.counts('test', { ...view, fresh: ['fresh'] });
  assert.equal(fresh.statuses.new, 2);
  assert.equal(fresh.statuses.rejected, 1);
  assert.equal(fresh.statuses.applied, 0, 'old00 is from an earlier run');
  assert.deepEqual(store.counts('test', { ...view, statuses: ['applied'] }).fresh, { fresh: 0, earlier: 1 });
  store.closeAll();
});

// The owner, 2026-10-14: a fifth drop-down, "Company" — the intermediaries by
// kind and by name, every other company one row. The kinds are the
// pipeline's (meta 'company_kinds', tools/company_kinds.py).
function withCompanies(file) {
  const db = new DatabaseSync(file);
  const setCompany = db.prepare(
    "UPDATE vacancy_identity SET view = json_set(view, '$.company', ?) WHERE vacancy_id = ?");
  setCompany.run('Proxify', 'new0');
  setCompany.run('Proxify AB', 'new1');
  setCompany.run('Hays Technology', 'old00');
  db.prepare("INSERT INTO meta (key, value) VALUES ('company_kinds', ?)").run(JSON.stringify({
    Proxify: { kind: 'marketplace', name: 'Proxify' },
    'Proxify AB': { kind: 'marketplace', name: 'Proxify' },
    'Hays Technology': { kind: 'agency', name: 'Hays' },
  }));
  db.close();
}

test('the company list: each intermediary by name, every other company one row', () => {
  const { store, file } = setup();
  assert.deepEqual(store.companies('test', v('full', 'all')), [{ kind: 'other', name: null, total: 23 }],
    'a base without company kinds: every company is "other"');
  withCompanies(file);
  assert.deepEqual(store.companies('test', v('full', 'all')), [
    { kind: 'other', name: null, total: 20 },
    { kind: 'marketplace', name: 'Proxify', total: 2 },
    { kind: 'agency', name: 'Hays', total: 1 },
  ]);
  const chosen = { ...v('full', 'all'), companies: { kinds: ['other'], hidden: [] } };
  assert.deepEqual(store.companies('test', chosen), store.companies('test', v('full', 'all')),
    'the chosen companies aside');
  assert.deepEqual(store.companies('test', v('full', 'all', { source: 'nowhere' })), []);
  assert.deepEqual(store.companies('other', v('full', 'all')), []);
  store.closeAll();
});

test('the company narrows the list, the counts, the classes and the boards', () => {
  const { store, file } = setup();
  withCompanies(file);
  const every = ['hot_lead', 'worth_a_look'];
  const ids = (companies) => store.listing('test', { ...v('full', 'all'), companies }, { expanded: every })
    .map((r) => r.id).sort();
  assert.deepEqual(ids({ kinds: ['marketplace'], hidden: [] }), ['new0', 'new1']);
  assert.deepEqual(ids({ kinds: ['marketplace', 'agency'], hidden: ['Proxify'] }), ['old00']);
  assert.deepEqual(ids({ kinds: [], hidden: [] }), []);
  assert.equal(ids(null).length, 23);
  const noIntermediaries = { ...v('full', 'all'), companies: { kinds: ['other'], hidden: [] } };
  assert.equal(count(store, 'test', noIntermediaries), 20);
  const totals = store.classTotals('test', noIntermediaries);
  assert.equal(Object.values(totals).reduce((a, b) => a + b, 0), 20);
  assert.equal(store.sources('test', noIntermediaries).reduce((a, s) => a + s.total, 0), 20);
  assert.throws(() => store.listing('test', { ...v('full', 'all'), companies: { kinds: ['employer'] } }),
    /unknown company kind/);
  store.closeAll();
});

test('age: the posted date sorts each vacancy into one bucket; the filter narrows list and counts', () => {
  const { store, file } = setup();
  const db = new DatabaseSync(file);
  const day = (n) => new Date(Date.now() - n * 86400000).toISOString().slice(0, 10);
  const setPosted = (id, posted) => db.prepare("UPDATE vacancy_identity SET view = json_set(view, '$.posted_on', ?) "
    + "WHERE identity_id = 'test' AND vacancy_id = ?").run(posted, id);
  setPosted('new0', day(0));
  setPosted('new1', day(5));
  setPosted('new2', day(20));
  db.close();
  const all = v('full', 'all');
  const ages = store.ages('test', { ...all, ages: ['today'] });
  assert.equal(ages.today, 1);
  assert.equal(ages.week, 1);
  assert.equal(ages.month, 1);
  assert.equal(Object.values(ages).reduce((a, b) => a + b, 0), count(store, 'test', all), 'ages ignore their own filter');
  assert.deepEqual(store.listing('test', { ...all, ages: ['today', 'week'] }).map((r) => r.id), ['new0', 'new1']);
  assert.equal(count(store, 'test', { ...all, ages: ['month'] }), 1);
  assert.equal(count(store, 'test', { ...all, ages: [] }), 0);
  store.closeAll();
});

// task 0049: on the stack, another stack the CV fits, a stretch for the CV
test('role: the stretch mark sorts each vacancy into one kind; the filter narrows list and counts', () => {
  const { store, file } = setup();
  const db = new DatabaseSync(file);
  const setFit = (id, fit) => db.prepare("UPDATE vacancy_identity SET view = json_set(view, '$.stretch', "
    + "json_object('fit', ?, 'work_kind', 'data', 'reason', 'r')) WHERE identity_id = 'test' AND vacancy_id = ?")
    .run(fit, id);
  setFit('new0', 'stretch');
  setFit('new1', 'fits');
  db.close();
  const all = v('full', 'all');
  const roles = store.roles('test', { ...all, roles: ['stretch'] });
  assert.equal(roles.stretch, 1);
  assert.equal(roles.off_stack, 1);
  assert.equal(Object.values(roles).reduce((a, b) => a + b, 0), count(store, 'test', all), 'roles ignore their own filter');
  const expanded = { expanded: ['hot_lead', 'worth_a_look'] };
  assert.deepEqual(store.listing('test', { ...all, roles: ['stretch'] }, expanded).map((r) => r.id), ['new0']);
  assert.deepEqual(store.listing('test', { ...all, roles: ['off_stack', 'stretch'] }, expanded).map((r) => r.id).sort(),
    ['new0', 'new1']);
  assert.equal(count(store, 'test', { ...all, roles: ['stack'] }), roles.stack);
  assert.equal(count(store, 'test', { ...all, roles: [] }), 0);
  const ages = store.ages('test', { ...all, roles: ['stretch'] });
  assert.equal(Object.values(ages).reduce((a, b) => a + b, 0), 1, 'the other drop-downs count under it');
  store.closeAll();
});

test('words: each one typed must be in the title, company, board or link, any case or accent; every count follows', () => {
  const { store, file } = setup();
  const db = new DatabaseSync(file);
  db.prepare("UPDATE vacancy_identity SET view = json_set(view, '$.title', 'Backend Engineer (Go)', "
    + "'$.company', 'Zürich Labs') WHERE identity_id = 'test' AND vacancy_id = 'new1'").run();
  db.prepare("UPDATE vacancy_identity SET view = json_set(view, '$.title', 'Разработчик Ёлка') "
    + "WHERE identity_id = 'test' AND vacancy_id = 'new2'").run();
  db.close();
  const all = v('full', 'all');
  const ids = (text) => store.listing('test', { ...all, text }).map((r) => r.id);
  assert.deepEqual(ids('backend'), ['new1']);
  assert.deepEqual(ids('ENGINEER zürich'), ['new1'], 'any case, every word');
  assert.deepEqual(ids('zurich'), ['new1'], 'no accent finds the accented');
  assert.deepEqual(ids('ZÜRICH'), ['new1']);
  assert.deepEqual(ids('разработчик'), ['new2'], 'any alphabet');
  assert.deepEqual(ids('ЕЛКА'), ['new2'], 'Ё is Е with a mark');
  assert.deepEqual(ids('engineer acme'), [], 'a word missing anywhere hides it');
  assert.deepEqual(ids('example.test/new2'), ['new2'], 'the link counts');
  assert.ok(ids('  ').length > 1, 'blank is no filter');
  assert.equal(count(store, 'test', { ...all, text: 'backend' }), 1);
  assert.equal(Object.values(store.classTotals('test', { ...all, text: 'backend' })).reduce((a, b) => a + b, 0), 1);
  assert.equal(store.sources('test', { ...all, text: 'backend' }).reduce((a, s) => a + s.total, 0), 1);
  store.closeAll();
});

test('an identity turned off and on again: the base keeps it, a new one gets its row', () => {
  const { store, file } = setup();
  assert.equal(store.setIdentityActive('test', false), false);
  assert.equal(store.setIdentityActive('test', true), true);
  assert.equal(store.setIdentityActive('test', false), false);
  store.closeAll();
  const db = new DatabaseSync(file);
  assert.equal(db.prepare("SELECT active FROM identities WHERE id = 'test'").get().active, 0);
  db.close();
});
