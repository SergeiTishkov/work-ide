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
  loadSegments: (identity) => call('segments', identity),
  loadListing: (identity, segment, filter, expanded) =>
    call('listing', identity, segment, filter, expanded || []),
  classTotals: (identity, segment, filter) => call('class-totals', identity, segment, filter),
  listingCounts: (identity, segment) => call('counts', identity, segment),
  setFeedback: (identity, id, status, reason) => call('set-feedback', identity, id, status, reason ?? null),
  pendingFeedbackCount: (identity) => call('pending-feedback', identity),
  pipelineStatus: (identity) => call('pipeline-status', identity),
  getRunState: () => call('run-state'),
  startRun: (request) => call('start-run', request),
  stopRun: () => call('stop-run'),
  refresh: () => call('refresh'),
  openExternal: (url) => call('open-external', url),
  onRunEvent: (listener) => {
    const wrapped = (_event, payload) => listener(payload);
    ipcRenderer.on('run-event', wrapped);
    return () => ipcRenderer.removeListener('run-event', wrapped);
  },
});
