# 0064 The task panel is shown with no tasks

Source: the owner, 2026-10-21, with a screenshot: "Show the task list" on,
and neither the panel nor its trapezoid tab at the bottom.
Scope: app

## Business
With "Show the task list" on, the bottom panel (or, folded, its tab) is
always there, as VS Code's panel: an empty queue shows the panel with "No
tasks" in it, not nothing. Until now the panel and the tab were drawn only
while the queue held a task (0062), so an empty queue looked like the
setting did not work; "Clear finished" made the whole panel disappear.

## Implementation
`app/renderer/app.js`: the panel and the tab follow the setting and the
fold only; an empty list shows a line saying there are no tasks and where
they come from. UI tests that expected no panel without tasks now expect
the empty panel.

## Items
- DONE - The panel and its tab shown with no tasks, the list saying so; UI tests
