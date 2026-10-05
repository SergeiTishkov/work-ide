'use strict';
// Runs the Claude Code agent headless for one identity, one run at a time.
//
// One at a time because the agent edits shared code, criteria and tests:
// two agents at once would edit the same files. The spawn and kill functions
// are injected, so tests check the exact command without starting anything.
const fs = require('node:fs');
const path = require('node:path');
const { spawn: nodeSpawn, execFile } = require('node:child_process');

const KINDS = {
  collect: (identity) => `/run ${identity}`,
  feedback: (identity) => `/feedback ${identity}`,
};

// What a run from the app may do without asking: run the project's Python
// and tests, read and edit files, search the web, use the project's skills
// (source-doctor repairs a source that changed under its fetcher). Committing
// is deliberately not on the list — changes wait for the person to review
// them. The one exception is not a tool: tools/source_doctor.py publishes a
// source repair itself, and only when a maintainer runs it.
const ALLOWED_TOOLS = [
  'Bash(python:*)',
  'Bash(.venv/Scripts/python.exe:*)',
  'Bash(.venv/bin/python:*)',
  'Bash(pytest:*)',
  'Bash(git status:*)',
  'Bash(git diff:*)',
  'Bash(git log:*)',
  'Read', 'Edit', 'Write', 'Glob', 'Grep',
  'WebSearch', 'WebFetch',
  'Skill',
];

// The same rule as identity.PREFIX_RE. The identity goes into a prompt, so
// anything else is refused rather than passed on.
const IDENTITY_PATTERN = /^[a-z][a-z0-9]{2,9}$/;

function buildCommand(kind, identity, { root, claude = 'claude' }) {
  if (!KINDS[kind]) throw new Error(`unknown run kind: ${kind}`);
  if (!IDENTITY_PATTERN.test(identity)) throw new Error(`invalid identity: ${identity}`);
  return {
    command: claude,
    args: [
      '-p', KINDS[kind](identity),
      '--output-format', 'stream-json',
      '--verbose',
      '--allowedTools', ALLOWED_TOOLS.join(','),
    ],
    cwd: root,
  };
}

// One line of stream-json output -> a line for the log panel, or null.
function describeEvent(line) {
  let event;
  try {
    event = JSON.parse(line);
  } catch {
    return line.trim() || null;
  }
  if (event.type === 'assistant' && event.message && Array.isArray(event.message.content)) {
    const parts = [];
    for (const block of event.message.content) {
      if (block.type === 'text' && block.text.trim()) parts.push(block.text.trim());
      if (block.type === 'tool_use') parts.push(`> ${block.name}${summarizeInput(block.input)}`);
    }
    return parts.length ? parts.join('\n') : null;
  }
  if (event.type === 'result') {
    const cost = typeof event.total_cost_usd === 'number' ? ` ($${event.total_cost_usd.toFixed(2)})` : '';
    return `= ${event.subtype || 'result'}${cost}${event.result ? `\n${event.result}` : ''}`;
  }
  return null;
}

function summarizeInput(input) {
  if (!input) return '';
  const value = input.command || input.file_path || input.pattern || input.query || input.url;
  if (!value) return '';
  const text = String(value).replace(/\s+/g, ' ');
  return `: ${text.length > 160 ? `${text.slice(0, 157)}...` : text}`;
}

// Follows the pipeline's own log while a run is going. The agent receives a
// command's output only when the command ends, and a pipeline run takes an
// hour: without this the panel would show "> Bash: python tools/pipeline.py"
// and then nothing. tools/progress.py writes data/identities/<p>/runs/pipeline_*.log.
class PipelineLogFollower {
  constructor({ dir, since, onLine, interval = 1000 }) {
    this.dir = dir;
    this.since = since;
    this.onLine = onLine;
    this.files = new Map();   // name -> { offset, rest }
    this.timer = setInterval(() => this.poll(), interval);
  }

