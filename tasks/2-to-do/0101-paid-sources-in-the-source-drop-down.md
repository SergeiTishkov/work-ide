# 0101 Paid and free boards in the "Source" drop-down

Source: the owner, 2026-10-26
Scope: config, tools, app

## Business
The owner, 2026-10-26, on freelancermap.de and weworkremotely.com: "these
two sources are paid: they ask me to pay before they assess me. Let us make
two subcategories of sources, paid and free."

## Implementation
- `config/sources.catalog.yaml`: `paid: true` on the two boards, a fact of
  the catalogue (`common.CATALOG_FACTS`), not an identity's choice.
- `tools/selections.py`: with the websites, the selection writes the paid
  boards to `meta` (`paid_sources`); the app reads the database only.
- `app/main/store.js`: each board of the drop-down comes with `paid`.
- `app/renderer/app.js`: "All sources" on top, "Free" and "Paid" under it
  with their boards, as in the "Company" drop-down; a kind with no board
  in the view has no row.
- Tests: `tests/test_selections.py`, `app/test/unit/store.test.js`,
  `app/test/ui/app.spec.js`.

## Items
- TO DO - The catalogue fact, meta, the store, the drop-down; tests
