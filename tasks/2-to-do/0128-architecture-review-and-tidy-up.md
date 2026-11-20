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
- DONE - App: the i18n parameter tests matched `{w}` only (a missing backslash) and checked nothing; fixed, with a check that they find parameters
- DONE - App: a class without a section label (low_priority, rejected, remote_unconfirmed rows kept by the applications view) sorted first and showed its raw key; now last, named as in the clean-up
- DONE - App: comments naming files that no longer exist (main/tasks.js, reputation.js, cv.js, batch.js, rest.js, runner.js) point at what replaced them; `QueueClient.active()`, a duplicate of `AGES` and two orphaned comments removed
- DONE - App: the Electron smoke test failed since 2026-10-23 (the filters' card starts folded in a fresh profile); it opens the card
- TO DO - Tools: the findings of the Python review
