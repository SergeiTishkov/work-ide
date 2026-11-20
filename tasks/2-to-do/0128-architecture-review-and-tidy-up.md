# 0128 Architecture review: duplicates and structure

Source: the owner, 2026-11-20
Scope: tools, app, docs

## Business
The owner, 2026-11-20, after the availability work (task 0127): an
architecture review at the end, to tidy the application up: remove
duplicates, improve the structure.

## Implementation
Two read-only reviews (Python `tools/`, Electron `app/`) list the
duplicates, dead code and lists kept in sync by hand, each with file and
line. The findings are checked against the code; the small, low-risk ones
are done here with tests, the larger ones become items or triage tasks.

## Items
- DONE - The two reviews (2026-11-20)
- TO DO - App: the i18n parameter tests match `{w}` only (a missing backslash) and check nothing
- TO DO - App: classes without a label (remote_unconfirmed, low_priority, rejected rows in the applications view) sort first and show the raw key
- TO DO - App: dead exports and comments naming files that no longer exist
- TO DO - Tools: the findings of the Python review
