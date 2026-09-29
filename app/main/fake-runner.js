'use strict';
// A stand-in for `claude` when WORK_IDE_FAKE_RUNNER=1: the smoke test drives
// the real window without spending tokens. Emits stream-json like the real
// CLI, then exits 0.
const { EventEmitter } = require('node:events');
const { PassThrough } = require('node:stream');

function fakeSpawn(command, args) {
  const child = new EventEmitter();
  child.pid = 0;
  child.stdout = new PassThrough();
  child.stderr = new PassThrough();
  const lines = [
    { type: 'assistant', message: { content: [{ type: 'text', text: `fake run: ${args[1]}` }] } },
    { type: 'result', subtype: 'success', total_cost_usd: 0, result: 'done' },
  ];
  setTimeout(() => {
    for (const line of lines) child.stdout.write(`${JSON.stringify(line)}\n`);
    child.stdout.end();
    child.emit('close', 0);
  }, 50);
  return child;
}

function fakeKill(child) {
  child.emit('close', null);
}

module.exports = { fakeSpawn, fakeKill };
