# 0012 Personal weights and overrides on top of a shared search

Commits: a07c5a6 1959f8f 0b0b9e6 cd810b7 c72a394 8e5092d (2026-08-05 — 2026-08-06)
Source: the owner's question: can something bad in general be fine for me?

## Business
Two developers with the same ".NET/JS" line can be strong in different
halves; a country can be preferred for tax residency or a pension record.
Those are facts about the person, not the search. And a red flag is not bad
for everyone: "unpredictable work availability" is a threat to someone living
on the income and a promise to someone who wants to be left alone — for this
owner two such flags went from -22 together to +2.

What an override must not do is rescue a vacancy a gate refused: if a
generous weight could lift one, a single number would bring back everything
filtered out on the merits.

## Implementation
One resolver for settings: defaults -> template -> personal, with provenance
for every value (`--conflicts` lists keys set by more than one layer). Lists
replace rather than append; an explicit null deletes; frozen keys
(`config/settings_policy.yaml`) cannot be lifted by a later layer, and the
attempt fails loudly. Red flags resolve against a shared catalogue with a
weight per kind; the sign may flip. Template text that reaches the report is
translated by a personal override. `docs/OVERRIDES.md`.

## Items
- DONE - A personal market bonus
- DONE - Personal stack weights (.NET +12, JS backend -10, counted once per group)
- DONE - Red flags weighed per kind, overridable both ways; gates beyond override
- DONE - One deterministic resolver with provenance and frozen keys
