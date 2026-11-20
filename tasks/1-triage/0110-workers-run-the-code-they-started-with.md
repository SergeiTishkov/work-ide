# 0110 The task workers run the code they started with

Source: the agent, 2026-11-02
Scope: tools

## Business
A worker (`tools/taskd.py run`) is one long process. It builds each task's
command line with the `taskd.py` it loaded at start, so a change to
`taskd.command()` does not reach it until it restarts. On 2026-11-02 the
background worker had been running since 2026-10-24, before task 0103 taught
`command()` to pass `--reread` (2026-10-28). Task 64, an AI re-read the owner
asked for, ran as a plain `pipeline.py --ai` and read nothing ("considered
0"). The desktop worker had been running since 2026-10-30. Both were
restarted by hand (`schtasks /End`, `/Run`), and the re-read ran again as
task 65.

Again on 2026-11-20: the background worker (since 2026-11-12) and the
desktop worker (since 2026-11-17) predate `{"read": true}` for `links`
(task 0129) and `{"staged": true}` for `linkedin` (task 0135). The backlog
read (#303) would have run as a plain link check and was stopped; the
merge of the kept LinkedIn fetch waits for a restart (emergency.md).

The pipeline itself starts as a new process for each task and runs the
current code; only what the worker computes in its own process is stale.

## Items
- TO DO - Decide with the owner: the worker exits when its own source files changed since it started (Task Scheduler starts it again within five minutes), or `command()` moves to a child process, or the worker logs the commit it runs
