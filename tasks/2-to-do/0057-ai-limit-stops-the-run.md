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

In the app, the agent run (`runner.js`) and the Python lanes end with that
reason in the task panel, and queued tasks that need AI wait for the reset
time instead of starting and failing one after another. Whether the queue
picks up by itself after the reset or waits for the owner is the owner's
call.

## Items
- TO DO - Capture what `claude -p --output-format json` and `stream-json` return at the usage limit (fields, text, reset time, exit code) and write it here
- TO DO - List every place that calls `claude` and how each handles an error today (ai_screen, ai_brief, reputation_lookup, cv_tailor, cover_letter, cv_batch, the agent run)
- TO DO - One recogniser and one error for the limit in `tools/`; every `call_model` uses it
- TO DO - The stage that meets the limit stops at once and keeps what it finished; the pipeline ends with the reason, the reset time and its own exit code
- TO DO - The app: a task stopped by the limit says so; queued AI tasks wait for the reset
- TO DO - Ask the owner: after the reset, the queue resumes by itself or waits for a click
- TO DO - Tests with a fake `claude` that answers with the limit: one refused call stops the screen, no further calls are sent
