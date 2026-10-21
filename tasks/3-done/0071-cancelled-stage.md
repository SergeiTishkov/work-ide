# 0071 A fourth stage, 4-cancelled, for work the owner decided not to do

Source: the owner, 2026-10-21: "a fourth status is needed, 4-cancelled; put
0053 there"
Scope: tasks, rules

## Business
Until now a task the owner did not want was deleted, and with it the record
of what was considered and why it was dropped. A cancelled task keeps its
file in `tasks/4-cancelled/`, with who decided, when and why, so the same
idea is not proposed again without that answer at hand.

## Implementation
`tools/tasks.py` STAGES; `tests/test_tasks.py` (four folders, a `Cancelled:`
line in a cancelled task, its TO DO items left as they stood); the commit
hook treats a cancelled task as it treats a triage one (it covers no work
outside `tasks/`), with tests; `tasks/README.md`, CLAUDE.md §12, the `task`
skill, `docs/ARCHITECTURE.md`.

## Items
- DONE - The stage, its format check, the hook and its tests, the documents
- DONE - 0053 (UK salary yardstick in the app) cancelled
