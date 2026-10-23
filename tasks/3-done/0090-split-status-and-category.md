# 0090 Freshness and Role are drop-downs of their own

Source: the owner, 2026-10-23
Scope: app

## Business
The owner, 2026-10-23: "Status" and "Category" each hold several filters
in one drop-down; split them.

Before:
- "Status" held the freshness (fresh, earlier) and the status groups (new;
  applications; denied) in one list.
- "Category" held the classes and the kinds of role (stack, off stack,
  stretch) in one list.

## Implementation
- `app/renderer/app.js`:
  - "Freshness" (`fresh-filter`): fresh and earlier, with "Fresh and
    earlier" for both. It sits before "Status".
  - "Status" (`filter`): the status groups only.
  - "Category" (`fit-filter`): the classes only.
  - "Role" (`role-filter`): the kinds of role, with "All roles". It sits
    after "Category".
  - The view and the listing call are unchanged: `fresh`, `statuses`,
    `fits` and `roles` as before.
- Locales: `filter.fresh_legend`, `filter.fresh_all`, `filter.role_legend`;
  `filter.group.freshness` removed.
- Eight boxes of 205px take 1724px. A narrower window wraps the row of
  filters (as before, the row wraps).
- Tests: `app/test/ui/app.spec.js`, `app/test/ui/dropdown.spec.js`,
  `app/test/smoke/electron.spec.js`, `app/test/helpers/dropdown.js`.

## Items
- DONE - "Freshness" is a drop-down of its own, out of "Status"
- DONE - "Role" is a drop-down of its own, out of "Category"
- DONE - Tests: UI 138, unit 98, Python 1490 pass
