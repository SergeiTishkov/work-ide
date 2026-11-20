# 0137 The "Identity fit" drop-down lists the identity's own classes

Source: the owner, 2026-11-21
Scope: tools, app

## Business
The owner, 2026-11-21: "Hours not confirmed" belongs to another identity;
every fit of this identity is to be shown, the others hidden. Since task
0133 every class was listed with 0. Two classes depend on the criteria:
"Never say never" exists only with `classification_thresholds.never_say_never`
(task 0124), "Hours not confirmed" only with an `engagement_fit` whose
`unconfirmed_policy` is not "accept". The app reads the database only, so
every selection now writes the identity's classes to meta
`listed_classes:<prefix>`, and the drop-down lists those. A class outside
them that holds rows is still listed (no row is hidden with no way to see
it); with no meta row yet (before the next selection) every class is.

## Items
- DONE - `selections.listed_classes` / `write_listed_classes`, the query, `store.listedClasses`, the IPC, the renderer filter
- DONE - Tests: pytest, store unit test, UI test; ARCHITECTURE
