'use strict';
// window.api: the renderer's only door to the rest of the world. UI tests
// replace exactly this object with a mock, so everything the UI can cause
// passes through here.
const { contextBridge, ipcRenderer } = require('electron');

async function call(channel, ...args) {
  const reply = await ipcRenderer.invoke(channel, ...args);
  if (!reply.ok) throw new Error(reply.error);
  return reply.value;
}

contextBridge.exposeInMainWorld('api', {
  listIdentities: () => call('identities'),
  // false turns the identity off: nothing collects for it
  setIdentityActive: (identity, active) => call('set-identity-active', identity, Boolean(active)),
  loadSegments: (identity) => call('segments', identity),
  // view: { segments, statuses, fresh, sources, fits, companies, ages, text } (store.viewParams);
  // page: { shown: { class: rows }, expanded: [class] }
  loadListing: (identity, view, page) => call('listing', identity, view, page || {}),
  classTotals: (identity, view) => call('class-totals', identity, view),
  listingCounts: (identity, view) => call('counts', identity, view),
  listSources: (identity, view) => call('sources', identity, view),
  listCompanies: (identity, view) => call('companies', identity, view),
  listAges: (identity, view) => call('ages', identity, view),
  // filters: { ages, statuses, classes } (main/cleanup.js); a dry run counts
  cleanup: (identity, filters, dryRun) => call('cleanup', identity, filters, Boolean(dryRun)),
  setFeedback: (identity, id, status, reason) => call('set-feedback', identity, id, status, reason ?? null),
  advance: (identity, id, step, comment) => call('advance', identity, id, step, comment ?? ''),
  stepBack: (identity, id) => call('step-back', identity, id),
  editComment: (identity, id, kind, index, text) => call('edit-comment', identity, id, kind, index ?? null, text ?? ''),
  pendingFeedbackCount: (identity) => call('pending-feedback', identity),
  pipelineStatus: (identity) => call('pipeline-status', identity),
  refresh: () => call('refresh'),
  openExternal: (url) => call('open-external', url),
  copyText: (text) => call('copy-text', text),
  minimizeWindow: () => call('minimize-window'),
  // The task queue (main/tasks.js). request: { kind: 'collect' | 'cv' |
  // 'letter', identity, vacancyId?, title?, company?, instructions? }
  enqueueTask: (request) => call('enqueue-task', request),
  listTasks: () => call('tasks'),
  taskLog: (id) => call('task-log', id),
  cancelTask: (id) => call('cancel-task', id),
  cancelQueued: (identity) => call('cancel-queued', identity ?? null),
  clearTasks: () => call('clear-tasks'),
  // Schedules (tools/schedules.py, task 0061)
  listSchedules: () => call('schedules'),
  saveSchedule: (schedule) => call('save-schedule', schedule),
  enableSchedule: (id, on) => call('enable-schedule', id, on),
  removeSchedule: (id) => call('remove-schedule', id),
  nextRuns: (cron) => call('next-runs', cron),
  // { type: 'tasks', tasks } | { type: 'log', id, text } | { type: 'finished', task }
  onTaskEvent: (listener) => {
    const wrapped = (_event, payload) => listener(payload);
    ipcRenderer.on('task-event', wrapped);
    return () => ipcRenderer.removeListener('task-event', wrapped);
  },
  // The folder of generated documents: { id: { dir, cv, letter, errors } }
  documentsState: (identity, ids) => call('documents-state', identity, ids),
  openDocumentsDir: (identity, vacancyId) => call('open-documents-dir', identity, vacancyId),
  openCvFile: (file) => call('open-cv-file', file),
  showCvFile: (file) => call('show-cv-file', file),
});
