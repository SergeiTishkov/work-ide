'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const F = require('../../renderer/funnel.js');

const T1 = '2026-10-01T10:00:00+00:00';
const T2 = '2026-10-03T10:00:00+00:00';
const T3 = '2026-10-07T10:00:00+00:00';
const T4 = '2026-10-10T10:00:00+00:00';

function applied() {
  return {
    status: 'applied', at: T1, appliedAt: T1, rejectedReason: null, buggedReason: null,
    contactComment: null, contactAt: null, interviewComments: [], interviewAt: [],
    finalComment: null, finalAt: null,
  };
}

test('what can follow what', () => {
  assert.deepEqual(F.nextSteps('applied'), ['contacted', 'declined']);
  assert.deepEqual(F.nextSteps('contacted'), ['interview', 'awaiting_final', 'declined']);
  assert.deepEqual(F.nextSteps('interview'), ['interview', 'awaiting_final', 'declined']);
  assert.deepEqual(F.nextSteps('awaiting_final'), ['awaiting_offer', 'declined']);
  assert.deepEqual(F.nextSteps('awaiting_offer'), ['declined']);
  assert.deepEqual(F.nextSteps('declined'), []);
  assert.deepEqual(F.nextSteps('new'), []);
  assert.deepEqual(F.nextSteps('rejected'), []);
});

test('a step that happened keeps its comment, and an empty one is "" not null', () => {
  const contacted = F.advance(applied(), 'contacted', null, T2);
  assert.equal(contacted.status, 'contacted');
  assert.equal(contacted.contactComment, '');
  assert.equal(contacted.contactAt, T2);
  const interviewed = F.advance(F.advance(contacted, 'interview', 'tech round', T3), 'interview', '', T4);
  assert.deepEqual(interviewed.interviewComments, ['tech round', '']);
  assert.deepEqual(interviewed.interviewAt, [T3, T4]);
  const waiting = F.advance(interviewed, 'awaiting_final', 'answer by Friday', T4);
  assert.equal(waiting.finalComment, 'answer by Friday');
  assert.equal(waiting.status, 'awaiting_final');
  assert.deepEqual(interviewed.interviewComments, ['tech round', ''], 'the input record is not changed');
});

test('a step out of order is refused', () => {
  assert.throws(() => F.advance(applied(), 'interview', '', T2));
  assert.throws(() => F.advance(applied(), 'awaiting_final', '', T2));
  assert.throws(() => F.advance({ ...applied(), status: 'new' }, 'contacted', '', T2));
});

test('undo goes back one step, forgetting only that step', () => {
  let r = F.advance(applied(), 'contacted', 'hr call', T2);
  r = F.advance(r, 'interview', 'one', T3);
  r = F.advance(r, 'interview', 'two', T4);
  r = F.advance(r, 'awaiting_final', 'soon', T4);

  r = F.stepBack(r, T4);
  assert.equal(r.status, 'interview');
  assert.equal(r.finalComment, null);
  assert.deepEqual(r.interviewComments, ['one', 'two']);
  r = F.stepBack(r, T4);
  assert.equal(r.status, 'interview');
  assert.deepEqual(r.interviewComments, ['one']);
  r = F.stepBack(r, T4);
  assert.equal(r.status, 'contacted');
  assert.deepEqual(r.interviewComments, []);
  assert.equal(r.contactComment, 'hr call');
  r = F.stepBack(r, T4);
  assert.equal(r.status, 'applied');
  assert.equal(r.contactComment, null);
  r = F.stepBack(r, T4);
  assert.equal(r.status, 'new');
  assert.equal(r.appliedAt, null);
});

test('from the final word without interviews, undo returns to the contact', () => {
  const r = F.advance(F.advance(applied(), 'contacted', '', T2), 'awaiting_final', '', T3);
  assert.equal(F.stepBack(r, T4).status, 'contacted');
});

test('undo on a negative answer clears it', () => {
  const r = F.stepBack({ ...applied(), status: 'rejected', rejectedReason: 'far too senior' }, T2);
  assert.equal(r.status, 'new');
  assert.equal(r.rejectedReason, null);
});

test('editing: positive comments may become empty, negative ones become null and are re-dated', () => {
  let r = F.advance(F.advance(applied(), 'contacted', '', T2), 'interview', 'x', T3);
  r = F.editComment(r, 'contact', null, 'they called back', T4);
  assert.equal(r.contactComment, 'they called back');
  r = F.editComment(r, 'interview', 0, '', T4);
  assert.deepEqual(r.interviewComments, ['']);
  assert.equal(r.at, T3, 'editing a positive comment does not re-date the feedback');
  assert.throws(() => F.editComment(r, 'interview', 3, 'no such', T4));

  const rejected = { ...applied(), status: 'rejected', rejectedReason: 'travel', at: T1 };
  const cleared = F.editComment(rejected, 'rejected', null, '   ', T4);
  assert.equal(cleared.rejectedReason, null);
  assert.equal(cleared.at, T4, '/feedback reviews the new words');
  assert.throws(() => F.editComment(rejected, 'bugged', null, 'x', T4));
});

