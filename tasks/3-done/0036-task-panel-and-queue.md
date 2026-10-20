# 0036 Long work runs as tasks in a queue

Commits: cf7b113 49fb489 36a8319 (2026-10-13 — 2026-10-20)
Source: the owner

## Business
Collections, document generation and reputation lookups take minutes to
hours, and the person starts them from the app while reading. Each kind of
work runs one at a time in its own lane; the same task is never queued
twice; a collection that ends well is followed by the rest of the base and
the documents batch. The panel at the bottom lists tasks and shows the
chosen one's steps. The commands live in one menu that spins while anything
runs.

## Implementation
Lanes (collect, documents, reputation) in the main process; steps parsed
from the log (`app/main/steps.js`); the queue in memory; Refresh waits while
a task is active.

## Items
- DONE - Task panel with logs and steps
- DONE - Lanes and an in-memory queue
- DONE - Rest of the base and the documents batch after a good collection
- DONE - Commands, Refresh and the collection's status in one menu
