---
description: The fast daily cycle - the top vacancies first, about an hour
---

The fast cycle for the top vacancies (the owner, 2026-10-17: collect, check
remoteness by script, check the remote ones with AI, polish, CVs; the rest
afterwards). It runs as a task of the queue (`tools/taskq.py`, task 0056):
"Collect" in the app and `python tools/taskq.py collect <p>` add it with
LinkedIn, the rest of the base and the CVs as tasks of their own, beside it
or after it. LinkedIn is not in this command (the owner, 2026-10-20): it is
`python tools/pipeline.py --identity <p> --linkedin`, a task beside this
one.

Identity: `$ARGUMENTS` (empty means: establish it in step 1).

## The order

0. `python tools/taskq.py current` — `{"task": null}` means this session is
   not the queue's task: establish the identity (step 1), then add the
   collection with `python tools/taskq.py collect <p>` and follow it as the
   `run-task` skill says (`taskq.py wait <ids>` in the background, its log
   with `taskq.py log <id>`); when it ends, give the summary of step 5 from
   the logs. Do not run steps 2-4 in this session. A task id means a worker
   started this session for it: go on with step 1.
1. `python tools/identity.py which` — establish the identity. If several exist
   and it is unclear which is meant, ask; do not guess.
2. `python tools/templates.py check --identity <p>` — if the template moved
   ahead, ask the person whether to update (see `/run`, step 2). Started by a
   queue worker: the answer is "not now"; name the changes in the summary.
3. `python tools/source_contract.py --identity <p>` — act on each status as in
   `/run`, step 3 (`broken`: repair with `/source-doctor <source>` first).
4. `python tools/pipeline.py --identity <p> --top --skip-contracts` — the
   pipeline's top mode:
   - fetch every enabled source but LinkedIn;
   - the remote check by script: the pages of the top classes and of what
     this run brought, then a rescore of those;
   - the AI check of the top classes (`tools/ai_screen.py`, with the brief of
     `tools/ai_brief.py`), then a rescore;
   - links, direct application channels and company facts of the top;
   - selection.
   If it prints `SKIPPED: identity '<p>' is inactive`, the person turned the
   identity off: stop here and say so; do not turn it on.
5. A short summary: **what was collected** (the pipeline's `collected` line,
   as it is: LinkedIn is fetched by its own run), how many hot leads and
   worth-a-look there are,
   how many the AI check turned down, what the fetch reported as broken or
   blocked.

Not in this command: the checklist read of `/run` (step 5), employer
reputation (a button on the vacancy in the app, `tools/reputation_lookup.py`),
and everything below the top classes. The whole base is
processed by `python tools/pipeline.py --identity <p> --rest`, which the
queue runs after the top and LinkedIn of the same collection. `remote_unconfirmed` gets no processing after its page
was read once.

## Started by a queue worker (headless)

The worker runs this command as `claude -p "/top <p>"`. The same rules as
`/run`'s headless run: ask nothing, do not commit, say briefly what each step
does as you go; the panel shows it as the task's live log.
