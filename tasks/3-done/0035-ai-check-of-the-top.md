# 0035 A model reads the top before the person does

Commits: cf7b113 7f77436 (2026-10-17 — 2026-10-20)
Source: the owner: the top held vacancies a person rejects in one reading

## Business
Rules miss what a reader sees at once: a posting that is not a job, "remote"
that means remote teams, a role nothing like the CV. A cheap model reads
each top-class vacancy against a brief of the person's search and rejects
with a reason and a quote; "keep" changes nothing. The brief is written from
the CV, the profile and the owner's rejection reasons. First top run: 400
read, 388 rejected, $3.14.

## Implementation
`tools/ai_brief.py` (Opus writes the brief, rewritten when its inputs
change), `tools/ai_screen.py` (Haiku through `claude -p`, no tools,
6 workers, results stored with hashes of the text and the brief). The
scorer's computed time-zone fact goes to the model: a prompt alone did not
stop it misreading time zones (tried twice on 2026-10-20).

## Items
- DONE - Brief from the person's documents
- DONE - Screen of the top classes, reject as a dealbreaker with reason and quote
- DONE - Time-zone fact passed from the scorer