  poll() {
    let names;
    try {
      names = fs.readdirSync(this.dir).filter((n) => /^pipeline_.*\.log$/.test(n)).sort();
    } catch {
      return;
    }
    for (const name of names) {
      const file = path.join(this.dir, name);
      let stat;
      try {
        stat = fs.statSync(file);
      } catch {
        continue;
      }
      if (!this.files.has(name)) {
        if (stat.mtimeMs < this.since) continue;   // an older run's log
        this.files.set(name, { offset: 0, rest: '' });
      }
      const state = this.files.get(name);
      if (stat.size <= state.offset) continue;
      const fd = fs.openSync(file, 'r');
      const buffer = Buffer.alloc(stat.size - state.offset);
      fs.readSync(fd, buffer, 0, buffer.length, state.offset);
      fs.closeSync(fd);
      state.offset = stat.size;
      const lines = (state.rest + buffer.toString('utf8')).split(/\r?\n/);
      state.rest = lines.pop();
      for (const line of lines) if (line.trim()) this.onLine(line);
    }
  }

  stop() {
    clearInterval(this.timer);
    this.poll();
  }
}

function killTree(child) {
  if (process.platform === 'win32') {
    execFile('taskkill', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true }, () => {});
  } else {
    child.kill('SIGTERM');
  }
}

class Runner {
  constructor({ root, logDirOf, spawn = nodeSpawn, kill = killTree, claude = 'claude',
    followInterval = 1000 }) {
    this.followInterval = followInterval;
    this.root = root;
    this.logDirOf = logDirOf;
    this.spawn = spawn;
    this.kill = kill;
    this.claude = claude;
    this.current = null;
    this.listeners = new Set();
  }

  onEvent(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  emit(event) {
    for (const listener of this.listeners) listener(event);
  }

  state() {
    return this.current
      ? { running: true, identity: this.current.identity, kind: this.current.kind }
      : { running: false };
  }

  start(kind, identity) {
    if (this.current) {
      return { ok: false, error: 'busy', running: this.state() };
    }
    const { command, args, cwd } = buildCommand(kind, identity, { root: this.root, claude: this.claude });
    const logDir = this.logDirOf(identity);
    fs.mkdirSync(logDir, { recursive: true });
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    const log = fs.createWriteStream(path.join(logDir, `${stamp}_${kind}.log`), { flags: 'a' });

    let child;
    try {
      child = this.spawn(command, args, { cwd, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
    } catch (error) {
      log.end();
      return { ok: false, error: error.code === 'ENOENT' ? 'claude_not_found' : error.message };
    }
    const follower = new PipelineLogFollower({
      dir: logDir,
      since: Date.now() - 1000,
      onLine: (line) => this.emit({ type: 'output', text: `  | ${line}` }),
      interval: this.followInterval,
    });
    this.current = { kind, identity, child };
    this.emit({ type: 'start', kind, identity });

    let buffer = '';
    child.stdout.on('data', (chunk) => {
      log.write(chunk);
      buffer += chunk.toString('utf8');
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop();
      for (const line of lines) {
        const text = describeEvent(line);
        if (text) this.emit({ type: 'output', text });
      }
    });
    child.stderr.on('data', (chunk) => {
      log.write(chunk);
      const text = chunk.toString('utf8').trim();
      if (text) this.emit({ type: 'output', text });
    });

    let finished = false;
    const finish = (event) => {
      if (finished) return;
      finished = true;
      follower.stop();
      log.end();
      this.current = null;
      this.emit({ ...event, kind, identity });
    };
    child.on('error', (error) => finish({
      type: 'exit', code: null,
      error: error.code === 'ENOENT' ? 'claude_not_found' : error.message,
    }));
    child.on('close', (code) => finish({ type: 'exit', code }));
    return { ok: true };
  }

  stop() {
    if (!this.current) return { ok: false };
    this.kill(this.current.child);
    return { ok: true };
  }
}

module.exports = { Runner, PipelineLogFollower, buildCommand, describeEvent, ALLOWED_TOOLS };
