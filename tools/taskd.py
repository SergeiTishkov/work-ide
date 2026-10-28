"""
The workers that run the task queue (task 0056): tools/taskq.py holds the
tasks, this runs them, outside the app.

    python tools/taskd.py install          # once, elevated (WorkIDE-Background-Setup.cmd)
    python tools/taskd.py status
    python tools/taskd.py run --role desktop   # what Task Scheduler starts
    python tools/taskd.py probe            # does `claude` answer here?
    python tools/taskd.py uninstall

TWO WORKERS, BOTH STARTED BY WINDOWS TASK SCHEDULER
---------------------------------------------------
background  at system start, "run whether the user is logged on or not"
            with no stored password (S4U). The password is never stored
            (the owner, 2026-10-21). Runs what needs no desktop: collections,
            LinkedIn, the rest of the base, clean-ups. Goes on while the
            owner is signed out or another user is active.
desktop     at the owner's sign-in, in the owner's session. Runs what needs
            the desktop — CVs and cover letters drive Word through COM — and
            anything the background worker cannot (AI, if `claude` does not
            answer under S4U: such tasks wait for the sign-in, the owner,
            2026-10-21: "if AI does not work without signing in, let it wait
            for the sign-in").

Task Scheduler restarts a worker that exits with an error (every minute)
and starts it again every five minutes if it is not running; one worker of a
role runs at a time (its row in `workers`, refreshed every POLL_SECONDS).

A RUNNING TASK
--------------
The worker starts the task's process (command()), writes its lines to the
task's log (data/tasks/<id>.log), beats for it, and records how it ended. A
stop asked in the panel kills the process tree; a CV/CL batch is asked to
stop after its current document instead. While anything runs the worker
keeps the system from sleeping on idle (SetThreadExecutionState); closing
the lid still sleeps it.

After a sleep every worker waits SLEEP_GRACE_SECONDS before declaring
another worker's task dead: all of them were asleep, and each needs a beat
to say it is alive.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_limit  # noqa: E402
import common  # noqa: E402
import taskq  # noqa: E402

ROLES = ("background", "desktop")
POLL_SECONDS = 2.0
# A gap this long between two ticks means the machine slept (or the worker
# was frozen): the beats of every process stopped alike.
GAP_SECONDS = 30.0
SLEEP_GRACE_SECONDS = taskq.STALE_AFTER_SECONDS + 15
# A CV/CL batch asked to stop ends after its current document; one document
# takes up to twenty minutes (app/main/cv.js).
GRACEFUL_STOP_SECONDS = 25 * 60
WORKER_LOG_LIMIT = 5 * 1024 * 1024
TASK_PREFIX = "WorkIDE"
TASK_NAMES = {"background": rf"{TASK_PREFIX}\Task worker (background)",
              "desktop": rf"{TASK_PREFIX}\Task worker (desktop)"}

# What the agent may do in a collection without asking (the same list the app
# used, app/main/runner.js until 2026-10-21): run the project's Python and
# tests, read and edit files, search the web, use the project's skills.
# Committing is not on the list: changes wait for the person to review them.
ALLOWED_TOOLS = [
    "Bash(python:*)",
    "Bash(.venv/Scripts/python.exe:*)",
    "Bash(.venv/bin/python:*)",
    "Bash(pytest:*)",
    "Bash(git status:*)",
    "Bash(git diff:*)",
    "Bash(git log:*)",
    "Read", "Edit", "Write", "Glob", "Grep",
    "WebSearch", "WebFetch",
    "Skill",
]
VACANCY_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
PROGRESS_LINE = re.compile(r"^\[\d\d:\d\d:\d\d\] ")
CLEAN_FILTERS = ("ages", "statuses", "classes")
INSTRUCTIONS_LIMIT = 8000


# --- what runs a task ---------------------------------------------------------------

def python_executable() -> str:
    """python.exe beside the running interpreter: the desktop worker runs
    under pythonw.exe (no console window), whose children need python.exe."""
    here = Path(sys.executable)
    console = here.with_name("python.exe")
    return str(console if here.name.lower() == "pythonw.exe" and console.exists() else here)


def claude_executable() -> Optional[str]:
    found = shutil.which("claude")
    if found:
        return found
    fallback = Path.home() / ".local" / "bin" / "claude.exe"
    return str(fallback) if fallback.exists() else None


def pipeline_line(line: str) -> str:
    """The pipeline's progress lines, prefixed the way the app's step list
    reads them (app/main/steps.js)."""
    return f"  | {line}" if PROGRESS_LINE.match(line) else line


def describe_event(line: str) -> Optional[str]:
    """One line of `claude --output-format stream-json` -> a log line, or None."""
    try:
        event = json.loads(line)
    except ValueError:
        return line.strip() or None
    if not isinstance(event, dict):
        return None
    if event.get("type") == "assistant" and isinstance((event.get("message") or {}).get("content"), list):
        parts = []
        for block in event["message"]["content"]:
            if block.get("type") == "text" and (block.get("text") or "").strip():
                parts.append(block["text"].strip())
            if block.get("type") == "tool_use":
                parts.append(f"> {block.get('name')}{_summarize(block.get('input'))}")
        return "\n".join(parts) or None
    if event.get("type") == "result":
        cost = event.get("total_cost_usd")
        cost = f" (${cost:.2f})" if isinstance(cost, (int, float)) else ""
        text = f"\n{event['result']}" if event.get("result") else ""
        return f"= {event.get('subtype') or 'result'}{cost}{text}"
    return None


def _summarize(value) -> str:
    if not isinstance(value, dict):
        return ""
    text = next((value[k] for k in ("command", "file_path", "pattern", "query", "url") if value.get(k)), None)
    if not text:
        return ""
    text = re.sub(r"\s+", " ", str(text))
    return f": {text[:157] + '...' if len(text) > 160 else text}"


def last_json(lines: Sequence[str]) -> Optional[dict]:
    for line in reversed(lines):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                return None
    return None


class Command:
    """How one task runs: the command line, how its lines read in the log,
    whether it follows the pipeline's own log, how it is stopped, what it
    adds to the environment."""

    def __init__(self, argv: List[str], *, map_line: Callable[[str], Optional[str]] = lambda s: s,
                 follow_dir: Optional[Path] = None, graceful_stop: Optional[Callable[[], None]] = None,
                 result_json: bool = False, env: Optional[Dict[str, str]] = None) -> None:
        self.argv = argv
        self.env = env or {}
        self.map_line = map_line
        self.follow_dir = follow_dir
        self.graceful_stop = graceful_stop
        self.result_json = result_json


def _identity(task: dict) -> str:
    prefix = task.get("identity") or ""
    if not taskq.PREFIX_RE.match(prefix):
        raise ValueError(f"invalid identity: {prefix!r}")
    return prefix


def _vacancy(task: dict) -> str:
    vacancy = task.get("vacancy_id") or ""
    if not VACANCY_RE.match(vacancy):
        raise ValueError(f"invalid vacancy id: {vacancy!r}")
    return vacancy


# The agent's session of a collection runs the pipeline as one foreground
# command, an hour and more (task 0088). Claude Code moves a command past its
# timeout (2 minutes unless asked) into the background, and a background
# command of `claude -p` has a time limit of its own; on 2026-10-22 the
# session ended its turn 28 s after starting the pipeline, and the pipeline
# died with it. Documented settings (code.claude.com/docs/en/env-vars):
# no background tasks, and a Bash timeout of 3 hours.
AGENT_ENV = {
    "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",
    "BASH_DEFAULT_TIMEOUT_MS": str(3 * 3600 * 1000),
    "BASH_MAX_TIMEOUT_MS": str(3 * 3600 * 1000),
}

# The pipeline's first and last lines (tools/pipeline.py).
PIPELINE_TASK_RE = re.compile(r"\(queue task (\d+)\)")
PIPELINE_FINISHED = "pipeline finished in"


def pipeline_task(first_line: str) -> Optional[int]:
    """The queue task a pipeline log belongs to, from its first line."""
    found = PIPELINE_TASK_RE.search(first_line or "")
    return int(found.group(1)) if found else None


def cut_off_pipeline(runs_dir: Path, task_id: int, since: float) -> Optional[str]:
    """The last line of a pipeline log of this task that never says
    "pipeline finished": the session ended and its pipeline died with it
    (task 0088). None when every log of the task finished, or there is none
    (an inactive identity starts no pipeline)."""
    try:
        files = sorted(runs_dir.glob("pipeline_*.log"))
    except OSError:
        return None
    for path in files:
        try:
            if path.stat().st_mtime < since - 1:
                continue
            lines = [line for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
                     if line.strip()]
        except OSError:
            continue
        if not lines or pipeline_task(lines[0]) != task_id:
            continue
        if not any(PIPELINE_FINISHED in line for line in lines):
            return lines[-1].strip()
    return None


def command(task: dict, *, python: Optional[str] = None, claude: Optional[str] = None) -> Command:
    """The command for a task, refused when its fields do not fit."""
    python = python or python_executable()
    kind, args = task["kind"], task.get("args") or {}
    tool = lambda name: str(Path("tools") / name)  # noqa: E731
    if kind == "collect":
        prefix = _identity(task)
        claude = claude or claude_executable()
        if not claude:
            raise RuntimeError("the `claude` command was not found (Claude Code CLI)")
        return Command([claude, "-p", f"/top {prefix}", "--output-format", "stream-json", "--verbose",
                        "--allowedTools", ",".join(ALLOWED_TOOLS)],
                       map_line=describe_event, follow_dir=common.identity_data_dir(prefix) / "runs",
                       env=AGENT_ENV)
    if kind in ("rest", "linkedin", "pipeline", "ai"):
        mode = {"rest": ["--rest"], "linkedin": ["--linkedin"], "ai": ["--ai"]}.get(kind)
        if mode is None:
            mode = ["--top"] if args.get("mode") == "top" else []
            if args.get("skip_contracts"):   # the agent checked them just before (`/run`, step 3)
                mode.append("--skip-contracts")
        elif kind == "ai" and args.get("reread"):   # the owner asked for the re-read (task 0103)
            mode = [*mode, "--reread"]
        return Command([python, tool("pipeline.py"), "--identity", _identity(task), *mode], map_line=pipeline_line)
    if kind == "clean":
        argv = [python, tool("cleanup.py"), "--identity", _identity(task), "--json"]
        for name in CLEAN_FILTERS:
            values = args.get(name) or []
            if not isinstance(values, list) or not all(isinstance(v, str) and re.match(r"^[a-z_]+$", v)
                                                       for v in values):
                raise ValueError(f"invalid {name}: {values!r}")
            if values:
                argv += [f"--{name}", *values]
        if argv[-1] == "--json":
            raise ValueError("a clean-up names at least one filter")
        return Command(argv, result_json=True)
    if kind in ("cv", "letter"):
        script = "cv_tailor.py" if kind == "cv" else "cover_letter.py"
        argv = [python, tool(script), "--identity", _identity(task), "--vacancy", _vacancy(task), "--json"]
        instructions = (args.get("instructions") or "").strip()
        if len(instructions) > INSTRUCTIONS_LIMIT:
            raise ValueError(f"the instructions are {len(instructions)} characters, more than {INSTRUCTIONS_LIMIT}")
        if instructions:
            argv += ["--instructions", instructions]
        return Command(argv, result_json=True)
    if kind == "cv_batch":
        import cv_batch
        argv = [python, tool("cv_batch.py"), _identity(task)]
        return Command(argv, graceful_stop=lambda: cv_batch.paths()["stop"].touch())
    if kind == "reputation":
        return Command([python, tool("reputation_lookup.py"), "--identity", _identity(task),
                        "--vacancy", _vacancy(task)])
    if kind == "links":
        return Command([python, tool("pipeline.py"), "--identity", _identity(task), "--links"],
                       map_line=pipeline_line)
    raise ValueError(f"no runner for the kind {kind!r}")


# --- a running process ----------------------------------------------------------------

def kill_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        os.kill(pid, 9)


class Process:
    """The task's process: its lines to on_line, as they come."""

    def __init__(self, task: dict, cmd: Command, on_line: Callable[[str], None], *,
                 popen=subprocess.Popen, kill=kill_tree, root: Optional[Path] = None) -> None:
        self.task, self.cmd, self.on_line, self.kill = task, cmd, on_line, kill
        self.lines: List[str] = []
        # the usage limit, as a line of the output said it (task 0057)
        self.limit: Optional[ai_limit.UsageLimit] = None
        self.stopping_since: Optional[float] = None
        self.forced = False
        self._lock = threading.Lock()
        env = {**os.environ, **cmd.env, "PYTHONIOENCODING": "utf-8", taskq.TASK_ENV: str(task["id"])}
        self.started = time.time()
        self.proc = popen(cmd.argv, cwd=str(root or common.ROOT), env=env, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.pid = self.proc.pid
        self._threads = [threading.Thread(target=self._read, args=(self.proc.stdout, True), daemon=True),
                         threading.Thread(target=self._read, args=(self.proc.stderr, False), daemon=True)]
        if cmd.follow_dir is not None:
            self._threads.append(threading.Thread(target=self._follow, daemon=True))
        for thread in self._threads:
            thread.start()

    def _seen(self, line: str) -> None:
        found = ai_limit.from_line(line)
        if found is not None and self.limit is None:
            self.limit = found

    def _emit(self, text: Optional[str]) -> None:
        if text:
            with self._lock:
                self.on_line(text)

    def _read(self, stream, is_stdout: bool) -> None:
        for raw in iter(stream.readline, b""):
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if not line.strip():
                continue
            self._seen(line)
            if is_stdout:
                self.lines.append(line)
                del self.lines[:-200]
                self._emit(self.cmd.map_line(line))
            else:
                self._emit(pipeline_line(line))
        stream.close()

    def _follow(self) -> None:
        """The pipeline's own log, while the agent runs it: the agent sees a
        command's output only when it ends, an hour later. Only the logs of
        this task: a LinkedIn run beside it writes to the same folder (task
        0088)."""
        offsets: Dict[Path, int] = {}
        rest: Dict[Path, str] = {}
        others: set = set()
        while True:
            alive = self.proc.poll() is None
            try:
                files = sorted(self.cmd.follow_dir.glob("pipeline_*.log"))
            except OSError:
                files = []
            for path in files:
                if path in others:
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                if path not in offsets:
                    if stat.st_mtime < self.started - 1:
                        continue
                    first = self._first_line(path)
                    if first is None:
                        continue                    # not written yet: the next round
                    if pipeline_task(first) != self.task["id"]:
                        others.add(path)
                        continue
                    offsets[path] = 0
                if stat.st_size <= offsets[path]:
                    continue
                with path.open("rb") as fh:
                    fh.seek(offsets[path])
                    chunk = fh.read()
                offsets[path] += len(chunk)
                parts = (rest.get(path, "") + chunk.decode("utf-8", errors="replace")).split("\n")
                rest[path] = parts.pop()
                for part in parts:
                    if part.strip():
                        self._seen(part)
                        self._emit(f"  | {part.rstrip()}")
            if not alive:
                return
            time.sleep(1)

    @staticmethod
    def _first_line(path: Path) -> Optional[str]:
        try:
            with path.open("rb") as fh:
                head = fh.readline()
        except OSError:
            return None
        return head.decode("utf-8", errors="replace") if head.endswith(b"\n") else None

    def cut_off(self) -> Optional[str]:
        """cut_off_pipeline for a session that runs the pipeline."""
        if self.cmd.follow_dir is None:
            return None
        return cut_off_pipeline(self.cmd.follow_dir, self.task["id"], self.started)

    def poll(self) -> Optional[int]:
        code = self.proc.poll()
        if code is None and self.stopping_since and time.monotonic() - self.stopping_since > GRACEFUL_STOP_SECONDS:
            self.force()
        if code is not None:
            for thread in self._threads:
                thread.join(timeout=5)
        return code

    def stop(self) -> None:
        if self.stopping_since is not None:
            return
        self.stopping_since = time.monotonic()
        if self.cmd.graceful_stop is not None:
            self.cmd.graceful_stop()
            self._emit("asked to stop: ends after the current document")
        else:
            self.force()

    def force(self) -> None:
        self.forced = True
        try:
            self.kill(self.pid)
        except Exception:  # noqa: BLE001 — already gone
            pass

    def outcome(self, code: int) -> tuple:
        """(state, error, result) of an ended process."""
        result = last_json(self.lines) if self.cmd.result_json else None
        if self.stopping_since is not None:
            return "stopped", "stopped", result
        if code == 0 and not (isinstance(result, dict) and result.get("ok") is False):
            return "done", None, result
        error = (result or {}).get("error") if isinstance(result, dict) else None
        return "failed", error or f"exit {code}", result


class FakeRun:
    """WORK_IDE_FAKE_RUNNER=1: a task that prints a line and ends done, for
    the app's smoke test (no agent, no tokens, no Word)."""

    def __init__(self, task: dict, on_line: Callable[[str], None]) -> None:
        self.task, self.pid = task, None
        what = f"/top {task['identity']}" if task["kind"] == "collect" else task["identity"] or ""
        on_line(f"fake {'run' if task['kind'] == 'collect' else task['kind']}: {what}")
        self.stopped = False

    def poll(self) -> Optional[int]:
        return 0

    def stop(self) -> None:
        self.stopped = True

    def force(self) -> None:
        self.stopped = True

    def outcome(self, code: int) -> tuple:
        return ("stopped", "stopped", None) if self.stopped else ("done", None, {"ok": True})


def fake_runner() -> bool:
    return os.environ.get("WORK_IDE_FAKE_RUNNER") == "1"


# --- the machine ----------------------------------------------------------------------

def keep_awake(on: bool) -> None:
    """ES_SYSTEM_REQUIRED while a task runs: no sleep on idle. A closed lid
    and the power button still sleep the machine."""
    if os.name != "nt":
        return
    import ctypes
    es_continuous, es_system_required = 0x80000000, 0x00000001
    ctypes.windll.kernel32.SetThreadExecutionState(es_continuous | (es_system_required if on else 0))


def session_id() -> Optional[int]:
    if os.name != "nt":
        return None
    import ctypes
    out = ctypes.c_ulong()
    if ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(out)):
        return out.value
    return None


