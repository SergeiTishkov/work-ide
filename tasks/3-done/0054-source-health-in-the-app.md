# 0054 Source health and usefulness in the app

Source: task 0052, 2026-10-20: the Markdown report was the only place that
showed it
Scope: app, tools

## Business
The Markdown report had a Source health table (each source's status, last
success and last error, days failing) and a usefulness table (how many of
each source's vacancies reached the shortlist), plus link-check counts. Now
the run log and the state file hold the raw facts, and the app shows only
the run log. Decide whether the app should show source health and usefulness
(it is how a narrow source's yield is judged after a couple of runs,
docs/SOURCES.md), and where.

## Implementation
Menu → "Sources…", a window with a row a board of the open identity.

- Last run, from `<dataDir>/<prefix>_state.json` (`state["sources"]`, kept
  by tools/pipeline.py): the date and how many records it fetched, or how
  many runs in a row failed with the last success and the error's first
  line; a board with no attempt on record says so. A fetch's note (the
  LinkedIn query count) shows under it, not as a failure.
- Yield, from the base (`source_yield` in schemas/queries.sql): every
  vacancy of the board the identity holds, near-duplicates aside; how many
  are in the shortlist now (hot_lead, worth_a_look, long_shot); how many
  were applied to (any step of the funnel).
- Failing boards first, then the most shortlisted.

The main process reads the state file (app/main/source-health.js) and asks
the store thread for the yield. Measured on the real base, 2026-10-21: the
yield query takes about 2 seconds over 50,000 vacancies, read once when the
window opens. Link-check counts stay in each run's log.

## Items
- DONE - Work out the plan and write it here as the next items
- DONE - `source_yield` query and `Store.sourceYield`; the state file read and merged in main
- DONE - "Sources…" in the menu: the table, failing boards in red; English and Russian texts
- DONE - Tests: unit (merge, state file, query) and UI; README
