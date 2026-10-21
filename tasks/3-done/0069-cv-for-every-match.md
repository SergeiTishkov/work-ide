# 0069 Every matching vacancy has its CV and cover letter, not only the fresh ones

Source: the owner, 2026-10-21, with a screenshot of the Category drop-down
(Hot leads 2, Worth a look 11, Long shots 3): "we do not generate CV/CL for
every vacancy that fits worldwide remote. Generate for all of them, there
are only 10-15 a week. The only filter: outside 'remote not confirmed',
status 'not applied or denied', not a freelance marketplace. Every such
vacancy must have a CV/CL. Generate for the ones in the list now."
Scope: tools, identity:sharp

## Business
A vacancy that reaches the shortlist gets its CV and cover letter whenever
it gets there, not only when the collection that brought it was its first.
Until now a filter already applied took the fresh vacancies only (task of
2026-10-13, "fresh, and the catch-up"), so a vacancy that rose into a class
later — a rescore, a description fetched, the AI read of a stretch role —
never got documents: on 2026-10-21, 14 of the list's 16 matching vacancies
had none.

A filter can also name the kinds of company it takes, the groups of the
app's "Company" drop-down (`config/company_kinds.yaml`): marketplace,
agency, reposter, other. A freelance marketplace (A.Team, Lemon.io,
Proxify) is one application per marketplace, not per vacancy.

## Implementation
`tools/cv_auto.py`: every vacancy of the latest selection with no answer
that matches a filter, fresh or not; documents already made or found gone
are not made again (as before). The applied-filters bookkeeping
(`cv_auto.json`, `--remember`, `--all`) goes; `cv_batch.py`, `taskd.py` and
`schedules.py` lose the "all" mode it needed. New filter key
`company_kinds`. SHARP's profile: one filter, the three shortlist classes,
every company kind but marketplace.

## Items
- DONE - `cv_auto.pick`: every match of the latest selection; `company_kinds`; the fresh-only bookkeeping removed (cv_batch, taskd, schedules); tests; docs
- DONE - SHARP's `cv.auto`: hot leads, worth a look, long shots; no marketplaces (local profile; `cv_auto.json` of both identities removed: nothing reads it)
- DONE - Documents for the vacancies in the list now: 13 vacancies, 26 documents made, 0 gone, 0 failed (task #3, 2026-10-21)
- DONE - A collection also queues a batch after the rest of the base: its AI read raised AI Engineer, Backend at Deel into Worth a look on 2026-10-21, and no batch followed it
