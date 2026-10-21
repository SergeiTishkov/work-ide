// The renderer: identity tabs, four filter drop-downs (markets, what to show,
// boards, classes), the vacancy rows with their answers, and the agent-run
// controls.
//
// Everything it does to the world goes through window.api (main/preload.js);
// the UI tests replace window.api with a mock and assert on the calls.
(function () {
  const api = window.api;

  // The "Show" drop-down (the owner, 2026-10-07): how fresh, then which
  // statuses. A row is listed when both its freshness and its status are
  // checked. "Not applied or denied" is one check box with no master row.
  const FRESHNESS = ['fresh', 'earlier'];
  const STATUS_GROUPS = [
    { key: 'new', statuses: ['new'] },
    { key: 'applications', label: 'filter.group.applications',
      statuses: ['applied', 'contacted', 'interview', 'awaiting_final', 'awaiting_offer', 'offered',
        'started', 'declined'] },
    { key: 'denied', label: 'filter.group.denied', statuses: ['rejected', 'bugged', 'expired'] },
  ];
  const STATUSES = STATUS_GROUPS.flatMap((group) => group.statuses);
  // What the drop-downs choose (schemas/queries.sql, THE VIEW). null
  // markets, boards, classes or companies: all of them, also the ones a later
  // run adds. companies: { kinds: [shown], hidden: [names hidden among them] }.
  // text: the words typed in the text field (WORDS there), '' for none.
  const DEFAULT_VIEW = {
    segments: null, statuses: ['new'], fresh: ['fresh'], sources: null, fits: null, companies: null, ages: null,
    text: '',
  };
  // The "Age" drop-down (the owner, 2026-10-17): how long ago it was posted,
  // in bands of their own (schemas/queries.sql, AGE).
  const AGES = ['today', 'week', 'month', 'older'];
  const AGE_KEYS = {
    today: 'filter.age.today', week: 'filter.age.week', month: 'filter.age.month', older: 'filter.age.older',
  };
  // The "Company" drop-down's groups, in its order (tools/company_kinds.py):
  // the intermediaries, each listed by name, then every other company as one row.
  const INTERMEDIARIES = ['marketplace', 'agency', 'reposter'];
  const COMPANY_KINDS = [...INTERMEDIARIES, 'other'];
  const COMPANY_KIND_KEYS = {
    marketplace: 'filter.company_kind.marketplace',
    agency: 'filter.company_kind.agency',
    reposter: 'filter.company_kind.reposter',
    other: 'filter.company_kind.other',
  };
  const CLASS_KEYS = {
    hot_lead: 'class.hot_lead',
    worth_a_look: 'class.worth_a_look',
    long_shot: 'class.long_shot',
    remote_unconfirmed: 'class.remote_unconfirmed',
    engagement_unconfirmed: 'class.engagement_unconfirmed',
  };
  // Listed in "Category" whether they hold any or not.
  const STABLE_CLASSES = ['hot_lead', 'worth_a_look', 'long_shot', 'remote_unconfirmed'];
  const FILTER_KEYS = {
    fresh: 'filter.fresh',
    earlier: 'filter.earlier',
    new: 'filter.new',
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
  const REASON_KEYS = { rejected: 'reason.rejected', bugged: 'reason.bugged' };
  const LOG_LIMIT = 3000;
  const PANEL_KEY = 'work-ide-task-panel';
  // The app's own settings (Menu -> Settings...), kept per Windows user with
  // the rest of the app's storage
  const SETTINGS_KEY = 'work-ide-settings';
  // showFinished and taskOrder: the task list's gear (task 0068)
  const DEFAULT_SETTINGS = { showTasks: true, showFinished: true, taskOrder: 'oldest', minimizeOnCopy: true };
  const TASK_ORDERS = ['oldest', 'newest'];
  const TASK_ORDER_KEYS = { oldest: 'task.order_oldest', newest: 'task.order_newest' };
  // How often the pipeline indicator asks the databases. Tests shorten it.
  const POLL_MS = window.__WORK_IDE_POLL_MS || 5000;
  const SESSION_KEY = 'work-ide-view';

  const state = {
    identities: [],
    settings: readSettings(),
    settingsOpen: false,
    // "Task scheduler...": { list, error, form } while open
    scheduler: null,
    // the task the panel's cross asks about: { id, label }
    confirmStop: null,
    panelFolded: false,
    // false until the first answer of listIdentities: an empty list before it
    // is "not known yet", not "there are none"
    booted: false,
    active: null,
    // prefix -> { loaded, selection, segments, pending }
    byIdentity: {},
    // prefix -> the view (DEFAULT_VIEW's shape): every identity keeps its own
    views: {},
    // the check list left open while the list reloads under it, its cursor
    // and scroll: every click redraws the page
    openDropdown: null,
    dropdownCursor: 0,
    dropdownScroll: 0,
    // [{ source, site, total }]: the boards the view holds, the boards aside
    sources: [],
    // { identity: Set of boards }: every board listed since the app started,
    // so a board hidden and then emptied by the other drop-downs is known
    seenSources: {},
    // [{ kind, name, total }]: the companies the view holds, the companies
    // aside; every other company is one row, name null
    companies: [],
    // { age band: how many }: the "Age" drop-down's numbers, the ages aside
    ages: {},
    // the "Clean up" popup while open: { ages, statuses, classes, result, busy, error }
    cleanup: null,
    // intermediary name -> kind, kept across loads: a hidden one the view has
    // emptied stays on the list, unticked, to be ticked back
    companyKinds: {},
    listing: [],
    // the "Show" drop-down's numbers: { statuses: { status: n }, fresh: { fresh, earlier } }
    counts: { statuses: {}, fresh: {} },
    // vacancy id -> { class, index, status, expires }: rows marked out of the
    // current filter, or turned down, kept as a one-line stub with an undo
    // for STUB_LIFETIME_MS
    stubs: new Map(),
    // ids whose stub has gone: a filter that still holds them ("All") does not
    // show them again until the view changes
    gone: new Set(),
    reasonFor: null,   // { id, status } while a reason form is open
    stepFor: null,     // { id, step, draft } while a funnel step's comment is written
    // "Generate CV" and "Generate Cover Letter": the result of a generation
    // asked for from a card, shown on it until closed
    cvResults: new Map(),   // "<identity>/<id>/<kind>" -> the result shown on the card
    cvFor: null,       // { identity, id, kind, draft } while the instructions are written
    // "<identity>/<id>" -> { dir, cv, letter, errors }: the documents in the
    // vacancy's folder (main/documents.js)
    docs: {},
    editing: null,     // { key, id, kind, index, draft } while a timeline comment is edited
    openEntries: new Set(),   // timeline entries shown opened, by key
    shown: {},             // class -> rows without feedback asked for ("Show more")
    stalled: new Set(),    // classes where "more" brought nothing: the scroll stops asking
    loadingMore: false,
    classTotals: {},       // class -> how many the view holds, the classes aside
    // the number of the list load a drop-down started, 0 when none is going:
    // a spinner stands in for the vacancies meanwhile
    listLoading: 0,
    // the task queue (main/tasks.js), as its last event gave it
    tasks: [],
    // the task whose log the panel shows: chosen by a click, else the running one
    chosenTask: null,
    // a collection's steps: folded while it runs, opened after it ended
    foldedTasks: new Set(),
    openTasks: new Set(),
    shownTask: null,
    taskLog: [],
    // prefix -> { running, stage, startedAt }: a pipeline run of that
    // identity, however it was started (tools/runstate.py)
    pipelines: {},
    openPicker: null,   // which top-bar drop-down is open: 'theme', 'language' or null
    taskViewOpen: false,   // the task list's gear menu
  };

  // --- the view survives "Refresh" and a restart ----------------------------
  // localStorage, not sessionStorage: Refresh may restart the whole app, and
  // the tab, market and filter should come back after that too.

  function saveView() {
    try {
      localStorage.setItem(SESSION_KEY, JSON.stringify({ active: state.active, views: state.views }));
    } catch {
      // storage unavailable: a refresh starts from the defaults
    }
  }

  // A view saved before 2026-10-07 (one filter per market) has no `views`:
  // the defaults it is.
  function restoreView() {
    try {
      const saved = JSON.parse(localStorage.getItem(SESSION_KEY) || 'null');
      if (saved) {
        state.active = saved.active || null;
        state.views = saved.views || {};
      }
    } catch {
      state.views = {};
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

  function current() {
    return state.active ? state.byIdentity[state.active] : null;
  }

  function currentView() {
    return { ...DEFAULT_VIEW, ...(state.views[state.active] || {}) };
  }

  // The class the view narrows to, when it is one: the list then loads more
  // as it is scrolled.
  function onlyFit() {
    const { fits } = currentView();
    return fits && fits.length === 1 ? fits[0] : '';
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
    const on = state.identities.filter((i) => i.active !== false);
    const chosen = state.identities.find((i) => i.prefix === state.active);
    if (!chosen || (chosen.active === false && on.length)) {
      state.active = (on[0] || state.identities[0] || {}).prefix || null;
    }
    if (state.active) await loadIdentity(state.active);
  }

  async function loadIdentity(prefix) {
    const data = await api.loadSegments(prefix);
    state.byIdentity[prefix] = {
      loaded: true,
      selection: data.selection,
      displayName: data.displayName,
      segments: data.segments || [],
      pending: await api.pendingFeedbackCount(prefix),
    };
    await loadList();
  }

  // The view sent to the database: markets the latest selection no longer
  // has are left out, and when none of the chosen is left, every market.
  function viewToLoad(info) {
    const view = currentView();
    if (view.segments && view.segments.length) {
      const known = view.segments.filter((slug) => info.segments.some((s) => s.slug === slug));
      view.segments = known.length ? known : null;
    }
    return view;
  }

  // Every loadList is numbered; an answer that arrives after a newer one was
  // asked for is dropped, so quick clicks never end on an older list.
  let listRequest = 0;

  async function loadList() {
    const asked = ++listRequest;
    const info = current();
    if (!info || !info.segments.length) {
      state.listing = [];
      state.counts = { statuses: {}, fresh: {} };
      state.sources = [];
      state.companies = [];
      state.ages = {};
      state.classTotals = {};
      render();
      return;
    }
    const view = viewToLoad(info);
    // the rows asked for travel only when set
    const page = Object.keys(state.shown).length ? [{ shown: { ...state.shown } }] : [];
    const [listing, counts, totals, pending, sources, companies, ages] = await Promise.all([
      api.loadListing(state.active, view, ...page),
      api.listingCounts(state.active, view),
      api.classTotals(state.active, view),
      api.pendingFeedbackCount(state.active),
      api.listSources(state.active, view),
      api.listCompanies(state.active, view),
      api.listAges ? api.listAges(state.active, view) : {},
    ]);
    if (asked !== listRequest) return;
    state.ages = ages || {};
    state.listing = listing;
    state.counts = counts;
    state.classTotals = totals;
    state.sources = sources;
    const seen = state.seenSources[state.active] || (state.seenSources[state.active] = new Set());
    for (const s of sources) if (s.source) seen.add(s.source);
    state.companies = companies;
    for (const c of companies) if (c.name) state.companyKinds[c.name] = c.kind;
    // a chosen board the view has emptied keeps its website on the list
    state.sourceSites = state.sourceSites || {};
    for (const s of sources) if (s.site) state.sourceSites[s.source] = s.site;
    info.pending = pending;
    render();
    await loadDocs(state.active, listing.map((item) => item.id));
  }

  // The documents of the listed vacancies, for their buttons. Without an
  // answer (the folder could not be found) the buttons say "Generate": the
  // list itself is not held up by it.
  async function loadDocs(identity, ids) {
    if (!identity || !ids.length || !api.documentsState) return;
    let found;
    try {
      found = await api.documentsState(identity, ids);
    } catch (error) {
      console.warn('documents state:', error.message);
      return;
    }
    for (const id of ids) {
      const key = `${identity}/${id}`;
      if (found[id]) state.docs[key] = found[id];
      else delete state.docs[key];
    }
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

  // A click in a drop-down: the view changes, the list reloads from the top.
  // A click in a drop-down: the check box changes at once, the list follows
  // once the clicks stop for VIEW_DEBOUNCE_MS, and a spinner stands in for
  // the vacancies until it has come (the owner, 2026-10-12: the window
  // froze after each click). body[data-list-pending] is set from the click
  // until the list is in, for the UI tests to wait on.
  const VIEW_DEBOUNCE_MS = 200;
  let viewTimer = null;

  function changeView(change) {
    if (!current()) return;
    resetView();
    state.views[state.active] = { ...currentView(), ...change };
    saveView();
    document.body.dataset.listPending = '1';
    render();
    clearTimeout(viewTimer);
    viewTimer = setTimeout(() => {
      viewTimer = null;
      const mine = ++state.listLoading;
      render();
      guarded(loadList).finally(() => {
        if (state.listLoading !== mine) return;   // a later change is loading
        state.listLoading = 0;
        if (!viewTimer) delete document.body.dataset.listPending;
        render();
      });
    }, VIEW_DEBOUNCE_MS);
  }

  // After an answer: reload, and when the row left the current filter leave
  // a one-line stub in its place (with undo) until the view changes.
  //
  // The place is counted among everything the section shows, stubs included:
  // counted among rows only, each new stub landed above the ones before it
  // (the owner, 2026-10-04: the last vacancy marked jumped to the top).
  // One card, not the list (the owner, 2026-10-18: a click waited 1.5 s for
  // the whole list to load again). The store answers a write with the
  // vacancy's record as the base now holds it; the card is redrawn from that
  // at once, and the list with the drop-downs' numbers catches up behind it.
  // The store thread answers in the order asked, so a catch-up never brings
  // back a list older than a later click's record.
  function showRecord(item, record) {
    const row = state.listing.find((r) => r.id === item.id);
    if (row) {
      row.feedback = record;
      return;
    }
    const { stubIndex, ...back } = item;
    state.listing.splice(placeOf(item), 0, { ...back, feedback: record });
  }

  // Where a card brought back by "Undo" goes: where its stub stood among the
  // rows of its class.
  function placeOf(item) {
    const wanted = item.stubIndex == null ? Infinity : item.stubIndex;
    let seen = 0;
    let last = -1;
    for (let i = 0; i < state.listing.length; i++) {
      if (state.listing[i].class !== item.class) continue;
      if (seen === wanted) return i;
      seen += 1;
      last = i;
    }
    return last < 0 ? state.listing.length : last + 1;
  }

  // Does the view still hold a vacancy with this answer? Only the status
  // changes with an answer; the other filters held it a moment ago.
  function inView(record) {
    return currentView().statuses.includes(record.status);
  }

  function catchUp() {
    guarded(() => loadList());
  }

  // "Shown 10 of 660" as the list that catches up will have it, so it does
  // not jump half a second later (the owner, 2026-10-18).
  function countIn(cls, change) {
    state.classTotals[cls] = Math.max(0, (state.classTotals[cls] || 0) + change);
  }

  // A card brought back into a capped class pushes out its last unanswered
  // card, as the store's limit per class does.
  function trimClass(cls, keep) {
    const waiting = state.listing.filter((r) => r.class === cls && r.id !== keep && r.feedback.status === 'new');
    const last = waiting.at(-1);
    if (last) state.listing = state.listing.filter((r) => r !== last);
  }

  function answered(item, status, record) {
    const shown = arranged().byClass.get(item.class) || [];
    const index = shown.findIndex((entry) => entry.kind === 'row' && entry.row.id === item.id);
    showRecord(item, record);
    // A vacancy turned down goes out of sight whatever the filter (the owner,
    // 2026-10-04: "Vacancy expired" must fold like "Not for me"). One that
    // goes on along the funnel stays while the filter holds it.
    const left = !inView(record);
    // Left, it counts no more; its row stays under the stub until the list
    // catches up and the next card moves up into its place.
    if (left) countIn(item.class, -1);
    if (status !== 'new' && (left || TURNED_DOWN.includes(status))) {
      const stub = {
        class: item.class, index, status, row: item, left, expires: Date.now() + STUB_LIFETIME_MS,
      };
      state.stubs.set(item.id, stub);
      setTimeout(() => expireStub(item.id, stub), STUB_LIFETIME_MS);
    } else if (left) {
      state.listing = state.listing.filter((r) => r.id !== item.id);
    }
    render();
    catchUp();
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
      const record = await api.setFeedback(state.active, item.id, status, reason);
      answered(item, status, record);
    });
  }

  // One step along the funnel; the comment is '' when nothing was written.
  function advance(item, step, comment) {
    return guarded(async () => {
      state.stepFor = null;
      const record = await api.advance(state.active, item.id, step, comment || '');
      answered(item, step, record);
    });
  }

  // "Undo": one step back — the funnel's last step, or the answer altogether.
  function undo(id) {
    return guarded(async () => {
      const stub = state.stubs.get(id);
      const item = state.listing.find((r) => r.id === id) || (stub && { ...stub.row, stubIndex: stub.index });
      state.stubs.delete(id);
      state.gone.delete(id);
      state.stepFor = null;
      state.editing = null;
      const record = await api.stepBack(state.active, id);
      if (item) {
        const listed = state.listing.some((r) => r.id === id);
        const capped = hiddenIn(item.class) > 0;
        showRecord(item, record);
        const back = inView(record);
        if (!back) state.listing = state.listing.filter((r) => r.id !== id);
        if (stub && stub.left && back) countIn(item.class, 1);
        if (!stub && listed && !back) countIn(item.class, -1);
        if (!listed && back && capped) trimClass(item.class, id);
      }
      render();
      catchUp();
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
      const record = await api.editComment(state.active, editing.id, editing.kind,
        editing.index == null ? null : editing.index, editing.draft);
      state.editing = null;
      // A comment written is a comment to read: its entry stays open.
      if (editing.draft.trim()) state.openEntries.add(editing.key);
      else state.openEntries.delete(editing.key);
      const row = state.listing.find((r) => r.id === editing.id);
      if (row) showRecord(row, record);
      render();
      catchUp();
    });
  }

  // --- the task queue ----------------------------------------------------------
  // "Collect vacancies", "Generate CV" and "Generate Cover Letter" queue a
  // task (main/tasks.js); the bottom panel lists the tasks and the log of one.

  const ACTIVE_TASK = new Set(['queued', 'running']);

  function findTask(identity, kind, vacancyId = null) {
    const own = state.tasks.find((task) => ACTIVE_TASK.has(task.state) && task.identity === identity
      && task.kind === kind && (task.vacancyId || null) === vacancyId);
    if (own) return own;
    // the document the CV/CL batch is making now
    const current = batchCurrent();
    return current && current.identity === identity && current.kind === kind && current.vacancyId === vacancyId
      ? { ...current, state: 'running', origin: 'external' } : null;
  }

  function batchCurrent() {
    const batch = state.tasks.find((task) => task.kind === 'batch' && task.state === 'running');
    return batch ? batch.current : null;
  }

  async function enqueue(request) {
    const reply = await api.enqueueTask(request);
    if (reply && reply.task) mergeTask(reply.task);
    render();
    return reply;
  }

  function mergeTask(task) {
    const index = state.tasks.findIndex((t) => t.id === task.id);
    if (index < 0) state.tasks.push(task);
    else state.tasks[index] = task;
  }

  function startCollect() {
    const identity = state.active;
    return guarded(() => enqueue({ kind: 'collect', identity }));
  }

  function stopCollect() {
    const task = findTask(state.active, 'collect');
    if (task) guarded(() => api.cancelTask(task.id));
  }

  function onTaskEvent(event) {
    if (event.type === 'log') {
      if (event.id === state.shownTask) appendTaskLog(event.text);
      return;
    }
    if (event.type === 'finished') {
      taskFinished(event.task);
      return;
    }
    if (event.type === 'tasks') {
      // the batch moved on: the document it made shows on its card
      const before = batchCurrent();
      state.tasks = event.tasks;
      const after = batchCurrent();
      if (before && (!after || after.vacancyId !== before.vacancyId || after.kind !== before.kind)) {
        loadDocs(before.identity, [before.vacancyId]);
      }
      render();
    }
  }

  function taskFinished(task) {
    mergeTask(task);
    if (task.kind === 'batch') {
      render();
      return;
    }
    if (PIPELINE_KINDS.has(task.kind)) {
      const problem = task.result && task.result.error === 'claude_not_found' ? t('run.claude_not_found') : null;
      // A run may have created the database, recorded a selection or changed
      // the feedback: what it touched is reloaded. The reload clears the
      // error box, so a problem is shown after it.
      let reload = Promise.resolve();
      if (task.identity === state.active) {
        reload = guarded(async () => {
          resetView();
          state.byIdentity = {};
          await loadIdentities();
        });
      } else {
        delete state.byIdentity[task.identity];
      }
      reload.then(() => { if (problem) showError(problem); });
      render();
      return;
    }
    if (task.kind === 'reputation') {
      // the lookup rendered the company's rows again: the list shows them
      // (and the button goes)
      const problem = task.state === 'failed' ? `${t('reputation.failed')}: ${task.error || '?'}` : null;
      if (task.identity === state.active) {
        guarded(() => loadList()).then(() => { if (problem) showError(problem); });
      } else if (problem) {
        showError(problem);
      }
      render();
      return;
    }
    // a CV or a cover letter: the buttons follow the folder; a generation
    // asked for from a card shows its result there
    const key = `${task.identity}/${task.vacancyId}/${task.kind}`;
    if (task.origin === 'app' && task.state !== 'stopped') {
      const result = task.result || {};
      state.cvResults.set(key, result.ok ? result : { ok: false, error: task.error || result.error || '?' });
    }
    guarded(() => loadDocs(task.identity, [task.vacancyId]));
    render();
  }

  // --- rendering -------------------------------------------------------------

  function render() {
    document.title = t('app.title');
    renderPickers();
    renderIdentityTabs();
    renderPanel();
    renderTaskPanel();
    watchScroll();
  }

  // --- the top bar's pickers: theme and language --------------------------------
  // Each is a button showing the current choice — an icon, a flag, no arrow —
  // that opens a short list under it. One open at a time. Refresh stands to
  // their left, a button of the same size (the owner, 2026-10-20: out of the
  // menu, the same ring-arrow icon).

  function flag(language) {
    return el('img', { class: 'flag', src: `flags/${language}.svg`, alt: '', width: 21, height: 14 });
  }

  // Line icons in the text colour. Constants of this file, never data.
  const THEME_ICONS = {
    system: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
    light: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4'
      + 'M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    dark: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
  };
  const THEME_KEYS = { system: 'theme.system', light: 'theme.light', dark: 'theme.dark' };

  function themeIcon(theme) {
    const icon = el('span', { class: 'theme-icon', 'data-theme-icon': theme });
    icon.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" '
      + `stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${THEME_ICONS[theme]}</svg>`;
    return icon;
  }

  function renderPicker(name, { title, current, options, choose }) {
    const host = document.querySelector(`[data-testid="${name}-picker"]`);
    const open = state.openPicker === name;
    const chosen = options.find((option) => option.value === current) || options[0];
    const button = el('button', {
      class: 'picker-button', testid: `${name}-button`, title, 'aria-label': title,
      'aria-haspopup': 'listbox', 'aria-expanded': open ? 'true' : 'false',
      onclick: (event) => { event.stopPropagation(); togglePicker(open ? null : name); },
    }, chosen.icon());
    const menu = open && el('ul', { class: 'picker-menu', role: 'listbox', testid: `${name}-menu` },
      options.map((option) => el('li', {
        role: 'option',
        class: option.value === current ? 'active' : null,
        'aria-selected': option.value === current ? 'true' : 'false',
        testid: `${name}-option-${option.value}`,
        onclick: (event) => {
          event.stopPropagation();
          state.openPicker = null;
          choose(option.value);
        },
      }, option.icon(), el('span', {}, option.label))));
    host.replaceChildren(button, menu || '');
  }

  function renderRefreshButton() {
    const host = document.querySelector('[data-testid="refresh-slot"]');
    host.replaceChildren(el('button', {
      class: 'picker-button', testid: 'refresh', type: 'button',
      title: t('app.refresh_hint'), 'aria-label': t('app.refresh'), onclick: refresh,
    }, el('span', { class: 'refresh-icon', 'aria-hidden': 'true' }, '\u27F3')));
  }

  function renderPickers() {
    renderRefreshButton();
    renderPicker('theme', {
      title: t('theme.choose'),
      current: Theme.theme(),
      options: Theme.themes.map((theme) => ({
        value: theme, icon: () => themeIcon(theme), label: t(THEME_KEYS[theme]),
      })),
      choose: (theme) => { Theme.setTheme(theme); renderPickers(); },
    });
    renderPicker('language', {
      title: t('language.choose'),
      current: I18n.language(),
      options: I18n.languages.map((language) => ({
        value: language, icon: () => flag(language), label: t('language.name', null, language),
      })),
      choose: (language) => { I18n.setLanguage(language); render(); },
    });
  }

  function togglePicker(name) {
    if (state.openPicker === name) return;
    state.openPicker = name;
    renderPickers();
  }

  document.addEventListener('click', () => {
    togglePicker(null);
    closeMenu();
    openTaskView(false);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      togglePicker(null);
      closeMenu();
      openTaskView(false);
      closeDropdowns();
    }
  });

  // An identity turned off in "Identities" has no tab (the owner,
  // 2026-10-20: "hide the ones that exist but are not active"), unless it is
  // the one shown: turned off while open, it stays until another is chosen.
  function renderIdentityTabs() {
    const nav = document.querySelector('[data-testid="identity-tabs"]');
    const tabs = state.identities.filter((identity) => identity.active !== false || identity.prefix === state.active);
    nav.replaceChildren(...tabs.map((identity) => {
      const collecting = (state.pipelines[identity.prefix] || {}).running;
      const inactive = identity.active === false;
      return el('button', {
        class: `tab${identity.prefix === state.active ? ' active' : ''}${inactive ? ' inactive' : ''}`,
        role: 'tab',
        'aria-selected': identity.prefix === state.active ? 'true' : 'false',
        title: [identity.displayName, inactive && t('identities.inactive')].filter(Boolean).join(' · ') || null,
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

  // The menu stands in the top bar, right of the language (the owner,
  // 2026-10-21); it needs the identity's data, so it is drawn with the panel.
  function renderMenuSlot() {
    const host = document.querySelector('[data-testid="menu-slot"]');
    const info = state.booted && state.identities.length ? current() : null;
    if (!info) {
      host.replaceChildren();
      return;
    }
    const identity = state.identities.find((i) => i.prefix === state.active);
    const pending = info.pending ? info.pending.bugged + info.pending.rejected : 0;
    host.replaceChildren(renderMenu(identity, pending));
  }

  function renderPanel() {
    renderMenuSlot();
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
    if (state.cleanup) parts.push(renderCleanup());
    if (state.identitiesPopup) parts.push(renderIdentities());
    if (!info.selection) {
      parts.push(el('p', { class: 'empty', testid: 'never-collected' }, t('identity.never_collected')));
    } else if (!info.segments.length) {
      parts.push(el('p', { class: 'empty' }, t('identity.no_segments')));
    } else {
      parts.push(renderFilters(info), renderList());
    }
    const focused = document.activeElement && document.activeElement.closest
      && document.activeElement.closest('.dropdown');
    const typing = textFilterCaret();
    panel.replaceChildren(...parts);
    if (typing) typing.restore(panel);
    // a check list stays open across the redraw its own click caused
    const open = state.openDropdown && panel.querySelector(`[data-dropdown="${state.openDropdown}"]`);
    if (open) open.reopen(Boolean(focused));
    else state.openDropdown = null;
  }

  // --- the commands menu (the owner, 2026-10-20) ----------------------------
  // Collect, Stop, Review feedback, Clean up and the identities live in one
  // menu; Refresh is a button of its own in the top bar. Collect shows its spinner and stage in the menu; the menu's
  // own button spins while anything runs (busyWith), so it is seen with the
  // menu closed.

  function collectState() {
    const pipeline = state.pipelines[state.active] || { running: false };
    const task = findTask(state.active, 'collect');
    return {
      pipeline, task,
      running: Boolean(pipeline.running || (task && task.state === 'running')),
      queued: Boolean(task && task.state === 'queued'),
    };
  }

  function collectingText(pipeline) {
    return pipeline.stage ? t('run.collecting_stage', { stage: pipeline.stage }) : t('run.collecting');
  }

  // What runs right now, one line each: the app's tasks, a pipeline run of
  // any identity started anywhere, a clean-up being counted or deleted.
  function busyWith() {
    const lines = [];
    for (const task of state.tasks) {
      if (task.state !== 'running') continue;
      const kind = TASK_KIND_KEYS[task.kind] ? t(TASK_KIND_KEYS[task.kind]) : task.kind;
      lines.push(task.identity ? `${kind} · ${task.identity}` : kind);
    }
    for (const [prefix, pipeline] of Object.entries(state.pipelines)) {
      if (pipeline && pipeline.running) lines.push(`${collectingText(pipeline)} · ${prefix}`);
    }
    if (state.cleanup && state.cleanup.busy) lines.push(t('cleanup.button'));
    return lines;
  }

  function menuItem({ testid, text, title, disabled, onclick, busy = false }) {
    return el('button', {
      class: busy ? 'menu-item busy' : 'menu-item', role: 'menuitem', type: 'button', testid, title, disabled,
      onclick: (event) => {
        event.stopPropagation();
        state.openMenu = false;
        render();
        if (onclick) onclick();
      },
    }, text);
  }

  function collectItem(identity) {
    const { pipeline, task, running, queued } = collectState();
    if (queued) {
      return menuItem({
        testid: 'run-collect', disabled: true, text: t('run.queued'),
        title: task.waitingFor ? waitText(task.waitingFor) : t('run.queued_hint'),
      });
    }
    if (running) {
      return menuItem({
        testid: 'run-collect', disabled: true, busy: true,
        title: t('run.collecting_since', { time: String(pipeline.startedAt || '').slice(11, 16) }),
        text: [el('span', { class: 'spinner small', testid: 'collect-indicator' }),
          el('span', { class: 'menu-text' }, collectingText(pipeline))],
      });
    }
    if (identity && identity.active === false) {
      return menuItem({ testid: 'run-collect', disabled: true, text: t('run.collect'), title: t('run.inactive') });
    }
    // Another identity's run holds the shared base: this one queues behind
    // it (main/tasks.js).
    return menuItem({
      testid: 'run-collect', text: t('run.collect'), onclick: startCollect,
      title: pipeline.busyWith ? t('run.busy_other', { identity: pipeline.busyWith }) : null,
    });
  }

  // "Review feedback (N)" starts nothing: the review runs from an agent
  // session, and the item says how.
  function feedbackItem(pending) {
    return el('div', { class: 'menu-item inert', role: 'menuitem', 'aria-disabled': 'true' },
      el('span', { testid: 'run-feedback' }, t('run.feedback', { n: pending })),
      el('span', { class: 'menu-tip', testid: 'run-feedback-tip' }, t('run.feedback_hint', { identity: state.active })));
  }

  function renderMenu(identity, pending) {
    const open = Boolean(state.openMenu);
    // "Stop" stops what the app started; a run started elsewhere is shown, not stopped
    const { task } = collectState();
    const running = Boolean(task && task.state === 'running');
    const busy = busyWith();
    const button = el('button', {
      class: 'menu-button', testid: 'menu-button', type: 'button',
      'aria-haspopup': 'menu', 'aria-expanded': open ? 'true' : 'false',
      title: busy.length ? busy.join('\n') : null,
      onclick: (event) => {
        event.stopPropagation();
        state.openMenu = !open;
        render();
      },
    }, busy.length
      ? el('span', { class: 'spinner small', testid: 'menu-busy' })
      : el('span', { class: 'menu-icon', 'aria-hidden': 'true' }, '\u2630'),
    t('menu.button'));
    const menu = open && el('div', {
      class: 'commands-menu', role: 'menu', testid: 'menu', onclick: (event) => event.stopPropagation(),
    },
    collectItem(identity),
    running && menuItem({ testid: 'run-stop', text: t('run.stop'), onclick: stopCollect }),
    feedbackItem(pending),
    menuItem({ testid: 'cleanup', text: t('cleanup.button'), title: t('cleanup.hint'), onclick: openCleanup }),
    menuItem({ testid: 'open-identities', text: t('menu.identities'), onclick: openIdentities }),
    menuItem({ testid: 'open-scheduler', text: t('menu.scheduler'), onclick: openScheduler }),
    menuItem({ testid: 'open-settings', text: t('menu.settings'), onclick: openSettings }));
    return el('span', { class: 'commands' }, button, menu);
  }

  function closeMenu() {
    if (!state.openMenu) return;
    state.openMenu = false;
    render();
  }

  // --- "Identities": which ones are collected (the owner, 2026-10-20) ---------
  // A switch per identity. One turned off is not collected: the app refuses
  // to queue it and tools/pipeline.py skips it. Its vacancies stay.

  function openIdentities() {
    state.identitiesPopup = { busy: null, error: null };
    render();
  }

  function closeIdentities() {
    state.identitiesPopup = null;
    render();
  }

  async function setIdentityActive(prefix, active) {
    const p = state.identitiesPopup;
    p.busy = prefix;
    p.error = null;
    render();
    try {
      const now = await api.setIdentityActive(prefix, active);
      const entry = state.identities.find((i) => i.prefix === prefix);
      if (entry) entry.active = now;
    } catch (error) {
      p.error = error.message || String(error);
    } finally {
      p.busy = null;
      render();
    }
  }

  function renderIdentities() {
    const p = state.identitiesPopup;
    if (!p) return null;
    const rows = state.identities.map((identity) => {
      const active = identity.active !== false;
      return el('li', {
        class: active ? 'identity-row' : 'identity-row inactive', testid: `identity-row-${identity.prefix}`,
      },
      el('label', { class: 'identity-switch' },
        el('input', {
          type: 'checkbox', testid: `identity-active-${identity.prefix}`, checked: active,
          disabled: p.busy === identity.prefix || !identity.hasDatabase,
          title: identity.hasDatabase ? null : t('identities.no_base'),
          onchange: (event) => setIdentityActive(identity.prefix, event.target.checked),
        }),
        el('span', { class: 'identity-prefix' }, identity.prefix),
        el('span', { class: 'muted' }, identity.displayName || '')),
      el('span', { class: 'muted identity-state', testid: `identity-state-${identity.prefix}` },
        t(active ? 'identities.active' : 'identities.inactive')));
    });
    return el('div', {
      class: 'overlay', testid: 'identities-overlay',
      onclick: (event) => { if (event.target === event.currentTarget) closeIdentities(); },
    },
    el('div', { class: 'popup identities', role: 'dialog', 'aria-modal': 'true', testid: 'identities-dialog' },
      el('h2', {}, t('identities.title')),
      el('p', { class: 'muted' }, t('identities.explain')),
      el('ul', { class: 'identity-list' }, rows),
      p.error && el('p', { class: 'cleanup-error', testid: 'identities-error' }, p.error),
      el('div', { class: 'reason-actions' },
        el('button', { testid: 'identities-close', onclick: closeIdentities }, t('identities.close')))));
  }

  // --- "Settings...": the app's own settings (the owner, 2026-10-21) ------------
  // The first one: whether the task list is shown at all. Hidden, the tasks
  // run as before; neither the panel nor its tab is there. The second (task
  // 0070): "Copy URL" and "Copy CV/CL Directory Path" minimize the app, so the
  // window the copy goes into comes forward; on unless turned off.

  function readSettings() {
    try {
      return { ...DEFAULT_SETTINGS, ...(JSON.parse(localStorage.getItem(SETTINGS_KEY) || 'null') || {}) };
    } catch {
      return { ...DEFAULT_SETTINGS };
    }
  }

  function saveSetting(name, value) {
    state.settings = { ...state.settings, [name]: value };
    try {
      localStorage.setItem(SETTINGS_KEY, JSON.stringify(state.settings));
    } catch {
      // storage unavailable: the setting holds until the app restarts
    }
  }

  function openSettings() {
    state.settingsOpen = true;
    renderModals();
  }

  function closeSettings() {
    state.settingsOpen = false;
    renderModals();
  }

  function renderSettings() {
    if (!state.settingsOpen) return null;
    return el('div', {
      class: 'overlay', testid: 'settings-overlay',
      onclick: (event) => { if (event.target === event.currentTarget) closeSettings(); },
    },
    el('div', { class: 'popup settings', role: 'dialog', 'aria-modal': 'true', testid: 'settings-dialog' },
      el('h2', {}, t('settings.title')),
      el('label', { class: 'setting' },
        el('input', {
          type: 'checkbox', testid: 'setting-show-tasks', checked: state.settings.showTasks,
          onchange: (event) => {
            saveSetting('showTasks', event.target.checked);
            renderTaskPanel();
          },
        }),
        el('span', {}, t('settings.show_tasks'))),
      el('p', { class: 'muted setting-hint' }, t('settings.show_tasks_hint')),
      el('label', { class: 'setting' },
        el('input', {
          type: 'checkbox', testid: 'setting-minimize-on-copy', checked: state.settings.minimizeOnCopy,
          onchange: (event) => saveSetting('minimizeOnCopy', event.target.checked),
        }),
        el('span', {}, t('settings.minimize_on_copy'))),
      el('p', { class: 'muted setting-hint' }, t('settings.minimize_on_copy_hint')),
      el('div', { class: 'reason-actions' },
        el('button', { testid: 'settings-close', onclick: closeSettings }, t('settings.close')))));
  }

  // --- "Task scheduler...": work on a timetable (task 0061) -------------------
  // The schedules live in the queue's file (tools/schedules.py); the workers
  // queue a schedule's tasks when it is due, and they show in the panel like
  // any other. The time is a preset or a raw cron line; the next three runs
  // are shown before saving, as tools/schedules.py counts them.
  const SCHEDULE_WHAT_KEYS = {
    collect: 'scheduler.what.collect', linkedin: 'scheduler.what.linkedin', rest: 'scheduler.what.rest',
    clean: 'scheduler.what.clean', cv_batch: 'scheduler.what.cv_batch', links: 'scheduler.what.links',
  };
  const SCHEDULE_WHAT = Object.keys(SCHEDULE_WHAT_KEYS);
  const SCHEDULE_PRESET_KEYS = {
    daily: 'scheduler.preset.daily', hours: 'scheduler.preset.hours', weekly: 'scheduler.preset.weekly',
    cron: 'scheduler.preset.cron',
  };
  const SCHEDULE_PRESETS = Object.keys(SCHEDULE_PRESET_KEYS);
  const SCHEDULE_MISSED_KEYS = { catch_up: 'scheduler.missed.catch_up', skip: 'scheduler.missed.skip' };
  // cron's day numbers -> their names, shown from Monday
  const WEEKDAY_KEYS = {
    1: 'scheduler.day.1', 2: 'scheduler.day.2', 3: 'scheduler.day.3', 4: 'scheduler.day.4',
    5: 'scheduler.day.5', 6: 'scheduler.day.6', 0: 'scheduler.day.0',
  };
  const WEEK = [1, 2, 3, 4, 5, 6, 0];
  const SCHEDULE_RESULT_KEYS = {
    running: 'task.state.running', queued: 'task.state.queued', done: 'task.state.done',
    failed: 'task.state.failed', stopped: 'task.state.stopped',
  };

  function openScheduler() {
    state.scheduler = { list: null, error: null, form: null };
    renderModals();
    loadSchedules();
  }

  function closeScheduler() {
    state.scheduler = null;
    renderModals();
  }

  async function loadSchedules() {
    const s = state.scheduler;
    if (!s) return;
    try {
      s.list = await api.listSchedules();
      s.error = null;
    } catch (error) {
      s.error = error.message || String(error);
    }
    if (state.scheduler === s) renderModals();
  }

  function pad(n) {
    return String(n).padStart(2, '0');
  }

  // An ISO time -> "2026-10-22 07:00" on this computer's clock
  function localTime(iso) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso || '');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  // A cron line -> the preset that writes it, or "cron"
  function presetOf(cron) {
    const line = String(cron || '').trim();
    let m = /^(\d{1,2}) (\d{1,2}) \* \* \*$/.exec(line);
    if (m && Number(m[1]) < 60 && Number(m[2]) < 24) return { preset: 'daily', time: `${pad(m[2])}:${pad(m[1])}` };
    m = /^0 \*\/(\d{1,2}) \* \* \*$/.exec(line);
    if (m && Number(m[1]) >= 1 && Number(m[1]) <= 23) return { preset: 'hours', hours: Number(m[1]) };
    m = /^(\d{1,2}) (\d{1,2}) \* \* ([0-6](?:,[0-6])*)$/.exec(line);
    if (m && Number(m[1]) < 60 && Number(m[2]) < 24) {
      return { preset: 'weekly', time: `${pad(m[2])}:${pad(m[1])}`, days: m[3].split(',').map(Number) };
    }
    return { preset: 'cron' };
  }

  function cronOf(form) {
    const [h, m] = String(form.time || '07:00').split(':').map((v) => Number(v) || 0);
    if (form.preset === 'daily') return `${m} ${h} * * *`;
    if (form.preset === 'hours') return `0 */${form.hours} * * *`;
    if (form.preset === 'weekly') {
      return form.days.length ? `${m} ${h} * * ${[...form.days].sort((a, b) => a - b).join(',')}` : '';
    }
    return String(form.cron || '').trim();
  }

  function whenText(cron) {
    const p = presetOf(cron);
    if (p.preset === 'daily') return t('scheduler.daily_at', { time: p.time });
    if (p.preset === 'hours') return t('scheduler.every_hours', { n: p.hours });
    if (p.preset === 'weekly') {
      const days = WEEK.filter((d) => p.days.includes(d)).map((d) => t(WEEKDAY_KEYS[d])).join(', ');
      return t('scheduler.weekly_at', { days, time: p.time });
    }
    return cron;
  }

  function scheduleForm(schedule) {
    const cron = schedule ? schedule.cron : '0 7 * * *';
    const identities = schedule ? schedule.identities : ['all'];
    const args = (schedule && schedule.args) || {};
    return {
      id: schedule ? schedule.id : null,
      what: schedule ? schedule.what : 'collect',
      all: identities.includes('all'),
      identities: identities.filter((p) => p !== 'all'),
      preset: 'daily', time: '07:00', hours: 6, days: [1, 2, 3, 4, 5], cron,
      ...presetOf(cron),
      missed: schedule ? schedule.missed : 'catch_up',
      name: schedule ? schedule.name : '',
      filters: { ages: args.ages || ['older'], statuses: args.statuses || [], classes: args.classes || [] },
      enabled: schedule ? schedule.enabled : true,
      next: null, error: null, busy: false,
    };
  }

  function editSchedule(schedule) {
    state.scheduler.form = scheduleForm(schedule);
    renderModals();
    previewRuns();
  }

  let previewTimer = null;

  // The next runs of the form's line, asked a moment after the last change.
  function previewRuns() {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(async () => {
      const s = state.scheduler;
      const form = s && s.form;
      if (!form) return;
      const cron = cronOf(form);
      if (form.next && form.next.cron === cron) return;
      let next;
      try {
        next = cron ? { cron, runs: await api.nextRuns(cron) } : { cron, error: t('scheduler.no_days') };
      } catch (error) {
        next = { cron, error: String(error.message || error).replace(/^.*?taskq schedule: /, '') };
      }
      if (state.scheduler !== s || s.form !== form || cronOf(form) !== cron) return;
      form.next = next;
      renderModals();
    }, 250);
  }

  function changeForm(change) {
    Object.assign(state.scheduler.form, change, { error: null });
    renderModals();
    previewRuns();
  }

  function formProblem(form) {
    if (!form.all && !form.identities.length) return t('scheduler.no_identity');
    if (form.what === 'clean' && !(form.filters.ages.length + form.filters.statuses.length + form.filters.classes.length)) {
      return t('scheduler.clean_needs_one');
    }
    if (!form.next || form.next.error || !form.next.runs.length) return t('scheduler.no_runs');
    return null;
  }

  async function saveSchedule() {
    const s = state.scheduler;
    const form = s.form;
    form.busy = true;
    renderModals();
    try {
      await api.saveSchedule({
        id: form.id, what: form.what, identities: form.all ? ['all'] : form.identities,
        cron: cronOf(form), missed: form.missed, name: form.name.trim(), enabled: form.enabled,
        args: form.what === 'clean' ? form.filters : {},
      });
      s.form = null;
      await loadSchedules();
    } catch (error) {
      form.error = error.message || String(error);
      form.busy = false;
      renderModals();
    }
  }

  async function scheduleAction(action) {
    const s = state.scheduler;
    try {
      await action();
    } catch (error) {
      s.error = error.message || String(error);
    }
    await loadSchedules();
  }

  function renderScheduleRow(schedule) {
    const who = schedule.identities.includes('all') ? t('scheduler.all') : schedule.identities.join(', ');
    const last = schedule.last_run_at
      ? t('scheduler.last', { time: localTime(schedule.last_run_at),
        result: schedule.last_result ? t(SCHEDULE_RESULT_KEYS[schedule.last_result]) : '—' })
      : t('scheduler.never');
    return el('li', { class: schedule.enabled ? 'schedule-row' : 'schedule-row off', testid: `schedule-${schedule.id}` },
      el('input', {
        type: 'checkbox', testid: `schedule-on-${schedule.id}`, checked: schedule.enabled, title: t('scheduler.on'),
        onchange: (event) => scheduleAction(() => api.enableSchedule(schedule.id, event.target.checked)),
      }),
      el('div', { class: 'schedule-text' },
        el('div', { class: 'schedule-title' },
          schedule.name ? el('b', {}, `${schedule.name} · `) : null,
          `${t(SCHEDULE_WHAT_KEYS[schedule.what])} · ${who}`),
        el('div', { class: 'muted schedule-when', testid: `schedule-when-${schedule.id}` },
          [whenText(schedule.cron),
            schedule.next_at && t('scheduler.next', { time: localTime(schedule.next_at) }),
            t(SCHEDULE_MISSED_KEYS[schedule.missed])].filter(Boolean).join(' · ')),
        el('div', { class: 'muted schedule-last', testid: `schedule-last-${schedule.id}`, title: schedule.last_note || null },
          last)),
      el('button', { class: 'link', testid: `schedule-edit-${schedule.id}`, onclick: () => editSchedule(schedule) },
        t('scheduler.edit')),
      el('button', {
        class: 'link', testid: `schedule-remove-${schedule.id}`,
        onclick: () => scheduleAction(() => api.removeSchedule(schedule.id)),
      }, t('scheduler.remove')));
  }

  function renderScheduleForm(form) {
    const field = (label, ...body) => el('div', { class: 'schedule-field' },
      el('div', { class: 'schedule-label' }, label), el('div', { class: 'schedule-input' }, ...body));
    const checkbox = (testid, checked, onchange, text, disabled = false) => el('label', { class: 'schedule-option' },
      el('input', { type: 'checkbox', testid, checked, disabled, onchange: (event) => onchange(event.target.checked) }),
      ` ${text}`);
    const toggle = (list, value, on) => (on ? [...list, value] : list.filter((v) => v !== value));
    const time = () => el('input', {
      type: 'time', testid: 'schedule-time', value: form.time,
      onchange: (event) => changeForm({ time: event.target.value || '07:00' }),
    });
    let when = null;
    if (form.preset === 'daily') when = time();
    else if (form.preset === 'hours') {
      when = el('span', {}, el('input', {
        type: 'number', min: 1, max: 23, testid: 'schedule-hours', value: form.hours, class: 'schedule-hours',
        onchange: (event) => changeForm({ hours: Math.min(23, Math.max(1, Number(event.target.value) || 1)) }),
      }), ` ${t('scheduler.hours_unit')}`);
    } else if (form.preset === 'weekly') {
      when = el('span', { class: 'schedule-days' }, WEEK.map((d) => checkbox(`schedule-day-${d}`, form.days.includes(d),
        (on) => changeForm({ days: toggle(form.days, d, on) }), t(WEEKDAY_KEYS[d]))), ' ', time());
    } else {
      when = el('input', {
        type: 'text', testid: 'schedule-cron', value: form.cron, class: 'schedule-cron', placeholder: t('scheduler.cron_hint'),
        spellcheck: 'false',
        oninput: (event) => { form.cron = event.target.value; form.error = null; previewRuns(); },
      });
    }
    const next = form.next;
    const runs = !next ? el('span', { class: 'spinner small' })
      : next.error ? el('span', { class: 'cleanup-error' }, next.error)
        : next.runs.length ? t('scheduler.next_runs', { list: next.runs.map(localTime).join(' · ') })
          : t('scheduler.no_runs');
    const group = (key, values, label) => el('div', { class: 'schedule-filter' },
      el('span', { class: 'muted' }, `${t(CLEANUP_LEGENDS[key])}: `),
      values.map((value) => checkbox(`schedule-${key}-${value}`, form.filters[key].includes(value),
        (on) => changeForm({ filters: { ...form.filters, [key]: toggle(form.filters[key], value, on) } }), label(value))));
    const problem = formProblem(form);
    return el('div', { class: 'schedule-form', testid: 'schedule-form' },
      el('h3', {}, form.id == null ? t('scheduler.add') : t('scheduler.edit_title')),
      field(t('scheduler.what'), el('select', {
        testid: 'schedule-what', onchange: (event) => changeForm({ what: event.target.value }),
      }, SCHEDULE_WHAT.map((what) => el('option', { value: what, selected: what === form.what },
        t(SCHEDULE_WHAT_KEYS[what]))))),
      form.what === 'clean' && field(t('scheduler.clean_filters'),
        group('ages', CLEANUP_AGES, (a) => t(AGE_KEYS[a])),
        group('statuses', Object.keys(CLEANUP_STATUS_KEYS), (v) => t(CLEANUP_STATUS_KEYS[v])),
        group('classes', Object.keys(CLEANUP_CLASS_KEYS), (v) => t(CLEANUP_CLASS_KEYS[v]))),
      field(t('scheduler.identities'),
        checkbox('schedule-all', form.all, (on) => changeForm({ all: on }), t('scheduler.all')),
        state.identities.map((identity) => checkbox(`schedule-identity-${identity.prefix}`,
          form.all || form.identities.includes(identity.prefix),
          (on) => changeForm({ identities: toggle(form.identities, identity.prefix, on) }), identity.prefix, form.all))),
      field(t('scheduler.when'),
        el('select', {
          testid: 'schedule-preset',
          onchange: (event) => {
            const preset = event.target.value;
            // the raw line starts from what the preset wrote
            changeForm(preset === 'cron' ? { preset, cron: cronOf(form) } : { preset });
          },
        }, SCHEDULE_PRESETS.map((p) => el('option', { value: p, selected: p === form.preset }, t(SCHEDULE_PRESET_KEYS[p])))),
        ' ', when,
        el('div', { class: 'muted schedule-next', testid: 'schedule-next' }, runs)),
      field(t('scheduler.missed'),
        ['catch_up', 'skip'].map((value) => el('label', { class: 'schedule-option' },
          el('input', {
            type: 'radio', name: 'schedule-missed', testid: `schedule-missed-${value}`, checked: form.missed === value,
            onchange: () => changeForm({ missed: value }),
          }), ` ${t(SCHEDULE_MISSED_KEYS[value])}`))),
      field(t('scheduler.name'), el('input', {
        type: 'text', testid: 'schedule-name', value: form.name, class: 'schedule-name', maxlength: 120,
        oninput: (event) => { form.name = event.target.value; },
      })),
      form.error && el('p', { class: 'cleanup-error', testid: 'schedule-error' }, form.error),
      el('div', { class: 'popup-actions' },
        problem && next && el('span', { class: 'muted', testid: 'schedule-problem' }, problem),
        form.busy && el('span', { class: 'spinner' }),
        el('button', {
          class: 'primary', testid: 'schedule-save', disabled: form.busy || Boolean(problem), onclick: saveSchedule,
        }, t('scheduler.save')),
        el('button', {
          testid: 'schedule-cancel', disabled: form.busy,
          onclick: () => { state.scheduler.form = null; renderModals(); },
        }, t('scheduler.cancel'))));
  }

  function renderScheduler() {
    const s = state.scheduler;
    if (!s) return null;
    let body;
    if (s.form) body = renderScheduleForm(s.form);
    else if (s.list === null && !s.error) body = el('div', { class: 'loading' }, el('span', { class: 'spinner' }));
    else {
      body = el('div', {},
        s.list && s.list.length
          ? el('ul', { class: 'schedule-list', testid: 'schedule-list' }, s.list.map(renderScheduleRow))
          : el('p', { class: 'muted', testid: 'schedule-empty' }, t('scheduler.empty')),
        el('div', { class: 'popup-actions' },
          el('button', { class: 'primary', testid: 'schedule-add', onclick: () => editSchedule(null) }, t('scheduler.add')),
          el('button', { testid: 'scheduler-close', onclick: closeScheduler }, t('scheduler.close'))));
    }
    return el('div', {
      class: 'overlay', testid: 'scheduler-overlay',
      onclick: (event) => { if (event.target === event.currentTarget && !(s.form && s.form.busy)) closeScheduler(); },
    },
    el('div', { class: 'popup scheduler', role: 'dialog', 'aria-modal': 'true', testid: 'scheduler-dialog' },
      el('h2', {}, t('scheduler.title')),
      el('p', { class: 'muted' }, t('scheduler.explain')),
      s.error && el('p', { class: 'cleanup-error', testid: 'scheduler-error' }, s.error),
      body));
  }

  // --- the stop confirmation: the panel's cross (the owner, 2026-10-21) -------

  function askStop(task) {
    state.confirmStop = { id: task.id, label: taskLabel(task) };
    renderModals();
  }

  function answerStop(stop) {
    const asked = state.confirmStop;
    state.confirmStop = null;
    renderModals();
    if (stop && asked) guarded(() => api.cancelTask(asked.id));
  }

  function renderStopConfirm() {
    const asked = state.confirmStop;
    if (!asked) return null;
    return el('div', {
      class: 'overlay', testid: 'stop-overlay',
      onclick: (event) => { if (event.target === event.currentTarget) answerStop(false); },
    },
    el('div', { class: 'popup confirm', role: 'alertdialog', 'aria-modal': 'true', testid: 'stop-dialog' },
      el('p', { class: 'confirm-question' }, t('task.stop_confirm')),
      el('p', { class: 'muted' }, asked.label),
      el('div', { class: 'reason-actions' },
        el('button', { class: 'primary', testid: 'stop-yes', onclick: () => answerStop(true) }, t('task.stop_yes')),
        el('button', { testid: 'stop-no', onclick: () => answerStop(false) }, t('task.stop_no')))));
  }

  // Drawn again only when one of them changes, not with the page: a field
  // being typed in keeps its focus and caret.
  function renderModals() {
    const focused = document.activeElement;
    const testid = focused && focused.closest && focused.closest('[data-testid="modal-host"]')
      ? focused.dataset.testid : null;
    const caret = testid && typeof focused.selectionStart === 'number'
      ? [focused.selectionStart, focused.selectionEnd] : null;
    const host = document.querySelector('[data-testid="modal-host"]');
    host.replaceChildren(...[renderScheduler(), renderSettings(), renderStopConfirm()].filter(Boolean));
    const again = testid && host.querySelector(`[data-testid="${testid}"]`);
    if (again) {
      again.focus();
      if (caret) again.setSelectionRange(...caret);
    }
  }

  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    if (state.confirmStop) answerStop(false);
    else if (state.settingsOpen) closeSettings();
    else if (state.scheduler && state.scheduler.form && !state.scheduler.form.busy) {
      state.scheduler.form = null;
      renderModals();
    } else if (state.scheduler) closeScheduler();
  });

  function renderToolbar(identity, info) {
    const selection = info.selection;
    return el('div', { class: 'toolbar' },
      el('div', { class: 'identity-heading' },
        el('h1', { testid: 'identity-name' }, info.displayName || (identity && identity.displayName) || state.active),
        selection && el('span', { class: 'muted selection-caption', testid: 'selection-caption' },
          t('selection.caption', {
            id: selection.id,
            run: selection.run,
            date: String(selection.created_at || '').slice(0, 16).replace('T', ' '),
          }) + (selection.kind === 'rebuild' ? ` · ${t('selection.rebuild')}` : ''))));
  }

  // --- "Clean up": vacancies deleted for good (tools/cleanup.py) ----------------
  // The owner, 2026-10-17: old vacancies and old answers go, no shadow ban. A
  // popup over the page: the filters, a count of what would go, then the
  // deletion. Applications and feedback not yet reviewed stay whatever is
  // ticked; that is the Python side's rule, the popup only says so.
  const CLEANUP_AGES = ['today', 'week', 'month', 'older'];
  const CLEANUP_STATUS_KEYS = {
    new: 'cleanup.status.new', expired: 'cleanup.status.expired',
    rejected: 'cleanup.status.rejected', bugged: 'cleanup.status.bugged',
  };
  const CLEANUP_CLASS_KEYS = {
    hot_lead: 'cleanup.class.hot_lead', worth_a_look: 'cleanup.class.worth_a_look',
    long_shot: 'cleanup.class.long_shot', remote_unconfirmed: 'cleanup.class.remote_unconfirmed',
    engagement_unconfirmed: 'cleanup.class.engagement_unconfirmed',
    low_priority: 'cleanup.class.low_priority', rejected: 'cleanup.class.rejected',
  };
  const CLEANUP_LEGENDS = { ages: 'cleanup.ages', statuses: 'cleanup.statuses', classes: 'cleanup.classes' };

  function openCleanup() {
    state.cleanup = { ages: ['older'], statuses: [], classes: [], result: null, busy: false, error: null };
    render();
  }

  function closeCleanup() {
    state.cleanup = null;
    render();
  }

  function cleanupFilters() {
    const c = state.cleanup;
    return { ages: c.ages, statuses: c.statuses, classes: c.classes };
  }

  async function runCleanup(dryRun) {
    const c = state.cleanup;
    c.busy = true;
    c.error = null;
    render();
    try {
      const result = await api.cleanup(state.active, cleanupFilters(), dryRun);
      if (state.cleanup !== c) return;
      c.result = result;
    } catch (error) {
      if (state.cleanup !== c) return;
      c.error = error.message || String(error);
    }
    c.busy = false;
    if (!dryRun && c.result && !c.error) {
      for (const identity of state.identities) delete state.byIdentity[identity.prefix];
      await guarded(() => loadIdentity(state.active));
    }
    render();
  }

  function renderCleanup() {
    const c = state.cleanup;
    if (!c) return null;
    const group = (key, values, label) => el('fieldset', { class: 'cleanup-group', testid: `cleanup-${key}` },
      el('legend', {}, t(CLEANUP_LEGENDS[key])),
      values.map((value) => el('label', { class: 'cleanup-option' },
        el('input', {
          type: 'checkbox', testid: `cleanup-${key}-${value}`, checked: c[key].includes(value),
          disabled: c.busy,
          onchange: (event) => {
            c[key] = event.target.checked ? [...c[key], value] : c[key].filter((v) => v !== value);
            c.result = null;
            render();
          },
        }), ` ${label(value)}`)),
      el('div', { class: 'muted cleanup-any' }, t('cleanup.none_is_any')));
    const chosen = c.ages.length + c.statuses.length + c.classes.length;
    const r = c.result;
    let outcome = null;
    if (c.error) outcome = el('p', { class: 'cleanup-error', testid: 'cleanup-error' }, c.error);
    else if (r) {
      outcome = el('p', { class: 'cleanup-outcome', testid: 'cleanup-outcome' },
        t(r.dry_run ? 'cleanup.would_delete' : 'cleanup.deleted', { n: r.dry_run ? r.matched : r.deleted }),
        ' ', t('cleanup.kept', { funnel: r.kept_funnel, unreviewed: r.kept_unreviewed, other: r.kept_other_identity }));
    }
    const counted = r && r.dry_run;
    return el('div', { class: 'overlay', testid: 'cleanup-overlay',
      onclick: (event) => { if (event.target === event.currentTarget && !c.busy) closeCleanup(); } },
    el('div', { class: 'popup cleanup', role: 'dialog', 'aria-modal': 'true', testid: 'cleanup-dialog' },
      el('h2', {}, t('cleanup.title')),
      el('p', { class: 'muted' }, t('cleanup.explain')),
      el('div', { class: 'cleanup-groups' },
        group('ages', CLEANUP_AGES, (a) => t(AGE_KEYS[a])),
        group('statuses', Object.keys(CLEANUP_STATUS_KEYS), (v) => t(CLEANUP_STATUS_KEYS[v])),
        group('classes', Object.keys(CLEANUP_CLASS_KEYS), (v) => t(CLEANUP_CLASS_KEYS[v]))),
      outcome,
      el('div', { class: 'popup-actions' },
        c.busy && el('span', { class: 'spinner', testid: 'cleanup-busy' }),
        el('button', { testid: 'cleanup-count', disabled: c.busy || !chosen, onclick: () => runCleanup(true) },
          t('cleanup.count')),
        el('button', {
          class: 'danger', testid: 'cleanup-delete',
          disabled: c.busy || !chosen || !counted || !r.matched,
          onclick: () => runCleanup(false),
        }, counted ? t('cleanup.delete_n', { n: r.matched }) : t('cleanup.delete')),
        el('button', { testid: 'cleanup-close', disabled: c.busy, onclick: closeCleanup }, t('cleanup.close')))));
  }

  // "Review feedback (N)" starts nothing: the review runs in an agent session
  // the person opens, where they follow and steer it (the owner, 2026-10-07).
  // The count stays, and hovering or clicking says where to go. Not
  // `disabled`: a disabled button gets no clicks, and the click must show it.
  // --- the filters' drop-downs ---------------------------------------------------
  // An outlined box with its name on the top edge (Material's outlined field),
  // all four the same width. Not a <select>: a native list cannot wrap a long
  // option onto a second line, and the four are the same width only if a long
  // option may take two (2026-10-06). The list stays in the page while closed
  // (hidden), so what it offers can be read without opening it.
  //
  // Each is a check list (the owner, 2026-10-07): several rows at once. A
  // group's master row is on when all its rows are, partly on when some are,
  // off when none; a click turns it off from on, and on from the other two.
  // A click leaves the list open: the page redraws under it.
  //
  // groups: [{ key, label (or none), master: { text, testid } (or none),
  //   whole (the master shows on whatever the rows: the view takes all),
  //   options: [{ value, text, testid, checked }] }]
  // onToggle(group, values): the group's checked values after the click.
  // Three levels (the "Company" drop-down): `top`, { text, testid, mark,
  // toggle }, is a row above every group, and a master given its own `mark`
  // and `toggle` stands for its group whatever its rows say (a group may have
  // none); `nested` stands the groups in from the top row.
  function checklist({ testid, label, labelTestid, summary, groups, onToggle, top, nested }) {
    const id = `${testid}-select`;
    const button = el('button', {
      id, class: 'dropdown-button', testid, type: 'button',
      'aria-haspopup': 'listbox', 'aria-expanded': 'false', title: summary,
    }, el('span', { class: 'dropdown-value', testid: `${testid}-value` }, summary),
    el('span', { class: 'dropdown-arrow' }));
    const rows = [];   // { node, toggle }, top to bottom
    const row = (rowTestid, value, text, mark, master, toggle) => {
      const node = el('li', {
        role: 'option', testid: rowTestid, class: master ? 'master' : null, 'data-value': value,
        'aria-selected': mark === 'on' ? 'true' : 'false', 'data-state': mark,
        onclick: (event) => { event.stopPropagation(); choose(node); },
      }, el('span', { class: `check ${mark}`, 'aria-hidden': 'true' }), el('span', { class: 'option-text' }, text));
      rows.push({ node, toggle });
      return node;
    };
    const topNode = top && el('li', { class: 'dropdown-group', role: 'presentation' },
      el('ul', { role: 'group' }, row(top.testid, null, top.text, top.mark, true, top.toggle)));
    const groupNodes = groups.map((group) => {
      const values = group.options.map((option) => option.value);
      const checked = group.options.filter((option) => option.checked).map((option) => option.value);
      let mark = 'partial';
      if (group.whole || (values.length && checked.length === values.length)) mark = 'on';
      else if (!checked.length) mark = 'off';
      const nodes = [];
      if (group.master) {
        const { master } = group;
        if (master.mark) mark = master.mark;
        nodes.push(row(master.testid, null, master.text, mark, true,
          master.toggle || (() => onToggle(group, mark === 'on' ? [] : values))));
      }
      for (const option of group.options) {
        nodes.push(row(option.testid, option.value, option.text, option.checked ? 'on' : 'off', false,
          () => onToggle(group, values.filter((v) => (v === option.value ? !option.checked : checked.includes(v))))));
      }
      return el('li', { class: 'dropdown-group', role: 'presentation' },
        group.label && el('div', { class: 'dropdown-group-label' }, group.label),
        el('ul', { role: 'group', 'aria-label': group.label || null }, nodes));
    });
    const menu = el('ul', {
      class: nested ? 'dropdown-menu nested' : 'dropdown-menu', role: 'listbox', 'aria-multiselectable': 'true',
      testid: `${testid}-menu`, hidden: true, onclick: (event) => event.stopPropagation(),
      onscroll: () => { if (state.openDropdown === testid) state.dropdownScroll = menu.scrollTop; },
    }, topNode, groupNodes);
    const box = el('span', { class: 'field dropdown', 'data-dropdown': testid },
      button, el('label', { for: id, testid: labelTestid }, label), menu);

    const items = () => rows.map((r) => r.node);
    function setCursor(item) {
      for (const node of items()) node.classList.toggle('cursor', node === item);
      if (item) {
        state.dropdownCursor = items().indexOf(item);
        item.scrollIntoView({ block: 'nearest' });
      }
    }
    function show() {
      closeDropdowns(box);
      state.openDropdown = testid;
      menu.hidden = false;
      box.classList.add('open');
      button.setAttribute('aria-expanded', 'true');
    }
    function open() {
      show();
      state.dropdownScroll = 0;
      setCursor(menu.querySelector('[data-state="on"]') || items()[0]);
    }
    function close() {
      if (state.openDropdown === testid) state.openDropdown = null;
      menu.hidden = true;
      box.classList.remove('open');
      button.setAttribute('aria-expanded', 'false');
    }
    function choose(node) {
      setCursor(node);
      rows[items().indexOf(node)].toggle();
    }
    box.closeDropdown = close;
    // after a redraw: open again where it was
    box.reopen = (focus) => {
      show();
      menu.scrollTop = state.dropdownScroll;
      const item = items()[Math.min(state.dropdownCursor, rows.length - 1)];
      for (const node of items()) node.classList.toggle('cursor', node === item);
      if (focus) button.focus();
    };
    button.addEventListener('click', (event) => {
      event.stopPropagation();
      if (menu.hidden) open(); else close();
    });
    button.addEventListener('keydown', (event) => {
      const list = items();
      const at = list.indexOf(menu.querySelector('.cursor'));
      if (menu.hidden) {
        if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(event.key)) { event.preventDefault(); open(); }
        return;
      }
      if (event.key === 'ArrowDown') { event.preventDefault(); setCursor(list[Math.min(at + 1, list.length - 1)]); }
      else if (event.key === 'ArrowUp') { event.preventDefault(); setCursor(list[Math.max(at - 1, 0)]); }
      else if (event.key === 'Home') { event.preventDefault(); setCursor(list[0]); }
      else if (event.key === 'End') { event.preventDefault(); setCursor(list[list.length - 1]); }
      else if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        if (at >= 0) choose(list[at]);
      } else if (event.key === 'Escape') { event.stopPropagation(); close(); }
      else if (event.key === 'Tab') close();
    });
    menu.addEventListener('mousemove', (event) => {
      const item = event.target.closest('[role="option"]');
      if (item && !item.classList.contains('cursor')) {
        for (const node of items()) node.classList.toggle('cursor', node === item);
        state.dropdownCursor = items().indexOf(item);
      }
    });
    return box;
  }

  function closeDropdowns(except) {
    for (const box of document.querySelectorAll('.dropdown.open')) {
      if (box !== except) box.closeDropdown();
    }
  }

  document.addEventListener('click', () => closeDropdowns());

  // What a check list shows closed: its master's name when every row is on,
  // the rows that are when some are, "Nothing chosen" when none.
  function summaryOf(all, options) {
    const on = options.filter((option) => option.checked);
    if (on.length === options.length) return all;
    return on.length ? on.map((option) => option.label).join(', ') : t('filter.none');
  }

  function counted(label, n) {
    return `${label} ${t('filter.count', { n: n || 0 })}`;
  }

  // The markets of the selection (tabs until 2026-10-06; eight of them took a
  // line of their own). The market holding everything is the master row; the
  // others, each a part of it, are its rows. A market's name comes from the
  // identity's configuration, translated there; English when it gives no
  // translation for the current language.
  function segmentName(segment) {
    return (segment.names && segment.names[I18n.language()]) || segment.name;
  }

  function renderSegmentFilter(info, view) {
    const everything = info.segments.find((segment) => segment.everything);
    const parts = info.segments.filter((segment) => segment !== everything);
    const markets = parts.length ? parts : info.segments;
    const options = markets.map((segment) => ({
      value: segment.slug, label: segmentName(segment), text: segmentName(segment),
      testid: `segment-option-${segment.slug}`, checked: !view.segments || view.segments.includes(segment.slug),
    }));
    let all = t('filter.segment_all');
    if (markets.length === 1) all = segmentName(markets[0]);
    else if (everything) all = segmentName(everything);
    return checklist({
      testid: 'segment-filter', label: t('filter.segment_legend'), labelTestid: 'segment-label',
      summary: summaryOf(all, options),
      groups: [{
        key: 'segments', options, whole: !view.segments && options.length > 1,
        master: options.length > 1 && { text: all, testid: 'segment-option-all' },
      }],
      onToggle: (group, values) => changeView({ segments: values.length === options.length ? null : values }),
    });
  }

  // How fresh, and which statuses, each row with how many it holds: the
  // statuses counted under the chosen freshness, the freshness under the
  // chosen statuses.
  function renderShowFilter(view) {
    const { counts } = state;
    const option = (value, n, checked) => ({
      value, label: t(FILTER_KEYS[value]), text: counted(t(FILTER_KEYS[value]), n),
      testid: `filter-option-${value}`, checked,
    });
    const sum = (values, of) => values.reduce((n, value) => n + (of[value] || 0), 0);
    const freshness = {
      key: 'fresh', label: t('filter.group.freshness'),
      master: { text: counted(t('filter.all'), sum(FRESHNESS, counts.fresh)), testid: 'filter-master-fresh' },
      options: FRESHNESS.map((f) => option(f, counts.fresh[f], view.fresh.includes(f))),
    };
    const statusGroups = STATUS_GROUPS.map((group) => ({
      key: group.key, label: group.label && t(group.label),
      master: group.statuses.length > 1
        && { text: counted(t('filter.all'), sum(group.statuses, counts.statuses)), testid: `filter-master-${group.key}` },
      options: group.statuses.map((status) => option(status, counts.statuses[status], view.statuses.includes(status))),
    }));
    const parts = [];
    if (view.fresh.length === 1) parts.push(t(FILTER_KEYS[view.fresh[0]]));
    for (const group of statusGroups) {
      const on = group.options.filter((o) => o.checked);
      if (on.length && on.length === group.options.length) parts.push(group.label || on[0].label);
      else parts.push(...on.map((o) => o.label));
    }
    const nothing = !view.fresh.length || !view.statuses.length;
    return checklist({
      testid: 'filter', label: t('filter.legend'), labelTestid: 'filter-label',
      summary: nothing ? t('filter.none') : parts.join(' · '),
      groups: [freshness, ...statusGroups],
      onToggle: (group, values) => {
        if (group.key === 'fresh') return changeView({ fresh: values });
        const others = view.statuses.filter((status) => !group.options.some((o) => o.value === status));
        const chosen = new Set([...others, ...values]);
        return changeView({ statuses: STATUSES.filter((status) => chosen.has(status)) });
      },
    });
  }

  function renderFilters(info) {
    const view = currentView();
    return el('div', { class: 'filters', testid: 'filters' },
      renderSegmentFilter(info, view),
      renderShowFilter(view),
      renderAgeFilter(view),
      renderSourceFilter(view),
      renderCompanyFilter(view),
      renderFitFilter(view),
      renderTextFilter(view));
  }

  // Words to look for in the title, company, board, link, country and
  // technologies, on top of the drop-downs (the owner, 2026-10-19; WORDS in
  // schemas/queries.sql). Every word must be there; the list follows the
  // typing as it follows a click in a drop-down.
  function renderTextFilter(view) {
    const input = el('input', {
      id: 'text-filter-input', class: 'text-filter-input', type: 'search', testid: 'text-filter',
      placeholder: t('filter.text_hint'), spellcheck: 'false', autocomplete: 'off',
      oninput: (event) => changeView({ text: event.target.value }),
    });
    input.value = view.text || '';
    return el('span', { class: 'field text-filter' },
      input, el('label', { for: 'text-filter-input' }, t('filter.text_legend')));
  }

  // The panel is drawn anew on every change, the text field with it: the
  // field being typed in gets the focus and the caret back.
  function textFilterCaret() {
    const input = document.activeElement;
    if (!input || input.dataset.testid !== 'text-filter') return null;
    const { selectionStart, selectionEnd } = input;
    return {
      restore(panel) {
        const next = panel.querySelector('[data-testid="text-filter"]');
        if (!next) return;
        next.focus();
        next.setSelectionRange(selectionStart, selectionEnd);
      },
    };
  }

  // How long ago the employer posted it: today, up to a week, up to a month,
  // longer (the owner, 2026-10-17). Each band with how many it holds under
  // the other drop-downs; null in the view is every age.
  function renderAgeFilter(view) {
    const chosen = view.ages;
    const options = AGES.map((age) => ({
      value: age, label: t(AGE_KEYS[age]), text: counted(t(AGE_KEYS[age]), state.ages[age]),
      testid: `age-option-${age}`, checked: !chosen || chosen.includes(age),
    }));
    const all = AGES.reduce((sum, age) => sum + (state.ages[age] || 0), 0);
    return checklist({
      testid: 'age-filter', label: t('filter.age_legend'), labelTestid: 'age-label',
      summary: !chosen ? t('filter.age_all') : summaryOf(t('filter.age_all'), options),
      groups: [{
        key: 'ages', options, whole: !chosen,
        master: { text: counted(t('filter.age_all'), all), testid: 'age-option-all' },
      }],
      onToggle: (group, values) => changeView({ ages: values.length === AGES.length ? null : values }),
    });
  }

  // The classes ("Hot leads", "Worth a look", ...) under the other three
  // drop-downs, each with how many. The classes of every selection are
  // always listed, with 0 too (the owner, 2026-10-20: "a stable filter is
  // neither hidden nor switched off when it empties"): until then an empty
  // class left the list, a click on another row left it out of the view,
  // and its vacancies stayed hidden once they came back. Another class
  // (engagement_unconfirmed, the part-time search's) while it holds any or
  // is chosen.
  function renderFitFilter(view) {
    const chosen = view.fits;
    const totals = state.classTotals;
    const order = Object.keys(CLASS_KEYS);
    const classes = [...order, ...Object.keys(totals).filter((cls) => !order.includes(cls))]
      .filter((cls) => STABLE_CLASSES.includes(cls) || totals[cls] || (chosen && chosen.includes(cls)));
    const all = Object.values(totals).reduce((sum, n) => sum + n, 0);
    const options = classes.map((cls) => {
      const name = CLASS_KEYS[cls] ? t(CLASS_KEYS[cls]) : cls;
      return {
        value: cls, label: name, text: counted(name, totals[cls]), testid: `fit-option-${cls}`,
        checked: !chosen || chosen.includes(cls),
      };
    });
    return checklist({
      testid: 'fit-filter', label: t('filter.fit_legend'), labelTestid: 'fit-label',
      summary: !chosen ? t('filter.fit_all') : summaryOf(t('filter.fit_all'), options),
      groups: [{
        key: 'fits', options, whole: !chosen,
        master: { text: counted(t('filter.fit_all'), all), testid: 'fit-option-all' },
      }],
      onToggle: (group, values) => changeView({ fits: values.length === options.length ? null : values }),
    });
  }

  // The boards under the other three drop-downs, each with how many; a
  // chosen one stays on the list even when nothing is left from it. The view
  // keeps the boards shown; every board ticked becomes "all" (null, the ones
  // a later run brings too) only when no board known to be hidden is off the
  // list (task 0048: a hidden board the other drop-downs emptied came back
  // ticked after a click on another one).
  function renderSourceFilter(view) {
    const chosen = view.sources;
    const sources = state.sources.filter((s) => s.source);
    for (const source of chosen || []) {
      if (!sources.some((s) => s.source === source)) {
        sources.push({ source, site: (state.sourceSites || {})[source] || null, total: 0 });
      }
    }
    const all = state.sources.reduce((sum, s) => sum + s.total, 0);
    const options = sources.map((s) => ({
      value: s.source, label: s.site || s.source, text: counted(s.site || s.source, s.total),
      testid: `source-option-${s.source}`, checked: !chosen || chosen.includes(s.source),
    }));
    return checklist({
      testid: 'source-filter', label: t('filter.source_legend'), labelTestid: 'source-label',
      summary: !chosen ? t('filter.source_all') : summaryOf(t('filter.source_all'), options),
      groups: [{
        key: 'sources', options, whole: !chosen,
        master: {
          text: counted(t('filter.source_all'), all), testid: 'source-option-all',
          toggle: () => changeView({ sources: chosen ? null : [] }),
        },
      }],
      onToggle: (group, values) => {
        const known = state.seenSources[state.active] || new Set();
        const hiddenAside = [...known].some((source) => !options.some((o) => o.value === source));
        changeView({ sources: values.length === options.length && !hiddenAside ? null : values });
      },
    });
  }

  // The companies under the other four drop-downs (the owner, 2026-10-14):
  // all of them on top; under it each kind of intermediary — freelance
  // marketplaces, agencies, reposters — with each one by name beneath it,
  // and every other company as one row. The view keeps the kinds shown and
  // the names hidden, so an intermediary or a company a later run brings is
  // listed unless its kind is off.
  function renderCompanyFilter(view) {
    const chosen = view.companies || { kinds: COMPANY_KINDS, hidden: [] };
    const kindOn = (kind) => chosen.kinds.includes(kind);
    const nameOn = (name, kind) => kindOn(kind) && !chosen.hidden.includes(name);
    const rows = state.companies.slice();
    // a hidden one the view has emptied stays, to be ticked back
    for (const name of chosen.hidden) {
      const kind = state.companyKinds[name];
      if (kind && !rows.some((c) => c.name === name)) rows.push({ kind, name, total: 0 });
    }
    const totalOf = (list) => list.reduce((n, c) => n + c.total, 0);
    const kindName = (kind) => t(COMPANY_KIND_KEYS[kind]);
    const without = (list, drop) => list.filter((x) => !drop.includes(x));
    const change = (kinds, hidden) => {
      const shown = COMPANY_KINDS.filter((k) => kinds.includes(k));
      const everything = shown.length === COMPANY_KINDS.length && !hidden.length;
      changeView({ companies: everything ? null : { kinds: shown, hidden } });
    };

    const groups = [];
    const marks = [];
    for (const kind of INTERMEDIARIES) {
      const members = rows.filter((c) => c.kind === kind);
      if (!members.length && kindOn(kind)) continue;   // none in the view: no row
      const names = members.map((c) => c.name);
      const on = names.filter((name) => nameOn(name, kind));
      let mark = 'partial';
      if (!kindOn(kind) || (names.length && !on.length)) mark = 'off';
      else if (on.length === names.length) mark = 'on';
      marks.push(mark);
      groups.push({
        key: kind,
        master: {
          text: counted(kindName(kind), totalOf(members)), testid: `company-kind-${kind}`, mark,
          // on: the kind goes; off or partly on: the kind and every name of it
          toggle: () => (mark === 'on'
            ? change(without(chosen.kinds, [kind]), without(chosen.hidden, names))
            : change([...chosen.kinds, kind], without(chosen.hidden, names))),
        },
        options: members.map((c) => ({
          value: c.name, label: c.name, text: counted(c.name, c.total),
          testid: `company-option-${c.name}`, checked: nameOn(c.name, kind),
        })),
      });
    }
    const other = rows.find((c) => c.kind === 'other');
    marks.push(kindOn('other') ? 'on' : 'off');
    groups.push({
      key: 'other', options: [],
      master: {
        text: counted(kindName('other'), other ? other.total : 0), testid: 'company-kind-other',
        mark: kindOn('other') ? 'on' : 'off',
        toggle: () => change(kindOn('other') ? without(chosen.kinds, ['other']) : [...chosen.kinds, 'other'],
          chosen.hidden),
      },
    });

    // a name ticked under a kind that was off: the kind comes back with it alone
    const onToggle = (group, values) => {
      const names = group.options.map((o) => o.value);
      const hidden = [...without(chosen.hidden, names), ...without(names, values)];
      const kinds = values.length ? [...without(chosen.kinds, [group.key]), group.key] : chosen.kinds;
      change(kinds, hidden);
    };

    let topMark = 'partial';
    if (marks.every((m) => m === 'on')) topMark = 'on';
    else if (marks.every((m) => m === 'off')) topMark = 'off';
    let summary = t('filter.company_all');
    if (topMark === 'off') summary = t('filter.none');
    else if (view.companies) {
      const off = COMPANY_KINDS.filter((k) => !kindOn(k)).map(kindName);
      const hidden = chosen.hidden.filter((name) => kindOn(state.companyKinds[name]));
      summary = t('filter.company_except', { list: [...off, ...hidden].join(', ') });
    }
    return checklist({
      testid: 'company-filter', label: t('filter.company_legend'), labelTestid: 'company-label', summary,
      nested: true,
      top: {
        text: counted(t('filter.company_all'), totalOf(state.companies)), testid: 'company-option-all',
        mark: topMark,
        toggle: () => (topMark === 'on' ? change([], []) : change(COMPANY_KINDS, [])),
      },
      groups,
      onToggle,
    });
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
    if (state.listLoading) {
      return el('div', { class: 'loading', role: 'status', testid: 'list-loading' },
        el('span', { class: 'spinner' }), el('span', {}, t('app.loading')));
    }
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

  // A row that left the view stays under its stub until the list catches up
  // (answered): the list then shows as many as before, the total allowing.
  function leftUnder(cls) {
    return state.listing.some((r) => r.class === cls && (state.stubs.get(r.id) || {}).left);
  }

  function sectionCount(cls) {
    const loaded = loadedIn(cls).length;
    const shown = leftUnder(cls) ? Math.min(loaded, state.classTotals[cls] || 0) : loaded;
    const total = Math.max(state.classTotals[cls] || 0, shown);
    const hidden = hiddenIn(cls);
    if (!hidden) return t('list.shown_all', { n: total });
    const n = Math.min(PAGE, hidden);
    if (onlyFit() === cls && !state.stalled.has(cls)) return t('list.shown_scroll', { shown, total, n });
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
    const scroll = hidden > 0 && onlyFit() === cls && !state.stalled.has(cls)
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
    // The label has one width whatever the status, so "undo" and "hide" stand
    // in one column down a run of stubs (the owner, 2026-10-16).
    return el('div', { class: 'row stub', testid: `stub-${id}` },
      el('span', {},
        el('span', { class: 'stub-label', testid: 'stub-label' }, t('stub.marked', { status: t(STATUS_KEYS[stub.status]) })),
        ' · ',
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
          t('badge.manual_review')),
        // off the stack or level, let through by the screening model's read
        // against the CV (criteria stretch_roles, the owner, 2026-10-20)
        view.stretch && el('span', {
          class: 'badge stretch', testid: 'badge-stretch', title: view.stretch.reason || null,
        }, t(view.stretch.fit === 'stretch' ? 'badge.stretch' : 'badge.off_stack'))),
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
    children.push(renderDocForm(item));
    children.push(renderDocResult(item, 'cv'));
    children.push(renderDocResult(item, 'letter'));
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
    // the screening model's answer (tools/ai_screen.py), with its quote
    if (view.ai_screen && view.ai_screen.verdict) {
      const said = view.ai_screen;
      lines.push(el('li', { testid: 'details-ai' },
        `${t('row.ai')}: ${said.verdict === 'reject' ? t('row.ai_reject') : t('row.ai_keep')}`
        + (said.reason ? ` — ${said.reason}` : '') + (said.quote ? ` «${said.quote}»` : '')));
    }
    const score = renderScoreParts(view.score_parts);
    if (!lines.length && !score) return null;
    return el('details', { class: 'details' }, el('summary', {}, t('row.details')),
      lines.length ? el('ul', {}, lines) : null, score);
  }

  // "Score": what each part of the score earned out of what it could, most
  // positive first (tools/score.py, score_parts). A cell per point; the
  // minus side of every row is as wide as the widest one, so the axes line up.
  const SCORE_PART_KEYS = {
    remote_location: 'score.part.remote_location', reachability: 'score.part.reachability',
    stack: 'score.part.stack', legacy: 'score.part.legacy', intensity: 'score.part.intensity',
    compensation: 'score.part.compensation', contractor: 'score.part.contractor',
    reputation: 'score.part.reputation', company_age: 'score.part.company_age',
    market: 'score.part.market', tech: 'score.part.tech', title: 'score.part.title',
    exporter: 'score.part.exporter', stretch: 'score.part.stretch',
  };

  function renderScoreParts(parts) {
    if (!parts || !parts.length) return null;
    const signed = (n) => (n > 0 ? `+${n}` : String(n));
    const cells = (count, lit, kind, fromAxis) => {
      const list = [];
      for (let i = 0; i < count; i += 1) {
        const on = fromAxis ? i < lit : i >= count - lit;
        list.push(el('span', { class: `score-cell ${kind}${on ? '' : ' off'}` }));
      }
      return list;
    };
    const widest = Math.max(...parts.map((p) => -p.min));
    const rows = [];
    for (const part of parts) {
      const name = part.label || (SCORE_PART_KEYS[part.key] ? t(SCORE_PART_KEYS[part.key]) : part.key);
      const bound = part.points < 0 || (part.points === 0 && part.max === 0) ? part.min : part.max;
      const range = part.min < 0 && part.max > 0 ? `${signed(part.min)}…${signed(part.max)}` : signed(bound);
      rows.push(el('span', { class: 'score-label', testid: `score-label-${part.key}` }, `${name} `,
        el('span', { class: 'score-points' }, `(${signed(part.points)}/${range})`)));
      const minus = el('span', { class: 'score-side minus', style: `min-width: ${widest * 7}px` },
        cells(-part.min, Math.max(0, -part.points), 'minus', false));
      const plus = el('span', { class: 'score-side plus' },
        cells(part.max, Math.max(0, part.points), 'plus', true));
      rows.push(el('span', { class: 'score-bar', testid: `score-bar-${part.key}` },
        widest ? minus : null, el('span', { class: 'score-axis' }), plus));
    }
    return el('details', { class: 'score-parts', testid: 'score-parts' },
      el('summary', {}, t('score.summary')), el('div', { class: 'score-grid' }, rows));
  }

  // Opens the vacancy the way the operating system opens any link: in the
  // default browser, as a new tab when it is already running.
  function openLink(view) {
    if (view.url) guarded(() => api.openExternal(view.url));
  }

  // "Open", and beside it a small "Copy URL" (the owner, 2026-10-04: the link
  // is sometimes wanted elsewhere). The copy says so on the button for a
  // moment, since nothing else on screen changes.
  function openButton(item) {
    const view = viewOf(item);
    return [
      el('button', {
        class: 'open', testid: 'btn-open', disabled: !view.url, onclick: () => openLink(view),
      }, t('action.open')),
      el('button', {
        class: 'copy', testid: 'btn-copy-url', disabled: !view.url,
        onclick: (event) => copyLink(view, event.currentTarget),
      }, t('action.copy_url')),
      docButton(item, 'cv'),
      docButton(item, 'letter'),
      ...reputationButton(item),
      ...folderButtons(item),
    ];
  }

  // "Collect reputation" (the owner, 2026-10-17): the employer's reputation
  // is no longer looked up by every collection; this button looks it up for
  // the vacancy's company (main/reputation.js) and is gone once the company
  // has a result — found, or too few sources.
  function reputationButton(item) {
    const view = viewOf(item);
    if (view.reputation_collected) return [];
    const task = findTask(state.active, 'reputation', item.id);
    const label = !task ? t('action.collect_reputation')
      : task.state === 'running' ? t('action.collecting_reputation') : t('action.queued');
    const identity = state.active;
    return [el('button', {
      class: 'copy reputation', testid: 'btn-collect-reputation', disabled: Boolean(task),
      onclick: () => guarded(() => enqueue({
        kind: 'reputation', identity, vacancyId: item.id, title: view.title || '', company: view.company || '',
      })),
    }, label)];
  }

  // "Open CV/CL Directory" and "Copy CV/CL Directory Path" (the owner,
  // 2026-10-13): once the vacancy has a CV or a cover letter, its folder —
  // opened in the file manager, or its path copied, as "Open" and "Copy URL"
  // do with the link.
  function folderButtons(item) {
    const docs = state.docs[`${state.active}/${item.id}`];
    if (!docs || !(docs.cv || docs.letter)) return [];
    const identity = state.active;
    return [
      el('button', {
        class: 'copy folder', testid: 'btn-open-docs',
        onclick: () => guarded(() => api.openDocumentsDir(identity, item.id)),
      }, t('action.open_docs')),
      el('button', {
        class: 'copy', testid: 'btn-copy-docs-path',
        onclick: (event) => copyText(docs.dir, event.currentTarget, 'action.copy_docs_path'),
      }, t('action.copy_docs_path')),
    ];
  }

  // "Generate CV" (the owner, 2026-10-06): a CV tailored to this vacancy
  // (tools/cv_tailor.py). "Generate Cover Letter" beside it (2026-10-12): a
  // cover letter from the same CVs (tools/cover_letter.py). Both go into the
  // vacancy's own folder of documents, versioned (tools/documents.py). Each
  // takes a minute or three; a click queues a task (main/tasks.js), and the
  // tasks run one at a time, of either kind (app/main/cv.js says why).
  //
  // Both buttons behave alike. Like the reason of a rejection (the owner,
  // 2026-10-12): the first click opens a field for instructions to this one
  // document, the second click on the same button queues it with whatever
  // the field holds, empty included. While queued or generating the button
  // says so. Once the vacancy has the document it reads "CV is generated" /
  // "Cover letter is generated" — for good, since every vacancy has its own
  // folder (2026-10-13) — and still makes a new version when pressed.
  const DOC_KINDS = {
    cv: {
      testid: 'cv', button: 'btn-generate-cv', css: 'cv',
      generate: 'action.generate_cv', generating: 'action.generating_cv', done: 'action.cv_generated',
      failed: 'cv.failed', ready: 'cv.ready', readyPages: 'cv.ready_pages',
      instructionsTitle: 'cv.instructions_title', instructionsHint: 'cv.instructions_hint',
    },
    letter: {
      testid: 'letter', button: 'btn-generate-letter', css: 'cv letter',
      generate: 'action.generate_letter', generating: 'action.generating_letter', done: 'action.letter_generated',
      failed: 'letter.failed', ready: 'letter.ready', readyPages: 'letter.ready_pages',
      instructionsTitle: 'letter.instructions_title', instructionsHint: 'letter.instructions_hint',
    },
  };

  const sameCard = (mark, item) => Boolean(mark && mark.identity === state.active && mark.id === item.id);

  // Generate, queued, generating, or generated — the last from the
  // vacancy's folder, so it stays whatever is generated elsewhere.
  function docButton(item, kind) {
    const k = DOC_KINDS[kind];
    const task = findTask(state.active, kind, item.id);
    const docs = state.docs[`${state.active}/${item.id}`] || {};
    const done = !task && docs[kind] > 0;
    const gone = !task && !done && (docs.errors || {})[kind];
    const classes = [k.css, docFormOpen(item, kind) && 'pressed', done && 'done'].filter(Boolean).join(' ');
    const label = !task ? (done ? t(k.done) : t(k.generate))
      : task.state === 'running' ? t(k.generating) : t('action.queued');
    return el('button', {
      class: classes, testid: k.button, disabled: Boolean(task),
      title: gone || (task && task.state === 'queued' ? t('cv.queued_hint') : null),
      onclick: () => askDoc(item, kind),
    }, label);
  }

  function docFormOpen(item, kind) {
    return sameCard(state.cvFor, item) && state.cvFor.kind === kind;
  }

  function askDoc(item, kind) {
    if (findTask(state.active, kind, item.id)) return;
    if (docFormOpen(item, kind)) return generateDoc(item, kind, state.cvFor.draft || '');
    state.cvFor = { identity: state.active, id: item.id, kind, draft: '' };
    render();
  }

  // The draft lives in the state, as a reason's does: the list re-renders
  // now and then and must not wipe instructions half typed.
  function renderDocForm(item) {
    const form = state.cvFor;
    if (!sameCard(form, item)) return null;
    const k = DOC_KINDS[form.kind];
    const input = el('textarea', {
      class: 'big', testid: `${k.testid}-instructions`, rows: '4', placeholder: t(k.instructionsHint),
      oninput: (event) => { form.draft = event.target.value; },
      onkeydown: saveOnCtrlEnter(() => generateDoc(item, form.kind, input.value)),
    });
    input.value = form.draft || '';
    setTimeout(() => {
      if (document.activeElement !== input) {
        input.focus();
        input.setSelectionRange(input.value.length, input.value.length);
      }
    }, 0);
    return el('div', { class: 'step-form cv-form', testid: `${k.testid}-form` },
      el('div', { class: 'step-form-title' }, t(k.instructionsTitle)),
      input,
      el('div', { class: 'reason-actions' },
        el('button', {
          class: 'primary', testid: `${k.testid}-instructions-generate`,
          onclick: () => generateDoc(item, form.kind, input.value),
        }, t(k.generate)),
        el('button', {
          testid: `${k.testid}-instructions-cancel`, onclick: () => { state.cvFor = null; render(); },
        }, t('reason.cancel'))));
  }

  function generateDoc(item, kind, instructions) {
    const identity = state.active;
    if (findTask(identity, kind, item.id)) return;
    const view = viewOf(item);
    state.cvFor = null;
    state.cvResults.delete(`${identity}/${item.id}/${kind}`);
    guarded(() => enqueue({
      kind, identity, vacancyId: item.id, title: view.title || '', company: view.company || '',
      instructions: (instructions || '').trim(),
    }));
  }

  // What the generation produced: the files, the page count, and what to
  // look at before sending — claims the fact check could not find in the
  // CVs, the vacancy's requirements with no evidence, what came from the
  // parent CV, what was cut for length.
  function renderDocResult(item, kind) {
    const k = DOC_KINDS[kind];
    const key = `${state.active}/${item.id}/${kind}`;
    const result = state.cvResults.get(key);
    if (!result) return null;
    const id = (name) => `${k.testid}-${name}`;
    const close = el('button', {
      class: 'link', testid: id('close'), onclick: () => { state.cvResults.delete(key); render(); },
    }, t('cv.close'));
    if (!result.ok) {
      const text = `${t(k.failed)}: ${result.error === 'stopped' ? t('task.stopped') : result.error}`;
      return el('div', { class: 'cv-result failed', testid: id('result') },
        el('div', { class: 'cv-head' }, el('span', {}, text), close));
    }
    const fileButton = (file, label, testid) => file && el('button', {
      testid, onclick: () => guarded(() => api.openCvFile(file)),
    }, label);
    const report = result.report || {};
    const list = (title, items, testid) => (items && items.length
      ? el('div', { class: 'cv-list', testid },
        el('div', { class: 'cv-list-title' }, title),
        el('ul', {}, items.map((x) => el('li', {}, x))))
      : null);
    const findings = (result.findings || []).map((f) => `${f.where}: ${f.text ? `"${f.text}" — ` : ''}${f.message}`);
    return el('div', { class: 'cv-result', testid: id('result') },
      el('div', { class: 'cv-head' },
        el('span', { testid: id('summary') }, result.pages
          ? t(k.readyPages, { pages: result.pages }) : t(k.ready)),
        fileButton(result.pdf, t('cv.open_pdf'), id('open-pdf')),
        fileButton(result.docx, t('cv.open_docx'), id('open-docx')),
        (result.pdf || result.docx) && el('button', {
          testid: id('show-folder'), onclick: () => guarded(() => api.showCvFile(result.pdf || result.docx)),
        }, t('cv.show_folder')),
        close),
      list(t('cv.findings'), findings, id('findings')),
      list(t('cv.warnings'), result.warnings, id('warnings')),
      list(t('cv.gaps'), report.gaps, id('gaps')),
      list(t('cv.from_parent'), report.from_parent, id('from-parent')),
      list(t('cv.notes'), report.notes, id('notes')),
      list(t('cv.removed'), result.removed_for_length, id('removed')));
  }

  function copyLink(view, button) {
    if (view.url) copyText(view.url, button, 'action.copy_url');
  }

  function copyText(text, button, labelKey) {
    guarded(async () => {
      await api.copyText(text);
      button.textContent = t('action.copied');
      setTimeout(() => { button.textContent = t(labelKey); }, 1500);
      if (state.settings.minimizeOnCopy) await api.minimizeWindow();
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
      openButton(item),
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
      openButton(item),
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

  // The bottom panel (the owner, 2026-10-13), as an IDE's: the tasks on the
  // left, top to bottom; the log of the chosen one on the right — the
  // running one until a click chooses another. It shows while there are
  // tasks. Its height and the split are dragged by their sashes and kept.

  const TASK_STATE_ICONS = {
    queued: '○', running: null, done: '✓', failed: '✕', stopped: '■', skipped: '–', interrupted: '■',
    pending: '○',
  };
  // the tasks that run the pipeline: an identity's base changes when they end
  const PIPELINE_KINDS = new Set(['collect', 'rest', 'linkedin', 'pipeline', 'clean', 'links']);
  const TASK_KIND_KEYS = {
    collect: 'task.kind.collect', rest: 'task.kind.rest', linkedin: 'task.kind.linkedin', cv: 'task.kind.cv',
    letter: 'task.kind.letter', reputation: 'task.kind.reputation', batch: 'task.kind.batch',
    pipeline: 'task.kind.pipeline', clean: 'task.kind.clean', links: 'task.kind.links',
  };
  // who added a task, when not this app (tools/taskq.py ORIGINS)
  const TASK_ORIGIN_KEYS = {
    agent: 'task.origin.agent', terminal: 'task.origin.terminal', schedule: 'task.origin.schedule',
    auto: 'task.origin.auto',
  };
  // a collection's steps (main/steps.js); a stage the app has no name for
  // shows as the pipeline wrote it
  const RUN_STEP_KEYS = {
    prepare: 'step.prepare', checklist: 'step.checklist', summary: 'step.summary',
    wait_base: 'step.wait_base', merge_linkedin: 'step.merge_linkedin',
    rescore_top: 'step.rescore_top', remote_check: 'step.remote_check',
    ai_brief: 'step.ai_brief', ai_check: 'step.ai_check',
    load: 'step.load', fetch: 'step.fetch', rescore: 'step.rescore', duplicates: 'step.duplicates',
    links: 'step.links', companies: 'step.companies', descriptions: 'step.descriptions',
    channels: 'step.channels', wikidata: 'step.wikidata', save: 'step.save',
    selection: 'step.selection', contracts: 'step.contracts',
  };
  const TASK_STATE_KEYS = {
    queued: 'task.state.queued', running: 'task.state.running', done: 'task.state.done',
    failed: 'task.state.failed', stopped: 'task.state.stopped', skipped: 'task.state.skipped',
    interrupted: 'task.state.interrupted',
  };

  function taskLabel(task) {
    const what = t(TASK_KIND_KEYS[task.kind] || 'task.kind.other', { kind: task.kind });
    if (PIPELINE_KINDS.has(task.kind)) return [what, task.identity].filter(Boolean).join(' · ');
    if (task.kind === 'batch') {
      const p = task.progress;
      return [what, task.identity, p && `${p.index || 0}/${p.total || 0}`].filter(Boolean).join(' · ');
    }
    const vacancy = [task.title, task.company].filter(Boolean).join(' — ') || task.vacancyId;
    return `${what} · ${vacancy} · ${task.identity}`;
  }

  function taskStateText(task) {
    if (task.kind === 'batch') return batchStateText(task);
    if (task.state === 'queued' && task.waitingFor) return waitText(task.waitingFor);
    if (task.state === 'failed' && task.error) return `${t('task.state.failed')}: ${task.error}`;
    return t(TASK_STATE_KEYS[task.state]);
  }

  // Why a task waits, as the queue's workers write it (tools/taskq.py plan).
  function waitText(reason) {
    const after = /^#(\w+) to end$/.exec(reason);
    if (after) {
      const other = state.tasks.find((task) => String(task.id) === after[1]);
      if (other && other.kind === 'batch') return t('task.waiting_batch');
      return t('task.wait.after', { task: other ? taskLabel(other) : `#${after[1]}` });
    }
    const limit = /^the AI usage limit; tried again at (.+)$/.exec(reason);
    if (limit) return t('task.wait.ai_limit', { time: limit[1] });
    if (reason === 'the AI usage limit; checking whether it has reset') return t('task.wait.ai_checking');
    const base = /^the base: (.+)$/.exec(reason);
    if (base) return t('task.wait.base', { holder: base[1] });
    if (reason.startsWith("the owner's sign-in: Word")) return t('task.wait.signin_desktop');
    if (reason.startsWith("the owner's sign-in: AI")) return t('task.wait.signin_ai');
    if (reason.startsWith('no worker is running')) return t('task.wait.no_worker');
    if (reason === 'the documents the app asked for') return t('task.wait.app_documents');
    return t('task.wait.other', { reason });
  }

  function batchStateText(task) {
    const p = task.progress;
    const summary = p ? t('batch.summary', { made: p.made || 0, gone: p.gone || 0, failed: p.failed || 0 }) : '';
    if (task.state === 'running') {
      if (task.stopping) return `${t('batch.stopping')} · ${summary}`;
      if (task.holding) return `${t('batch.holding')} · ${summary}`;
      const c = task.current;
      const now = c ? `${t(TASK_KIND_KEYS[c.kind])} · ${[c.title, c.company].filter(Boolean).join(' — ') || c.vacancyId}` : '';
      return [t('task.state.running'), now, summary].filter(Boolean).join(' · ');
    }
    if (task.state === 'queued' && task.waitingFor) return waitText(task.waitingFor);
    const state = task.state === 'failed' && task.error ? `${t('task.state.failed')}: ${task.error}` : t(TASK_STATE_KEYS[task.state]);
    return [state, summary].filter(Boolean).join(' · ');
  }

  function stepName(step) {
    return RUN_STEP_KEYS[step.key] ? t(RUN_STEP_KEYS[step.key]) : step.name || step.key || '?';
  }

  function stepClock(ms) {
    const seconds = Math.max(0, Math.round(ms / 1000));
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = String(seconds % 60).padStart(2, '0');
    return h ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`;
  }

  // A collection's steps under it: shown while it runs, and when opened.
  function stepRows(task) {
    if (!task.steps || !task.steps.length) return [];
    if (!(task.state === 'running' ? !state.foldedTasks.has(task.id) : state.openTasks.has(task.id))) return [];
    return task.steps.map((step, index) => el('div', {
      class: `task-step ${step.state}`, testid: `task-step-${task.id}-${index}`, 'data-state': step.state,
      title: [stepName(step), step.progress || step.note].filter(Boolean).join(' · '),
      onclick: () => chooseTask(task.id),
    },
    el('span', { class: 'task-icon' }, step.state === 'running'
      ? el('span', { class: 'spinner small' }) : TASK_STATE_ICONS[step.state]),
    el('span', { class: 'task-label' }, stepName(step),
      (step.progress || step.note) && el('span', { class: 'step-detail' }, step.progress || step.note)),
    el('span', { class: 'step-time', ...(step.began != null ? { 'data-began': String(step.began) } : {}) },
      step.began != null ? stepClock(Date.now() - step.began) : step.duration || '')));
  }

  function toggleSteps(task) {
    const set = task.state === 'running' ? state.foldedTasks : state.openTasks;
    if (set.has(task.id)) set.delete(task.id);
    else set.add(task.id);
    renderTaskPanel();
  }

  // the running steps' time, counted here between the log's lines
  setInterval(() => {
    for (const cell of document.querySelectorAll('[data-testid="task-list"] [data-began]')) {
      cell.textContent = stepClock(Date.now() - Number(cell.dataset.began));
    }
  }, 1000);

  // The tasks the list shows, in its order: the gear's two settings.
  function shownTasks() {
    const tasks = state.settings.showFinished ? state.tasks
      : state.tasks.filter((task) => ACTIVE_TASK.has(task.state));
    return state.settings.taskOrder === 'newest' ? [...tasks].reverse() : tasks;
  }

  // the chosen task, else the latest running one, else the latest shown
  function shownTaskId() {
    const tasks = state.settings.taskOrder === 'newest' ? [...shownTasks()].reverse() : shownTasks();
    const chosen = tasks.find((task) => task.id === state.chosenTask);
    if (chosen) return chosen.id;
    const running = tasks.filter((task) => task.state === 'running');
    if (running.length) return running[running.length - 1].id;
    return tasks.length ? tasks[tasks.length - 1].id : null;
  }

  function openTaskView(open) {
    if (state.taskViewOpen === open) return;
    state.taskViewOpen = open;
    renderTaskPanel();
  }

  function setTaskView(name, value) {
    saveSetting(name, value);
    renderTaskPanel();
  }

  function gearIcon() {
    const icon = el('span', { class: 'chevron', 'aria-hidden': 'true' });
    icon.innerHTML = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" '
      + 'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/>'
      + '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 '
      + '1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 '
      + '1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 '
      + '4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 '
      + '1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06'
      + '.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>';
    return icon;
  }

  // The gear's menu: drawn in the pane, under the title (the title clips
  // what overflows it).
  function renderTaskView() {
    const host = document.querySelector('[data-testid="task-view-host"]');
    if (!state.taskViewOpen) {
      host.replaceChildren();
      return;
    }
    host.replaceChildren(el('div', {
      class: 'task-view-menu', testid: 'task-view-menu', onclick: (event) => event.stopPropagation(),
    },
    el('label', {},
      el('input', {
        type: 'checkbox', testid: 'task-view-finished', checked: state.settings.showFinished,
        onchange: (event) => setTaskView('showFinished', event.target.checked),
      }),
      t('task.view_finished')),
    el('div', { class: 'task-view-sep' }),
    TASK_ORDERS.map((order) => el('label', {},
      el('input', {
        type: 'radio', name: 'task-order', testid: `task-view-order-${order}`,
        checked: state.settings.taskOrder === order,
        onchange: () => setTaskView('taskOrder', order),
      }),
      t(TASK_ORDER_KEYS[order])))));
  }

  function chooseTask(id) {
    state.chosenTask = id;
    renderTaskPanel();
  }

  function appendTaskLog(text) {
    state.taskLog.push(text);
    if (state.taskLog.length > LOG_LIMIT) state.taskLog.splice(0, state.taskLog.length - LOG_LIMIT);
    const log = document.querySelector('[data-testid="task-log"]');
    if (!log) return;
    const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 24;
    log.append(`${log.textContent ? '\n' : ''}${text}`);
    if (atBottom) log.scrollTop = log.scrollHeight;
  }

  let taskLogRequest = 0;

  function showTaskLog(id) {
    if (state.shownTask === id) return;
    state.shownTask = id;
    state.taskLog = [];
    const log = document.querySelector('[data-testid="task-log"]');
    if (log) log.textContent = '';
    if (id == null) return;
    const asked = ++taskLogRequest;
    guarded(async () => {
      const lines = await api.taskLog(id);
      if (asked !== taskLogRequest) return;
      // lines that came as events meanwhile are in the answer too
      state.taskLog = lines.slice(-LOG_LIMIT);
      if (log) {
        log.textContent = state.taskLog.join('\n');
        log.scrollTop = log.scrollHeight;
      }
    });
  }

  // Folded (the owner, 2026-10-21), the panel is a tab out of the window's
  // bottom edge; the setting "Show the task list" off, neither is shown. The
  // tasks run either way.
  function renderTaskTab() {
    const tab = document.querySelector('[data-testid="task-tab"]');
    // shown with no tasks too, as VS Code's panel (task 0064)
    tab.hidden = !state.settings.showTasks || !state.panelFolded;
    if (tab.hidden) return;
    const active = state.tasks.filter((task) => ACTIVE_TASK.has(task.state)).length;
    tab.title = t('task.unfold');
    tab.replaceChildren(
      // the DOM's own replaceChildren writes a false as text: not el()
      ...(state.tasks.some((task) => task.state === 'running') ? [el('span', { class: 'spinner small' })] : []),
      el('span', {}, t('task.list_title', { n: active })));
  }

  function chevronDown() {
    const icon = el('span', { class: 'chevron', 'aria-hidden': 'true' });
    icon.innerHTML = '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" '
      + 'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6l4 4 4-4"/></svg>';
    return icon;
  }

  function foldTaskPanel(folded) {
    state.panelFolded = folded;
    savePanelLayout({ folded });
    renderTaskPanel();
  }

  function renderTaskPanel() {
    const panel = document.querySelector('[data-testid="task-panel"]');
    renderTaskTab();
    panel.hidden = !state.settings.showTasks || state.panelFolded;
    if (panel.hidden) return;
    const id = shownTaskId();
    const list = document.querySelector('[data-testid="task-list"]');
    const scroll = list.scrollTop;
    const tasks = shownTasks();
    if (!tasks.length) {
      list.replaceChildren(el('div', { class: 'task-empty', testid: 'task-empty' },
        t(state.tasks.length ? 'task.none_shown' : 'task.empty')));
    } else list.replaceChildren(...tasks.flatMap((task) => [el('div', {
      class: `task ${task.state}${task.id === id ? ' chosen' : ''}`,
      testid: `task-${task.id}`, 'data-state': task.state, title: taskStateText(task),
      onclick: () => chooseTask(task.id),
    },
    task.steps && task.steps.length ? el('button', {
      class: 'link task-fold', testid: 'task-fold',
      onclick: (event) => { event.stopPropagation(); toggleSteps(task); },
    }, stepRows(task).length ? '▾' : '▸') : null,
    el('span', { class: 'task-icon' }, task.state === 'running'
      ? el('span', { class: 'spinner small' }) : TASK_STATE_ICONS[task.state]),
    el('span', { class: 'task-label' }, taskLabel(task),
      TASK_ORIGIN_KEYS[task.origin] && el('span', { class: 'task-auto' }, t(TASK_ORIGIN_KEYS[task.origin])),
      task.kind === 'batch' && el('span', { class: 'step-detail' }, batchStateText(task))),
    ACTIVE_TASK.has(task.state) && !task.stopping && el('button', {
      class: 'link task-cancel', testid: 'task-cancel',
      title: task.kind === 'batch' ? t('batch.stop') : t('task.cancel'),
      onclick: (event) => { event.stopPropagation(); askStop(task); },
    }, '✕')), ...stepRows(task)]));
    list.scrollTop = scroll;
    const queued = state.tasks.filter((task) => task.state === 'queued').length;
    const finished = state.tasks.filter((task) => !ACTIVE_TASK.has(task.state)).length;
    document.querySelector('[data-testid="task-list-title"]').replaceChildren(
      el('span', {}, t('task.list_title', { n: state.tasks.length - finished })),
      el('span', { class: 'pane-actions' },
        queued > 0 && el('button', {
          class: 'link', testid: 'tasks-cancel-queued', onclick: () => guarded(() => api.cancelQueued(null)),
        }, t('task.cancel_queued', { n: queued })),
        finished > 0 && state.settings.showFinished && el('button', {
          class: 'link', testid: 'tasks-clear', onclick: () => guarded(() => api.clearTasks()),
        }, t('task.clear')),
        el('button', {
          class: `link pane-fold${state.taskViewOpen ? ' pressed' : ''}`, testid: 'task-view',
          title: t('task.view'), 'aria-label': t('task.view'), 'aria-expanded': state.taskViewOpen ? 'true' : 'false',
          onclick: (event) => { event.stopPropagation(); openTaskView(!state.taskViewOpen); },
        }, gearIcon())));
    renderTaskView();
    const shown = state.tasks.find((task) => task.id === id);
    document.querySelector('[data-testid="task-log-title"]').replaceChildren(
      el('span', { class: 'pane-caption' }, shown
        ? `${t('task.log_title')} · ${taskLabel(shown)} · ${taskStateText(shown)}` : t('task.log_title')),
      el('span', { class: 'pane-actions' },
        el('button', {
          class: 'link pane-fold', testid: 'task-panel-fold', title: t('task.fold'), 'aria-label': t('task.fold'),
          onclick: () => foldTaskPanel(true),
        }, chevronDown())));
    showTaskLog(id);
  }

  // --- the panel's sashes: its height, and the split between its panes -------

  function readPanelLayout() {
    try {
      return JSON.parse(localStorage.getItem(PANEL_KEY) || 'null') || {};
    } catch {
      return {};
    }
  }

  function savePanelLayout(layout) {
    try {
      localStorage.setItem(PANEL_KEY, JSON.stringify({ ...readPanelLayout(), ...layout }));
    } catch {
      // storage unavailable: the next start has the defaults
    }
  }

  function applyPanelLayout() {
    const layout = readPanelLayout();
    const panel = document.querySelector('[data-testid="task-panel"]');
    // 20% of the window, 220 px at least (the owner, 2026-10-13)
    const height = layout.height || Math.max(220, Math.round(window.innerHeight * 0.2));
    panel.style.height = `${clamp(height, 100, window.innerHeight - 160)}px`;
    panel.style.setProperty('--tasks-width', `${clamp(layout.split || 38, 15, 85)}%`);
  }

  function clamp(value, low, high) {
    return Math.min(Math.max(value, low), Math.max(low, high));
  }

  function dragSash(sash, onMove, onEnd) {
    sash.addEventListener('mousedown', (event) => {
      event.preventDefault();
      sash.classList.add('active');
      document.body.classList.add(sash.dataset.axis === 'x' ? 'resizing-x' : 'resizing-y');
      const move = (e) => onMove(e);
      const up = () => {
        sash.classList.remove('active');
        document.body.classList.remove('resizing-x', 'resizing-y');
        window.removeEventListener('mousemove', move);
        window.removeEventListener('mouseup', up);
        onEnd();
      };
      window.addEventListener('mousemove', move);
      window.addEventListener('mouseup', up);
    });
  }

  function setupTaskPanel() {
    const panel = document.querySelector('[data-testid="task-panel"]');
    applyPanelLayout();
    state.panelFolded = Boolean(readPanelLayout().folded);
    document.querySelector('[data-testid="task-tab"]').addEventListener('click', () => foldTaskPanel(false));
    dragSash(document.querySelector('[data-testid="task-panel-sash"]'), (event) => {
      const height = clamp(window.innerHeight - event.clientY, 100, window.innerHeight - 160);
      panel.style.height = `${height}px`;
    }, () => savePanelLayout({ height: panel.getBoundingClientRect().height }));
    dragSash(document.querySelector('[data-testid="task-split-sash"]'), (event) => {
      const box = panel.getBoundingClientRect();
      const split = clamp(((event.clientX - box.left) / box.width) * 100, 15, 85);
      panel.style.setProperty('--tasks-width', `${split}%`);
    }, () => {
      const value = parseFloat(panel.style.getPropertyValue('--tasks-width'));
      if (!Number.isNaN(value)) savePanelLayout({ split: value });
    });
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

  api.onTaskEvent(onTaskEvent);
  restoreView();
  setupTaskPanel();
  window.addEventListener('beforeunload', saveView);
  guarded(async () => {
    state.tasks = (await api.listTasks()) || [];
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
