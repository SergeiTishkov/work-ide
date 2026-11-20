# 0135 The emergency file; a kept LinkedIn fetch merged without fetching again

Source: the owner, 2026-11-21 (the incident: the agent, 2026-11-20)
Scope: tools, rules

## Business
Queue task 296 (the Friday collection's LinkedIn part, SHARP) started at
01:00 on 2026-11-20 with the code of that moment (schema 11). It fetched
for 21:59 hours: 189 query pairs, 4,613 pages, 17,240 records, 1,328
answers 429. During the day task 0131 was merged (schema 12) and the base
was upgraded by a process running the new code. At 22:59 the pipeline
reached "wait for the base", got SchemaVersionError ("schema version 12,
newer than this code (11)") and ended failed. The records were kept in
data/identities/sharp/runs/linkedin_fetched.json, but the next LinkedIn
run would have fetched the days again instead of merging them, and nothing
told anyone the file was there. The CV/CL batch after it (#299) was skipped.

The owner, 2026-11-21: what was fetched is not lost when the base changes;
it is kept, and the incident is written to a file in the repository's root,
emergency.md: serious breakdowns of the scripts, appended as text, entries
apart by a line of underscores. It is never committed (a rule, and the
commit hook). An agent fixes what has an obvious, clear fix and reports it,
reports the rest, and reminds the owner of every open entry each time it
ends its work or commits, as long as the owner leaves it open.

## Implementation
- `tools/emergency.py`: `report(title, text)` appends, `entries()` reads,
  `python tools/emergency.py` lists, `... add TITLE TEXT` appends.
- `.gitignore` holds `/emergency.md`; `.githooks/commit-msg` refuses a
  commit that stages it and lists its open entries at every commit.
- The rule: CLAUDE.md §12, "Emergencies".
- `pipeline.py --linkedin --staged` (queue: `linkedin` with
  `{"staged": true}`): merges the kept fetch without fetching. A LinkedIn
  run that fails after its fetch was kept writes an emergency entry with
  the file and that command. The kept file was the "other storage" the
  owner asked for: of the runs, only LinkedIn fetches before it opens the
  base; the others open it first, so a schema error stops them before any
  fetch.

## Items
- DONE - The emergency file, the hook, the rule; `--linkedin --staged` and the entry on a failed merge; tests
- TO DO - The fetch of 2026-11-20 merged (queued with `{"staged": true}` after the rest run)
