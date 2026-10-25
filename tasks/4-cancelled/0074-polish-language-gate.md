# 0074 A posting that asks for Polish alone is not refused

Source: the agent, 2026-10-22, scoring the justjoin.it fetcher
Cancelled: the owner, 2026-10-25: more phrases only add refusals, and a Polish posting that slips through is one the person sees and turns down; the language read moves to the screening model (task 0084)
Scope: config

## Business
justjoin.it lists the languages an offer asks for; 35 of its 118 remote
.NET offers on 2026-10-22 listed Polish. The fetcher writes them as
"Languages: Polish and English skills required", which the scoring's
"English and another language" rule refuses. An offer that lists Polish
without English passes: SHARP's criteria and config/derivation/languages.yaml
name no Polish phrases. The person does not speak Polish.

## Implementation
Polish phrases in config/derivation/languages.yaml and in the templates'
language gate, the way German is handled; a template version step.

## Items
- TO DO - Count the offers in the base that ask for Polish alone after a few runs; add the phrases if any reach the shortlist
