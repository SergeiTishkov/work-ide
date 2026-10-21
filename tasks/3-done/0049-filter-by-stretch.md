# 0049 Show only stretch roles, or none

Source: the agent, 2026-10-20, with the stretch badge

## Business
Stretch roles carry a badge in the list, but the person cannot read them
apart from the rest, or hide them on a day they want only on-stack roles.

## Implementation
The owner, 2026-10-21: wanted. A second group in the "Category" drop-down,
"Every kind of role": on the CV's stack, another stack the CV fits, a
stretch, each with its count under the other drop-downs. The view dimension
`roles` (ROLE in schemas/queries.sql) comes from `view.stretch.fit`; null is
every kind, as with the boards and the ages.

## Items
- DONE - Decide with the owner whether it is wanted after the first stretch review; write the plan here
- DONE - The `roles` dimension in the view queries, selections.py and the app's store, with `view_roles` for the counts
- DONE - The role group in "Category", its counts and the closed box's text; tests in Python, unit and UI
