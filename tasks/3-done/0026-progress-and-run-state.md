# 0026 Seeing that a collection is alive and how long it has left

Commits: df6917a 1f1ebe7 b4d2760 (2026-09-30)
Source: the owner

## Business
A collection runs for an hour or more. The person wants to see that it is
running, which stage it is in and how long is left, without a terminal.
An estimate taken from the first minutes was far off once the pace changed,
so it follows the recent pace.

## Implementation
Progress lines in the pipeline log with counts and time left from a moving
window; a collection indicator in the app read from the base, not from a
process the app started itself.

## Items
- DONE - Progress logging per stage
- DONE - Collection indicator from the base
- DONE - Time left from the recent pace
