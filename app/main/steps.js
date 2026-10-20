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
  [/^salary benchmark/, 'benchmark'],
  [/^find direct application channels/, 'channels'],
  [/^company facts from Wikidata/, 'wikidata'],
  [/^save the knowledge base/, 'save'],
  [/^record the selection/, 'selection'],
  [/^write the reports/, 'reports'],
  [/^check source contracts/, 'contracts'],
];

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
  constructor({ now = () => Date.now(), agent = true } = {}) {
    this.now = now;
    this.agent = agent;
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
  }

  // A running step carries `began` (ms): the panel counts its time itself.
  steps() {
    return this.list.map(({ began, agent, ...step }) => (step.state === 'running' ? { ...step, began } : step));
  }
}

module.exports = { StepTracker, stageKey, clock };
