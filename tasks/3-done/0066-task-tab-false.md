# 0066 The folded panel's tab says "false" before its title

Source: the owner, 2026-10-21, with a screenshot of the tab: "false  Tasks
(0 active)".
Scope: app

## Business
The trapezoid tab of the folded task panel showed the word "false" before
"Tasks (0 active)" whenever no task was running. It shows the title only,
with a spinner in front while a task runs.

## Implementation
`app/renderer/app.js`, `renderTaskTab`: the spinner's condition went to the
DOM's `replaceChildren`, which writes `false` as text (the file's `el()`
skips it; this call did not go through `el()`). Seen since 0064, which
draws the tab with no tasks. A UI test folds the empty panel and checks the
tab's text.

## Items
- DONE - The tab without "false"; UI test
