# 0057 An AI usage limit stops the run instead of calling again and again

Source: the owner, 2026-10-20 ("the scripts use AI; when it refuses because
the limit is used up, the scripts must stop, not keep knocking on an AI
that is out of limit")
Scope: tools, app

## Business
A collection calls Claude in several places: the headless agent that runs
the cycle (`claude -p /top <p>` from the app), the AI screen of the top
(one call per posting, several at once), the brief, the reputation lookup,
the CV and cover-letter tools. When the account's usage limit runs out,
every further call is refused until the limit resets, hours later.

Today a refused call is an ordinary error. `ai_screen.screen` counts it
and goes on to the next posting ("one posting must not stop the rest"), so
at the limit it sends one refused call per posting left in the worklist,
and the run ends looking finished with an error count. The owner wants
the run to stop at the first such refusal and say so: what stopped it,
when the limit resets, what was done before the stop.

## Implementation
One place in `tools/` recognises a usage-limit answer of `claude -p`
(`is_error` with the limit text and its reset time; the exact shape is
captured first, not guessed) and raises its own error, separate from a
per-posting failure. Every `call_model` (`ai_screen`, `ai_brief`,
`reputation_lookup`, `cv_tailor`) goes through it. A stage that meets it
stops: no new calls, the calls not yet sent in the thread pool are
dropped. What was already fetched, scored and screened is saved. The run
state records "AI limit, resets at <time>", and the pipeline exits with a
code of its own.

In the app, the agent run and the Python tasks end with that
reason in the task panel, and queued tasks that need AI wait for the reset
time instead of starting and failing one after another.

The queue resumes by itself (the owner, 2026-10-21): the task service
(0056) checks whether the limit has reset, at the reset time the answer
gave and otherwise every 8 hours, with one minimal `claude -p` call; when
it has, the waiting tasks start again from where they stopped.

## Items
- DONE - The usage-limit answer: not captured, closed without it (the owner, 2026-10-28). No refused call in any task or run log up to 2026-10-28; the recogniser takes the wordings Claude Code is known to print ("Claude AI usage limit reached|<epoch>", "5-hour limit reached ∙ resets 3pm", "You've hit your limit · resets 5pm (zone)", "Your limit will reset at 5pm"). If the first real refusal is not recognised, each refused call counts as one posting's error, as before this task, and the log of that run is the start of a new task
- DONE - Every place that calls `claude`, and how each handled an error: `ai_brief.call_model` (BriefError; the pipeline skipped the AI check), `ai_screen.call_model` (ScreenError; `screen` counted it and went on to the next posting), `reputation_lookup.call_model` (exit 1), `cv_tailor.call_model`, also used by `cover_letter` (TailorError, `{"ok": false}`, exit 1; `cv_batch` counted it failed and went on), the agent run `claude -p "/top <p>"` (taskd: failed on its exit code), `taskd.probe_ai` (a limit counted as working)
- DONE - One recogniser and one error for the limit (`tools/ai_limit.py`: `check`, `UsageLimit`, `EXIT_CODE` 75, the line `AI usage limit reached; resets at <time>`); every `call_model` uses it; only a refused call is read, and not LinkedIn's rate limit
- DONE - The stage that meets the limit stops at once and keeps what it finished: `ai_screen` sends nothing after the first refusal and saves the answers given; the pipeline goes on without AI and exits 75 with the line; `cv_tailor`, `cover_letter`, `reputation_lookup` exit 75; a CV/CL batch stops before its next document
- DONE - The app: a task stopped by the limit goes back to the queue and says "Waits for the AI usage limit to reset; tries again at <time>", then "checking whether it has reset"; queued AI tasks wait for the reset
- DONE - Ask the owner: the queue resumes by itself; the check runs every 8 hours (2026-10-21)
- DONE - The task service checks for the reset (reset time, else every 8 hours) with one minimal `claude -p` call in a thread, one worker at a time, and resumes the waiting tasks; a tool run by hand records the limit in the queue too (`taskq.block_ai`)
- DONE - Tests (`tests/test_ai_limit.py`, `tests/test_taskd.py`, `tests/test_taskq.py`, `tests/test_cv_tailor.py`, a UI test): one refused call stops the screen, no further calls are sent; the wordings, the reset times, other limits not taken for it; the worker's requeue, the exit code, the check at the reset
- DONE - Docs: ARCHITECTURE "The AI usage limit stops the AI work, and the queue waits for the reset", RUNBOOK step 1
