# 0096 The canonical copy of a duplicate is the best filled, not the best scored

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

The owner, 2026-10-24: "in a duplicated vacancy pick one, the best
filled, and work with it alone, whatever happens: a re-read by the AI, a
stretch score, anything."

## Implementation
- `tools/kb.py`, `mark_duplicates`: the canonical is the best-filled copy
  (`_filled`): the copy the person answered (applied, rejected, bugged…);
  then a text of 600+ characters (`score.TEXT_READ_MIN_CHARS`, read) before
  a shorter one; then more facts among `FILLED_FACTS` (salary, employment
  types, workplace type, posted date, apply URL, company URL, location,
  tags); then the longer text; then the first seen; then the id. Nothing
  the scoring, the class or the model made of a copy takes part, so a
  rescore, a stretch's points or an AI answer cannot move the choice. A
  copy's own facts can: a later fetch that reads a copy's page makes it
  better filled.
- `tools/db.py`, `load_vacancies`: the person's answer when it is not
  "new" comes as the transient `_feedback` (never saved into the facts,
  `TRANSIENT_KEYS`). `kb.merge_vacancy` keeps it when the source serves the
  copy again in the same run.
- Tests: `tests/test_kb.py` (fill beats score and stays after a rescore and
  an AI refusal; facts, then the text length; the answered copy stays, also
  after a re-fetch), `tests/test_db.py` (loaded, not saved).
- Docs: `schemas/db.sql`, `docs/ARCHITECTURE.md` (the rule, and "The
  best-scored copy as the canonical one" among the things tried).

Counted on the base before the next run (read-only, 2026-10-24): the
canonical changes in 667 of 6,979 SHARP groups and 510 of 4,985 PARTSHARP.
SHARP: 650 from one unlisted copy to another; 68 to a read copy from an
unread one; 3 to the copy the person answered (the "bugged" ones that were
hidden duplicates); 7 to a listed copy; 7 from a listed copy to a refused
one: in all 7 the listed copy was unread ("remote unconfirmed" for want of
a text) and the new one is read and says office, on site or French (Accenture
France, CreateFuture, FR Consultancy, Methods, VirtueTech, Ivalua; Incedo's
new copy has more facts and says on site). The next run marks the groups
again; a new canonical without a text gets its description fetched and read
in the runs that follow, within the usual limits.

## Items
- DONE - The owner decides (2026-10-24: the best-filled copy, whatever happens)
- DONE - The canonical by fill, in `kb.mark_duplicates`, with the person's answer first
