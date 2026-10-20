# 0052 No Markdown reports: the app is where the shortlist is read

Source: the owner, 2026-10-20 ("the reports folder is not needed any more, I
only ever use the UI; delete it and clean the tools of it")
Scope: tools, app, docs, config, rules

## Business
Every collection still wrote `reports/<prefix>_latest.md`, a file per
market and a dated copy in `reports/archive/`, and docs and commands still
sent a person to read them. The owner reads and answers the shortlist only
in the app, so the files are work nobody reads and a second description of
the same shortlist that can drift from the first. What the app lists (the
selections, split by market as configured in `<prefix>_reports.yaml`)
stays exactly as it is.

What only the Markdown report showed goes with it, each kept as a triage
task in case it is wanted in the app: the UK salary yardstick (0053) and
the source health and usefulness tables (0054). Link-check counts stay in
each run's result and log.

## Implementation
`tools/report.py` keeps the vacancy row (`vacancy_view`, shared with the
app) and the market and ordering helpers; the Markdown builder, the writers
and the segment file names go. `python tools/report.py --identity <p>`
records a selection without fetching (used by `/feedback`). The pipeline
stops writing reports and stops refreshing the salary benchmark (its only
reader was the report); runs no longer return `report_path`.
`common.REPORTS_*` and the `reports_root` argument go. Docs and commands
point at the app. The local `reports/` folder is deleted after the running
collection has finished and the branch is merged, since the running code
still writes it.

## Items
- DONE - Plan
- DONE - Markdown builder and writers removed from `tools/report.py`; its CLI re-selects
- DONE - Pipeline: no report stage, no salary benchmark refresh, no `report_path`
- DONE - `common`: reports folders removed; tests and fixture clean-up follow
- DONE - Docs, commands, configuration comments, `.gitignore`
- DONE - Triage tasks for what only the report showed
- TO DO - Delete the local `reports/` folder after the merge
