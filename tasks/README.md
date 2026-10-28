# Tasks

The list of work on Work IDE: what was done, what is agreed and waiting, and
what is only an idea (the owner, 2026-10-20). One Markdown file per task; the
folder a file sits in is its stage.

| Folder | Stage | What is in it |
|---|---|---|
| `0-potential/` | POTENTIAL | Questions the owner checks in practice before anything is decided (2026-10-28): "look at real selections and say whether X". From here a task moves to any stage, done included, when the owner decides on the spot how to close it. |
| `1-triage/` | TRIAGE | Ideas nobody has agreed to yet: the agent's own backlog, sources noticed in passing, offers made in a conversation. The owner decides whether each goes to TO DO or is cancelled. |
| `2-to-do/` | TO DO | Work the owner wants, with at least one item still to do. |
| `3-done/` | DONE | Work finished: every item is DONE. Written from the git history up to 2026-10-20. |
| `4-cancelled/` | CANCELLED | Work the owner decided not to do (2026-10-21), on purpose, from any stage: the file stays as it stood, with a `Cancelled:` line under `Source:` saying who decided, when and why. Its TO DO items stay; nothing is done under it. |

A task moves by moving its file. Its number stays.

## One file, one task

`NNNN-a-few-words.md`: four digits from 0000, then a few words in English.
The number is unique across the five folders and is never reused; a new
task takes the next free one. Tasks are written in English, like the rest of
the repository.

A file can be a ticket, a feature or an epic. The shape follows its size:

```markdown
# NNNN Title: what the person gets

Commits: <hashes> (tasks 0000-0050 only; later ones: python tools/tasks.py log NNNN)
Source: who asked for it, and when
Cancelled: who decided, when: why (a task in 4-cancelled only)
Scope: tools, docs

## Business
What the person needs and why: the case that showed it, measured where it
was measured. Written so that someone who never saw the code can judge it.

## Implementation
In outline, where it helps: the parts of the system it touches, the
approach. Not a copy of the code.

## Items
- DONE - <what>
- TO DO - <what>
```

## Scope

Every task from 0052 on says what it is about on a `Scope:` line under
`Source:` (the owner, 2026-10-20): one or more of the scopes below,
comma-separated. Tasks before 0052 have none and keep it that way.

| Scope | What it covers |
|---|---|
| `identity:<prefix>` | one identity: its template, its documents (`identity:sharp`) |
| `tools` | `tools/` and their tests |
| `app` | the desktop app |
| `config` | shared configuration in `config/`, sources included |
| `rules` | `CLAUDE.md`, skills, commands, hooks: how the agent works |
| `docs` | README, RUNBOOK, `docs/` |
| `tasks` | the task system: this README, `tools/tasks.py`, the commit hook |
| `other` | anything else |

The list is `SCOPES` in `tools/tasks.py`; a new scope goes there and here.

## Items

The items are the last section. Each is one line starting with
`- TO DO - ` or `- DONE - `, spelled exactly so.

- **A small task** has a few items.
- **A task not thought through yet** has one item:
  `- TO DO - Work out the plan and write it here as the next items`.
- **A large task** has its own few items (usually investigation and
  planning), then `## Sub-tickets`: each sub-ticket is a
  `### TO DO - <name>` or `### DONE - <name>` heading with its own short
  description and items under it.
- **A task that grew** after it was started as a small one: its investigation
  and planning items move into sub-ticket 1, and the rest of the work becomes
  sub-tickets after it.

`tests/test_tasks.py` checks the format: the five folders, unique numbers,
the scope of every task from 0052 on, `## Business` first, the marks spelled one way, no TO DO left in a DONE task,
at least one TO DO in potential, triage and to-do, a `Cancelled:` line in a cancelled task.

## Every commit names its task

The owner, 2026-10-20: every change is a task, every commit names its task.
The procedure is the `task` skill (`.claude/skills/task/SKILL.md`).

- A task is for work that ends in a commit. Purely local work — checking or
  fixing local data, running a collection, answering a question — has none.
- Work that has no task gets one before the first edit
  (`python tools/tasks.py new to-do <a-few-words> "<Title>" --scope <scopes>`):
  in `2-to-do/` when the owner asked for it, in `1-triage/` when it is the
  agent's own idea, in `0-potential/` when it is a question the owner will
  check in practice.
- A task that turned out to need no commit is deleted (`git rm`, in a commit
  of task files only). A task the owner decided against is not deleted: it
  moves to `4-cancelled/` with its `Cancelled:` line.
- A task done in spirit goes to `3-done/`, not to `4-cancelled/` (the owner,
  2026-10-28, task 0080): its problem is solved by other work, or its purpose
  is reached another way than its items say. Cancelled is only for work the
  owner does not want. Before the move the text is rewritten so that a later
  agent does not take the old plan for work still owed: the proposed
  measures are removed, the Business says why no change of its own is
  needed and which work solved it, and the items are what was checked. History is not rewritten, and the number is not
  handed out again: `tools/tasks.py next` reads it from git history.
- The commit message has a line `Task: NNNN`, and the commit changes that
  task's file: the item it finishes marked DONE, the work it does added as an
  item, or the file moved to `3-done/` with its last item.
- A task in `0-potential/` waits for the owner's check, one in `1-triage/`
  is not agreed work, and one in `4-cancelled/` will not be done: a commit
  naming only such tasks changes nothing outside `tasks/`.
- A commit that changes task files only (`tasks/<stage>/NNNN-*.md`) needs no
  task. A change to this README, the hook or `tools/tasks.py` does.
- Merges, reverts and fixups are exempt.

`.githooks/commit-msg` enforces this; it is turned on once per clone with
`git config core.hooksPath .githooks`.

A task's history is `python tools/tasks.py log NNNN` (the commits that name
it). Tasks written from the history up to 2026-10-20 (0000-0050) list their
commits in a `Commits:` line instead.
