'use strict';
// window.api for UI tests: in-memory data, and every call recorded in
// window.__calls so a test can assert on exactly what the UI asked for.
// installMockApi runs INSIDE the page (page.addInitScript), so it must be
// self-contained.

function installMockApi(fixture) {
  const calls = [];
  const data = JSON.parse(JSON.stringify(fixture));
  window.__calls = calls;
  window.__setPipeline = (identity, status) => { data.pipelines = { ...(data.pipelines || {}), [identity]: status }; };
  window.__WORK_IDE_POLL_MS = 50;
  window.__holdListing = () => { data.holdListing = true; };

  function record(name, args) {
    calls.push({ name, args });
  }

  // The task queue as main/tasks.js keeps it: two lanes, one task at a time
  // in each. A CV or a cover letter finishes by itself at once — unless
  // holdCv, when window.__releaseCv() finishes the running one; failCv makes
  // it fail. A collection runs until window.__finishCollect(result), or ends
  // at once with collectReply. window.__taskLine(text) writes to the log of
  // the running task.
  const taskListeners = [];
  const tasks = [];
  const logs = {};
  let nextTaskId = 1;
  const copy = (value) => JSON.parse(JSON.stringify(value));
  const laneOf = (kind) => (kind === 'collect' ? 'collect' : kind === 'reputation' ? 'reputation' : 'documents');
  // The CV/CL batch (main/batch.js): window.__setBatch(task, lines) sets it
  // as the status file would, null removes it; it is listed after the tasks.
  let batch = null;
  let batchDismissed = null;
  const shownBatch = () => (batch && batch.startedAt !== batchDismissed ? batch : null);
  const publicTasks = () => [
    ...tasks.map((task) => ({ ...copy(task), logLines: (logs[task.id] || []).length })),
    ...(shownBatch() ? [{ ...copy(batch), logLines: (logs.batch || []).length }] : []),
  ];
  const emitTask = (event) => taskListeners.forEach((listener) => listener(copy(event)));
  const tasksChanged = () => emitTask({ type: 'tasks', tasks: publicTasks() });

  function documentResult(task) {
    if (data.failCv) return { ok: false, error: `generate-${task.kind} failed` };
    if (task.kind === 'cv') {
      return data.cvReply || {
        ok: true, pages: 3, docx: '/docs/sharp/a1/CV.docx', pdf: '/docs/sharp/a1/CV.pdf',
        findings: [], warnings: [], removed_for_length: [], report: {},
      };
    }
    return data.letterReply || {
      ok: true, pages: 1, docx: '/docs/sharp/a1/Cover Letter.docx', pdf: '/docs/sharp/a1/Cover Letter.pdf',
      findings: [], warnings: [], report: {},
    };
  }

  function pumpTasks() {
    for (const lane of ['collect', 'documents', 'reputation']) {
      if (tasks.some((task) => laneOf(task.kind) === lane && task.state === 'running')) continue;
      const next = tasks.find((task) => laneOf(task.kind) === lane && task.state === 'queued');
      if (!next) continue;
      // the batch's document goes first; the batch pauses after it (holding)
      if (lane === 'documents' && batch && batch.state === 'running' && !batch.holding) {
        next.waitingFor = 'batch';
        continue;
      }
      next.waitingFor = null;
      next.state = 'running';
      if (lane === 'documents' && !data.holdCv) setTimeout(() => finishTask(next.id), 0);
      if (lane === 'collect' && data.collectReply) setTimeout(() => finishTask(next.id, data.collectReply), 0);
      // holdReputation: the lookup waits for window.__finishReputation()
      if (lane === 'reputation' && !data.holdReputation) setTimeout(() => finishTask(next.id), 0);
    }
  }

  function finishTask(id, given) {
    const task = tasks.find((t) => t.id === id);
    if (!task || task.state !== 'running') return;
    const result = given || (task.kind === 'collect' || task.kind === 'reputation'
      ? { ok: true, code: 0 } : documentResult(task));
    task.state = result.ok ? 'done' : result.error === 'stopped' ? 'stopped' : 'failed';
    task.result = result;
    task.error = result.ok ? null : result.error;
    if (result.ok && task.kind === 'reputation') {
      // the lookup renders the company's rows again (tools/reputation_lookup.py)
      const company = Object.values(data.rows[task.identity] || {}).flat()
        .find((r) => r.id === task.vacancyId).view.company;
      for (const r of Object.values(data.rows[task.identity] || {}).flat()) {
        if (r.view.company === company) {
          r.view.reputation_collected = true;
          r.view.reputation = '4.1/5 (Glassdoor)';
        }
      }
    }
    if (result.ok && task.kind !== 'collect' && task.kind !== 'reputation') {
      data.docs = data.docs || {};
      const mine = (data.docs[task.identity] = data.docs[task.identity] || {});
      const entry = (mine[task.vacancyId] = mine[task.vacancyId]
        || { dir: `/docs/${task.identity}/${task.vacancyId}`, cv: 0, letter: 0, errors: {} });
      entry[task.kind] += 1;
    }
    pumpTasks();
    tasksChanged();
    emitTask({ type: 'finished', task: { ...task, logLines: (logs[task.id] || []).length } });
  }

  window.__releaseCv = () => {
    const task = tasks.find((t) => t.kind !== 'collect' && t.kind !== 'reputation' && t.state === 'running');
    if (task) finishTask(task.id);
  };
  window.__finishReputation = (result) => {
    const task = tasks.find((t) => t.kind === 'reputation' && t.state === 'running');
    if (task) finishTask(task.id, result);
  };
  window.__finishCollect = (result) => {
    const task = tasks.find((t) => t.kind === 'collect' && t.state === 'running');
    if (task) finishTask(task.id, result);
  };
  // a task queued by the app itself (the automatic documents of a collection)
  window.__addTask = (task) => {
    tasks.push({
      id: nextTaskId++, vacancyId: null, title: '', company: '', instructions: '', origin: 'auto',
      state: 'queued', waitingFor: null, result: null, error: null, ...task,
    });
    pumpTasks();
    tasksChanged();
  };
  window.__setBatch = (task, lines = []) => {
    const before = batch;
    batch = task ? {
      id: 'batch', kind: 'batch', lane: 'documents', identity: 'sharp', vacancyId: null, title: '', company: '',
      origin: 'external', state: 'running', holding: false, stopping: false, waitingFor: null,
      queuedAt: '2026-10-13T03:30:54+04:00', startedAt: '2026-10-13T03:30:54+04:00', endedAt: null,
      progress: { index: 0, total: 0, made: 0, failed: 0, gone: 0 }, current: null, result: null, error: null,
      ...task,
    } : null;
    for (const text of lines) {
      (logs.batch = logs.batch || []).push(text);
      emitTask({ type: 'log', id: 'batch', text });
    }
    pumpTasks();
    tasksChanged();
    if (before && before.state === 'running' && batch && batch.state !== 'running') {
      emitTask({ type: 'finished', task: { ...batch, logLines: (logs.batch || []).length } });
    }
  };
  // the steps of the running collection, as main/steps.js gives them
  window.__setSteps = (steps) => {
    const task = tasks.find((t) => t.kind === 'collect' && t.state === 'running');
    if (!task) return;
    task.steps = steps;
    tasksChanged();
  };
  window.__taskLine = (text) => {
    const task = tasks.find((t) => t.state === 'running');
    if (!task) return;
    (logs[task.id] = logs[task.id] || []).push(text);
    emitTask({ type: 'log', id: task.id, text });
  };

  // The view as schemas/queries.sql reads it (THE VIEW): the rows of the
  // chosen markets, each once, and the applications from every market.
  const FUNNEL = ['applied', 'contacted', 'interview', 'awaiting_final', 'awaiting_offer', 'offered',
    'started', 'declined'];
  const STATUSES = ['new', ...FUNNEL, 'rejected', 'bugged', 'expired'];

  function poolOf(identity, view) {
    const segments = (data.segments[identity] || {}).segments || [];
    let chosen = view.segments;
    if (chosen == null) {
      const everything = segments.filter((s) => s.everything);
      chosen = (everything.length ? everything : segments).map((s) => s.slug);
    }
    const byId = new Map();
    for (const [slug, rows] of Object.entries(data.rows[identity] || {})) {
      for (const row of rows) {
        if (!byId.has(row.id) && (chosen.includes(slug) || FUNNEL.includes(row.feedback.status))) byId.set(row.id, row);
      }
    }
    return [...byId.values()];
  }

  // A company's kind as the pipeline records it (meta 'company_kinds'):
  // fixture.companyKinds { company: { kind, name } }, every other one 'other'.
  function kindOf(row) {
    return (data.companyKinds || {})[row.view.company] || { kind: 'other', name: null };
  }

  function companyShown(row, companies) {
    if (companies == null) return true;
    const { kind, name } = kindOf(row);
    return companies.kinds.includes(kind) && !companies.hidden.includes(name || '');
  }

  // the view's rows; `aside` names the one choice a drop-down's own numbers leave out
  function narrowed(identity, view, aside) {
    return poolOf(identity, view).filter((row) => (aside === 'statuses' || view.statuses.includes(row.feedback.status))
      && (aside === 'fresh' || view.fresh.includes(row.fresh ? 'fresh' : 'earlier'))
      && (aside === 'sources' || view.sources == null || view.sources.includes(row.view.source))
      && (aside === 'fits' || view.fits == null || view.fits.includes(row.class))
      && (aside === 'companies' || companyShown(row, view.companies))
      && (aside === 'ages' || view.ages == null || view.ages.includes(ageOf(row))));
  }

  // The age band the query works out of the posted date (schemas/queries.sql,
  // AGE); here a row's own `age`, else today.
  const ageOf = (row) => row.age || 'today';

  const NOW = '2026-10-01T10:00:00+00:00';

  // -> the record as written, as the store answers
  function update(identity, id, change) {
    let written = null;
    for (const rows of Object.values(data.rows[identity] || {})) {
      for (const row of rows) {
        if (row.id !== id) continue;
        row.feedback = change(row.feedback);
        written = copy(row.feedback);
      }
    }
    return written;
  }

  window.api = {
    async listIdentities() {
      record('listIdentities', []);
      // holdIdentities: the answer waits for window.__releaseIdentities(), so
      // a test can see what the window shows before it arrives
      if (data.holdIdentities) {
        await new Promise((resolve) => { window.__releaseIdentities = resolve; });
        data.holdIdentities = false;
      }
      if (data.failIdentities) throw new Error('listIdentities failed');
      return data.identities;
    },
    async loadSegments(identity) {
      record('loadSegments', [identity]);
      return data.segments[identity] || { selection: null, displayName: null, segments: [] };
    },
    async loadListing(identity, view, page) {
      record('loadListing', page ? [identity, view, page] : [identity, view]);
      // holdListing: the answer waits for window.__releaseListing(), so a
      // test sees what stands in for the list meanwhile
      if (data.holdListing) {
        await new Promise((resolve) => { window.__releaseListing = resolve; });
        data.holdListing = false;
      }
      const { shown = {}, expanded = [] } = page || {};
      const seen = {};
      return narrowed(identity, view).filter((row) => {
        if (row.feedback.status !== 'new' || expanded.includes(row.class)) return true;
        seen[row.class] = (seen[row.class] || 0) + 1;
        return seen[row.class] <= (shown[row.class] || data.limit || 1000);
      });
    },
    async classTotals(identity, view) {
      record('classTotals', [identity, view]);
      if (data.failClassTotals) throw new Error("No handler registered for 'class-totals'");
      const totals = {};
      for (const row of narrowed(identity, view, 'fits')) totals[row.class] = (totals[row.class] || 0) + 1;
      return totals;
    },
    async listingCounts(identity, view) {
      record('listingCounts', [identity, view]);
      const counts = { statuses: {}, fresh: { fresh: 0, earlier: 0 } };
      for (const status of STATUSES) counts.statuses[status] = 0;
      for (const row of narrowed(identity, view, 'statuses')) counts.statuses[row.feedback.status] += 1;
      for (const row of narrowed(identity, view, 'fresh')) counts.fresh[row.fresh ? 'fresh' : 'earlier'] += 1;
      return counts;
    },
    async listSources(identity, view) {
      record('listSources', [identity, view]);
      const totals = new Map();
      for (const row of narrowed(identity, view, 'sources')) {
        totals.set(row.view.source, (totals.get(row.view.source) || 0) + 1);
      }
      const sites = { linkedin: 'linkedin.com', devitjobs: 'devitjobs.uk, devitjobs.com' };
      return [...totals].map(([source, total]) => ({ source, site: sites[source] || null, total }))
        .sort((a, b) => b.total - a.total || a.source.localeCompare(b.source));
    },
    // fixture.cleanupReply: what tools/cleanup.py answers; the count by default
    async cleanup(identity, filters, dryRun) {
      record('cleanup', [identity, filters, dryRun]);
      const reply = data.cleanupReply || { matched: 3, kept_funnel: 1, kept_unreviewed: 2, kept_other_identity: 0 };
      return { ...reply, dry_run: dryRun, deleted: dryRun ? 0 : reply.matched };
    },
    async listAges(identity, view) {
      record('listAges', [identity, view]);
      const totals = { today: 0, week: 0, month: 0, older: 0 };
      for (const row of narrowed(identity, view, 'ages')) totals[ageOf(row)] += 1;
      return totals;
    },
    async listCompanies(identity, view) {
      record('listCompanies', [identity, view]);
      const totals = new Map();
      for (const row of narrowed(identity, view, 'companies')) {
        const { kind, name } = kindOf(row);
        const key = JSON.stringify([kind, name]);
        totals.set(key, (totals.get(key) || 0) + 1);
      }
      return [...totals].map(([key, total]) => {
        const [kind, name] = JSON.parse(key);
        return { kind, name, total };
      }).sort((a, b) => b.total - a.total || a.kind.localeCompare(b.kind)
        || String(a.name).localeCompare(String(b.name)));
    },
    async setFeedback(identity, id, status, reason) {
      record('setFeedback', [identity, id, status, reason]);
      return update(identity, id, () => ({
        status,
        at: NOW,
        appliedAt: status === 'applied' ? NOW : null,
        rejectedReason: status === 'rejected' ? reason : null,
        buggedReason: status === 'bugged' ? reason : null,
        interviewComments: [],
        interviewAt: [],
      }));
    },
    // The funnel through the page's own rules (renderer/funnel.js), like the
    // main process does.
    async advance(identity, id, step, comment) {
      record('advance', [identity, id, step, comment]);
      return update(identity, id, (fb) => window.WorkIdeFunnel.advance(fb, step, comment, NOW));
    },
    async stepBack(identity, id) {
      record('stepBack', [identity, id]);
      return update(identity, id, (fb) => window.WorkIdeFunnel.stepBack(fb, NOW));
    },
    async editComment(identity, id, kind, index, text) {
      record('editComment', [identity, id, kind, index, text]);
      return update(identity, id, (fb) => window.WorkIdeFunnel.editComment(fb, kind, index, text, NOW));
    },
    async pendingFeedbackCount(identity) {
      record('pendingFeedbackCount', [identity]);
      const seen = new Map();
      for (const rows of Object.values(data.rows[identity] || {})) {
        for (const row of rows) seen.set(row.id, row.feedback.status);
      }
      const statuses = [...seen.values()];
      return {
        bugged: statuses.filter((s) => s === 'bugged').length,
        rejected: statuses.filter((s) => s === 'rejected').length,
      };
    },
    async pipelineStatus(identity) {
      record('pipelineStatus', [identity]);
      return (data.pipelines || {})[identity] || { running: false };
    },
    async refresh() {
      record('refresh', []);
      return data.refreshReply || 'reload';
    },
    async enqueueTask(request) {
      record('enqueueTask', [request]);
      const same = tasks.find((t) => ['queued', 'running'].includes(t.state) && t.kind === request.kind
        && t.identity === request.identity && (t.vacancyId || null) === (request.vacancyId || null));
      if (same) return { ok: false, error: 'already_queued', task: copy(same) };
      const task = {
        id: nextTaskId++, kind: request.kind, identity: request.identity, vacancyId: request.vacancyId || null,
        title: request.title || '', company: request.company || '', instructions: request.instructions || '',
        origin: 'manual', state: 'queued', waitingFor: null, result: null, error: null,
      };
      tasks.push(task);
      pumpTasks();
      tasksChanged();
      return { ok: true, task: { ...copy(task), logLines: 0 } };
    },
    async listTasks() {
      record('listTasks', []);
      return publicTasks();
    },
    async taskLog(id) {
      record('taskLog', [id]);
      return [...(logs[id] || [])];
    },
    async cancelTask(id) {
      record('cancelTask', [id]);
      if (id === 'batch') {
        if (!batch || batch.state !== 'running') return { ok: false };
        batch.stopping = true;
        tasksChanged();
        return { ok: true };
      }
      const task = tasks.find((t) => t.id === id);
      if (!task) return { ok: false };
      if (task.state === 'running') finishTask(id, { ok: false, error: 'stopped' });
      else if (task.state === 'queued') {
        task.state = 'stopped';
        tasksChanged();
      }
      return { ok: true };
    },
    async cancelQueued(identity) {
      record('cancelQueued', [identity]);
      for (const task of tasks) if (task.state === 'queued' && (!identity || task.identity === identity)) task.state = 'stopped';
      tasksChanged();
      return { ok: true };
    },
    async clearTasks() {
      record('clearTasks', []);
      if (batch && batch.state !== 'running') batchDismissed = batch.startedAt;
      for (let i = tasks.length - 1; i >= 0; i -= 1) {
        if (!['queued', 'running'].includes(tasks[i].state)) tasks.splice(i, 1);
      }
      tasksChanged();
      return { ok: true };
    },
    onTaskEvent(listener) {
      taskListeners.push(listener);
      return () => {};
    },
    // data.docs: { identity: { id: { dir, cv, letter, errors } } }
    async documentsState(identity, ids) {
      record('documentsState', [identity, ids]);
      const mine = (data.docs || {})[identity] || {};
      return Object.fromEntries(ids.filter((id) => mine[id]).map((id) => [id, copy(mine[id])]));
    },
    async openDocumentsDir(identity, id) {
      record('openDocumentsDir', [identity, id]);
    },
    async openExternal(url) {
      record('openExternal', [url]);
    },
    async copyText(text) {
      record('copyText', [text]);
    },
    async openCvFile(file) {
      record('openCvFile', [file]);
    },
    async showCvFile(file) {
      record('showCvFile', [file]);
    },
    ...(fixture.withoutRefresh ? { refresh: undefined } : {}),
  };
}

