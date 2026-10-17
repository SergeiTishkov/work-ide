---
description: The fast daily cycle - the top vacancies first, about an hour
---

The fast cycle for the top vacancies (the owner, 2026-10-17: collect, check
remoteness by script, check the remote ones with AI, polish, CVs; the rest
afterwards). The desktop app's "Collect" runs it; the CVs and the rest of the
base are tasks of their own that the app queues after it.

Identity: `$ARGUMENTS` (empty means: establish it in step 1).

## The order

1. `python tools/identity.py which` — establish the identity. If several exist
   and it is unclear which is meant, ask; do not guess.
2. `python tools/templates.py check --identity <p>` — if the template moved
   ahead, ask the person whether to update (see `/run`, step 2). Started from
   the app: the answer is "not now"; name the changes in the summary.
3. `python tools/source_contract.py --identity <p>` — act on each status as in
   `/run`, step 3 (`broken`: repair with `/source-doctor <source>` first).
4. `python tools/pipeline.py --identity <p> --top --skip-contracts` — the
   pipeline's top mode:
   - fetch every enabled source; LinkedIn for the days since the last
     collection, both included, or the full month when there was none
     (`linkedin_window`); at most 25 minutes unless it is the full month;
   - the remote check by script: the pages of the top classes and of what
     this run brought, then a rescore of those;
   - the AI check of the top classes (`tools/ai_screen.py`, with the brief of
     `tools/ai_brief.py`), then a rescore;
   - links, direct application channels and company facts of the top;
   - selection and report.
5. A short summary: **how many days of vacancies were collected** (the
   pipeline's `collected` line, as it is: the LinkedIn window, whether it
   stopped at the time budget), how many hot leads and worth-a-look there are,
   how many the AI check turned down, what the fetch reported as broken or
   blocked.

Not in this command: the checklist read of `/run` (step 5), employer
reputation (a button on the vacancy in the app, `tools/reputation_lookup.py`),
and everything below the top classes. The whole base is
processed by `python tools/pipeline.py --identity <p> --rest`, which the app
queues after every collection queued before it. `remote_unconfirmed` gets no processing after its page
was read once.

## Started from the desktop app (headless)

The same rules as `/run`: ask nothing, do not commit, say briefly what each
step does as you go.
