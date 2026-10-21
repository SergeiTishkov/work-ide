# 0073 The ITAR dealbreaker fires inside Mitarbeiter and military

Source: the agent, 2026-10-22, scoring the freelancermap and justjoin.it fetchers
Scope: config

## Business
A hard dealbreaker refuses a vacancy outright. The keyword "itar" (export
control, in effect a US person) matched as a substring, so it refused
German postings saying "Mitarbeiter" or "Mitarbeit" and a posting saying
"military": 11 of the first freelancermap and justjoin.it records, none of
which named ITAR. A refused vacancy the person could take is the costlier
mistake.

## Implementation
" itar" (the leading space is a word boundary, score.keyword_needle) and
"(itar" in the hard dealbreakers of the three templates and in the US
citizenship phrases of config/derivation/regions.yaml. The templates go up
a version (sharp 30, partsharp 17, blank 6) with a changelog entry; sharp
and partsharp were moved onto them with `tools/templates.py update`. A
test checks every template's hard dealbreaker keywords against the words
that hid them. Rescored on 2026-10-22: no verdict on the 232 new records
names ITAR.

## Items
- DONE - Plan
- DONE - The keyword as a word in the templates and the derivation table; template versions and changelogs
- DONE - A test against keywords hiding inside ordinary words; sharp and partsharp updated
