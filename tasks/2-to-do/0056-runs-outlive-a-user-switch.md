# 0056 A task service: every task runs outside the app, listed in one queue

Source: the owner, 2026-10-20 ("when the active Windows user changes, my
long-running collection scripts started under the first user stop working;
make them able to work while another user is active, or even while the
system sleeps, if that is possible at all"); the design agreed 2026-10-21
("a backend service registered in Windows"; "through Task Scheduler, as you
recommend"; "tasks the agent starts are registered in the list too")
Scope: tools, app, rules, docs

## Business
The owner starts a collection, then another person signs in to the same
laptop with Fast User Switching, and the collection stops. A collection
takes hours (the LinkedIn walk alone six hours and more, task 0050).

Today the queue lives in the memory of the app's window
(`app/main/tasks.js`): closing the window stops every task
(`window-all-closed` -> `stopAll`), and a run started by the agent or from
a terminal never appears in the bottom panel. The panel showed one old CV
batch for weeks and nothing else (the owner, 2026-10-21).

What the owner wants:
- Tasks run in a service of their own, not in the app: closing or
  collapsing the app stops nothing; another user being active stops
  nothing; after a reboot the service starts without anybody signing in.
- Every task is in the list, whoever started it: the app, the agent, a
  terminal, a schedule (task 0061). It is queued, runs, ends as done,
  failed or stopped, and the list shows exactly that.
- Only LinkedIn runs beside the other collection work; the rest of a
  collection queues. CVs and cover letters run in parallel to collections.
- A task that needs something the machine does not have right now (Word
  needs a signed-in desktop; AI needs the usage limit, task 0057) waits
  with the reason shown, and starts by itself when it is there.

Other operating systems are not needed now (the owner, 2026-10-21).

## Implementation
**The queue is SQLite, a file of its own** (`data/tasks.sqlite`, WAL): the
tasks, their steps, their state and who runs them; logs are files beside
it. Separate from `data/workide.sqlite`, so a 30-second save of the
vacancy base never holds up a task's state, and so the queue survives a
broken base.

**Workers, not one daemon** (`tools/taskd.py`), each claiming the tasks it
can run, in a transaction:
- the background worker: a Task Scheduler task at system start, "run
  whether the user is logged on or not" with no stored password (S4U). The
  password is never stored (the owner, 2026-10-21). If `claude` does not
  work under S4U, tasks that need AI wait for the owner's logon and run in
  the desktop worker. Runs collections, LinkedIn, the rest of the base,
  clean-ups.
- the desktop worker: a Task Scheduler task at the owner's logon, in the
  owner's session. Runs what needs the desktop: CVs and cover letters
  (Word COM). Keeps running while another user is active.

Slots: one collection slot (collect, rest, clean-up, ...), one LinkedIn
slot, one documents slot. A task names what it needs (`desktop`, `ai`);
a worker that lacks it leaves the task queued with the reason.

**Reliability:** Task Scheduler restarts a worker that exits with an error
(every minute, without limit) and starts it at boot and logon; one worker
of each kind (a lock in the queue's file); each writes a heartbeat. A task
whose worker died (heartbeat stale, pid gone) is marked interrupted and
queued again at the step it can restart from. While a task runs the worker
keeps the system awake (`SetThreadExecutionState`). The app checks the
heartbeats and, if a worker is gone, starts its scheduled task
(`schtasks /run`) and says so.

**One collection is a group of tasks**, each a row in the panel:
- collect the top (the agent's `/top` run; its pipeline stages shown inside
  the row as a checklist, task 0062);
- LinkedIn (`pipeline.py --linkedin`), in its own slot, at the same time;
- the rest of the base, after both;
- the CV/CL batch for what they brought, in the documents slot.
The dependencies are rows of the queue ("after #12 and #13"), not code in
the app.

**The app is a client**: it adds tasks, lists them, stops them (a flag the
worker acts on); it never runs one. `app/main/tasks.js` becomes a reader of
the queue; its rules (lanes, "rest after LinkedIn", the batch) move into
`tools/taskd.py`.

**Runs started outside the queue are listed too**: `pipeline.py` started
directly registers itself as a task (kind and identity, state, log), so a
terminal run is visible; the agent uses the queue instead (below).

**The agent**: `tools/taskq.py` (`add`, `list`, `show`, `log`, `stop`,
`wait`); a skill `run-task` and a CLAUDE.md rule: long work (collections,
LinkedIn, the rest, clean-ups, CV/CL batches) is added to the queue, never
started as a process of the agent's own. Checked by subagents given only the
rules and a request ("collect for <fixture identity>"), on the test fixture:
the task must appear in the queue and run there.

## Items
- DONE - Plan (2026-10-21, with the owner)
- DONE - Queue schema in `data/tasks.sqlite` (`schemas/tasks.sql`), `tools/taskq.py`, tests (add, claim, depend, stop, interrupted, slots); a run started by hand registers itself with `taskq.Registered`
- DONE - `tools/taskd.py` workers: claim by slot and capability, run, log, heartbeat, keep-awake, one worker per role, a sleep gap holds the sweep; the CV/CL batch pauses for a CV the app asked for; tests with fake and real processes
- DONE - Task Scheduler registration (`tools/taskd.py install/uninstall/status`): background at start (check `claude` under S4U first), desktop at logon, restart on failure. Code and tests done; registering the S4U task needs an elevated PowerShell, which the owner runs once (`python tools\taskd.py install`). 2026-10-24: the 01:00 collection did not run, no worker was registered (the app's worker had ended at 05:19 the day before, after ten idle minutes); the owner asked for a cmd in the root: `WorkIDE-Background-Setup.cmd` asks for elevation, passes the signed-in user (`taskd.py install --user`), warns that a missed scheduled collection runs at once, and shows `status`. Registered by the owner 2026-10-24 13:45 and checked: background S4U at boot ("claude answers" in session 0), desktop interactive at sign-in, both restart on failure; the desktop worker caught up the missed 01:00 collection at once (#21-#26)
- DONE - `WorkIDE-Background-Remove.cmd` (the owner, 2026-10-24): elevated `taskd.py uninstall`, then `status`; the queue and the schedules stay, running workers keep going until a restart or a sign-out
- DONE - The app's "Task scheduler…" page says whether the workers are registered (`worker-registration`, asked afresh on each opening) and names the setup script in the repository folder, or the removal one when they are; UI and unit tests
- DONE - The agent tells about the two scripts when it sets up an identity: `docs/ONBOARDING.md` step 6c and step 6 of the second identities, `/start` step 11, `/add-identity` step 7, CLAUDE.md, README
- DONE - Direct `pipeline.py` and `cv_batch.py` runs register themselves in the queue (`taskq.Registered`); the batch prints its log lines for the worker too
- DONE - The app reads and controls the queue (`app/main/queue.js`): it adds, lists, stops and clears through `tools/taskq.py`, shows every task with who added it and why it waits; `tasks.js`, the runner and the batch watcher are gone; closing the window stops nothing. With no worker registered the app starts a desktop worker itself (`app/main/workers.js`, `taskd.py start`, detached from the app's handles; it ends after ten idle minutes); a registered one that stopped beating is started through Task Scheduler
- DONE - Agent infrastructure: the `run-task` skill, the CLAUDE.md and RUNBOOK rules, `/top` and `/run` add their long step to the queue unless `taskq.py current` names the session's own task; the `pipeline` kind takes `skip_contracts`
- DONE - Docs: README (the task service, registering the workers), ARCHITECTURE (the task service, the in-memory queue it replaced, what was not taken), IDENTITIES
- DONE - Subagent check (2026-10-21, dry runs on the real identities): asked to collect, the agent ran `taskq.py current`, chose `taskq.py collect <p>`, a background `wait`, saw no worker registered and named `taskd.py install`, and did not run the pipeline itself; asked for a CV and a clean-up, it chose `taskq.py add cv` and `add clean`, and pointed out that the skill's clean-up example read `older` as "before the last run" (it is more than 30 days): the example now names the filter values from `cleanup.py --help` and a dry run first
- TO DO - End-to-end check: tasks from the app, the agent, a terminal and a schedule all appear, run, and end with the right state
- TO DO - Reproduce the user switch and the 30-minute battery sleep with the service; record what happens
