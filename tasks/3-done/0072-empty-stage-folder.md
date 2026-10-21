# 0072 An empty stage folder does not break a fresh clone

Source: the agent, 2026-10-21, after the triage emptied
Scope: tasks

## Business
On 2026-10-21 the owner took every triage task into work, and
`tasks/1-triage/` became empty. Git keeps no empty folder, so a fresh clone
has no `1-triage/`: the format test asked for all four folders and failed
there, and `tools/tasks.py new triage` had no folder to write into.

## Implementation
`tests/test_tasks.py`: no folder but the four stages, an absent one allowed;
`tools/tasks.py new` makes its stage folder.

## Items
- DONE - The format test and `tasks.py new` work with an absent stage folder
