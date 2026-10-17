'use strict';
// "Generate CV" and "Generate Cover Letter": run tools/cv_tailor.py or
// tools/cover_letter.py for one vacancy and hand the result to the task queue
// (tasks.js). The files go into the vacancy's folder of documents
// (tools/documents.py). One generation at a time, of either kind: each tool
// drives Word through COM, and two of them at once could share one Word,
// whose Quit() at the end of one run would close the other's document. The
// queue's documents lane keeps it so; the check here stays as a guard.
//
// The tool's progress lines (stderr) go to the task's log as they come.
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

function buildCvCommand(identity, vacancyId, { root, python, documentsDir }, instructions, kind = 'cv') {
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
      '--documents-dir', documentsDir, '--json', ...(text ? ['--instructions', text] : [])],
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
  // documentsDir: the folder of documents, or a function giving it (it is
  // asked of Python once, at the first generation)
  constructor({ root, python, documentsDir, spawn = nodeSpawn, kill = (child) => child.kill(),
    timeoutMs = TIMEOUT_MS }) {
    this.root = root;
    this.python = python;
    this.documentsDir = documentsDir;
    this.kill = kill;
    this.spawn = spawn;
    this.timeoutMs = timeoutMs;
    this.current = null;
    // Paths the tool reported: the only ones the renderer may ask to open.
    this.produced = new Set();
  }

  state() {
    if (!this.current) return { running: false };
    const { identity, vacancyId, kind } = this.current;
    return { running: true, identity, vacancyId, kind };
  }

  // For the queue: { done: Promise<result>, stop() }.
  start(identity, vacancyId, instructions, kind = 'cv', onLine = null) {
    const done = this.generate(identity, vacancyId, instructions, kind, onLine);
    return { done, stop: () => this.stop() };
  }

  stop() {
    if (this.current && this.current.child) {
      this.current.stopped = true;
      this.kill(this.current.child);
    }
  }

  // kind: 'cv' or 'letter'; onLine(text): each progress line of the tool
  async generate(identity, vacancyId, instructions, kind = 'cv', onLine = null) {
    if (this.current) return { ok: false, error: 'busy', running: this.state() };
    this.current = { identity, vacancyId, kind };
    let documentsDir;
    let command;
    let args;
    let cwd;
    try {
      documentsDir = typeof this.documentsDir === 'function' ? await this.documentsDir() : this.documentsDir;
      ({ command, args, cwd } = buildCvCommand(identity, vacancyId, {
        root: this.root, python: this.python, documentsDir,
      }, instructions, kind));
    } catch (error) {
      this.current = null;
      throw error;
    }
    return new Promise((resolve) => {
      let stdout = '';
      let stderr = '';
      let done = false;
      let child;
      const finish = (result) => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        if (this.current && this.current.stopped && !result.ok) result = { ...result, error: 'stopped' };
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
      this.current.child = child;
      let pending = '';
      child.stdout.on('data', (chunk) => { stdout += chunk.toString('utf8'); });
      child.stderr.on('data', (chunk) => {
        const text = chunk.toString('utf8');
        stderr += text;
        if (!onLine) return;
        const lines = (pending + text).split(/\r?\n/);
        pending = lines.pop();
        for (const line of lines) if (line.trim()) onLine(line);
      });
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
