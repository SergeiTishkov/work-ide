'use strict';
// The rest of the base after a fast collection (the owner, 2026-10-17: the
// top vacancies first, the rest afterwards). Python alone, no agent:
// `tools/pipeline.py --identity <p> --rest`. LinkedIn's own run (the owner,
// 2026-10-20), `--linkedin`, starts the same way. Their progress lines
// ("[04:14:11] >> check links") are prefixed the way runner.js prefixes the
// pipeline's log during a collection, so steps.js reads both alike.

const { spawn: nodeSpawn } = require('node:child_process');
const path = require('node:path');

const IDENTITY_PATTERN = /^[a-z][a-z0-9]{2,9}$/;
const PROGRESS_LINE = /^\[\d\d:\d\d:\d\d\] /;

function pipelineArgs(identity, mode) {
  if (!IDENTITY_PATTERN.test(String(identity))) throw new Error(`invalid identity: ${identity}`);
  return [path.join('tools', 'pipeline.py'), '--identity', identity, mode];
}

const restArgs = (identity) => pipelineArgs(identity, '--rest');
const linkedinArgs = (identity) => pipelineArgs(identity, '--linkedin');

function restLine(line) {
  return PROGRESS_LINE.test(line) ? `  | ${line}` : line;
}

// One Python tool of the repo, its lines to onLine (the task's log); the
// reputation lookup runs through it too (reputation.js).
// -> { done: Promise<{ ok, code?, error? }>, stop() }
function startPython({ root, python, args, onLine, spawn = nodeSpawn, kill }) {
  const child = spawn(python, args, {
    cwd: root, windowsHide: true, env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
  });
  const feed = (stream) => {
    let rest = '';
    stream.setEncoding('utf8');
    stream.on('data', (chunk) => {
      const lines = (rest + chunk).split(/\r?\n/);
      rest = lines.pop();
      for (const line of lines) if (line.trim()) onLine(restLine(line));
    });
    stream.on('end', () => { if (rest.trim()) onLine(restLine(rest)); });
  };
  feed(child.stdout);
  feed(child.stderr);
  const done = new Promise((resolve) => {
    child.on('error', (error) => resolve({ ok: false, error: error.message }));
    child.on('close', (code) => resolve({ ok: code === 0, code }));
  });
  return { done, stop: () => (kill ? kill(child) : child.kill()) };
}

function startRest({ identity, ...options }) {
  return startPython({ ...options, args: restArgs(identity) });
}

function startLinkedIn({ identity, ...options }) {
  return startPython({ ...options, args: linkedinArgs(identity) });
}

module.exports = { startRest, startLinkedIn, startPython, restArgs, linkedinArgs, restLine, IDENTITY_PATTERN };
