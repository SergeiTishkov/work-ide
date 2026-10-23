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

The owner, 2026-10-24: keeping a copy apart makes sense only if copies
differ in worldwide remote reach (an office in Spain hiring in the EU
only, one in Czechia hiring worldwide), and that is unlikely. Asked to
measure it.

Measured on SHARP, 2026-10-24 (6,979 groups, 23,205 copies):
- Only the canonical copy gets its description fetched and read
  (enrich_descriptions and the AI skip duplicates). A copy with no text is
  "the employer never states this is remote" or "remote unconfirmed"; the
  canonical, read, is refused for what the text says. Most of the 948
  "hidden listed copies" are this: unread copies behind a read refusal
  (e.g. Akkodis: the read copy says on site, five unread ones are remote
  unconfirmed).
- Groups with two or more read copies (600+ characters): 918. The scripts'
  location verdict is the same in 849 (92.5%), different in 69. In the
  examples looked at, the difference is the location field, not the
  employer's offer: an aggregator writes "Remote" where the employer's ATS
  says "Remote, United Kingdom" (GitLab, a dozen), or both offices are out
  of reach anyway ("US Remote" and "Dublin", Stripe). No copy was found
  that is reachable worldwide while another is not.
- Groups with two or more AI reads: 23. `location_ok` the same in 20; the
  3 others are the same location read twice (TalentHop, Iris) and Deel
  (Austria "unclear", Belarus "yes"). The verdict differs in 5: the model's
  noise on a borderline fit, as the Deel and Doit copies.

So a class-first rule would be wrong: it would put an unread copy (remote
unconfirmed for want of text) above the read one refused for what it says.

## Implementation
Proposed: the canonical is the copy that knows the most: a read text
before none, an AI answer before none; among equals, a listed class before
low priority before rejected; then the score; then the first seen. The
Deel and Doit copies (both read, both answered) then show the kept one;
Akkodis keeps its read refusal.

## Items
- TO DO - The owner decides
