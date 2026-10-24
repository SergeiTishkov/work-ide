# 0098 "Remote not confirmed" is not listed in the app

Source: the owner, 2026-10-24
Scope: app

## Business
The owner, 2026-10-24: "remove the Remote not confirmed category from the
UI. The class can stay in the data, but I never look at these vacancies, so
they can go from the app."

## Implementation
- `schemas/queries.sql`, `view_pool`: the rows from the selection leave out
  the class `remote_unconfirmed` (NOT LISTED in the header), so the list,
  every drop-down's numbers and the "Identity fit" drop-down never see it.
  An application of that class is still listed (applications come from
  their own branch). `tools/selections.py` reads the same text, so the CV
  auto batch (`cv_auto.py`) no longer picks them either.
- The data keeps the class: the scorer, the selection (`selection_items`),
  the reports and the clean-up's class filter are unchanged.
- `app/renderer/app.js`: out of `CLASS_KEYS` and `STABLE_CLASSES`;
  `UNLISTED_CLASSES` keeps it out of the drop-down also when a view saved
  before names it. The locale text `class.remote_unconfirmed` is gone.
- Tests: `tests/test_selections.py`, `app/test/unit/store.test.js` (not
  listed, not counted, still in the selection; an application stays),
  `app/test/ui/app.spec.js` (the drop-down has no such row).

## Items
- DONE - Out of the list, the counts and the drop-down; kept in the data
