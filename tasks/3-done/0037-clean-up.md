# 0037 Clean up the base

Commits: cf7b113 (2026-10-17)
Source: the owner: the base passed 57,000 vacancies

## Business
Old refused vacancies make the base slow and large. The person deletes by
age, status and class, sees the count first, and nothing they acted on is
lost: a vacancy goes only when it matches in every identity holding it;
funnel vacancies and unreviewed answers stay.

## Implementation
`tools/cleanup.py` (with `--dry-run`, `--json`) and a "Clean up" popup in
the app; VACUUM afterwards.

## Items
- DONE - Delete by age, status and class, counted first
