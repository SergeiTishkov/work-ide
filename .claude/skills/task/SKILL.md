---
name: task
description: Tie every change and every commit to a task in tasks/. Use before starting any change to the repository — a fix however small, a feature, a rule, a prompt, a doc edit — and before every git commit. The owner's rule (2026-10-20): every fix becomes a task, every commit names its task. Takes optional words describing the change.
---

# Every change has a task

The change: `$ARGUMENTS` (or the one just asked for).

The rule is the owner's (2026-10-20) and has no exceptions: a one-line fix
asked for in passing is a task too. The format of a task is
`tasks/README.md`; the commit hook `.githooks/commit-msg` refuses a commit
that does not follow this.

## 1. Before the first edit: find or make the task

```
python tools/tasks.py find <two or three words of the change>
```

- **A task in `2-to-do/` covers it** — work under it. If the change is not
  among its items yet, add it as `- TO DO - <what>` first.
- **A task in `3-done/` covers the area** — it stays done. A fix to what it
  delivered is a new task that names the old one in its Business ("0031
  delivered X; Y turned out wrong").
- **A task in `1-triage/` covers it** — triage is not agreed work. If the
  owner has now asked for it, move the file to `2-to-do/` (same number) as
  part of the first commit. If the owner has not, do not start: ask.
- **Nothing covers it** — make one:

  ```
  python tools/tasks.py new to-do <a-few-words> "<Title: what the person gets>" --source "the owner, <date>"
  ```

  `to-do` when the owner asked for it, `triage` when it is the agent's own
  idea (and then stop and ask, as above). Fill `## Business` with what the
  person needs and why, in English, before writing code; replace the
  "Work out the plan" item with the items as soon as the plan is known.

One task per piece of work the owner would name separately. A large one gets
sub-tickets (`### TO DO - <name>`), not several loose tasks.

## 2. Before every commit: update the task in the same commit

- Mark each item the commit finishes `- DONE - `; add an item for any work
  the commit does that the task did not list.
- When the last item is DONE, move the file to `tasks/3-done/` in this
  commit (`git mv`, the number stays).
- `git add` the task file with the rest.

## 3. The message names the task

The subject and body as CLAUDE.md §12 "Commits" asks (every business change
listed), then the task on its own line, before the co-author line:

```
Task: 0052
```

Several tasks: one `Task:` line each, and each task file is changed in the
commit. Merges, reverts and fixups are exempt.

If the hook refuses, fix the task or the message — never `--no-verify`.

## 4. Afterwards

`python tools/tasks.py log <number>` lists the commits of a task; that is
its history, so tasks made from now on carry no `Commits:` line.
