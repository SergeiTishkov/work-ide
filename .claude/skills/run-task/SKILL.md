---
name: run-task
description: Run long work through the task queue (tools/taskq.py), never as a process of the agent's own. Use before any collection (/top, /run, pipeline.py in any mode), LinkedIn, the rest of the base, a clean-up, a CV/CL batch, a CV or cover letter, or an employer reputation lookup. The queue's workers run it outside the session, so it survives the session ending, the app closing, another Windows user signing in; the app's panel lists it. Takes optional words naming the work and the identity.
---

# Long work goes through the queue

The work: `$ARGUMENTS` (or the one just asked for).

The queue (`data/tasks.sqlite`, task 0056) is run by workers
(`tools/taskd.py`) that Task Scheduler starts at boot and at sign-in. A task
added there runs whether this session lives or not, and every task is in the
app's bottom panel with who added it. A pipeline started from this session
dies with the session, holds the base against the queue's own runs, and is
listed only as "terminal".

## 1. Already a queue task?

```bash
python tools/taskq.py current
```

`{"task": 12, "kind": "collect", ...}`: a worker started this session for
task #12 — do the work here, directly; it is the task. `{"task": null}`:
go on.

## 2. Add it

| The work | Command |
|---|---|
| A collection (the app's "Collect") | `python tools/taskq.py collect <p>` |
| The same without LinkedIn / without CVs | `... collect <p> --no-linkedin` / `--no-documents` |
| The full cycle of `/run` (step 4) | `python tools/taskq.py add pipeline --identity <p> --args '{"skip_contracts": true}'` |
| The top only (`pipeline.py --top`) | `python tools/taskq.py add pipeline --identity <p> --args '{"mode": "top"}'` |
| LinkedIn / the rest of the base | `python tools/taskq.py add linkedin --identity <p>` / `add rest ...` |
| A clean-up | `python tools/taskq.py add clean --identity <p> --args '{"statuses": [...], "ages": [...], "classes": [...]}'` — at least one list, with the values of `tools/cleanup.py --help` (an age is counted from the posting date: `older` is more than 30 days, not "before the last run"). Deleting cannot be undone: run `cleanup.py ... --dry-run` first and show the person the counts |
| A CV / a cover letter | `python tools/taskq.py add cv --identity <p> --vacancy <id> [--instructions "..."]` (`letter` alike) |
| A CV/CL batch | `python tools/taskq.py add cv_batch --identity <p>` |
| Employer reputation | `python tools/taskq.py add reputation --identity <p> --vacancy <id>` |
| The shortlist's links again | `python tools/taskq.py add links --identity <p>` |
| On a timetable ("every day at 7") | `python tools/taskq.py schedule add <collect\|linkedin\|rest\|clean\|cv_batch\|links> --identities <p,p\|all> --cron "0 7 * * *" [--missed catch_up\|skip] [--args '<JSON>']`; `schedule list`, `schedule next "<cron>"` (show the person the next runs before adding), `schedule on\|off\|remove <id>`. Ask the person what a run missed while the computer was off does: caught up once, or skipped |

`collect` queues a group: the top (the agent's `/top`), LinkedIn beside it,
the rest of the base after both, a CV/CL batch after each. `--after <ids>`
makes a task wait for others. The origin is set by itself ("agent" in a
Claude Code session). The same task already queued or running is not added
twice: the answer is `"added": false` with the task that is there.

## 3. Follow it

- `python tools/taskq.py wait <ids>` — until they end; exit 0 when all ended
  done. A collection takes an hour and more: run it as a background command
  (`run_in_background`), and you are told when it ends.
- `python tools/taskq.py list` — what is queued and running, and why a task
  waits (`waiting_for`: another task, the AI usage limit, the owner's
  sign-in, no worker running).
- `python tools/taskq.py log <id>` (`-f` to follow) — its log.
- `python tools/taskq.py stop <id>` — stop it.
- `python tools/taskq.py status` — the live workers.

When it ends, read its log and report as the command asked (`/top` step 5,
`/run` "At the end"). A task that failed says why at the end of its log and
in `error` (`taskq.py show <id>`).

## When the queue cannot run it

`waiting_for: no worker is running` means no worker beats. `python
tools/taskd.py status` shows whether they are registered with Task
Scheduler. Not registered: tell the person — `python tools\taskd.py install`
from an elevated PowerShell registers them, once (the password is not
stored). Meanwhile `python tools/taskd.py start --role desktop --idle-exit
600` starts a worker for this sign-in, as the app does.

Do not fall back to running the pipeline in this session to get round a
waiting task: the reason it waits (the usage limit, a running collection)
holds for that run too.
