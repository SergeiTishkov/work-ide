# 0023 One SQLite base for every identity

Commits: 8f2eae3 771b29e c0ec538 ac64313 5b4e304 ee6576a (2026-09-29 — 2026-10-05)
Source: the desktop app needed to write feedback while the pipeline runs

## Business
The person answers on vacancies in the app while a collection may be
rewriting the base. With one 150 MB JSON file per identity every click
rewrote the whole file, and two writers could lose each other's work. A
vacancy fetched for one search is also a vacancy for the other: it should be
stored once and judged by each identity on its next run. What the person
learned about a vacancy (its description, liveness, application channels)
must survive a re-fetch — every re-fetched LinkedIn card was losing its
description.

## Implementation
`data/workide.sqlite`: `vacancies` holds what a posting is,
`vacancy_identity` what one identity made of it (score, class, views,
answer, funnel). `kb.load_vacancies()` keeps its dict contract, so the
pipeline did not change. Selections record what each run showed. Schema
migrations run per version (the first rebuilt a table for a new status).
One status system: the app's answers; the old manual statuses were removed.
The merge was rehearsed on a copy: 46,603 vacancies, 107 listings equal
under old and new queries.

## Items
- DONE - JSON to SQLite, the dict contract kept
- DONE - Selections and feedback in the base
- DONE - Per-version schema migrations
- DONE - Learned facts kept on re-fetch; one status system
- DONE - One base shared by every identity
