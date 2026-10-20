# 0038 The app answers at once

Commits: 491fb25 e9112aa (2026-10-18)
Source: the owner: every click waited for the list

## Business
Every answer and filter change waited for a list reload that had grown to
1.9 s. It is back to 0.3 s, and an answer redraws only its own card and
count.

## Implementation
The slow part of the listing query removed; a local redraw after an answer.

## Items
- DONE - List reload 0.3 s
- DONE - Answer redraws locally
