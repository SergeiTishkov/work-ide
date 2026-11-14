# 0118 A must-have's buried evidence surfaces in the Summary

Source: the owner, 2026-11-14 (after the Sonnet review of task 0115)
Scope: config

## Business
The Sonnet review of the 86 CVs regenerated in task 0114 found five real
misses (task 0115). In all five the parent CV had the evidence, and the
CV had it too, or could have, but where a recruiter does not look: the
last line of the oldest job, mid-sentence in a job description, a
project cut for length. A version revised after the review fixed each of
them by moving the evidence into the Summary; in the 3-page CVs the
added text pushed other strong bullets out (task 0115, "The revision").

The owner's decision: the generation does this itself, the first time.
A must-have the parent CV answers but the top of the CV does not show
gets one short clause in the Summary. At most three per CV, so a vacancy
with ten requirements does not turn the Summary into a keyword list. An
ATS reads the whole CV; a recruiter reads the top.

## Implementation
- `config/cv_tailor_prompt.md`, the Summary section: the rule, with its
  limits:
  - only a requirement the vacancy states as required;
  - only when the evidence is not already visible in the Summary or
    Technologies;
  - one short clause each, at most three, the ones that weigh most for
    the screening;
  - the parent CV's fact; the vacancy's term only when the fact is that
    thing.

## Items
- DONE - The rule in the CV prompt
- TO DO - Measure: the five CVs of task 0115 and the agent's seven, made anew with the rule; compare with the versions made anew without it
