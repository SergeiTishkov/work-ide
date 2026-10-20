# 0055 Every task names its scope; tickets only for committed work

Source: the owner, 2026-10-20 ("every ticket from now on must state its
scope: an identity, the tools, the rules, the docs or something else; several
are fine; do not forget `other`. Purely local work needs no ticket. A ticket
that needed no commit is simply deleted from git; do not rewrite history")
Scope: tasks, rules

## Business
A list of tasks says what each one is about only through its title, so
"everything that touched the sharp identity" or "every change to the rules"
is a full-text search with misses. Each task now states its scope on one
line, from a short fixed list, so the list can be read by area.

The owner also drew the line of what is a ticket: a ticket is for work that
ends in a commit. Checking or fixing local data, running a collection or
answering a question has none. A ticket that turned out to need no commit is
deleted from git in a commit of its own; history stays as it is, and its
number is not handed out again.

## Implementation
A `Scope:` line under `Source:` with one or more of `identity:<prefix>`,
`tools`, `app`, `config`, `rules`, `docs`, `tasks`, `other`, comma-separated.
Required from task 0052 on (0052-0054 get one); older tasks are left as they
are. `tools/tasks.py` holds the list and the check, `new` requires
`--scope`, `next` skips numbers that only git history still knows.
`tests/test_tasks.py` checks every task. The rule goes into
`tasks/README.md`, CLAUDE.md §12 and the `task` skill.

## Items
- DONE - Plan
- DONE - Scope list and check in `tools/tasks.py`; `new --scope` required
- DONE - A deleted task's number is not handed out again
- DONE - `tests/test_tasks.py` checks the scope of tasks from 0052 on; 0052-0054 get one
- DONE - Hook test: deleting a task that needed no commit needs no task line
- DONE - Rule in `tasks/README.md`, CLAUDE.md §12 and the `task` skill
