# 0051 Every change is a task, every commit names its task

Source: the owner, 2026-10-20

## Business
The list of work is only useful if nothing happens outside it. Every fix,
however small, becomes a task before it is made, and every commit says which
task it belongs to, so the history of a behaviour can be read from its task
and the task's items show what was really done. The one kind of commit with
no task is one that only writes, plans or moves tasks; a change to the task
system itself is ordinary work and has a task. A task in triage is not
agreed work and covers no change outside `tasks/`.

The rule holds for a person and for an agent alike, so it is checked by git,
not left to memory.

## Implementation
`.githooks/commit-msg` (turned on with `git config core.hooksPath
.githooks`): a `Task: NNNN` line, the task exists, the commit changes its
file, triage tasks cover only `tasks/`; commits of task files only, merges,
reverts and fixups pass. `tests/test_commit_hook.py` runs the hook through
git in a scratch repository and fails while the hook is off in this clone;
`tools/doctor.py` warns. `tools/tasks.py` (`next`, `find`, `new`, `log`).
The `task` skill is the procedure; CLAUDE.md §12 "Tasks" and
`tasks/README.md` hold the rule. `source_doctor.py publish`, the one tool
that commits, takes `--task` and commits the task file with the repair.

## Items
- DONE - The rule in CLAUDE.md and tasks/README.md
- DONE - The commit hook and its tests
- DONE - `tools/tasks.py` and the `task` skill
- DONE - Source doctor publishes with its task
- DONE - Hook turned on in this clone; doctor warns when it is off; README install step
- DONE - The hook keeps LF line endings in every clone (`.githooks/.gitattributes`): `sh` reads a CRLF script as broken
