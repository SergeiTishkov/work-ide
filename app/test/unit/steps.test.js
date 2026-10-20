'use strict';
// main/steps.js: a collection's steps, read from its log as it comes.
const test = require('node:test');
const assert = require('node:assert/strict');
const { StepTracker } = require('../../main/steps');

test('a collection shows its steps as its log comes', () => {
  let ms = 0;
  const steps = new StepTracker({ now: () => ms });
  steps.feed('> Bash: python tools/identity.py which');
  ms = 65000;
  steps.feed('> Bash: python tools/pipeline.py --identity sharp --skip-contracts');
  steps.feed('  | [04:14:11] >> fetch 19 sources: weworkremotely, remoteok');
  steps.feed('  | [04:19:48]    linkedin pairs: 1/168 (0%), ~12:44:56 left - 100 pages');
  let list = steps.steps();
  assert.deepEqual(list.map((s) => [s.key, s.state]), [['prepare', 'done'], ['fetch', 'running']]);
  assert.equal(list[0].duration, '1:05');
  assert.match(list[1].progress, /^linkedin pairs: 1\/168/);
  assert.equal(list[1].began, 65000);
  steps.feed('  | [06:53:16] ok fetch - 2:39:05 (17 906 records, 12 381 new)');
  steps.feed('  | [06:53:17] >> rescore the base, current criteria (58 984 vacancies)');
  steps.feed('  | [06:58:51] !! rescore the base, current criteria (58 984 vacancies) - failed after 5:34: MemoryError');
  steps.feed('  | [08:38:08] pipeline finished in 4:24:03');
  steps.feed('> Bash: python tools/kb.py --identity sharp dump --min-class long_shot');
  list = steps.steps();
  assert.deepEqual(list.map((s) => [s.key, s.state, s.duration]), [
    ['prepare', 'done', '1:05'], ['fetch', 'done', '2:39:05'], ['rescore', 'failed', '5:34'],
    ['checklist', 'running', null]]);
  assert.equal(list[1].note, '17 906 records, 12 381 new');
  assert.equal(list[2].note, 'MemoryError');
  steps.finish('done');
  assert.equal(steps.steps()[3].state, 'done');
});

test('the fast cycle ends with the summary by the agent instead of the checklist', () => {
  const steps = new StepTracker();
  steps.feed('> Bash: python tools/pipeline.py --identity sharp --top --skip-contracts');
  steps.feed('  | [04:14:11] >> fetch 19 sources (LinkedIn: posted in the last 1 day)');
  steps.feed('  | [04:40:11] ok fetch 19 sources (LinkedIn: posted in the last 1 day) - 26:00 (3 000 records, 900 new)');
  steps.feed('  | [04:52:44] >> AI brief');
  steps.feed('  | [04:52:44] ok AI brief - 0 s (current)');
  steps.feed('  | [05:00:00] pipeline finished in 45:49');
  assert.deepEqual(steps.steps().map((s) => [s.key, s.state]), [
    ['prepare', 'done'], ['fetch', 'done'], ['ai_brief', 'done'], ['summary', 'running']]);
});

test('the rest of the base shows the pipeline stages, with no agent steps', () => {
  const steps = new StepTracker({ agent: false });
  steps.feed('  | [04:14:11] >> check links');
  steps.feed('  | [04:15:00] ok check links - 49 s');
  steps.feed('  | [04:15:01] pipeline finished in 0:50');
  assert.deepEqual(steps.steps().map((s) => [s.key, s.state]), [['links', 'done']]);
});

test('a task that failed fails the step it was in', () => {
  const steps = new StepTracker({ agent: false });
  steps.feed('  | [04:14:11] >> merge LinkedIn');
  steps.finish('failed');
  assert.deepEqual(steps.steps().map((s) => [s.key, s.state]), [['merge_linkedin', 'failed']]);
});
