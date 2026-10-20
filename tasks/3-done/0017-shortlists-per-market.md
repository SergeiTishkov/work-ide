# 0017 Several shortlists, one per market

Commits: a674e99 7c3c66c 8f464eb (2026-09-04 — 2026-10-06)
Source: the owner: one list mixes a Singapore agency posting with a UK contract at four times the rate

## Business
One list sorted by score mixes markets with very different pay and terms.
The person wants to read one market at a time: worldwide first (for someone
contracting from outside every market it is the one where geography is no
obstacle), then the UK, the Gulf and so on, and everything together when
they want it. No vacancy may fall out of every list when a market is added.

## Implementation
`config/derivation/market_groups.yaml` (which countries form a group, true
for everybody) and `<prefix>_reports.yaml` (which groups deserve a list, a
judgement per search). `rest` is computed from what the others claimed; a
test asserts every vacancy reaches a list. Market names translated per
interface language; "Everything together" became "All regions together".
In the app, markets are the Region drop-down.

## Items
- DONE - Market groups and per-identity report segments
- DONE - Rest computed, every vacancy in some list
- DONE - Market names in the person's language
