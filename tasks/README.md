# Tasks

The list of work on Work IDE: what was done, what is agreed and waiting, and
what is only an idea (the owner, 2026-10-20). One Markdown file per task; the
folder a file sits in is its stage.

| Folder | Stage | What is in it |
|---|---|---|
| `1-triage/` | TRIAGE | Ideas nobody has agreed to yet: the agent's own backlog, sources noticed in passing, offers made in a conversation. The owner decides whether each goes to TO DO or is deleted. |
| `2-to-do/` | TO DO | Work the owner wants, with at least one item still to do. |
| `3-done/` | DONE | Work finished: every item is DONE. Written from the git history up to 2026-10-20. |

A task moves by moving its file. Its number stays.

## One file, one task

`NNNN-a-few-words.md`: four digits from 0000, then a few words in English.
The number is unique across the three folders and is never reused; a new
task takes the next free one. Tasks are written in English, like the rest of
the repository.

A file can be a ticket, a feature or an epic. The shape follows its size:

```markdown
# NNNN Title: what the person gets

Commits: <hashes> (DONE tasks; the history is the evidence)
Source: who asked for it, and when

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

`tests/test_tasks.py` checks the format: the three folders, unique numbers,
`## Business` first, the marks spelled one way, no TO DO left in a DONE task,
at least one TO DO in the other two stages.

## When work is done

The commit that finishes an item marks it DONE in the same change; the
commit that finishes the last one moves the file to `3-done/`. Work that has
no task yet gets one — in `2-to-do/` when the owner asked for it, in
`1-triage/` when it is the agent's own idea.
