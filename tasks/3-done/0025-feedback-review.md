# 0025 The owner's answers teach the next run

Commits: 771b29e de8389e b04f71e ac6b248 (2026-09-29 — 2026-10-04)
Source: the owner

## Business
"Wrong pick" and "Not for me" with a reason say where the scoring is wrong.
They are reviewed together with the agent: each answer next to the score
breakdown and the class then and now, so a rule is changed where it was
wrong and not where one vacancy happened to fall. A reason can be a quote
from the posting and is read as one. After every collection the agent says
how many answers wait for review.

## Implementation
`tools/feedback.py collect` builds a review package; the `/feedback`
command walks it; reviewed answers are marked so they are not proposed
again. Pending counts are in every run's result.

## Items
- DONE - Review package with the breakdown and the class then and now
- DONE - Quotes from the posting read as quotes
- DONE - Pending answers reported after every collection
