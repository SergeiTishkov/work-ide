# 0130 RemoteOK is a paid board; a free board's copy is the primary one

Source: the owner, 2026-11-20
Scope: config, tools, docs

## Business
The owner, 2026-11-20: move remoteok.com to the paid sources. And when one
vacancy is found on a paid and on a free board, always keep it under the
free one as the primary record: an application cannot be made on a paid
board; the owner has to find the company's own vacancies page anyway.

Measured 2026-11-20, SHARP: 21 duplicate groups had a paid canonical copy
and a free twin (19 on We Work Remotely, 2 on RemoteOK; the free copies on
LinkedIn 7, 4dayweek 6, Working Nomads 5, Remotive 1, an ATS board 1, an
RSS board 1). None of the 21 was answered by the owner; 18 canonical copies
were rejected, 3 hot leads. RemoteOK has 198 records in the base.

## Implementation
`paid: true` on remoteok in `config/sources.catalog.yaml`. `kb._filled`
puts a free board's copy first, ahead of the person's answer: the owner's
"always". A paid copy the person answered loses to a free twin, which then
shows without the answer (none such on 2026-11-20). The choice is recomputed
on every run, so the base follows on the next collection or rest run.

## Items
- DONE - remoteok `paid: true`; `kb.mark_duplicates` prefers a free board's copy; tests (tests/test_kb.py, tests/test_selections.py); docs (ARCHITECTURE, SOURCES, the catalogue's header)
