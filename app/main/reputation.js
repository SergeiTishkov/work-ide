'use strict';
// One vacancy's employer reputation on request (the owner, 2026-10-17: not
// worth the time of every collection, a button on the vacancy instead).
// Python alone: `tools/reputation_lookup.py --identity <p> --vacancy <id>`
// asks a model with web search, records the result and renders the
// company's rows again.

const path = require('node:path');
const { startPython, IDENTITY_PATTERN } = require('./rest');

const VACANCY_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;

function reputationArgs(identity, vacancyId) {
  if (!IDENTITY_PATTERN.test(String(identity))) throw new Error(`invalid identity: ${identity}`);
  if (!VACANCY_PATTERN.test(String(vacancyId))) throw new Error(`invalid vacancy id: ${vacancyId}`);
  return [path.join('tools', 'reputation_lookup.py'), '--identity', identity, '--vacancy', vacancyId];
}

// -> { done: Promise<{ ok, code?, error? }>, stop() }
function startReputation({ identity, vacancyId, ...options }) {
  return startPython({ ...options, args: reputationArgs(identity, vacancyId) });
}

module.exports = { startReputation, reputationArgs };
