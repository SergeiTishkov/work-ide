'use strict';
// "Clean up": tools/cleanup.py deletes vacancies from the shared base for
// good, by age, status and class (the owner, 2026-10-17). A dry run counts
// what would go; the Python side refuses while a collection runs, and keeps
// the application funnel and feedback not yet reviewed whatever is chosen.
const path = require('node:path');
const { execFile } = require('node:child_process');

const AGES = ['today', 'week', 'month', 'older'];
const STATUSES = ['new', 'applied', 'contacted', 'interview', 'awaiting_final', 'awaiting_offer',
  'offered', 'started', 'declined', 'rejected', 'bugged', 'expired'];
const CLASSES = ['hot_lead', 'worth_a_look', 'long_shot', 'ai_unscreened', 'remote_unconfirmed',
  'engagement_unconfirmed', 'low_priority', 'rejected'];
const IDENTITY_PATTERN = /^[a-z][a-z0-9]{2,9}$/;

// The command line for one cleanup; anything outside the known values is refused.
function buildCleanupArgs(identity, filters, dryRun) {
  if (!IDENTITY_PATTERN.test(String(identity))) throw new Error(`invalid identity: ${identity}`);
  const f = filters || {};
  const args = [path.join('tools', 'cleanup.py'), '--identity', identity, '--json'];
  let chosen = 0;
  for (const [flag, values, allowed] of [['--ages', f.ages, AGES], ['--statuses', f.statuses, STATUSES],
    ['--classes', f.classes, CLASSES]]) {
    if (values == null) continue;
    if (!Array.isArray(values) || values.some((v) => !allowed.includes(v))) {
      throw new Error(`unknown ${flag.slice(2)}: ${JSON.stringify(values)}`);
    }
    if (!values.length) continue;
    args.push(flag, ...values);
    chosen += 1;
  }
  if (!chosen) throw new Error('choose at least one filter');
  if (dryRun) args.push('--dry-run');
  return args;
}

// { matched, deleted, kept_funnel, kept_unreviewed, kept_other_identity, dry_run }
function runCleanup({ root, python, identity, filters, dryRun, run = execFile }) {
  const args = buildCleanupArgs(identity, filters, dryRun);
  return new Promise((resolve, reject) => {
    run(python, args, { cwd: root, windowsHide: true, env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
      maxBuffer: 1 << 20 },
    (error, stdout, stderr) => {
      const last = String(stdout || '').trim().split(/\r?\n/).pop();
      let reply = null;
      try { reply = last ? JSON.parse(last) : null; } catch { reply = null; }
      if (reply && reply.error) reject(new Error(reply.error));
      else if (reply) resolve(reply);
      else reject(new Error(`tools/cleanup.py failed: ${String(stderr || (error && error.message) || '').trim()}`));
    });
  });
}

module.exports = { buildCleanupArgs, runCleanup, AGES, STATUSES, CLASSES };
