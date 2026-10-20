# 0021 A second identity for paid part-time side work

Commits: 355d965 7337c6b af92843 5a5246b 38a1490 (2026-09-13 — 2026-10-05)
Source: the owner

## Business
The same CV, the opposite search: money first, graded by hourly rate;
part-time required; interesting work (crypto, AI, distributed systems) a
small plus, dull work neutral; roles this CV will not be hired for cut
however interesting. A board's or employer's statement of hours decides;
silence goes to "Hours not confirmed" with the score untouched. Full time
said in other words ("Full-time & Long-term contract", "contract to hire")
is full time.

Named PJOICE first, renamed PARTSHARP (part-time SHARP) on 2026-10-05.

## Implementation
Machinery inert for any identity that does not ask for it: `engagement_fit`,
a normalised `employment_types` field filled from each board's own
classification, `extra_signals` (axes declared in configuration),
`hourly_equivalent_tiers`. Sources: Remote Rocketship and a Himalayas search
mode. Template `partsharp-part-time-dotnet-side-work`.

## Items
- DONE - Engagement gate and its own section
- DONE - Employment types from the boards
- DONE - Pay graded by rate; interesting work as declared axes
- DONE - Part-time sources
- DONE - Full-time wordings read from the first runs
