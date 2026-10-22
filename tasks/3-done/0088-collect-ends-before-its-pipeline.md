# 0088 A collect task ends while its pipeline still runs, and the pipeline dies

Source: the agent, 2026-10-22, queue task 10
Scope: tools

## Business
The owner asked on 2026-10-22 whether a run stops and is never started
again. It does. At 20:12 the app caught up the missed 01:00 schedule and
queued a collection for sharp (tasks 10-15). Task 10 (`collect`, a Claude
session running `/start`) started `pipeline.py --identity sharp --top
--skip-contracts` at 20:14:04, wrote "I'm watching its log and will report
the summary when it finishes", and ended its turn. The queue marked the task
`done` at 20:14:32. The pipeline's log stops at 20:14:29, in the middle of
the fetch (jobicy, 4 of 23 sources): the pipeline died with the session.
Nothing was saved, so no AI check was queued (0078 queues it on save), and
nothing tells the person the run was lost. Task 11 (LinkedIn, its own
process) kept running.

## Implementation
- Why it ended (code.claude.com/docs, env-vars and headless): a Bash command
  past its timeout (2 minutes unless asked) moves into the background, and a
  background command of `claude -p` has a time limit of its own. Task 10's
  log shows it: the plain command was moved, the agent read its output file,
  started a Monitor on the pipeline log and ended its turn.
- `tools/taskd.py`: the collect session starts with `AGENT_ENV`:
  `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, `BASH_DEFAULT_TIMEOUT_MS` and
  `BASH_MAX_TIMEOUT_MS` of 3 hours (`Command.env`).
- `.claude/commands/top.md`, step 4: one foreground command, wait for it, no
  Monitor, do not end the turn while it runs.
- `tools/pipeline.py`: the first line names the queue task
  ("started (queue task 10)").
- `tools/taskd.py`: `cut_off_pipeline()` finds a log of the task with no
  "pipeline finished" line; the worker queues the task again (up to
  `taskq.MAX_ATTEMPTS` starts), then fails it with the log's last line.
- Found on the way: the session's live log mirrored every pipeline log
  written after it started, the LinkedIn run beside it included (task 10's
  log, line 2). It follows its own task's logs only now.
- Tests in `tests/test_taskd.py`; `docs/ARCHITECTURE.md`.

## Items
- DONE - The session keeps its pipeline in the foreground: no background tasks, a 3-hour Bash timeout
- DONE - A cut-off pipeline log queues the task again, then fails it
- DONE - The live log of a collection follows its own pipeline's log only
