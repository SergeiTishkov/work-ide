// The renderer: identity tabs, market sub-tabs, a filter per market, the
// vacancy rows with their three answers, and the agent-run controls.
//
// Everything it does to the world goes through window.api (main/preload.js);
// the UI tests replace window.api with a mock and assert on the calls.
(function () {
  const api = window.api;

  const FILTERS = ['fresh_new', 'no_feedback', 'all', 'fresh', 'rejected', 'bugged', 'expired',
    'applied', 'contacted', 'interview', 'awaiting_final', 'awaiting_offer', 'offered', 'started',
    'declined'];
  const DEFAULT_FILTER = 'fresh_new';
  // The drop-down's sections: what the selection holds, the person's own
  // answers about the pick, and their applications.
  const FILTER_GROUPS = [
    { key: 'filter.group.selection', filters: ['fresh_new', 'no_feedback', 'fresh', 'all'] },
    { key: 'filter.group.answers', filters: ['rejected', 'bugged', 'expired'] },
    { key: 'filter.group.applications',
      filters: ['applied', 'contacted', 'interview', 'awaiting_final', 'awaiting_offer', 'offered',
        'started', 'declined'] },
  ];
  const CLASS_KEYS = {
    hot_lead: 'class.hot_lead',
    worth_a_look: 'class.worth_a_look',
    long_shot: 'class.long_shot',
    remote_unconfirmed: 'class.remote_unconfirmed',
    engagement_unconfirmed: 'class.engagement_unconfirmed',
  };
  const FILTER_KEYS = {
    fresh_new: 'filter.fresh_new',
    no_feedback: 'filter.no_feedback',
    all: 'filter.all',
    fresh: 'filter.fresh',
    applied: 'filter.applied',
    rejected: 'filter.rejected',
    bugged: 'filter.bugged',
    expired: 'filter.expired',
    contacted: 'filter.contacted',
    interview: 'filter.interview',
    awaiting_final: 'filter.awaiting_final',
    awaiting_offer: 'filter.awaiting_offer',
    offered: 'filter.offered',
    started: 'filter.started',
    declined: 'filter.declined',
  };
  const STATUS_KEYS = {
    applied: 'status.applied',
    rejected: 'status.rejected',
    bugged: 'status.bugged',
    expired: 'status.expired',
    contacted: 'status.contacted',
    interview: 'status.interview',
    awaiting_final: 'status.awaiting_final',
    awaiting_offer: 'status.awaiting_offer',
    offered: 'status.offered',
    started: 'status.started',
    declined: 'status.declined',
  };
  // The funnel: the buttons that move an application on, what each step
  // asks for, and how the timeline under a vacancy names its entries.
  const Funnel = window.WorkIdeFunnel;
  const STEP_KEYS = {
    contacted: 'step.contacted',
    interview: 'step.interview',
    awaiting_final: 'step.awaiting_final',
    awaiting_offer: 'step.awaiting_offer',
    offered: 'step.offered',
    started: 'step.started',
    declined: 'step.declined',
  };
  const STEP_HINT_KEYS = {
    contacted: 'step.hint.contacted',
    interview: 'step.hint.interview',
    awaiting_final: 'step.hint.awaiting_final',
    awaiting_offer: 'step.hint.awaiting_offer',
    offered: 'step.hint.offered',
    started: 'step.hint.started',
    declined: 'step.hint.declined',
  };
  const TIMELINE_KEYS = {
    applied: 'timeline.applied',
    contact: 'timeline.contact',
    interview: 'timeline.interview',
    final: 'timeline.final',
    offer: 'timeline.offer',
    offered: 'timeline.offered',
    started: 'timeline.started',
    declined: 'timeline.declined',
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
    // false until the first answer of listIdentities: an empty list before it
    // is "not known yet", not "there are none"
    booted: false,
    active: null,
    // prefix -> { loaded, selection, segments, activeSegment, pending }
    byIdentity: {},
    // "identity/segment" -> filter; every market remembers its own choice
    filters: {},
    // "identity/segment" -> source ('' or missing: every board), applied
    // together with the filter above
    sourceFilters: {},
    // "identity/segment" -> class ('' or missing: every class), the third
    // drop-down, applied together with the two above
    fitFilters: {},
    // [{ source, total }]: the boards the current filter holds in this market
    sources: [],
    listing: [],
    counts: {},
    // vacancy id -> { class, index, status, expires }: rows marked out of the
    // current filter, or turned down, kept as a one-line stub with an undo
    // for STUB_LIFETIME_MS
    stubs: new Map(),
    // ids whose stub has gone: a filter that still holds them ("All") does not
    // show them again until the view changes
    gone: new Set(),
    reasonFor: null,   // { id, status } while a reason form is open
    stepFor: null,     // { id, step, draft } while a funnel step's comment is written
    editing: null,     // { key, id, kind, index, draft } while a timeline comment is edited
    openEntries: new Set(),   // timeline entries shown opened, by key
    shown: {},             // class -> rows without feedback asked for ("Show more")
    stalled: new Set(),    // classes where "more" brought nothing: the scroll stops asking
    loadingMore: false,
    classTotals: {},       // class -> how many the current filter holds
    run: { running: false },
    // a function, so the status follows a change of language
    runStatus: null,
    log: [],
    // prefix -> { running, stage, startedAt }: a pipeline run of that
    // identity, however it was started (tools/runstate.py)
    pipelines: {},
    // restored after "Refresh" (page reload): which tab, market and filter
    restored: null,
    languageOpen: false,   // the language drop-down is open
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
        {
          active: state.active, segments, filters: state.filters, sources: state.sourceFilters,
          fits: state.fitFilters,
        }));
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
        state.sourceFilters = saved.sources || {};
        state.fitFilters = saved.fits || {};
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
  // Written as the language writes dates: "29.09.2026", "29 Sep 2026".
  function formatDate(isoDate) {
    const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate || '');
    if (!match) return t('row.date_unknown');
    const month = t('date.months').split(' ')[Number(match[2]) - 1];
    return t('date.format', { day: match[3], mm: match[2], month, year: match[1] });
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

  function currentSource() {
    const info = current();
    if (!info || !info.activeSegment) return '';
    return state.sourceFilters[filterKey(state.active, info.activeSegment)] || '';
  }

  function currentFit() {
    const info = current();
    if (!info || !info.activeSegment) return '';
    return state.fitFilters[filterKey(state.active, info.activeSegment)] || '';
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
    state.booted = true;
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
      state.sources = [];
      render();
      return;
    }
    const segment = info.activeSegment;
    const filter = currentFilter();
    // The source, the class and the rows asked for travel only when set:
    // without them every call is what it was before they existed.
    const source = currentSource();
    const fit = currentFit();
    const view = {};
    if (Object.keys(state.shown).length) view.shown = { ...state.shown };
    if (fit) view.fit = fit;
    const listingArgs = [state.active, segment, filter];
    if (source || fit || view.shown) listingArgs.push([], source);
    if (fit || view.shown) listingArgs.push(view);
    const countArgs = [state.active, segment];
    if (source || fit) countArgs.push(source);
    if (fit) countArgs.push(fit);
    const [listing, counts, totals, pending, sources] = await Promise.all([
      api.loadListing(...listingArgs),
      api.listingCounts(...countArgs),
      source ? api.classTotals(state.active, segment, filter, source)
        : api.classTotals(state.active, segment, filter),
      api.pendingFeedbackCount(state.active),
      fit ? api.listSources(state.active, segment, filter, fit) : api.listSources(state.active, segment, filter),
    ]);
    state.listing = listing;
    state.counts = counts;
    state.classTotals = totals;
    state.sources = sources;
    // a chosen board the filter has emptied keeps its website on the list
    state.sourceSites = state.sourceSites || {};
    for (const s of sources) if (s.site) state.sourceSites[s.source] = s.site;
    info.pending = pending;
    render();
  }

  function resetView() {
    state.stubs.clear();
    state.gone.clear();
    state.reasonFor = null;
    state.stepFor = null;
    state.editing = null;
    state.shown = {};
    state.stalled.clear();
  }

  // A class shows its top rows; "Show more" (and, with one class chosen, the
  // scroll) brings PAGE more each time, "Show less" goes back to the top
  // (the owner, 2026-10-04: "ten at a time is enough").
  const PAGE = 10;

  function loadedIn(cls) {
    return state.listing.filter((row) => row.class === cls);
  }

  function showMore(cls) {
    if (state.loadingMore) return null;
    state.loadingMore = true;
    const before = loadedIn(cls).length;
    return guarded(async () => {
      const waiting = loadedIn(cls).filter((row) => row.feedback.status === 'new').length;
      state.shown[cls] = waiting + PAGE;
      await loadList();
      if (loadedIn(cls).length <= before) {
        state.stalled.add(cls);
        render();
      }
    }).finally(() => { state.loadingMore = false; });
  }

  function showLess(cls) {
    return guarded(async () => {
      delete state.shown[cls];
      state.stalled.delete(cls);
      await loadList();
    });
  }

  // With one class chosen, reaching the end of the list loads the next PAGE.
  let scrollWatcher = null;

  function watchScroll() {
    if (scrollWatcher) scrollWatcher.disconnect();
    scrollWatcher = null;
    const sentinel = document.querySelector('[data-scroll-more]');
    if (!sentinel || typeof IntersectionObserver === 'undefined') return;
    scrollWatcher = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) showMore(sentinel.dataset.scrollMore);
    }, { rootMargin: '200px' });
    scrollWatcher.observe(sentinel);
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

  function selectSource(source) {
    const info = current();
    if (!info || !info.activeSegment) return;
    return guarded(async () => {
      resetView();
      state.sourceFilters[filterKey(state.active, info.activeSegment)] = source;
      await loadList();
    });
  }

  function selectFit(cls) {
    const info = current();
    if (!info || !info.activeSegment) return;
    return guarded(async () => {
      resetView();
      state.fitFilters[filterKey(state.active, info.activeSegment)] = cls;
      await loadList();
    });
  }

  // After an answer: reload, and when the row left the current filter leave
  // a one-line stub in its place (with undo) until the view changes.
  //
  // The place is counted among everything the section shows, stubs included:
  // counted among rows only, each new stub landed above the ones before it
  // (the owner, 2026-10-04: the last vacancy marked jumped to the top).
  async function answered(item, status) {
    const shown = arranged().byClass.get(item.class) || [];
    const index = shown.findIndex((entry) => entry.kind === 'row' && entry.row.id === item.id);
    await loadList();
    // A vacancy turned down goes out of sight whatever the filter (the owner,
    // 2026-10-04: "Vacancy expired" must fold like "Not for me"). One that
    // goes on along the funnel stays while the filter holds it.
    const left = !state.listing.some((row) => row.id === item.id);
    if (status !== 'new' && (left || TURNED_DOWN.includes(status))) {
      const stub = { class: item.class, index, status, expires: Date.now() + STUB_LIFETIME_MS };
      state.stubs.set(item.id, stub);
      setTimeout(() => expireStub(item.id, stub), STUB_LIFETIME_MS);
      render();
    }
  }

  // A stub lives 30 seconds, then goes (the owner, 2026-10-04: a column of
  // "Marked" lines piled up). A ring on its right drains over that time; its
  // tooltip counts the seconds down.
  const STUB_LIFETIME_MS = 30000;
  const TURNED_DOWN = ['rejected', 'bugged', 'expired'];

  function expireStub(id, stub) {
    // undone, or cleared by a change of view, in the meantime
    if (state.stubs.get(id) !== stub) return;
    state.stubs.delete(id);
    state.gone.add(id);
    // The stubs below it move up one: their places count this one.
    for (const other of state.stubs.values()) {
      if (other.class === stub.class && other.index > stub.index) other.index -= 1;
    }
    render();
  }

  function secondsLeft(expires) {
    return Math.max(0, Math.ceil((expires - Date.now()) / 1000));
  }

  // The tooltips change every second without a render: a render would
  // rebuild the list under the cursor.
  function tickStubTimers() {
    for (const tip of document.querySelectorAll('[data-expires]')) {
      tip.textContent = t('stub.removed_in', { n: secondsLeft(Number(tip.dataset.expires)) });
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
      state.gone.delete(id);
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
      const identity = state.active;
      state.runStatus = () => t('run.running', { kind: t(RUN_KIND_KEYS[kind]), identity });
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
      state.runStatus = () => t('run.running', { kind: t(RUN_KIND_KEYS[event.kind]), identity: event.identity });
    } else if (event.type === 'output') {
      state.log.push(event.text);
      if (state.log.length > LOG_LIMIT) state.log.splice(0, state.log.length - LOG_LIMIT);
    } else if (event.type === 'exit') {
      state.run = { running: false };
      if (event.error === 'claude_not_found') state.runStatus = () => t('run.claude_not_found');
      else if (event.code === 0) state.runStatus = () => t('run.finished');
      else if (event.code === null) state.runStatus = () => t('run.stopped');
      else state.runStatus = () => t('run.failed', { code: event.code });
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
    renderLanguagePicker();
    renderIdentityTabs();
    renderPanel();
    renderRunPanel();
    watchScroll();
  }

  // --- the language: a small drop-down of flags --------------------------------

  function flag(language) {
    return el('img', { class: 'flag', src: `flags/${language}.svg`, alt: '', width: 21, height: 14 });
  }

  function renderLanguagePicker() {
    const picker = document.querySelector('[data-testid="language-picker"]');
    const current = I18n.language();
    const button = el('button', {
      class: 'language-button', testid: 'language-button',
      title: t('language.choose'), 'aria-label': t('language.choose'),
      'aria-haspopup': 'listbox', 'aria-expanded': state.languageOpen ? 'true' : 'false',
      onclick: (event) => { event.stopPropagation(); toggleLanguages(!state.languageOpen); },
    }, flag(current), el('span', { class: 'caret' }, '▾'));
    const menu = state.languageOpen && el('ul', { class: 'language-menu', role: 'listbox', testid: 'language-menu' },
      I18n.languages.map((language) => el('li', {
        role: 'option',
        class: language === current ? 'active' : null,
        'aria-selected': language === current ? 'true' : 'false',
        testid: `language-option-${language}`,
        onclick: (event) => { event.stopPropagation(); chooseLanguage(language); },
      }, flag(language), el('span', {}, t('language.name', null, language)))));
    picker.replaceChildren(button, menu || '');
  }

  function toggleLanguages(open) {
    if (state.languageOpen === open) return;
    state.languageOpen = open;
    renderLanguagePicker();
  }

  function chooseLanguage(language) {
    state.languageOpen = false;
    I18n.setLanguage(language);
    render();
  }

  document.addEventListener('click', () => toggleLanguages(false));
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') toggleLanguages(false);
  });

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

  function renderLoading() {
    return el('div', { class: 'loading', role: 'status', testid: 'loading' },
      el('span', { class: 'spinner' }), el('span', {}, t('app.loading')));
  }

  function renderPanel() {
    const panel = document.querySelector('[data-testid="panel"]');
    if (!state.booted) {
      panel.replaceChildren(renderLoading());
      return;
    }
    if (!state.identities.length) {
      panel.replaceChildren(el('p', { class: 'empty', testid: 'no-identities' }, t('app.no_identities')));
      return;
    }
    const info = current();
    if (!info) {
      panel.replaceChildren(renderLoading());
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

  // One drop-down, its options grouped, each with how many it holds.
  function renderFilters() {
    const active = currentFilter();
    const option = (name) => el('option', {
      value: name, testid: `filter-option-${name}`, selected: name === active,
    }, `${t(FILTER_KEYS[name])} ${t('filter.count', { n: state.counts[name] || 0 })}`);
    return el('div', { class: 'filters', testid: 'filters' },
      el('label', { for: 'filter-select', testid: 'filter-label' }, t('filter.legend')),
      el('select', {
        id: 'filter-select', testid: 'filter',
        onchange: (event) => selectFilter(event.target.value),
      }, FILTER_GROUPS.map((group) => el('optgroup', { label: t(group.key) },
        group.filters.map(option)))),
      renderSourceFilter(),
      renderFitFilter());
  }

  // The classes ("Hot leads", "Worth a look", ...) under the other two
  // filters, each with how many; the chosen one stays even when empty.
  function renderFitFilter() {
    const active = currentFit();
    const totals = state.classTotals;
    const order = Object.keys(CLASS_KEYS);
    const classes = [...order, ...Object.keys(totals).filter((cls) => !order.includes(cls))]
      .filter((cls) => totals[cls] || cls === active);
    const all = Object.values(totals).reduce((sum, n) => sum + n, 0);
    const option = (value, label, n) => el('option', {
      value, testid: `fit-option-${value || 'all'}`, selected: value === active,
    }, `${label} ${t('filter.count', { n })}`);
    return el('span', { class: 'source-filter' },
      el('label', { for: 'fit-select', testid: 'fit-label' }, t('filter.fit_legend')),
      el('select', {
        id: 'fit-select', testid: 'fit-filter',
        onchange: (event) => selectFit(event.target.value),
      }, option('', t('filter.fit_all'), all),
      classes.map((cls) => option(cls, CLASS_KEYS[cls] ? t(CLASS_KEYS[cls]) : cls, totals[cls] || 0))));
  }

  // The boards the current filter holds, each with how many; the chosen one
  // stays on the list even when the filter leaves nothing from it.
  function renderSourceFilter() {
    const active = currentSource();
    const sources = [...state.sources];
    if (active && !sources.some((s) => s.source === active)) {
      const known = (state.sourceSites || {})[active];
      sources.push({ source: active, site: known || null, total: 0 });
    }
    const all = state.sources.reduce((sum, s) => sum + s.total, 0);
    const option = (value, label, n) => el('option', {
      value, testid: `source-option-${value || 'all'}`, selected: value === active,
    }, `${label} ${t('filter.count', { n })}`);
    return el('span', { class: 'source-filter' },
      el('label', { for: 'source-select', testid: 'source-label' }, t('filter.source_legend')),
      el('select', {
        id: 'source-select', testid: 'source-filter',
        onchange: (event) => selectSource(event.target.value),
      }, option('', t('filter.source_all'), all),
      sources.filter((s) => s.source).map((s) => option(s.source, s.site || s.source, s.total))));
  }

  // Rows arrive ordered by class, then score; stubs go back where they were.
  // Each stub's index is its place in the section as shown when it was made,
  // so putting them back from the top down rebuilds that same order.
  function arranged() {
    const sections = [];
    const byClass = new Map();
    for (const row of state.listing) {
      // a row still in the filter but folded into its stub, or gone with it
      if (state.stubs.has(row.id) || state.gone.has(row.id)) continue;
      if (!byClass.has(row.class)) {
        byClass.set(row.class, []);
        sections.push(row.class);
      }
      byClass.get(row.class).push({ kind: 'row', row });
    }
    const stubs = [...state.stubs].sort((a, b) => a[1].index - b[1].index);
    for (const [id, stub] of stubs) {
      if (!byClass.has(stub.class)) {
        byClass.set(stub.class, []);
        sections.push(stub.class);
      }
      const items = byClass.get(stub.class);
      items.splice(Math.min(Math.max(stub.index, 0), items.length), 0, { kind: 'stub', id, stub });
    }
    const order = Object.keys(CLASS_KEYS);
    sections.sort((a, b) => order.indexOf(a) - order.indexOf(b));
    return { sections, byClass };
  }

  function renderList() {
    const { sections, byClass } = arranged();
    if (!sections.length) {
      return el('p', { class: 'empty', testid: 'list-empty' }, t('list.empty'));
    }
    return el('div', { class: 'list', testid: 'list' }, sections.map((cls) => el('section', {
      class: 'class-section', testid: `section-${cls}`,
    },
    el('h2', {}, el('span', { class: 'section-title' }, CLASS_KEYS[cls] ? t(CLASS_KEYS[cls]) : cls),
      el('span', { class: 'count', testid: `section-count-${cls}` }, sectionCount(cls))),
    byClass.get(cls).map((item) => (item.kind === 'row' ? renderRow(item.row) : renderStub(item.id, item.stub))),
    renderMore(cls))));
  }

  // How much of a class is on screen, and how to see the rest (the owner,
  // 2026-10-04: a grey "(80)" went unnoticed, and so did the button under it).
  // Counted on what the listing brought, so a folded row is still "shown".
  function hiddenIn(cls) {
    return Math.max(0, (state.classTotals[cls] || 0) - loadedIn(cls).length);
  }

  function sectionCount(cls) {
    const shown = loadedIn(cls).length;
    const total = Math.max(state.classTotals[cls] || 0, shown);
    const hidden = hiddenIn(cls);
    if (!hidden) return t('list.shown_all', { n: total });
    const n = Math.min(PAGE, hidden);
    if (currentFit() === cls && !state.stalled.has(cls)) return t('list.shown_scroll', { shown, total, n });
    return t('list.shown_of', { shown, total, n, button: t('list.show_more', { n }) });
  }

  function renderMore(cls) {
    const hidden = hiddenIn(cls);
    const more = hidden > 0 && el('button', {
      class: 'more', testid: `show-more-${cls}`, onclick: () => showMore(cls),
    }, t('list.show_more', { n: Math.min(PAGE, hidden) }));
    const less = state.shown[cls] && el('button', {
      class: 'more', testid: `show-less-${cls}`, onclick: () => showLess(cls),
    }, t('list.show_less'));
    const scroll = hidden > 0 && currentFit() === cls && !state.stalled.has(cls)
      && el('div', { class: 'scroll-more', testid: `scroll-more-${cls}`, 'data-scroll-more': cls });
    if (!more && !less) return null;
    return el('div', { class: 'more-bar' }, more, less, scroll);
  }

  // Ctrl+Enter in a comment saves it, as its Save button does.
  function saveOnCtrlEnter(save) {
    return (event) => {
      if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        save();
      }
    };
  }

  function renderStub(id, stub) {
    // A negative delay starts the drain where it stands, so a render half way
    // through does not refill the ring.
    const elapsed = STUB_LIFETIME_MS - Math.max(0, stub.expires - Date.now());
    return el('div', { class: 'row stub', testid: `stub-${id}` },
      el('span', {}, t('stub.marked', { status: t(STATUS_KEYS[stub.status]) }), ' · ',
        el('button', { class: 'link', testid: 'btn-undo', onclick: () => undo(id) }, t('action.undo')),
        ' · ',
        // Goes now rather than when the ring runs out (the owner, 2026-10-05).
        el('button', { class: 'link', testid: 'btn-hide', onclick: () => expireStub(id, stub) },
          t('action.hide'))),
      el('span', { class: 'stub-timer', testid: 'stub-timer' },
        el('span', {
          class: 'ring', style: `animation-duration: ${STUB_LIFETIME_MS}ms; animation-delay: -${elapsed}ms`,
        }),
        el('span', { class: 'tip', role: 'tooltip', testid: 'stub-timer-tip', 'data-expires': String(stub.expires) },
          t('stub.removed_in', { n: secondsLeft(stub.expires) }))));
  }

  // The vacancy's lines in the interface language. The pipeline renders them
  // in every language (vacancies.views); a row recorded before it did has
  // only the identity's own (view).
  function viewOf(item) {
    return (item.views && item.views[I18n.language()]) || item.view || {};
  }

  function renderRow(item) {
    const view = viewOf(item);
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
    // Where the vacancy came from, by the website a person knows: on LinkedIn
    // remote/hybrid shows only after logging in, so the board is worth seeing
    // before the link is opened.
    if (view.source) {
      const site = (state.sourceSites || {})[view.source] || view.source;
      lines.push(el('li', { testid: 'details-source' }, `${t('row.source')}: ${site}`));
    }
    if (view.to_confirm && view.to_confirm.length) {
      lines.push(md('li', `${t('row.to_confirm')}: ${view.to_confirm.join(', ')}`));
    }
    if (view.exclusivity && view.exclusivity.length) {
      lines.push(el('li', { testid: 'details-exclusivity' },
        `${t('row.exclusivity')}: ${view.exclusivity.join(', ')}`));
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
    if (!lines.length) return null;
    return el('details', { class: 'details' }, el('summary', {}, t('row.details')), el('ul', {}, lines));
  }

  // Opens the vacancy the way the operating system opens any link: in the
  // default browser, as a new tab when it is already running.
  function openLink(view) {
    if (view.url) guarded(() => api.openExternal(view.url));
  }

  // "Open", and beside it a small "Copy URL" (the owner, 2026-10-04: the link
  // is sometimes wanted elsewhere). The copy says so on the button for a
  // moment, since nothing else on screen changes.
  function openButton(view) {
    return [
      el('button', {
        class: 'open', testid: 'btn-open', disabled: !view.url, onclick: () => openLink(view),
      }, t('action.open')),
      el('button', {
        class: 'copy', testid: 'btn-copy-url', disabled: !view.url,
        onclick: (event) => copyLink(view, event.currentTarget),
      }, t('action.copy_url')),
    ];
  }

  function copyLink(view, button) {
    if (!view.url) return;
    guarded(async () => {
      await api.copyText(view.url);
      button.textContent = t('action.copied');
      setTimeout(() => { button.textContent = t('action.copy_url'); }, 1500);
    });
  }

  // One click opens the reason; a second one on the same button within a
  // double-click's time saves at once, with whatever reason is typed (the
  // owner, 2026-10-04: a double click skips "Save"). Timed by hand rather than
  // with dblclick: the first click re-renders the row, and the second lands on
  // a new button.
  const DOUBLE_CLICK_MS = 500;

  function askReason(item, status) {
    const open = state.reasonFor;
    if (open && open.id === item.id && open.status === status
        && Date.now() - open.at < DOUBLE_CLICK_MS) {
      return mark(item, status, open.draft || '');
    }
    const same = open && open.id === item.id && open.status === status;
    state.reasonFor = { id: item.id, status, at: Date.now(), draft: same ? open.draft : undefined };
    render();
  }

  function renderAnswers(item) {
    const open = state.reasonFor && state.reasonFor.id === item.id ? state.reasonFor.status : null;
    const answers = el('div', { class: 'answers' },
      openButton(viewOf(item)),
      el('button', { testid: 'btn-applied', onclick: () => mark(item, 'applied', null) }, t('action.applied')),
      el('button', {
        testid: 'btn-rejected', class: open === 'rejected' ? 'pressed' : null,
        onclick: () => askReason(item, 'rejected'),
      }, t('action.rejected')),
      el('button', {
        testid: 'btn-bugged', class: open === 'bugged' ? 'pressed' : null,
        onclick: () => askReason(item, 'bugged'),
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
      onkeydown: saveOnCtrlEnter(() => mark(item, open, input.value)),
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
      openButton(viewOf(item)),
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
      onkeydown: saveOnCtrlEnter(() => advance(item, form.step, input.value)),
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
        onkeydown: saveOnCtrlEnter(saveEdit),
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
      `${t('run.log_title')} · ${state.runStatus ? state.runStatus() : ''}`;
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
      state.runStatus = () => t('run.running', { kind: t(RUN_KIND_KEYS[run.kind]), identity: run.identity });
    }
    render();
    try {
      await loadIdentities();
    } finally {
      // a failed first load shows its error, not a spinner that never stops
      state.booted = true;
    }
    await pollPipelines();
    render();
    setInterval(() => { pollPipelines(); }, POLL_MS);
    setInterval(tickStubTimers, 1000);
  });
}());
