# 0096 A rejected copy can hide a listed copy of the same posting

Source: the agent, 2026-10-24, explaining duplicates to the owner (task 0042)
Scope: tools

## Business
`kb.mark_duplicates` groups vacancies by the exact normalised (company,
title) pair and keeps the best-scored one; the others get `duplicate_of`
and drop out of the list and of the AI read. The score alone decides, not
the class: a rejected copy with a higher score hides a listed one.

LinkedIn posts one job once per country, each under its own id. The copies
differ in location (reachable or not) and in the AI's read:
- Deel "AI Engineer, Backend": Israel copy worth a look (31, a stretch at
  -4), UAE copy rejected (35, the AI said "no"). The UAE copy is canonical:
  the kept one is hidden.
- The same for Deel "Back-End Engineer" (Belarus kept, Austria rejected)
  and Doit "Lead Engineer - Singapore".
- How both got read: the stretch's -4 dropped the read copy below the
  other, which became canonical and was read in a later run (2026-10-21,
  05:28 and 13:36).

The base on 2026-10-24, listed copies hidden behind a canonical that is not
listed: SHARP 948 (905 remote unconfirmed, 32 AI unscreened, 8 behind low
priority, 2 worth a look, 1 long shot), PARTSHARP 942.

## Implementation
Proposed: the canonical is chosen by the class first (a listed class before
low priority, low priority before rejected), then the score, then the
first seen. Open: whether copies whose location facts differ (one country
each) are one posting at all.

## Items
- TO DO - The owner decides
