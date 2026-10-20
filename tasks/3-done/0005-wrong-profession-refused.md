# 0005 A vacancy for another profession is refused, not ranked low

Commits: 164a6a2 b9e4112 8dda5a1 e2b62da 127815b 0ae9475 7e75494 (2026-08-04 — 2026-10-05)
Source: the owner, reading the report

## Business
The owner found Sales Manager, Business Partner Analyst, Patient Outreach
Specialist, Data Entry, Senior QA Engineer, a Technical Project Manager and a
Senior Security Engineer (SIRT) in their shortlist. Most were being refused
by accident — on location — and would have passed if remote. A wrong
profession is a 0% chance and must be a refusal on its own merit; a soft
penalty drowns in generic bonuses elsewhere in the posting.

The opposite mistake costs as much: ".NET AppSec Engineer", "Senior Software
Engineer (WPF, Firmware & Systems)", ".Net Technical Consultant" and
"Analytics Engineer" (Spark and Databricks are on the CV) are real work for
this person. A blanket rule over security titles would have removed fifteen
wrong vacancies and five right ones.

## Implementation
`role_relevance_signal` in criteria, three tiers: a hard list no stack can
rescue (sales, analyst, outreach, QA, mobile, project manager, VP); a soft
list cancelled by a developer word; and `wrong_discipline_title_patterns`
(security, data science, ML, embedded, support engineering) that fires
unless the vacancy names the core stack or is real data work (two context
words, since one stray "ETL" switched the filter off). When the title holds
no profession at all ("YC 19" from a mis-split HN header), the start of the
description is read.

## Items
- DONE - Professions refused on their own merit, specific patterns rather than bare words
- DONE - QA and mobile in the hard tier; a mobile product behind a neutral title gated
- DONE - A third tier for another branch of engineering, rescued by the core stack
- DONE - The description read when the title names no profession
