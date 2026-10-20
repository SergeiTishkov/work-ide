# 0027 The app starts from a shortcut and refreshes itself

Commits: de8389e df6917a 1f1ebe7 b577aa5 3dc5a04 (2026-09-29 — 2026-10-03)
Source: the owner

## Business
The app opens from a desktop shortcut, not a terminal. After a collection or
an update of the code, Refresh shows the new state; when the app's own main
process is outdated, Refresh restarts it. Until the identities arrive the
window shows a spinner, not an empty page.

## Implementation
`WorkIDE.cmd` and a desktop shortcut; Refresh compares the main process's
code with the files on disk and relaunches when they differ.

## Items
- DONE - Desktop shortcut
- DONE - Refresh, restarting an outdated main process
- DONE - Spinner until the identities arrive
