# 0059 The app's step list names no stage the pipeline dropped

Source: the agent, 2026-10-20: app unit test i18n.test.js failed after 0052
Scope: app

## Business
0052 removed the salary benchmark stage and its text step.benchmark, but the renderer's stage table still named it, so the app unit test 'every key the renderer uses has a text' failed (the UI tests did not catch it). The entry goes.

## Implementation
One line in `STEP_KEYS` of `app/renderer/app.js`.

## Items
- DONE - Drop `benchmark` from the stage table in `app/renderer/app.js`; app unit tests pass
