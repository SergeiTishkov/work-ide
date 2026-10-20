# 0060 The task panel: borders like VS Code, no stale CV batch on every start

Source: the owner, 2026-10-21 (with a screenshot of a VS Code panel border:
"the borders of the panels are thin; I want them a couple of pixels thick,
in the style of the VS Code panel borders")
Scope: app

## Business
The bottom panel (the task list on the left, the selected task's log on the
right) is split by 1px borders that are hard to see and to grab. The owner
wants them about two pixels thick, styled like the borders between VS Code's
panels: a visible line in the border colour, the accent colour on hover and
while dragging.

On every start the panel also shows one old finished task: the CV/CL batch.
The panel reads it from `data/cv_batch.json`, and "Clear finished" only hides
it until the app restarts (`dismissed` is kept in memory, `app/main/tasks.js`).
A finished batch that was cleared stays cleared.

That the panel lists every task (runs started outside the app included) is
part of the task service work, not of this task.

## Implementation
`app/renderer/styles.css`: the panel's top border and the split between the
two panes 2px in a stronger border colour; the sashes keep their hover and
drag highlight. The dismissed batch is remembered across restarts (the
batch's `started_at`, stored beside its status file or in the base).

## Items
- DONE - Borders of the panel and its split 2px, VS Code style; UI test for the width (`--panel-border`, a stronger line in both themes; the sashes 6px, centred over the lines, keep the accent on hover and drag)
- DONE - A cleared finished CV batch does not come back after a restart; test (the queue of task 0056 covers it: the panel lists `tasks.sqlite` rows, "Clear finished" sets their `hidden` column through `taskq.py hide`, and `cv_batch.json` is read only while its row runs; `app/test/unit/queue.test.js` restarts the client over a cleared batch)
