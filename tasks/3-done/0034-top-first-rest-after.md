# 0034 The top within an hour, the rest after

Commits: cf7b113 4ce4b86 992f1ca (2026-10-17 — 2026-10-18)
Source: the owner: a full cycle took hours before anything new could be read

## Business
What the person reads first is the top of the shortlist; it should be fresh
within about an hour. The tail of the base (rescoring everything, missed
LinkedIn days) follows without anyone waiting for it. After every
collection the person is told how many days were collected.

## Implementation
`pipeline.py --top` (every source, rescoring the top classes and what the
run brought, enrichment with budgets, AI check, reports) and `--rest`
(missed LinkedIn days, the full tail). They exclude each other. LinkedIn's
window runs from the last good fetch; its time budget was later replaced by
a run of its own (see 0041 LinkedIn lane). `closed_sources` are not
fetched.

## Items
- DONE - `--top` and `--rest`
- DONE - LinkedIn window and gap state
- DONE - "Collected N days" in every result
