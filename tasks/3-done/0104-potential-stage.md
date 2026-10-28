# 0104 A potential stage: a question the owner checks in practice

Source: the owner, 2026-10-28, while agreeing the language rule of task 0042
Scope: tasks, rules, docs

## Business
Some questions are not decided in a conversation: the owner wants to look
at real selections first and then say what to do. The first one: whether a
programming language named in a vacancy's title should count as stressed
expertise (a "no") or stay a stretch. Such a question is not an idea for
triage and not agreed work; it waits for the owner's check.

`tasks/0-potential/` holds them. From there a task moves to any stage:
triage, to-do, done or cancelled. The owner may decide on the spot how to
close it, and the agent does it and closes it at once.

## Implementation
- `tools/tasks.py`: the stage `potential`, a new task can start there.
- `.githooks/commit-msg`: a potential task, like triage and cancelled, covers
  no work outside `tasks/`.
- Tests, `tasks/README.md`, CLAUDE.md section 12, the `task` skill,
  docs/ARCHITECTURE.md.

## Items
- DONE - The stage in tools/tasks.py, the hook and their tests
- DONE - The README, CLAUDE.md, the task skill and docs/ARCHITECTURE.md
