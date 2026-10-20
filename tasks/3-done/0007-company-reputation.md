# 0007 Company reputation: known where it matters, collected on request

Commits: 5f5a5ac e2b62da f3a2a20 cf7b113 (2026-08-04 — 2026-10-18)
Source: the owner noticed a rebuilt shortlist with no reputation at all

## Business
A platform whose reviews say "late payments" was collecting +14 and leading
the report; for a contractor late payment is not a nuance. Then: 55
companies in the top classes, reputation known for none. The report wrote
"reputation not checked", which reads as a fact about the company rather
than a gap in the process. "Checked, nothing credible exists" is a different
answer from "nobody looked" — the owner asked for that state by name.

Later the owner moved the lookup out of every collection: the person asks
for it on the vacancy they are considering.

## Implementation
Company age and enrichment wired into the pipeline (`company_intel` existed
and nothing called it: 22 of 1083 companies had an age). A red flag costs
points. Three states: found / insufficient sources / not collected. Review
sites answer 403 behind Cloudflare and the Glassdoor API is 410, so the
lookup is an agent with web search: `tools/reputation_lookup.py` (Sonnet,
WebSearch and WebFetch only), run from the card's "Collect reputation"
button in a lane of its own; the result rescores that company's vacancies.

## Items
- DONE - Company enrichment and age in the pipeline
- DONE - A reputation red flag costs points
- DONE - Three states, and "checked, nothing found" recorded
- DONE - 46 companies of the shortlist looked up by hand (24 rated, 22 not found)
- DONE - Reputation on request from the app, out of the collection
