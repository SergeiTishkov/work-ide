'use strict';
// The Store on a thread of its own (the owner, 2026-10-12: a click on a filter
// froze the window). node:sqlite is synchronous, and Electron's main thread
// also carries the window's input, so a query that waits on the base — a
// pipeline writing it, a slow plan — froze everything, the spinner included.
// The main process forwards each call here (store-thread.js) and stays free.
const { parentPort, workerData } = require('node:worker_threads');
const { Store } = require('./store');

// identity -> its base file, sent along with each call: the identity list is
// the main process's and may change.
let databases = {};
const store = new Store({
  schemaDir: workerData.schemaDir,
  databasePathOf: (prefix) => databases[prefix] || null,
});

parentPort.on('message', ({ id, method, args, databases: known }) => {
  if (known) databases = known;
  try {
    parentPort.postMessage({ id, ok: true, value: store[method](...args) });
  } catch (error) {
    parentPort.postMessage({ id, ok: false, error: error.message });
  }
});
