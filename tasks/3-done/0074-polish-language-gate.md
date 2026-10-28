# 0074 A posting that asks for Polish alone is not refused

Source: the agent, 2026-10-22, scoring the justjoin.it fetcher
Scope: config

## Business
justjoin.it lists the languages an offer asks for; 35 of its 118 remote
.NET offers on 2026-10-22 listed Polish. The fetcher writes them as
"Languages: Polish and English skills required", which the scoring's
"English and another language" rule refuses. An offer that lists Polish
without English passes: SHARP's criteria and config/derivation/languages.yaml
name no Polish phrases. The person does not speak Polish.

Closed as done without a change of its own (the owner, 2026-10-28): task
0084 solved it. The screening model names the languages a posting is
written in and requires, and the program refuses one the person does not
know; no Polish phrases were added. Checked on 2026-10-28 in SHARP's base:
of 32 postings the model read with Polish, the 26 that require Polish or
are written in Polish alone are refused for language; the other 6 are
written in Polish and English and require English only: 2 refused on other
grounds, 4 kept (task 0099).

## Items
- DONE - Solved by task 0084; checked on 32 postings with Polish (2026-10-28)
