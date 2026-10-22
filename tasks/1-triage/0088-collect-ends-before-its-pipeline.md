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
- The collect session runs the pipeline in the foreground (or waits for it)
  and does not end its turn before the pipeline exits; the command text in
  `.claude/commands/start.md` says so.
- The worker checks after a `collect` session ends: a pipeline log for the
  task that has no "finished" line means the task failed, not done; the
  queue runs it again (attempts).
- A test on the worker's check with a cut-off log.

## Items
- TO DO - The session waits for its pipeline; a cut-off run fails the task and is run again
