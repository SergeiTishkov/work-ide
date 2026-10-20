-- The task queue: data/tasks.sqlite (task 0056)
--
-- Every long piece of work — a collection, LinkedIn, the rest of the base, a
-- clean-up, a CV, a cover letter, a CV/CL batch — is a row here, whoever
-- asked for it: the app, the agent, a terminal, a schedule. The workers
-- (tools/taskd.py) take the rows and run them; the app only reads the rows
-- and asks for a stop. A file of its own, apart from data/workide.sqlite: a
-- 30-second save of the vacancy base never holds up a task's state, and the
-- queue outlives a broken base.
--
-- Applied by tools/taskq.py (Python) and by the app's tests (JavaScript).
-- Every statement is idempotent.
--
-- WHO WRITES WHAT
--   tasks (a new row, stop_requested, hidden)  - tools/taskq.py, for whoever asks
--   tasks (state, worker, pid, heartbeat_at, waiting_for, started_at,
--          ended_at, error, result)           - the worker running it (tools/taskd.py),
--                                               or the process that registered itself
--   workers                                    - each worker, its own row
--   queue_state                                - the workers (the AI limit, task 0057)
--   schedules                                  - tools/schedules.py: the app, the agent
--                                                (rows), the workers (last_*)

PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS tasks (
  -- AUTOINCREMENT: a number is never given twice, so "#12" in a log line
  -- always means the same task.
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  kind           TEXT NOT NULL,            -- tools/taskq.py KINDS
  identity       TEXT,                     -- the identity's prefix; NULL for none
  vacancy_id     TEXT,                     -- a CV, a cover letter, a reputation lookup
  title          TEXT NOT NULL DEFAULT '', -- the vacancy's title, for the panel
  company        TEXT NOT NULL DEFAULT '',
  args           TEXT NOT NULL DEFAULT '{}', -- JSON: instructions, clean-up filters, ...
  slot           TEXT NOT NULL,            -- one running task per slot
  needs          TEXT NOT NULL DEFAULT '', -- comma-separated: desktop, ai
  origin         TEXT NOT NULL,            -- app, agent, terminal, schedule, auto
  group_id       INTEGER,                  -- a collection: the id of its first task
  state          TEXT NOT NULL DEFAULT 'queued',
                 -- queued, running, done, failed, stopped, skipped, interrupted
  waiting_for    TEXT,                     -- why a queued task has not started
  stop_requested INTEGER NOT NULL DEFAULT 0,
  attempts       INTEGER NOT NULL DEFAULT 0, -- how many times it was started
  worker         TEXT,                     -- background, desktop, external
  pid            INTEGER,                  -- the process doing the work
  host           TEXT,
  queued_at      TEXT NOT NULL,            -- ISO 8601, UTC
  started_at     TEXT,
  ended_at       TEXT,
  heartbeat_at   TEXT,
  error          TEXT,
  result         TEXT,                     -- JSON: what the work returned
  log_path       TEXT,
  hidden         INTEGER NOT NULL DEFAULT 0 -- cleared from the panel
);

CREATE INDEX IF NOT EXISTS tasks_state ON tasks (state);

-- "after #12 and #13": a task starts when every row it names here has ended.
-- needs_done = 1: and only if that one ended done; otherwise the task is
-- skipped (the rest of the base after a failed collection).
CREATE TABLE IF NOT EXISTS task_after (
  task_id    INTEGER NOT NULL,
  after_id   INTEGER NOT NULL,
  needs_done INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (task_id, after_id)
);

-- One row per worker role, refreshed every few seconds while it lives.
CREATE TABLE IF NOT EXISTS workers (
  role         TEXT PRIMARY KEY,           -- background, desktop
  pid          INTEGER,
  host         TEXT,
  session      INTEGER,                    -- the Windows session it runs in
  capabilities TEXT NOT NULL DEFAULT '',   -- comma-separated: desktop, ai
  started_at   TEXT,
  heartbeat_at TEXT,
  note         TEXT                        -- e.g. why it has no AI
);

CREATE TABLE IF NOT EXISTS queue_state (
  key   TEXT PRIMARY KEY,
  value TEXT
);

-- Work on a timetable (task 0061, tools/schedules.py). The workers queue a
-- schedule's tasks when it is due, with origin "schedule".
CREATE TABLE IF NOT EXISTS schedules (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT NOT NULL DEFAULT '',
  what        TEXT NOT NULL,               -- schedules.WHAT: collect, linkedin, rest, clean, cv_batch, links
  identities  TEXT NOT NULL DEFAULT 'all', -- comma-separated prefixes, or 'all': every active one
  args        TEXT NOT NULL DEFAULT '{}',  -- JSON: the clean-up's filters, the batch's "all"
  cron        TEXT NOT NULL,               -- minute hour day month weekday, local time
  enabled     INTEGER NOT NULL DEFAULT 1,
  missed      TEXT NOT NULL DEFAULT 'catch_up', -- a run missed while off or asleep: catch_up, skip
  created_at  TEXT NOT NULL,
  last_due_at TEXT,                        -- the last run time handled (queued, skipped)
  last_run_at TEXT,                        -- when it last queued its tasks
  last_tasks  TEXT,                        -- JSON: the ids it queued then
  last_note   TEXT                         -- what the last run time did, in words
);
