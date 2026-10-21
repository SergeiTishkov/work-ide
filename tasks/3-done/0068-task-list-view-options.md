# 0068 The task list's gear: finished tasks shown or not, oldest or newest on top

Source: the owner, 2026-10-21, with a screenshot of the task list's title:
"here a small gear that opens a list of checkboxes: what to show and in
what order: whether to show old finished tasks, oldest on top, newest on
top".
Scope: app

## Business
A gear at the right of the task list's title opens a short list:
- "Show finished tasks": off, the list holds only the running and the
  queued ones (the finished stay in the queue, "Clear finished" removes
  them);
- the order: oldest on top (as until now) or newest on top; one of the two.

The choice is kept across restarts, as the other settings. With every
task hidden by it, the list says so and where to change it.

## Implementation
`app/renderer/app.js`: two settings beside "Show the task list"
(`showFinished`, `taskOrder`), a `shownTasks()` the list, the log's choice
and the counts read; the gear in the list title, its menu drawn in the
pane (the title clips what overflows it). Locales en and ru, UI test.

## Items
- DONE - The gear, its menu, the filter and the order, kept; UI test
