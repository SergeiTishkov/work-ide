# 0079 The feedback review writes tickets, never code

Source: the owner, 2026-10-22
Scope: rules

## Business
The owner: the feedback review never changes code by itself. It may run
tasks and correct data with the agent, but every change to code goes into a
ticket: a triage task named `<number>-review-feedback-...`. It may not write
changes into the code or make changes in git. The owner decides which
tickets to take into work.

Until 2026-10-22 `/feedback` told the agent to fix the cause in the criteria
or `tools/score.py`, add a test and rerun the suite.

## Implementation
`.claude/commands/feedback.md` rewritten: what the review may do (read, run
the tools and tasks, change data under `data/`, write new triage tickets)
and may not (edit `tools/`, `tests/`, `app/`, `config/`, `schemas/`,
`identity-templates/`, `local-identities/`, `docs/`, the rules, existing
tasks; any git command that changes something). A ticket is made with
`tools/tasks.py new triage review-feedback-<slug>` and holds the vacancy
ids, the quotes, the proposed fix and its test. `mark-reviewed` names the
ticket in its outcome. `tests/test_feedback_command.py` keeps the rule in
the command file.

## Items
- DONE - The command rewritten; the rule tested
- TO DO - The first review under the rule (2026-10-22)
