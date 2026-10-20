# 0019 Descriptions are read where they decide something

Commits: 5f5a5ac 0c5218a 7337c6b a44601e a2928c9 cf7b113 (2026-08-04 — 2026-10-18)
Source: the agent's measurements of what was being decided unread

## Business
Many boards send a card without the text, and a vacancy judged on its title
alone is judged on a guess: 447 of 621 LinkedIn results were refused for "no
familiar language"; "Remote not confirmed" held 1268 vacancies, more than
every confident class together, in a class that exists because nobody read
whether the work is remote. Reading costs one request per vacancy, so it has
to go where the answer can change a verdict.

## Implementation
`tools/enrich_descriptions.py` with readers per source (LinkedIn pages,
Reed's schema.org markup, Remote Rocketship, devitjobs' detail API) and
queues by verdict: the top first, then "description wanted" (stack unread),
then unconfirmed remote. Reading happens after scoring, with budgets per run
(300 missing descriptions + 200 "description wanted" in the top run). An
enricher that cannot read a source no longer marks the vacancy tried for
ever.

## Items
- DONE - Job pages read for promising cards
- DONE - Readers per source; a source it cannot read is skipped, not marked tried
- DONE - Queues by verdict after scoring, with budgets
- DONE - Engagement re-read for a search with an engagement gate
