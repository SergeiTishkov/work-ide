'use strict';
// Has the main process's own code changed since it started?
//
// "Refresh" reloads the page, and the page reloads its preload script too —
// but the main process keeps running the code it started with. On 2026-09-30
// a refreshed page asked for 'class-totals', a channel the old main process
// did not have, and the whole list failed. Refresh now compares this stamp and
// restarts the app when the main process is out of date.
const fs = require('node:fs');
const path = require('node:path');

// Code the main process loads from outside main/: the funnel rules it shares
// with the page.
const SHARED = [path.join(__dirname, '..', 'renderer', 'funnel.js')];

function codeStamp(dir = __dirname, shared = SHARED) {
  const files = fs.readdirSync(dir)
    .filter((name) => name.endsWith('.js'))
    .sort()
    .map((name) => path.join(dir, name))
    .concat(shared.filter((file) => fs.existsSync(file)));
  return files.map((file) => `${path.basename(file)}:${fs.statSync(file).mtimeMs}`).join('|');
}

// What Refresh should do: 'reload' the page, 'relaunch' the app because the
// main process runs outdated code, or 'reload-busy' — outdated, but an agent
// run started from the app is going and a restart would cut it off.
function refreshAction({ startedWith, now, agentRunning }) {
  if (now === startedWith) return 'reload';
  return agentRunning ? 'reload-busy' : 'relaunch';
}

module.exports = { codeStamp, refreshAction };
