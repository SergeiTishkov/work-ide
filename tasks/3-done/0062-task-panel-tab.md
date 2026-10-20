# 0062 The task panel folds into a tab, can be hidden, and asks before stopping

Source: the owner, 2026-10-21 ("the window should not close but hide down
into the footer and stick out of it as a small trapezoid; clicking the
trapezoid opens it. A setting turns the task list on and off. Closing or
folding the list stops nothing; the crosses in the list stop a task, with a
modal 'Are you sure you want to stop this task?'")
Scope: app

## Business
- The bottom task panel folds down instead of closing: a small trapezoid
  tab sticks out of the bottom edge; a click opens the panel again.
- A setting shows or hides the task list altogether: hidden, neither the
  panel nor the tab is shown.
- Folding or hiding the panel stops nothing (with the task service, 0056,
  closing the whole app stops nothing either).
- The cross on a task stops it, after a confirmation: "Are you sure you
  want to stop this task?".
- A collection is one row with its stages written inside it, updated as it
  goes: an empty circle for a stage to do, a green tick for one done, a
  spinner for the one in progress (the owner, 2026-10-21: "fast, cheap and
  cheerful"). LinkedIn, the rest of the base and the CV/CL batch are rows of
  their own (0056).

## Implementation
The app has no settings window yet: a "Settings…" menu item with a popup,
its first setting "Show the task list", kept per user. The folded state and
the setting are remembered across restarts. The stage checklist reuses
`app/main/steps.js` (the steps the panel already tracks).

## Items
- DONE - Plan (2026-10-21, with the owner)
- DONE - Fold into a trapezoid tab and open from it; remembered; UI tests (the chevron at the log's title folds it; the tab on the bottom edge, right, says how many are active, a spinner while one runs)
- DONE - "Settings…" with "Show the task list"; hidden means no panel and no tab; UI tests (kept in the app's storage, per Windows user)
- DONE - Stop asks for confirmation; UI test (the panel's cross; Cancel, Escape and a click outside stop nothing; the menu's "Stop" is unchanged)
- DONE - A collection row lists its stages with circle, spinner and tick; UI test (the stages to come from an outline per kind in `app/main/steps.js`: a collection, the rest, LinkedIn; a stage passed over drops out; unit tests)
