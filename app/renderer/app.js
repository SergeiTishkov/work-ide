// The renderer: identity tabs, market sub-tabs, a filter per market, the
// vacancy rows with their three answers, and the agent-run controls.
//
// Everything it does to the world goes through window.api (main/preload.js);
// the UI tests replace window.api with a mock and assert on the calls.
(function () {
  const api = window.api;

  const FILTERS = ['fresh_new', 'all', 'fresh', 'rejected', 'bugged', 'expired',
    'applied', 'contacted', 'interview', 'awaiting_final'];
  const DEFAULT_FILTER = 'fresh_new';
  const CLASS_KEYS = {
    hot_lead: 'class.hot_lead',
    worth_a_look: 'class.worth_a_look',
    long_shot: 'class.long_shot',
    national_market: 'class.national_market',
    remote_unconfirmed: 'class.remote_unconfirmed',
    engagement_unconfirmed: 'class.engagement_unconfirmed',
  };
  const FILTER_KEYS = {
    fresh_new: 'filter.fresh_new',
    all: 'filter.all',
    fresh: 'filter.fresh',
    applied: 'filter.applied',
    rejected: 'filter.rejected',
    bugged: 'filter.bugged',
    expired: 'filter.expired',
    contacted: 'filter.contacted',
    interview: 'filter.interview',
    awaiting_final: 'filter.awaiting_final',
  };
  const STATUS_KEYS = {
    applied: 'status.applied',
    rejected: 'status.rejected',
    bugged: 'status.bugged',
    expired: 'status.expired',
    contacted: 'status.contacted',
    interview: 'status.interview',
    awaiting_final: 'status.awaiting_final',
  };
  // The funnel: the buttons that move an application on, what each step
  // asks for, and how the timeline under a vacancy names its entries.
  const Funnel = window.WorkIdeFunnel;
  const STEP_KEYS = {
    contacted: 'step.contacted',
    interview: 'step.interview',
    awaiting_final: 'step.awaiting_final',
  };
  const STEP_HINT_KEYS = {
    contacted: 'step.hint.contacted',
    interview: 'step.hint.interview',
    awaiting_final: 'step.hint.awaiting_final',
  };
  const TIMELINE_KEYS = {
    applied: 'timeline.applied',
    contact: 'timeline.contact',
    interview: 'timeline.interview',
    final: 'timeline.final',
    rejected: 'timeline.rejected',
    bugged: 'timeline.bugged',
    expired: 'timeline.expired',
  };
  const RUN_KIND_KEYS = { collect: 'run.kind.collect', feedback: 'run.kind.feedback' };
  const REASON_KEYS = { rejected: 'reason.rejected', bugged: 'reason.bugged' };
  const LOG_LIMIT = 500;
  // How often the pipeline indicator asks the databases. Tests shorten it.
  const POLL_MS = window.__WORK_IDE_POLL_MS || 5000;
  const SESSION_KEY = 'work-ide-view';

  const state = {
    identities: [],
    active: null,
    // prefix -> { loaded, selection, segments, activeSegment, pending }
    byIdentity: {},
    // "identity/segment" -> filter; every market remembers its own choice
    filters: {},
    listing: [],
    counts: {},
    // vacancy id -> { class, index, status }: rows marked out of the current
    // filter, kept as a one-line stub with an undo until the view changes
    stubs: new Map(),
    reasonFor: null,   // { id, status } while a reason form is open
    stepFor: null,     // { id, step, draft } while a funnel step's comment is written
    editing: null,     // { key, id, kind, index, draft } while a timeline comment is edited
    openEntries: new Set(),   // timeline entries shown opened, by key
    expanded: new Set(),   // classes showing all their rows in this view
    classTotals: {},       // class -> how many the current filter holds
    run: { running: false },
    runStatus: '',
    log: [],
    // prefix -> { running, stage, startedAt }: a pipeline run of that
    // identity, however it was started (tools/runstate.py)
    pipelines: {},
    // restored after "Refresh" (page reload): which tab, market and filter
    restored: null,
  };

  // --- the view survives "Refresh" and a restart ----------------------------
  // localStorage, not sessionStorage: Refresh may restart the whole app, and
  // the tab, market and filter should come back after that too.

  function saveView() {
    const segments = {};
    for (const [prefix, info] of Object.entries(state.byIdentity)) {
      if (info && info.activeSegment) segments[prefix] = info.activeSegment;
    }
    try {
      localStorage.setItem(SESSION_KEY, JSON.stringify(
        { active: state.active, segments, filters: state.filters }));
    } catch {
      // storage unavailable: a refresh starts from the defaults
    }
  }

  function restoreView() {
    try {
      const saved = JSON.parse(localStorage.getItem(SESSION_KEY) || 'null');
      if (saved) {
        state.active = saved.active || null;
        state.filters = saved.filters || {};
        state.restored = saved;
      }
    } catch {
      state.restored = null;
    }
  }

  // Refreshes everything, keeping the view. The main process decides how:
  // it restarts the whole app when its own code changed since it started
  // (a reloaded page alone would call channels the old process does not
  // have), otherwise the page reloads — markup, styles, code.
  async function refresh() {
    saveView();
    let how = 'reload';
    try {
      how = await api.refresh();
    } catch {
      // an older main process without 'refresh': reloading is what it can do
    }
    if (how !== 'relaunch') window.location.reload();
  }

  // --- small helpers ---------------------------------------------------------

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === undefined || value === null || value === false) continue;
      if (key === 'testid') node.dataset.testid = value;
      else if (key === 'class') node.className = value;
      else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
      else if (key === 'html') node.innerHTML = value;
      else node.setAttribute(key, value === true ? '' : value);
    }
    for (const child of children.flat()) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  // The light Markdown the pipeline's texts carry (_italic_, **bold**,
  // `code`). Escaped first, so nothing from the data becomes markup.
  function inlineMarkdown(text) {
    return escapeHtml(text || '')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/(^|[\s(«])_(.+?)_(?=$|[\s).,;:»])/g, '$1<em>$2</em>');
  }

  function md(tag, text, attrs) {
    return el(tag, { ...(attrs || {}), html: inlineMarkdown(text) });
  }

  // "2026-09-29" -> "29.09.2026"; the pipeline has already reduced every
  // source's format to YYYY-MM-DD, or to null when the source gave none.
  function formatDate(isoDate) {
    const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate || '');
    return match ? `${match[3]}.${match[2]}.${match[1]}` : t('row.date_unknown');
  }

  function filterKey(identity, segment) {
    return `${identity}/${segment}`;
  }

  function current() {
    return state.active ? state.byIdentity[state.active] : null;
  }

  function currentFilter() {
    const info = current();
    if (!info || !info.activeSegment) return DEFAULT_FILTER;
    return state.filters[filterKey(state.active, info.activeSegment)] || DEFAULT_FILTER;
  }

  function showError(error) {
    const box = document.querySelector('[data-testid="error"]');
    if (!error) {
      box.hidden = true;
      box.textContent = '';
      return;
    }
    box.hidden = false;
    box.textContent = t('app.error', { message: error.message || String(error) });
  }

  // Every action runs through here. On failure the error is shown AND the
  // screen redrawn from what did load: a failed request once left the start
  // screen up, saying there were no identities (2026-09-30).
  async function guarded(fn) {
    try {
      showError(null);
      await fn();
    } catch (error) {
      showError(error);
      render();
    }
  }

  // --- loading ---------------------------------------------------------------

  async function loadIdentities() {
    state.identities = await api.listIdentities();
    if (!state.identities.some((i) => i.prefix === state.active)) {
      state.active = state.identities.length ? state.identities[0].prefix : null;
    }
    if (state.active) await loadIdentity(state.active);
  }

  async function loadIdentity(prefix, { keepSegment = true } = {}) {
    const previous = state.byIdentity[prefix];
    const data = await api.loadSegments(prefix);
    const segments = data.segments || [];
    let activeSegment = keepSegment && previous ? previous.activeSegment : null;
    if (!activeSegment && state.restored && state.restored.segments) {
      activeSegment = state.restored.segments[prefix] || null;
    }
    if (!segments.some((s) => s.slug === activeSegment)) {
      const preferred = segments.find((s) => s.isDefault) || segments[0];
      activeSegment = preferred ? preferred.slug : null;
    }
    state.byIdentity[prefix] = {
      loaded: true,
      selection: data.selection,
      displayName: data.displayName,
      segments,
      activeSegment,
      pending: await api.pendingFeedbackCount(prefix),
    };
    await loadList();
  }

  async function loadList() {
    const info = current();
    if (!info || !info.activeSegment) {
      state.listing = [];
      state.counts = {};
      render();
      return;
    }
    const expanded = [...state.expanded];
    const [listing, counts, totals, pending] = await Promise.all([
      expanded.length
        ? api.loadListing(state.active, info.activeSegment, currentFilter(), expanded)
        : api.loadListing(state.active, info.activeSegment, currentFilter()),
      api.listingCounts(state.active, info.activeSegment),
      api.classTotals(state.active, info.activeSegment, currentFilter()),
      api.pendingFeedbackCount(state.active),
    ]);
    state.listing = listing;
    state.counts = counts;
    state.classTotals = totals;
    info.pending = pending;
    render();
  }

  function resetView() {
    state.stubs.clear();
    state.reasonFor = null;
    state.stepFor = null;
    state.editing = null;
    state.expanded.clear();
  }

  // A class shows its top rows; "N more" opens the rest of it, "Collapse"
  // closes it again. Counts above are always the whole number.
  function toggleClass(cls) {
    return guarded(async () => {
      if (state.expanded.has(cls)) state.expanded.delete(cls);
      else state.expanded.add(cls);
      await loadList();
    });
  }

  // --- actions ---------------------------------------------------------------

  function selectIdentity(prefix) {
    if (prefix === state.active) return;
    return guarded(async () => {
      resetView();
      state.active = prefix;
      const info = state.byIdentity[prefix];
      if (info && info.loaded) await loadList();
      else await loadIdentity(prefix);
    });
  }

  function selectSegment(slug) {
    const info = current();
    if (!info || info.activeSegment === slug) return;
    return guarded(async () => {
      resetView();
      info.activeSegment = slug;
      await loadList();
    });
  }

  function selectFilter(name) {
    const info = current();
    if (!info || !info.activeSegment) return;
    return guarded(async () => {
      resetView();
      state.filters[filterKey(state.active, info.activeSegment)] = name;
      await loadList();
    });
  }

  // After an answer: reload, and when the row left the current filter leave
  // a one-line stub in its place (with undo) until the view changes.
  async function answered(item, status) {
    const sameClass = state.listing.filter((row) => row.class === item.class);
    const index = sameClass.findIndex((row) => row.id === item.id);
    await loadList();
    if (status !== 'new' && !state.listing.some((row) => row.id === item.id)) {
      state.stubs.set(item.id, { class: item.class, index, status });
      render();
    }
  }

  function mark(item, status, reason) {
    return guarded(async () => {
      state.reasonFor = null;
      await api.setFeedback(state.active, item.id, status, reason);
      await answered(item, status);
    });
  }

  // One step along the funnel; the comment is '' when nothing was written.
  function advance(item, step, comment) {
    return guarded(async () => {
      state.stepFor = null;
      await api.advance(state.active, item.id, step, comment || '');
      await answered(item, step);
    });
  }

  // "Undo": one step back — the funnel's last step, or the answer altogether.
  function undo(id) {
    return guarded(async () => {
      state.stubs.delete(id);
      state.stepFor = null;
      state.editing = null;
      await api.stepBack(state.active, id);
      await loadList();
    });
  }

  function entryKey(id, step) {
    return `${id}:${step.kind}:${step.index == null ? '' : step.index}`;
  }

  function toggleEntry(key) {
    if (state.openEntries.has(key)) state.openEntries.delete(key);
    else state.openEntries.add(key);
    render();
  }

  function startEdit(item, step) {
    const key = entryKey(item.id, step);
    state.editing = { key, id: item.id, kind: step.kind, index: step.index, draft: step.comment || '' };
    render();
  }

  function saveEdit() {
    const editing = state.editing;
    return guarded(async () => {
      await api.editComment(state.active, editing.id, editing.kind,
        editing.index == null ? null : editing.index, editing.draft);
      state.editing = null;
      // A comment written is a comment to read: its entry stays open.
      if (editing.draft.trim()) state.openEntries.add(editing.key);
      else state.openEntries.delete(editing.key);
      await loadList();
    });
  }

  function startRun(kind) {
    return guarded(async () => {
      const reply = await api.startRun({ identity: state.active, kind });
      if (!reply || reply.ok === false) {
        const key = reply && reply.error === 'busy' ? 'run.busy'
          : reply && reply.error === 'claude_not_found' ? 'run.claude_not_found' : null;
        throw new Error(key ? t(key) : (reply && reply.error) || '?');
      }
      state.run = { running: true, identity: state.active, kind };
      state.log = [];
      state.runStatus = t('run.running', { kind: t(RUN_KIND_KEYS[kind]), identity: state.active });
      render();
    });
  }

  function stopRun() {
    return guarded(async () => {
      await api.stopRun();
    });
  }

  function onRunEvent(event) {
    if (event.type === 'start') {
      state.run = { running: true, identity: event.identity, kind: event.kind };
      state.runStatus = t('run.running', { kind: t(RUN_KIND_KEYS[event.kind]), identity: event.identity });
    } else if (event.type === 'output') {
      state.log.push(event.text);
      if (state.log.length > LOG_LIMIT) state.log.splice(0, state.log.length - LOG_LIMIT);
    } else if (event.type === 'exit') {
      state.run = { running: false };
      if (event.error === 'claude_not_found') state.runStatus = t('run.claude_not_found');
      else if (event.code === 0) state.runStatus = t('run.finished');
      else if (event.code === null) state.runStatus = t('run.stopped');
      else state.runStatus = t('run.failed', { code: event.code });
      render();
      // A run may have created the database, recorded a selection or changed
      // the feedback: everything on screen is reloaded.
      guarded(async () => {
        resetView();
        state.byIdentity = {};
        await loadIdentities();
      });
      return;
    }
    render();
  }

  // --- rendering -------------------------------------------------------------

  function render() {
    document.title = t('app.title');
    renderIdentityTabs();
    renderPanel();
    renderRunPanel();
  }

  function renderIdentityTabs() {
    const nav = document.querySelector('[data-testid="identity-tabs"]');
    nav.replaceChildren(...state.identities.map((identity) => {
      const collecting = (state.pipelines[identity.prefix] || {}).running;
      return el('button', {
        class: `tab${identity.prefix === state.active ? ' active' : ''}`,
        role: 'tab',
        'aria-selected': identity.prefix === state.active ? 'true' : 'false',
        title: identity.displayName || null,
        testid: `identity-tab-${identity.prefix}`,
        onclick: () => selectIdentity(identity.prefix),
      }, identity.prefix,
      collecting && el('span', { class: 'tab-dot', testid: 'tab-collecting', title: t('run.collecting') }));
    }));
  }

  function renderPanel() {
    const panel = document.querySelector('[data-testid="panel"]');
    if (!state.identities.length) {
      panel.replaceChildren(el('p', { class: 'empty', testid: 'no-identities' }, t('app.no_identities')));
      return;
    }
    const info = current();
    if (!info) {
      panel.replaceChildren(el('p', { class: 'empty' }, t('app.loading')));
      return;
    }
    const identity = state.identities.find((i) => i.prefix === state.active);
    const parts = [renderToolbar(identity, info)];
    if (!info.selection) {
      parts.push(el('p', { class: 'empty', testid: 'never-collected' }, t('identity.never_collected')));
    } else if (!info.segments.length) {
      parts.push(el('p', { class: 'empty' }, t('identity.no_segments')));
    } else {
      parts.push(renderSegmentTabs(info), renderFilters(), renderList());
    }
    panel.replaceChildren(...parts);
  }

  function collectButton(running) {
    const pipeline = state.pipelines[state.active] || { running: false };
    if (!pipeline.running) {
      return el('button', {
        class: 'primary', testid: 'run-collect', disabled: running,
        onclick: () => startRun('collect'),
      }, t('run.collect'));
    }
    // A run of this identity is going — from here or from anywhere else.
    const since = String(pipeline.startedAt || '').slice(11, 16);
    return el('button', {
      class: 'primary collecting', testid: 'run-collect', disabled: true,
      title: t('run.collecting_since', { time: since }),
    },
    el('span', { class: 'spinner', testid: 'collect-indicator' }),
    pipeline.stage ? t('run.collecting_stage', { stage: pipeline.stage }) : t('run.collecting'));
  }

  function renderToolbar(identity, info) {
    const running = state.run.running;
    const pending = info.pending ? info.pending.bugged + info.pending.rejected : 0;
    const selection = info.selection;
    return el('div', { class: 'toolbar' },
      el('div', { class: 'identity-heading' },
        el('h1', { testid: 'identity-name' }, info.displayName || (identity && identity.displayName) || state.active),
        selection && el('span', { class: 'muted', testid: 'selection-caption' },
          t('selection.caption', {
            id: selection.id,
            run: selection.run,
            date: String(selection.created_at || '').slice(0, 16).replace('T', ' '),
          }) + (selection.kind === 'rebuild' ? ` · ${t('selection.rebuild')}` : ''))),
      el('div', { class: 'actions' },
        el('button', { testid: 'refresh', title: t('app.refresh_hint'), onclick: refresh }, t('app.refresh')),
        collectButton(running),
        el('button', {
          testid: 'run-feedback', disabled: running || pending === 0,
          onclick: () => startRun('feedback'),
        }, t('run.feedback', { n: pending })),
        running && el('button', { class: 'danger', testid: 'run-stop', onclick: stopRun }, t('run.stop'))));
  }

  function renderSegmentTabs(info) {
    return el('nav', { class: 'tabs segment-tabs', role: 'tablist', testid: 'segment-tabs' },
      info.segments.map((segment) => el('button', {
        class: `tab${segment.slug === info.activeSegment ? ' active' : ''}`,
        role: 'tab',
        'aria-selected': segment.slug === info.activeSegment ? 'true' : 'false',
        testid: `segment-tab-${segment.slug}`,
        onclick: () => selectSegment(segment.slug),
      }, segment.name)));
  }

  function renderFilters() {
    const active = currentFilter();
    const group = `filter-${state.active}-${current().activeSegment}`;
    return el('fieldset', { class: 'filters', testid: 'filters' },
      el('legend', {}, t('filter.legend')),
      FILTERS.map((name) => el('label', { class: `filter${name === active ? ' active' : ''}` },
        el('input', {
          type: 'radio', name: group, value: name, testid: `filter-${name}`,
          checked: name === active,
          onchange: () => selectFilter(name),
        }),
        ` ${t(FILTER_KEYS[name])} `,
        el('span', { class: 'count', testid: `filter-count-${name}` },
          t('filter.count', { n: state.counts[name] || 0 })))));
  }

  function renderList() {
    // Rows arrive ordered by class, then score; stubs go back where they were.
    const sections = [];
    const byClass = new Map();
    for (const row of state.listing) {
      if (!byClass.has(row.class)) {
        byClass.set(row.class, []);
        sections.push(row.class);
      }
      byClass.get(row.class).push({ kind: 'row', row });
    }
    for (const [id, stub] of state.stubs) {
      if (!byClass.has(stub.class)) {
        byClass.set(stub.class, []);
        sections.push(stub.class);
      }
      const items = byClass.get(stub.class);
      items.splice(Math.min(Math.max(stub.index, 0), items.length), 0, { kind: 'stub', id, stub });
    }
    const order = Object.keys(CLASS_KEYS);
    sections.sort((a, b) => order.indexOf(a) - order.indexOf(b));
    if (!sections.length) {
      return el('p', { class: 'empty', testid: 'list-empty' }, t('list.empty'));
    }
    return el('div', { class: 'list', testid: 'list' }, sections.map((cls) => el('section', {
      class: 'class-section', testid: `section-${cls}`,
    },
    el('h2', {}, el('span', { class: 'section-title' }, CLASS_KEYS[cls] ? t(CLASS_KEYS[cls]) : cls),
      el('span', { class: 'count', testid: `section-count-${cls}` }, ` ${t('filter.count', {
        n: state.classTotals[cls] || byClass.get(cls).filter((i) => i.kind === 'row').length,
      })}`)),
    byClass.get(cls).map((item) => (item.kind === 'row' ? renderRow(item.row) : renderStub(item.id, item.stub))),
    renderMore(cls, byClass.get(cls).filter((i) => i.kind === 'row').length))));
  }

  function renderMore(cls, shown) {
    const hidden = (state.classTotals[cls] || 0) - shown;
    if (state.expanded.has(cls)) {
      return el('button', { class: 'more', testid: `show-less-${cls}`, onclick: () => toggleClass(cls) },
        t('list.show_less'));
    }
    if (hidden <= 0) return null;
    return el('button', { class: 'more', testid: `show-more-${cls}`, onclick: () => toggleClass(cls) },
      t('list.show_more', { n: hidden }));
  }

  function renderStub(id, stub) {
    return el('div', { class: 'row stub', testid: `stub-${id}` },
      t('stub.marked', { status: t(STATUS_KEYS[stub.status]) }), ' · ',
      el('button', { class: 'link', testid: 'btn-undo', onclick: () => undo(id) }, t('action.undo')));
  }

  function renderRow(item) {
    const view = item.view || {};
    const status = item.feedback.status;
    const children = [
      el('div', { class: 'row-head' },
        el('span', { class: 'score', testid: 'score' }, String(item.score)),
        el('a', {
          href: view.url || '#', class: 'title', testid: 'title',
          onclick: (event) => {
            event.preventDefault();
            openLink(view);
          },
        }, view.title || item.id),
        el('span', { class: 'company' }, view.company || ''),
        item.fresh && el('span', { class: 'badge fresh', testid: 'badge-fresh' }, t('badge.fresh')),
        view.needs_manual_review && el('span', { class: 'badge review', testid: 'badge-review' },
          t('badge.manual_review'))),
      el('div', { class: 'row-facts' },
        view.hiring_country && md('span', `${t('row.hiring_country')}: ${view.hiring_country}`),
        view.salary && md('span', `${t('row.salary')}: ${view.salary}`)),
      // When the employer posted it, and when it first reached our base.
      el('div', { class: 'row-facts row-dates' },
        el('span', { testid: 'posted-on' }, t('row.posted_on', { date: formatDate(view.posted_on) })),
        el('span', { testid: 'first-seen-on' },
          t('row.first_seen_on', { date: formatDate(view.first_seen_on) }))),
    ];
    if (view.highlights && view.highlights.length) {
      children.push(md('div', view.highlights.join('; '), { class: 'highlights' }));
    }
    children.push(renderDetails(view));
    children.push(status === 'new' ? renderAnswers(item) : renderMarked(item));
    children.push(renderTimeline(item));
    children.push(renderStepForm(item));
    return el('article', { class: `row status-${status}`, testid: `vacancy-${item.id}` }, children);
  }

  function renderDetails(view) {
    const lines = [];
    if (view.to_confirm && view.to_confirm.length) {
      lines.push(md('li', `${t('row.to_confirm')}: ${view.to_confirm.join(', ')}`));
    }
    if (view.eligibility) {
      lines.push(md('li', view.eligibility.label + (view.eligibility.reason ? ` — _${view.eligibility.reason}_` : '')));
    }
    for (const channel of view.apply_channels || []) lines.push(md('li', channel));
    if (view.company_url) lines.push(md('li', `${t('row.company_site')}: ${view.company_url}`));
    if (view.technologies && view.technologies.length) {
      lines.push(md('li', `${t('row.technologies')}: ${view.technologies.join(', ')}`));
    }
    if (view.reputation) lines.push(md('li', `${t('row.reputation')}: ${view.reputation}`));
    if (view.company_age) lines.push(md('li', `${t('row.company_age')}: ${view.company_age}`));
    if (view.note) lines.push(md('li', `${t('row.note')}: ${view.note}`));
    if (!lines.length) return null;
    return el('details', { class: 'details' }, el('summary', {}, t('row.details')), el('ul', {}, lines));
  }

  // Opens the vacancy the way the operating system opens any link: in the
  // default browser, as a new tab when it is already running.
  function openLink(view) {
    if (view.url) guarded(() => api.openExternal(view.url));
  }

  function openButton(view) {
    return el('button', {
      class: 'open', testid: 'btn-open', disabled: !view.url, onclick: () => openLink(view),
    }, t('action.open'));
  }

  function renderAnswers(item) {
    const open = state.reasonFor && state.reasonFor.id === item.id ? state.reasonFor.status : null;
    const answers = el('div', { class: 'answers' },
      openButton(item.view || {}),
      el('button', { testid: 'btn-applied', onclick: () => mark(item, 'applied', null) }, t('action.applied')),
      el('button', {
        testid: 'btn-rejected', class: open === 'rejected' ? 'pressed' : null,
        onclick: () => { state.reasonFor = { id: item.id, status: 'rejected' }; render(); },
      }, t('action.rejected')),
      el('button', {
        testid: 'btn-bugged', class: open === 'bugged' ? 'pressed' : null,
        onclick: () => { state.reasonFor = { id: item.id, status: 'bugged' }; render(); },
      }, t('action.bugged')),
      // Closed at the source or a dead link: recorded at once, no reason —
      // it says nothing about the pick.
      el('button', { testid: 'btn-expired', onclick: () => mark(item, 'expired', null) }, t('action.expired')));
    if (!open) return answers;
    // The draft lives in the state: the pipeline indicator re-renders the
    // list now and then, and must not wipe a reason half typed.
    const input = el('textarea', {
      testid: 'reason-input', rows: '2', placeholder: t(REASON_KEYS[open]),
      oninput: (event) => { state.reasonFor.draft = event.target.value; },
    });
    input.value = state.reasonFor.draft || '';
    const form = el('div', { class: 'reason', testid: 'reason-form' },
      input,
      el('div', { class: 'reason-actions' },
        el('button', { class: 'primary', testid: 'reason-save', onclick: () => mark(item, open, input.value) },
          t('reason.save')),
        el('button', { testid: 'reason-cancel', onclick: () => { state.reasonFor = null; render(); } },
          t('reason.cancel'))));
    setTimeout(() => {
      if (document.activeElement !== input) {
        input.focus();
        input.setSelectionRange(input.value.length, input.value.length);
      }
    }, 0);
    return el('div', {}, answers, form);
  }

  // A vacancy with an answer: its status, the next steps of the funnel, undo.
  function renderMarked(item) {
    const { status } = item.feedback;
    const pressed = state.stepFor && state.stepFor.id === item.id ? state.stepFor.step : null;
    return el('div', { class: 'marked' },
      openButton(item.view || {}),
      el('span', { class: `badge status ${status}`, testid: 'status-badge' }, t(STATUS_KEYS[status])),
      Funnel.nextSteps(status).map((step) => el('button', {
        testid: `btn-step-${step}`, class: pressed === step ? 'pressed' : null,
        onclick: () => { state.stepFor = { id: item.id, step, draft: '' }; render(); },
      }, t(STEP_KEYS[step]))),
      el('button', { class: 'link', testid: 'btn-undo', onclick: () => undo(item.id) }, t('action.undo')));
  }

  // The comment for a funnel step: a large, optional text area at the bottom
  // of the card. Saved empty, the step still happened.
  function renderStepForm(item) {
    const form = state.stepFor;
    if (!form || form.id !== item.id) return null;
    const input = el('textarea', {
      class: 'big', testid: 'step-input', rows: '6', placeholder: t(STEP_HINT_KEYS[form.step]),
      oninput: (event) => { form.draft = event.target.value; },
    });
    input.value = form.draft || '';
    setTimeout(() => { if (document.activeElement !== input) input.focus(); }, 0);
    return el('div', { class: 'step-form', testid: 'step-form' },
      el('div', { class: 'step-form-title' }, t(STEP_KEYS[form.step])),
      input,
      el('div', { class: 'reason-actions' },
        el('button', { class: 'primary', testid: 'step-save', onclick: () => advance(item, form.step, input.value) },
          t('reason.save')),
        el('button', { testid: 'step-cancel', onclick: () => { state.stepFor = null; render(); } },
          t('reason.cancel'))));
  }

  // Every step with its date, as a column: a step with a comment is an
  // accordion (the arrow opens the text under the date); an empty one is a
  // plain line. The pencil edits in place and opens the entry.
  function renderTimeline(item) {
    const steps = Funnel.timeline(item.feedback);
    if (!steps.length) return null;
    return el('div', { class: 'timeline', testid: 'timeline' }, steps.map((step) => renderEntry(item, step)));
  }

  function renderEntry(item, step) {
    const key = entryKey(item.id, step);
    const editing = state.editing && state.editing.key === key;
    const hasText = Boolean(step.comment);
    const open = editing || (hasText && state.openEntries.has(key));
    const label = t(TIMELINE_KEYS[step.kind], { n: (step.index || 0) + 1 });
    const head = el('div', { class: 'entry-head' },
      hasText || editing
        ? el('button', {
          class: `entry-toggle${open ? ' is-open' : ''}`, testid: 'entry-toggle',
          'aria-expanded': open ? 'true' : 'false', onclick: () => toggleEntry(key),
        })
        : el('span', { class: 'entry-toggle none' }),
      el('span', { class: 'entry-date', testid: 'entry-date' }, formatDate(step.at)),
      el('span', { class: 'entry-label', testid: 'entry-label' }, label),
      step.editable && !editing && el('button', {
        class: 'pencil', testid: 'entry-edit', title: t('timeline.edit'), onclick: () => startEdit(item, step),
      }, '\u270E'));
    let body = null;
    if (editing) {
      const input = el('textarea', {
        testid: 'entry-input', rows: '4', placeholder: t('timeline.edit_hint'),
        oninput: (event) => { state.editing.draft = event.target.value; },
      });
      input.value = state.editing.draft;
      setTimeout(() => { if (document.activeElement !== input) input.focus(); }, 0);
      body = el('div', { class: 'entry-body' }, input,
        el('div', { class: 'reason-actions' },
          el('button', { class: 'primary', testid: 'entry-save', onclick: saveEdit }, t('reason.save')),
          el('button', { testid: 'entry-cancel', onclick: () => { state.editing = null; render(); } },
            t('reason.cancel'))));
    } else if (open) {
      body = el('div', { class: 'entry-body entry-comment', testid: 'entry-comment' }, step.comment);
    }
    const suffix = step.index == null ? '' : `-${step.index}`;
    return el('div', { class: 'entry', testid: `entry-${step.kind}${suffix}` }, head, body);
  }

  function renderRunPanel() {
    const panel = document.querySelector('[data-testid="run-panel"]');
    const visible = state.run.running || state.log.length > 0 || state.runStatus;
    panel.hidden = !visible;
    if (!visible) return;
    document.querySelector('[data-testid="run-status"]').textContent =
      `${t('run.log_title')} · ${state.runStatus}`;
    const log = document.querySelector('[data-testid="run-log"]');
    log.textContent = state.log.join('\n');
    log.scrollTop = log.scrollHeight;
  }

  // --- the pipeline indicator ------------------------------------------------

  async function pollPipelines() {
    let changed = false;
    const finished = [];
    for (const identity of state.identities) {
      let status;
      try {
        status = await api.pipelineStatus(identity.prefix);
      } catch {
        status = { running: false };
      }
      const before = state.pipelines[identity.prefix] || { running: false };
      if (JSON.stringify(before) !== JSON.stringify(status)) changed = true;
      if (before.running && !status.running) finished.push(identity.prefix);
      state.pipelines[identity.prefix] = status;
    }
    // A run just ended: its identity has a new selection to show.
    for (const prefix of finished) {
      if (prefix === state.active) await guarded(() => loadIdentity(prefix));
      else delete state.byIdentity[prefix];
    }
    if (changed) render();
  }

  // --- start -----------------------------------------------------------------

  api.onRunEvent(onRunEvent);
  restoreView();
  window.addEventListener('beforeunload', saveView);
  guarded(async () => {
    const run = await api.getRunState();
    if (run && run.running) {
      state.run = run;
      state.runStatus = t('run.running', { kind: t(RUN_KIND_KEYS[run.kind]), identity: run.identity });
    }
    render();
    await loadIdentities();
    await pollPipelines();
    render();
    setInterval(() => { pollPipelines(); }, POLL_MS);
  });
}());