test('the timeline lists every step in order, with its date and comment', () => {
  let r = F.advance(applied(), 'contacted', '', T2);
  r = F.advance(r, 'interview', 'went well', T3);
  r = F.advance(r, 'awaiting_final', '', T4);
  assert.deepEqual(F.timeline(r), [
    { kind: 'applied', at: T1, comment: null, editable: false },
    { kind: 'contact', at: T2, comment: '', editable: true },
    { kind: 'interview', index: 0, at: T3, comment: 'went well', editable: true },
    { kind: 'final', at: T4, comment: '', editable: true },
  ]);
});

test('the timeline shows a negative answer with its reason, and nothing for a new vacancy', () => {
  assert.deepEqual(F.timeline({ ...applied(), status: 'new', appliedAt: null }), []);
  assert.deepEqual(F.timeline({ status: 'bugged', at: T2, buggedReason: 'Java role' }),
    [{ kind: 'bugged', at: T2, comment: 'Java role', editable: true }]);
  assert.deepEqual(F.timeline({ status: 'expired', at: T2 }),
    [{ kind: 'expired', at: T2, comment: null, editable: false }]);
  // Applied before the funnel had dates: the answer's own date stands in.
  assert.deepEqual(F.timeline({ status: 'applied', at: T2 }),
    [{ kind: 'applied', at: T2, comment: null, editable: false }]);
});

test('after the final resolution, the offer; and a no can come at any step', () => {
  const waiting = F.advance(F.advance(applied(), 'contacted', '', T2), 'awaiting_final', '', T3);
  const offer = F.advance(waiting, 'awaiting_offer', 'HR said within two weeks', T4);
  assert.equal(offer.status, 'awaiting_offer');
  assert.equal(offer.offerComment, 'HR said within two weeks');
  assert.equal(offer.offerAt, T4);

  const fellThrough = F.advance(offer, 'declined', null, T4);
  assert.equal(fellThrough.status, 'declined');
  assert.equal(fellThrough.declinedComment, '', 'a step that happened: empty, never null');
  assert.equal(fellThrough.offerComment, 'HR said within two weeks', 'what came before stays');

  const early = F.advance(applied(), 'declined', 'not enough Azure', T2);
  assert.equal(early.declinedComment, 'not enough Azure');
  assert.deepEqual(F.nextSteps(early.status), [], 'nothing follows a no');
  assert.throws(() => F.advance({ ...applied(), status: 'rejected' }, 'declined', '', T2),
    'a "not for me" answer is not an application');
});

test('undo on a no goes back to where the application stood', () => {
  const at = (r) => F.stepBack(F.advance(r, 'declined', 'x', T4), T4);
  assert.equal(at(applied()).status, 'applied');
  const contacted = F.advance(applied(), 'contacted', 'c', T2);
  assert.equal(at(contacted).status, 'contacted');
  const interviewed = F.advance(contacted, 'interview', 'i', T3);
  assert.equal(at(interviewed).status, 'interview');
  const waiting = F.advance(interviewed, 'awaiting_final', 'f', T3);
  assert.equal(at(waiting).status, 'awaiting_final');
  const offer = F.advance(waiting, 'awaiting_offer', 'o', T4);
  const back = at(offer);
  assert.equal(back.status, 'awaiting_offer');
  assert.equal(back.declinedComment, null);
  assert.equal(back.declinedAt, null);
  assert.equal(F.stepBack(offer, T4).status, 'awaiting_final');
  assert.equal(F.stepBack(offer, T4).offerAt, null);
});

test('the timeline ends with the offer and the no, each editable', () => {
  let r = F.advance(applied(), 'contacted', '', T2);
  r = F.advance(r, 'awaiting_final', '', T3);
  r = F.advance(r, 'awaiting_offer', 'soon', T3);
  r = F.advance(r, 'declined', '', T4);
  assert.deepEqual(F.timeline(r).slice(-2), [
    { kind: 'offer', at: T3, comment: 'soon', editable: true },
    { kind: 'declined', at: T4, comment: '', editable: true },
  ]);
  r = F.editComment(r, 'declined', null, 'budget frozen', T4);
  assert.equal(r.declinedComment, 'budget frozen');
  r = F.editComment(r, 'offer', null, '', T4);
  assert.equal(r.offerComment, '', 'a positive comment may become empty');
});