def pid_alive(pid) -> bool:
    import cv_batch
    return cv_batch.pid_alive(pid)


def probe_ai(claude: Optional[str] = None, run=subprocess.run, timeout: int = 180) -> tuple:
    """(True, note) when `claude` answers here. A usage-limit answer counts
    as working: the limit is waited for apart (task 0057)."""
    claude = claude or claude_executable()
    if not claude:
        return False, "the `claude` command was not found"
    with tempfile.TemporaryDirectory() as workdir:
        try:
            done = run([claude, "-p", "Reply with the single word OK.", "--output-format", "json",
                        "--tools", "", "--no-session-persistence", "--model", "haiku"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=workdir,
                       timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f"claude: {type(exc).__name__}: {exc}"
    text = (done.stdout or "") + (done.stderr or "")
    try:
        answer = json.loads(done.stdout or "")
    except ValueError:
        answer = None
    if isinstance(answer, dict) and not answer.get("is_error"):
        return True, "claude answers"
    if ai_limit.recognise(text):
        return True, "claude answers (usage limit now)"
    return False, f"claude did not answer: {text.strip()[:300]}"


# One worker checks the limit at a time; a check that died frees this soon.
PROBE_CLAIM = timedelta(minutes=5)
# A check that got no answer for another reason (network, a timeout).
PROBE_RETRY = timedelta(minutes=30)


def probe_limit(claude: Optional[str] = None, run=subprocess.run, timeout: int = 120) -> tuple:
    """(limited, resets_at, note): one minimal `claude -p` call. limited
    False with resets_at set: no answer for another reason, look again at
    resets_at."""
    claude = claude or claude_executable()
    if not claude:
        return False, taskq.now() + PROBE_RETRY, "the `claude` command was not found"
    with tempfile.TemporaryDirectory() as workdir:
        try:
            done = run([claude, "-p", "Reply with the single word OK.", "--output-format", "json",
                        "--tools", "", "--no-session-persistence", "--model", "haiku"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=workdir,
                       timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, taskq.now() + PROBE_RETRY, f"{type(exc).__name__}: {exc}"
    try:
        ai_limit.check(done)
    except ai_limit.UsageLimit as limit:
        return True, limit.resets_at, limit.text
    try:
        answer = json.loads(done.stdout or "")
    except ValueError:
        answer = None
    if isinstance(answer, dict) and not answer.get("is_error") and (done.returncode or 0) == 0:
        return False, None, "claude answers"
    said = ((done.stdout or "") + (done.stderr or "")).strip()[:200]
    return False, taskq.now() + PROBE_RETRY, f"claude did not answer: {said}"


def base_holder() -> Optional[str]:
    """Who holds the shared base outside the queue (tools/runstate.py)."""
    try:
        import runstate
        run = runstate.current()
    except Exception:  # noqa: BLE001 — no base yet, or it is being written
        return None
    if not run:
        return None
    return f"a pipeline run of {run.get('identity') or '?'} (pid {run.get('pid')}, stage {run.get('stage') or '?'})"


# --- the worker -------------------------------------------------------------------------

class AnotherWorker(RuntimeError):
    """A worker of this role is alive already."""


class Worker:
    def __init__(self, role: str, capabilities: Sequence[str], *, note: str = "",
                 start: Optional[Callable[[dict, Callable[[str], None]], object]] = None,
                 kill: Callable[[int], None] = kill_tree, awake: Callable[[bool], None] = keep_awake,
                 holder: Callable[[], Optional[str]] = base_holder, alive: Callable[[int], bool] = pid_alive,
                 say: Optional[Callable[[str], None]] = None, wall: Callable[[], float] = time.time) -> None:
        if role not in ROLES:
            raise ValueError(f"unknown role: {role}")
        self.role, self.capabilities, self.note = role, list(capabilities), note
        if start is None:
            start = FakeRun if fake_runner() else (lambda task, on_line: Process(task, command(task), on_line, kill=kill))
        self.start = start
        self.kill, self.awake, self.holder, self.alive = kill, awake, holder, alive
        self.say = say or (lambda text: print(text, flush=True))
        self.wall = wall
        self.pid = os.getpid()
        self.running: Dict[int, object] = {}
        self.last_tick: Optional[float] = None
        self.no_sweep_until = 0.0
        self.awake_now = False
        self.probe = probe_limit
        self.probing: Optional[threading.Thread] = None
        self.probed: Optional[tuple] = None   # what the last check of the limit found
        self.schedules_at = 0.0               # when the schedules were last looked at (wall)

    def register(self) -> None:
        """Takes the role's row, or raises AnotherWorker; a task this role
        was running when it last ended is queued again."""
        with taskq.session() as conn, taskq.transaction(conn):
            row = conn.execute("SELECT pid, heartbeat_at FROM workers WHERE role = ?", (self.role,)).fetchone()
            if row and row["pid"] != self.pid and not taskq.is_stale(row["heartbeat_at"]) and self.alive(row["pid"]):
                raise AnotherWorker(f"a {self.role} worker is running already (pid {row['pid']})")
            conn.execute(
                "INSERT INTO workers (role, pid, host, session, capabilities, started_at, heartbeat_at, note) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(role) DO UPDATE SET pid = excluded.pid, "
                "host = excluded.host, session = excluded.session, capabilities = excluded.capabilities, "
                "started_at = excluded.started_at, heartbeat_at = excluded.heartbeat_at, note = excluded.note",
                (self.role, self.pid, socket.gethostname(), session_id(), ",".join(self.capabilities),
                 taskq.iso(), taskq.iso(), self.note))
            for left in conn.execute("SELECT id, kind, pid FROM tasks WHERE state = 'running' AND worker = ?",
                                     (self.role,)).fetchall():
                if left["pid"]:
                    try:
                        self.kill(left["pid"])
                    except Exception:  # noqa: BLE001
                        pass
                conn.execute("UPDATE tasks SET state = 'queued', worker = NULL, pid = NULL, heartbeat_at = NULL, "
                             "started_at = NULL, error = ? WHERE id = ?",
                             (f"its {self.role} worker ended; queued again", left["id"]))
                self.say(f"#{left['id']} {left['kind']}: its worker ended; queued again")

    def unregister(self) -> None:
        with taskq.session() as conn:
            conn.execute("DELETE FROM workers WHERE role = ? AND pid = ?", (self.role, self.pid))

    def log_to(self, task: dict) -> Callable[[str], None]:
        return lambda text: taskq.append_log(task, text)

    def tick(self) -> None:
        wall = self.wall()
        if self.last_tick is not None and wall - self.last_tick > GAP_SECONDS:
            self.no_sweep_until = wall + SLEEP_GRACE_SECONDS
            self.say(f"a gap of {int(wall - self.last_tick)} s since the last beat (sleep?); "
                     f"no task is declared dead for {SLEEP_GRACE_SECONDS} s")
        self.last_tick = wall
        with taskq.session() as conn:
            conn.execute("UPDATE workers SET heartbeat_at = ? WHERE role = ? AND pid = ?",
                         (taskq.iso(), self.role, self.pid))
            taskq.beat(conn, list(self.running))
            if wall >= self.no_sweep_until:
                for line in taskq.sweep(conn, kill=self.kill):
                    self.say(line)
            for task_id, handle in list(self.running.items()):
                code = handle.poll()
                if code is not None:
                    self.finish(conn, task_id, handle, code)
                elif taskq.stop_requested(conn, task_id):
                    handle.stop()
            self.documents_hold(conn)
            self.check_ai_limit(conn)
            self.check_schedules(conn, wall)
            while True:
                task = taskq.claim(conn, self.role, self.capabilities, pid=self.pid, base_holder=self.holder)
                if task is None:
                    break
                self.begin(conn, task)
        busy = bool(self.running)
        if busy != self.awake_now:
            self.awake(busy)
            self.awake_now = busy

    def begin(self, conn, task: dict) -> None:
        log = self.log_to(task)
        log(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] started by the {self.role} worker"
            + (f" (attempt {task['attempts']})" if task["attempts"] > 1 else ""))
        try:
            handle = self.start(task, log)
        except Exception as exc:  # noqa: BLE001 — a bad task fails alone
            log(f"!! not started: {exc}")
            taskq.finish(conn, task["id"], "failed", f"not started: {exc}")
            self.say(f"#{task['id']} {task['kind']}: not started: {exc}")
            return
        taskq.beat(conn, [task["id"]], pid=getattr(handle, "pid", None))
        self.running[task["id"]] = handle
        self.say(f"#{task['id']} {task['kind']} {task['identity'] or ''}: started")

    def finish(self, conn, task_id: int, handle, code: int) -> None:
        del self.running[task_id]
        state, error, result = handle.outcome(code)
        task = taskq.get(conn, task_id)
        limit = getattr(handle, "limit", None)
        if state != "stopped" and (limit is not None or code == ai_limit.EXIT_CODE):
            # Not the task's failure: it goes back to the queue and runs again
            # after the reset, from where it stopped (the answers it got are
            # kept); every AI task waits until then (task 0057).
            until = taskq.block_ai(conn, limit.resets_at if limit else None)
            why = f"the AI usage limit; tried again at {until.astimezone():%H:%M}"
            if task is not None:
                self.log_to(task)(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] stopped at the AI usage limit; "
                                  f"queued again, AI work waits until {until.astimezone():%Y-%m-%d %H:%M}")
            taskq.requeue(conn, task_id, why)
            self.say(f"#{task_id}: the AI usage limit; queued again until {until.isoformat(timespec='minutes')}")
            return
        cut = handle.cut_off() if state == "done" and hasattr(handle, "cut_off") else None
        if cut is not None and task is not None:
            # The session ended its turn while its pipeline ran, and the
            # pipeline died with it (2026-10-22, task 10): nothing was saved.
            why = f"the session ended before its pipeline; the pipeline's log stops at: {cut}"
            if task["attempts"] < taskq.MAX_ATTEMPTS:
                self.log_to(task)(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {why}; queued again")
                taskq.requeue(conn, task_id, f"{why}; queued again")
                self.say(f"#{task_id}: the pipeline was cut off; queued again")
                return
            state, error = "failed", why
        if task is not None:
            self.log_to(task)(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] ended: {state}" + (f" ({error})" if error else ""))
        taskq.finish(conn, task_id, state, error, result)
        self.say(f"#{task_id}: {state}" + (f" ({error})" if error else ""))

    def check_schedules(self, conn, wall: float) -> None:
        """Queues the schedules that are due (tools/schedules.py, task 0061),
        every CHECK_EVERY_SECONDS. A broken schedule is said, not fatal."""
        import schedules
        if wall - self.schedules_at < schedules.CHECK_EVERY_SECONDS:
            return
        self.schedules_at = wall
        try:
            for line in schedules.run_due(conn):
                self.say(line)
        except Exception as exc:  # noqa: BLE001 - the worker goes on with its tasks
            self.say(f"schedules: {type(exc).__name__}: {exc}")

    def check_ai_limit(self, conn) -> None:
        """At the expected reset, one minimal call says whether `claude`
        answers again; until it does, the AI tasks stay queued. The call runs
        in a thread: it takes seconds, and the beats go on meanwhile. One
        worker checks at a time (`ai_probe_at`)."""
        if self.probed is not None:
            limited, resets, note = self.probed
            self.probed = None
            if limited:
                until = taskq.block_ai(conn, resets)
                self.say(f"the AI usage limit holds ({note}); checked again at {until.isoformat(timespec='minutes')}")
            elif resets is not None:   # no answer for another reason: look again later
                taskq.block_ai(conn, resets)
                self.say(f"the AI limit check got no answer ({note}); looked at again later")
            else:
                taskq.unblock_ai(conn)
                self.say("the AI usage limit has reset: the AI tasks go on")
            taskq.set_state_value(conn, "ai_probe_at", None)
            return
        if self.probing is not None and self.probing.is_alive():
            return
        if "ai" not in self.capabilities:
            return
        until = taskq.ai_block(conn)
        if until is None or until > taskq.now():
            return
        claimed = taskq.state_value(conn, "ai_probe_at")
        try:
            fresh = bool(claimed) and taskq.now() - datetime.fromisoformat(claimed) < PROBE_CLAIM
        except ValueError:
            fresh = False
        if fresh:
            return
        taskq.set_state_value(conn, "ai_probe_at", taskq.iso())

        def check() -> None:
            self.probed = self.probe()

        self.probing = threading.Thread(target=check, daemon=True)
        self.probing.start()

    def documents_hold(self, conn) -> None:
        """A CV the person asked for does not wait hours behind a batch: while
        one is queued, cv_batch.HOLD makes the batch pause between documents
        (tools/cv_batch.py), and the queue lets the CV into the slot."""
        import cv_batch
        where = cv_batch.paths()
        wanted = conn.execute("SELECT 1 FROM tasks WHERE kind IN ('cv', 'letter') AND state IN ('queued', 'running') "
                              "LIMIT 1").fetchone() is not None
        batch_here = any(getattr(h, "task", {}).get("kind") == "cv_batch" for h in self.running.values())
        if wanted and batch_here:
            where["hold"].parent.mkdir(parents=True, exist_ok=True)
            where["hold"].write_text(str(self.pid), encoding="utf-8")
        elif batch_here or not wanted:
            try:
                if where["hold"].exists() and where["hold"].read_text(encoding="utf-8").strip() == str(self.pid):
                    where["hold"].unlink()
            except OSError:
                pass
        status = cv_batch.read_status(where) or {}
        holding = bool(batch_here and status.get("state") == "running" and status.get("holding"))
        taskq.set_state_value(conn, "documents_yield", "1" if holding else None)

    def stop_all(self, why: str) -> None:
        """The worker is ending: its tasks go back to the queue."""
        with taskq.session() as conn:
            for task_id, handle in list(self.running.items()):
                handle.force()
                taskq.requeue(conn, task_id, why)
                self.running.pop(task_id, None)
        if self.awake_now:
            self.awake(False)
            self.awake_now = False


# --- the command line -----------------------------------------------------------------

def worker_log(role: str) -> Path:
    return taskq.logs_dir() / f"worker_{role}.log"


def _say_into(role: str) -> Callable[[str], None]:
    path = worker_log(role)

    def say(text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if path.exists() and path.stat().st_size > WORKER_LOG_LIMIT:
                os.replace(path, path.with_suffix(".old.log"))
        except OSError:
            pass
        line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {text}"
        with path.open("a", encoding="utf-8") as out:
            out.write(line + "\n")
        if sys.stdout is not None:
            try:
                print(line, flush=True)
            except (OSError, ValueError):
                pass
    return say


def capabilities_of(role: str, say: Callable[[str], None]) -> tuple:
    if fake_runner():
        return (["desktop", "ai"] if role == "desktop" else ["ai"]), "fake runner"
    if role == "desktop":
        claude = claude_executable()
        return (["desktop", "ai"] if claude else ["desktop"]), ("" if claude else "the `claude` command was not found")
    works, note = probe_ai()
    say(f"AI here: {note}")
    return (["ai"] if works else []), note


def idle(conn) -> bool:
    return conn.execute("SELECT 1 FROM tasks WHERE state IN ('queued', 'running') LIMIT 1").fetchone() is None


def run(role: str, idle_exit: Optional[float] = None) -> int:
    """idle_exit: end after this many seconds with nothing queued or going
    (a worker the app started itself, while Task Scheduler has none)."""
    say = _say_into(role)
    caps, note = capabilities_of(role, say)
    worker = Worker(role, caps, note=note, say=say)
    try:
        worker.register()
    except AnotherWorker as exc:
        say(str(exc))
        return 0
    say(f"{role} worker started: pid {worker.pid}, session {session_id()}, can: {', '.join(caps) or 'nothing'}")
    reprobe_at = time.time() + 3600
    idle_since = time.monotonic()
    try:
        while True:
            worker.tick()
            if idle_exit is not None:
                with taskq.session() as conn:
                    nothing = idle(conn) and not worker.running
                if not nothing:
                    idle_since = time.monotonic()
                elif time.monotonic() - idle_since > idle_exit:
                    worker.unregister()
                    say(f"{role} worker ends: nothing to do for {int(idle_exit)} s")
                    return 0
            if role == "background" and "ai" not in worker.capabilities and time.time() > reprobe_at:
                reprobe_at = time.time() + 3600
                works, note = probe_ai()
                if works:
                    worker.capabilities.append("ai")
                    with taskq.session() as conn:
                        conn.execute("UPDATE workers SET capabilities = ?, note = ? WHERE role = ?",
                                     (",".join(worker.capabilities), note, role))
                    say(f"AI here now: {note}")
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        worker.stop_all(f"its {role} worker was stopped; queued again")
        worker.unregister()
        say(f"{role} worker stopped")
        return 0
    except Exception as exc:  # noqa: BLE001 — Task Scheduler restarts a worker that fails
        say(f"{role} worker failed: {type(exc).__name__}: {exc}")
        worker.stop_all(f"its {role} worker failed; queued again")
        return 1


def start(role: str, idle_exit: Optional[float] = None) -> int:
    """Starts a worker apart from the caller and returns its pid at once (the
    app does this while Task Scheduler has no worker registered).

    The worker inherits no handle of the caller. Node starts a child with
    every inheritable handle of its parent, the pipes of Electron's own
    stdio among them: a worker spawned straight from the app held those
    pipes, and whoever waited on them (a terminal after `npm start`,
    Playwright closing the app) waited for the worker's end, up to ten
    minutes (2026-10-21). Here the worker gets only its null stdio."""
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = str(pythonw) if os.name == "nt" and pythonw.exists() else sys.executable
    argv = [exe, str(Path(__file__).resolve()), "run", "--role", role]
    if idle_exit is not None:
        argv += ["--idle-exit", str(idle_exit)]
    if os.name == "nt":
        apart = {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
    else:
        apart = {"start_new_session": True}
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, close_fds=True, cwd=str(common.ROOT), **apart)
    print(json.dumps({"pid": process.pid}))
    return 0


# --- Task Scheduler ------------------------------------------------------------------------

def _user() -> str:
    domain = os.environ.get("USERDOMAIN") or socket.gethostname()
    return f"{domain}\\{os.environ.get('USERNAME', '')}"


def task_xml(role: str, *, root: Path, python: str, user: str) -> str:
    """The scheduled task of one worker. Restart on failure every minute,
    and a start every five minutes that does nothing while it runs: a worker
    killed from outside comes back. No time limit, batteries allowed."""
    from xml.sax.saxutils import escape
    if role == "background":
        trigger = "<BootTrigger><Enabled>true</Enabled></BootTrigger>"
        principal = f"<UserId>{escape(user)}</UserId><LogonType>S4U</LogonType>"
        description = ("Work IDE: runs the task queue (collections, LinkedIn, the rest of the base) "
                       "whether the user is signed in or not. No password is stored (S4U).")
    else:
        trigger = f"<LogonTrigger><Enabled>true</Enabled><UserId>{escape(user)}</UserId></LogonTrigger>"
        principal = f"<UserId>{escape(user)}</UserId><LogonType>InteractiveToken</LogonType>"
        description = "Work IDE: runs the tasks that need the desktop (CVs and cover letters through Word)."
        python = str(Path(python).with_name("pythonw.exe")) if Path(python).with_name("pythonw.exe").exists() else python
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>{escape(description)}</Description></RegistrationInfo>
  <Triggers>
    {trigger}
    <TimeTrigger>
      <Repetition><Interval>PT5M</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>
      <StartBoundary>2026-01-01T00:00:00</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">{principal}<RunLevel>LeastPrivilege</RunLevel></Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
    <RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(python)}</Command>
      <Arguments>{escape(str(Path("tools") / "taskd.py"))} run --role {role}</Arguments>
      <WorkingDirectory>{escape(str(root))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def _schtasks(*args: str, run=subprocess.run) -> subprocess.CompletedProcess:
    return run(["schtasks", *args], capture_output=True, text=True, errors="replace",
               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def install(roles: Sequence[str], run=subprocess.run, user: Optional[str] = None) -> int:
    """user: whose session the workers run in, DOMAIN\\name. By default the
    one running this; WorkIDE-Background-Setup.cmd passes the one who
    double-clicked it, since the elevated copy may run as another
    administrator."""
    python = python_executable()
    user = user or _user()
    failed = False
    for role in roles:
        with tempfile.TemporaryDirectory() as tmp:
            xml = Path(tmp) / f"{role}.xml"
            xml.write_text(task_xml(role, root=common.ROOT, python=python, user=user), encoding="utf-16")
            done = _schtasks("/Create", "/TN", TASK_NAMES[role], "/XML", str(xml), "/F", run=run)
        if done.returncode != 0:
            failed = True
            print(f"{role}: not registered: {(done.stderr or done.stdout).strip()}")
            if role == "background":
                print("  A task that runs whether the user is signed in or not (S4U) is registered "
                      "elevated: double-click WorkIDE-Background-Setup.cmd, or from a PowerShell run as "
                      "administrator (Run as administrator):\n"
                      f"  cd {common.ROOT}; .venv\\Scripts\\python tools\\taskd.py install")
            continue
        print(f"{role}: registered as '{TASK_NAMES[role]}'")
        _schtasks("/Run", "/TN", TASK_NAMES[role], run=run)
    return 1 if failed else 0


def uninstall(roles: Sequence[str], run=subprocess.run) -> int:
    code = 0
    for role in roles:
        done = _schtasks("/Delete", "/TN", TASK_NAMES[role], "/F", run=run)
        print(f"{role}: " + ("removed" if done.returncode == 0 else (done.stderr or done.stdout).strip()))
        code |= done.returncode != 0
    return code


def status() -> dict:
    out = {"scheduled": {}, "workers": []}
    for role in ROLES:
        done = _schtasks("/Query", "/TN", TASK_NAMES[role], "/FO", "LIST")
        if done.returncode != 0:
            out["scheduled"][role] = "not registered"
            continue
        fields = dict(line.split(":", 1) for line in done.stdout.splitlines() if ":" in line)
        out["scheduled"][role] = next((v.strip() for k, v in fields.items() if k.strip().lower() == "status"),
                                      "registered")
    with taskq.session() as conn:
        out["workers"] = taskq.live_workers(conn)
        out["ai_blocked_until"] = taskq.state_value(conn, "ai_blocked_until")
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="The workers of the task queue (tools/taskq.py)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run", help="run a worker (Task Scheduler starts these)")
    p.add_argument("--role", choices=ROLES, required=True)
    p.add_argument("--idle-exit", type=float, default=None, metavar="SECONDS",
                   help="end after this long with nothing to do (a worker the app started)")
    p = sub.add_parser("start", help="start a worker apart from this process and return at once")
    p.add_argument("--role", choices=ROLES, required=True)
    p.add_argument("--idle-exit", type=float, default=None, metavar="SECONDS",
                   help="end after this long with nothing to do")
    p = sub.add_parser("install", help="register the workers with Task Scheduler")
    p.add_argument("--role", choices=ROLES, action="append")
    p.add_argument("--user", help="DOMAIN\\name whose session the workers run in (default: this one)")
    p = sub.add_parser("uninstall", help="remove the workers from Task Scheduler")
    p.add_argument("--role", choices=ROLES, action="append")
    sub.add_parser("status", help="registered tasks and live workers")
    sub.add_parser("probe", help="does `claude` answer in this session?")
    args = parser.parse_args(argv)
    if args.command == "run":
        return run(args.role, args.idle_exit)
    if args.command == "start":
        return start(args.role, args.idle_exit)
    if args.command == "install":
        return install(args.role or list(ROLES), user=args.user)
    if args.command == "uninstall":
        return uninstall(args.role or list(ROLES))
    if args.command == "status":
        print(json.dumps(status(), ensure_ascii=False, indent=2, default=str))
        return 0
    works, note = probe_ai()
    print(json.dumps({"ai": works, "note": note, "session": session_id()}))
    return 0 if works else 1


if __name__ == "__main__":
    sys.exit(main())
