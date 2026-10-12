'use strict';
// "Generate CV" and "Generate Cover Letter": run tools/cv_tailor.py or
// tools/cover_letter.py for one vacancy and hand the result to the renderer.
// One generation at a time, of either kind: each tool drives Word through
// COM, and two of them at once could share one Word, whose Quit() at the end
// of one run would close the other's document.
//
// The spawn function is injected, so tests check the exact command without
// starting Python.
const path = require('node:path');
const { spawn: nodeSpawn } = require('node:child_process');

// The same rules as runner.js and identity.PREFIX_RE; a vacancy id is
// common.stable_id(): 20 hex characters, longer ids from older sources allowed.
const IDENTITY_PATTERN = /^[a-z][a-z0-9]{2,9}$/;
const VACANCY_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;
// The model call takes 1-3 minutes, Word's first start up to one more.
const TIMEOUT_MS = 20 * 60 * 1000;
// The person's instructions for one CV go on the command line, whose limit on
// Windows is 32767 characters for the whole of it.
const INSTRUCTIONS_LIMIT = 8000;
const SCRIPTS = { cv: 'cv_tailor.py', letter: 'cover_letter.py' };

function buildCvCommand(identity, vacancyId, { root, python, outDir }, instructions, kind = 'cv') {
  if (!Object.hasOwn(SCRIPTS, kind)) throw new Error(`invalid kind: ${kind}`);
  if (!IDENTITY_PATTERN.test(identity)) throw new Error(`invalid identity: ${identity}`);
  if (!VACANCY_PATTERN.test(vacancyId)) throw new Error(`invalid vacancy id: ${vacancyId}`);
  if (instructions != null && typeof instructions !== 'string') throw new Error('instructions must be text');
  const text = (instructions || '').trim();
  if (text.length > INSTRUCTIONS_LIMIT) {
    throw new Error(`the instructions are ${text.length} characters, more than ${INSTRUCTIONS_LIMIT}`);
  }
  return {
    command: python,
    args: [path.join('tools', SCRIPTS[kind]), '--identity', identity, '--vacancy', vacancyId,
      '--out-dir', outDir, '--json', ...(text ? ['--instructions', text] : [])],
    cwd: root,
  };
}

// The tool prints one JSON line last; anything before it is a log line.
function parseResult(stdout, stderr, code, script = SCRIPTS.cv) {
  const lines = String(stdout || '').split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    if (!lines[i].startsWith('{')) continue;
    try {
      return JSON.parse(lines[i]);
    } catch {
      break;
    }
  }
  const detail = String(stderr || '').trim().split(/\r?\n/).slice(-5).join('\n');
  return { ok: false, error: detail || `${script} exited with ${code}` };
}

class CvGenerator {
  constructor({ root, python, outDir, spawn = nodeSpawn, timeoutMs = TIMEOUT_MS }) {
    this.root = root;
    this.python = python;
    this.outDir = outDir;
    this.spawn = spawn;
    this.timeoutMs = timeoutMs;
    this.current = null;
    // Paths the tool reported: the only ones the renderer may ask to open.
    this.produced = new Set();
  }

  state() {
    return this.current ? { running: true, ...this.current } : { running: false };
  }

  // kind: 'cv' or 'letter'
  generate(identity, vacancyId, instructions, kind = 'cv') {
    if (this.current) return Promise.resolve({ ok: false, error: 'busy', running: this.state() });
    const { command, args, cwd } = buildCvCommand(identity, vacancyId, {
      root: this.root, python: this.python, outDir: this.outDir,
    }, instructions, kind);
    this.current = { identity, vacancyId, kind };
    return new Promise((resolve) => {
      let stdout = '';
      let stderr = '';
      let done = false;
      let child;
      const finish = (result) => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        this.current = null;
        if (result.ok) {
          for (const key of ['docx', 'pdf']) if (result[key]) this.produced.add(path.resolve(result[key]));
        }
        resolve(result);
      };
      // finish first: killing the child fires its 'close', whose exit code
      // would otherwise be the reported error
      const timer = setTimeout(() => {
        finish({ ok: false, error: `no result in ${Math.round(this.timeoutMs / 60000)} min` });
        if (child) child.kill();
      }, this.timeoutMs);
      try {
        child = this.spawn(command, args, {
          cwd, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'],
          env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
        });
      } catch (error) {
        finish({ ok: false, error: error.message });
        return;
      }
      child.stdout.on('data', (chunk) => { stdout += chunk.toString('utf8'); });
      child.stderr.on('data', (chunk) => { stderr += chunk.toString('utf8'); });
      child.on('error', (error) => finish({ ok: false, error: error.message }));
      child.on('close', (code) => finish(parseResult(stdout, stderr, code, SCRIPTS[kind])));
    });
  }

  // A file the renderer asks to open must be one this generator produced.
  checkProduced(file) {
    const resolved = path.resolve(String(file || ''));
    if (!this.produced.has(resolved)) throw new Error('not a generated CV file');
    return resolved;
  }
}

module.exports = { CvGenerator, buildCvCommand, parseResult, INSTRUCTIONS_LIMIT };
