'use strict';
// The main process's side of store-worker.js: call(method, ...args) answers
// what Store[method](...args) would, as a promise. Calls run one at a time in
// the order sent, so an answer is written before the list that follows it is
// read. A thread that died is started again on the next call.
const path = require('node:path');
const { Worker } = require('node:worker_threads');

class StoreThread {
  // databases() -> { identity: base file } at the moment of the call
  constructor({ schemaDir, databases }) {
    this.schemaDir = schemaDir;
    this.databases = databases;
    this.worker = null;
    this.pending = new Map();
    this.nextId = 1;
  }

  start() {
    const worker = new Worker(path.join(__dirname, 'store-worker.js'), { workerData: { schemaDir: this.schemaDir } });
    worker.on('message', ({ id, ok, value, error }) => {
      const call = this.pending.get(id);
      if (!call) return;
      this.pending.delete(id);
      if (ok) call.resolve(value);
      else call.reject(new Error(error));
    });
    const fail = (error) => {
      if (this.worker === worker) this.worker = null;
      for (const call of this.pending.values()) call.reject(error);
      this.pending.clear();
    };
    worker.on('error', fail);
    worker.on('exit', (code) => fail(new Error(`the store thread stopped (${code})`)));
    this.worker = worker;
  }

  call(method, ...args) {
    if (!this.worker) this.start();
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.worker.postMessage({ id, method, args, databases: this.databases() });
    });
  }

  close() {
    if (this.worker) this.worker.terminate();
    this.worker = null;
  }
}

module.exports = { StoreThread };
