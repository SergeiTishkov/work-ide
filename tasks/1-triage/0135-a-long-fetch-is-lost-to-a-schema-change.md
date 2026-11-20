# 0135 A long fetch is lost when the base's schema changes under it

Source: the agent, 2026-11-20
Scope: tools

## Business
Queue task 296 (the Friday collection's LinkedIn part, SHARP) started at
01:00 on 2026-11-20 with the code of that moment (schema 11). It fetched
for 21:59 hours: 189 query pairs, 4,613 pages, 17,240 records, 1,328
answers 429. During the day task 0131 was merged (schema 12) and the base
was upgraded by a process running the new code. At 22:59 the pipeline
reached "wait for the base", opened it, got SchemaVersionError ("schema
version 12, newer than this code (11)") and ended failed. The records were
held in memory only: `data/raw/linkedin/` has no file of that day, so the
whole fetch is lost. The CV/CL batch after it (#299) was skipped.

## Items
- TO DO - Decide with the owner: the fetched records written to data/raw before the base is opened (a later failure then loses no fetch), and/or no schema upgrade of the base while a pipeline task runs (the upgrade waits for it)
