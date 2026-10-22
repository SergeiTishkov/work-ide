'use strict';
// The steps of a collection, read from its log as it comes (the owner,
// 2026-10-13: "a collection split into tasks"). A collection is the agent's
// /run, and its log holds both the agent's commands ("> Bash: ...") and the
// pipeline's own lines ("  | [04:14:11] >> fetch 19 sources ...", followed
// by runner.js). The steps:
//
//   prepare      the agent: the identity, the template, the source contracts
//   <stage>      each stage of tools/pipeline.py, as tools/progress.py logs
//                it: ">> name" starts it, "ok name - 5:35 (note)" ends it,
//                "!! name - failed after ..." fails it; an indented line in
//                between is its progress ("linkedin pairs: 36/168 ...")
//   checklist    the agent reads the candidates (RUNBOOK step 5)
//   summary      after the fast cycle (`pipeline.py --top`, /top): the
//                agent's summary, in place of the checklist
//
// The agent's step "reputation" went on 2026-10-17: a lookup is the
// vacancy's "Collect reputation" button (reputation.js).
//
// The rest of the base and LinkedIn's run (rest.js) are the pipeline alone:
// no agent steps.
//
// The CVs and cover letters after it are a task of their own (batch.js).
//
// The steps still to come are listed too, from the outline of the task's
// kind (the owner, 2026-10-21: an empty circle for a stage to do). A stage
// the run passed over (no AI, no contracts) drops out of the outline when a
// later one starts; the outline goes when the task ends.

const STAGE = /^\s*\|\s*\[(\d\d:\d\d:\d\d)\] (>>|ok|!!) (.+)$/;
const PROGRESS = /^\s*\|\s*\[\d\d:\d\d:\d\d\] {4}(\S.*)$/;
const PIPELINE_END = /^\s*\|\s*\[\d\d:\d\d:\d\d\] pipeline finished/;
const PIPELINE_COMMAND = /^> \w+: .*pipeline\.py/;

// The pipeline's stage names -> a short key the app translates; the rest are
// shown as the pipeline wrote them.
const STAGE_KEYS = [
  [/^load the knowledge base/, 'load'],
  [/^fetch missing descriptions/, 'descriptions'],
  [/^wait for the base/, 'wait_base'],
  [/^merge LinkedIn/, 'merge_linkedin'],
  [/^fetch\b/, 'fetch'],
  [/^rescore the base/, 'rescore'],
  [/^rescore the top/, 'rescore_top'],
  [/^remote check/, 'remote_check'],
  [/^AI brief/, 'ai_brief'],
  [/^AI check/, 'ai_check'],
  [/^mark near-duplicates/, 'duplicates'],
  [/^check links/, 'links'],
  [/^rebuild companies/, 'companies'],
  [/^find direct application channels/, 'channels'],
  [/^company facts from Wikidata/, 'wikidata'],
  [/^save the knowledge base/, 'save'],
  [/^record the selection/, 'selection'],
  [/^check source contracts/, 'contracts'],
];

// The stages each kind of task goes through, in order, as tools/pipeline.py
// runs them: run_top for a collection (the agent's /top), run_rest,
// fetch_linkedin_apart and merge_linkedin. A key may come more than once.
const OUTLINES = {
  collect: ['prepare', 'load', 'contracts', 'fetch', 'rescore_top', 'remote_check', 'rescore_top',
    'ai_brief', 'ai_check', 'rescore_top', 'duplicates', 'links', 'companies', 'channels', 'wikidata',
    'rescore_top', 'save', 'selection', 'summary'],
  rest: ['load', 'rescore', 'duplicates', 'links', 'companies', 'descriptions', 'rescore', 'ai_brief',
    'ai_check', 'rescore_top', 'channels', 'wikidata', 'rescore', 'save', 'selection'],
  linkedin: ['fetch', 'wait_base', 'load', 'merge_linkedin', 'save', 'selection'],
  links: ['load', 'links', 'save', 'selection'],
  ai: ['load', 'ai_brief', 'ai_check', 'rescore_top', 'save', 'selection'],
};

function stageKey(name) {
  const hit = STAGE_KEYS.find(([pattern]) => pattern.test(name));
  return hit ? hit[1] : null;
}

function clock(ms) {
  const seconds = Math.max(0, Math.round(ms / 1000));
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = String(seconds % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`;
}

class StepTracker {
  // agent: false for the pipeline alone (rest.js): no agent steps
  // outline: the keys of the steps to come (OUTLINES), or none
  constructor({ now = () => Date.now(), agent = true, outline = [] } = {}) {
    this.now = now;
    this.agent = agent;
    this.outline = outline;
    this.ended = false;
    this.list = [];
    this.pipelineDone = false;
    this.after = 'checklist';
  }

  current() {
    const last = this.list[this.list.length - 1];
    return last && last.state === 'running' ? last : null;
  }

  begin(step) {
    this.close('done');
    this.list.push({ duration: null, note: null, progress: null, ...step, state: 'running', began: this.now() });
  }

  close(state, fields = {}) {
    const step = this.current();
    if (!step) return;
    Object.assign(step, { state, progress: null, ...fields });
    if (!step.duration) step.duration = clock(this.now() - step.began);
  }

  // One line of the task's log; true when the steps changed.
  feed(line) {
    if (!this.list.length && this.agent) this.begin({ key: 'prepare', agent: true });
    const stage = STAGE.exec(line);
    if (stage) {
      const [, , mark, rest] = stage;
      if (mark === '>>') {
        this.begin({ key: stageKey(rest), name: rest.replace(/:.*$/, '') });
        return true;
      }
      const step = this.current();
      if (!step || step.agent) return false;
      if (mark === 'ok') {
        const done = /^(.*) - (\S+)(?: \((.*)\))?$/.exec(rest);
        this.close('done', done ? { duration: done[2], note: done[3] || null } : {});
      } else {
        const failed = /^.* - failed after (\S+): (.*)$/.exec(rest);
        this.close('failed', failed ? { duration: failed[1], note: failed[2] } : {});
      }
      return true;
    }
    const progress = PROGRESS.exec(line);
    if (progress) {
      const step = this.current();
      if (!step || step.agent) return false;
      step.progress = progress[1].trim();
      return true;
    }
    if (PIPELINE_END.test(line)) {
      this.pipelineDone = true;
      if (this.agent) this.begin({ key: this.after, agent: true });
      else this.close('done');
      return true;
    }
    if (PIPELINE_COMMAND.test(line)) {
      // the pipeline about to start: the preparation is over
      if (/\s--top\b/.test(line)) this.after = 'summary';
      const step = this.current();
      if (step && step.key === 'prepare') {
        this.close('done');
        return true;
      }
      return false;
    }
    return false;
  }

  // The task ended: the step going ends with it.
  finish(state) {
    this.close(state === 'done' ? 'done' : state);
    this.ended = true;
  }

  // The outline's keys after the last step that matched it, in order.
  pending() {
    if (this.ended) return [];
    let next = 0;
    for (const step of this.list) {
      const at = this.outline.indexOf(step.key, next);
      if (at >= 0) next = at + 1;
    }
    return this.outline.slice(next);
  }

  // A running step carries `began` (ms): the panel counts its time itself.
  steps() {
    return [
      ...this.list.map(({ began, agent, ...step }) => (step.state === 'running' ? { ...step, began } : step)),
      ...this.pending().map((key) => ({ key, state: 'pending' })),
    ];
  }
}

module.exports = { StepTracker, OUTLINES, stageKey, clock };