function row(id, { cls = 'hot_lead', score = 60, fresh = true, status = 'new', source = 'linkedin' } = {}) {
  return {
    id,
    class: cls,
    score,
    fresh,
    view: {
      id, title: `Senior .NET Developer ${id}`, company: `Company ${id}`,
      url: `https://example.test/${id}`, score, classification: cls,
      highlights: ['legacy/enterprise: insurance'], salary: 'not stated _(no data)_',
      to_confirm: [], company_url: null,
      exclusivity: id === 'b1' ? ['moonlighting prohibited'] : [],
      eligibility: { level: 'likely', label: 'likely', reason: 'anywhere' },
      apply_channels: [], technologies: ['C#'], reputation: 'not checked',
      hiring_country: 'United Kingdom', company_age: null, note: null,
      posted_on: id === 'a2r' ? null : '2026-09-20', first_seen_on: '2026-09-28',
      needs_manual_review: id.endsWith('r'),
      source,
    },
    feedback: { status, at: null, rejectedReason: null, buggedReason: null, interviewComments: [], interviewAt: [] },
  };
}

// sharp: collected, three markets; partsharp: collected, one market;
// newbie: never collected.
function standardFixture() {
  const full = [
    row('a1', { score: 80 }), row('a2r', { score: 70 }), row('a3', { score: 50, fresh: false }),
    row('b1', { cls: 'worth_a_look', score: 45, source: 'devitjobs' }),
    row('x1', { score: 40, status: 'bugged', source: 'devitjobs' }),
  ];
  const selection = { id: 7, run: 55, created_at: '2026-09-29T10:00:00+00:00', kind: 'run' };
  return {
    identities: [
      { prefix: 'sharp', displayName: 'Senior .NET/C# remote engineering', hasDatabase: true },
      { prefix: 'partsharp', displayName: 'Part-time side work', hasDatabase: true },
      { prefix: 'newbie', displayName: 'Nothing yet', hasDatabase: false },
    ],
    segments: {
      sharp: {
        selection, displayName: 'Senior .NET/C# remote engineering',
        segments: [
          { slug: 'worldwide', name: 'Worldwide', isDefault: false },
          { slug: 'uk', name: 'United Kingdom', names: { en: 'United Kingdom', ru: 'Velikobritaniya' }, isDefault: false },
          { slug: 'full', name: 'Everything', isDefault: true, everything: true },
        ],
      },
      partsharp: {
        selection: { ...selection, id: 3 }, displayName: 'Part-time side work',
        segments: [{ slug: 'full', name: 'Everything', isDefault: true, everything: true }],
      },
    },
    rows: {
      sharp: { full, uk: [row('u1'), row('u2', { fresh: false })], worldwide: [] },
      partsharp: { full: [row('p1')] },
    },
  };
}

module.exports = { installMockApi, standardFixture, row };
