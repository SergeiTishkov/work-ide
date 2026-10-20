# 0013 What the score pays for

Commits: a07c5a6 2254f5f c1db99d 71e74fa a894713 355d965 0ae9475 8b6906c (2026-08-05 — 2026-10-05)
Source: the owner's instructions on ranking, changed as the search changed

## Business
The score ranks vacancies that passed every gate; it must answer "what is
this job, can I take it, what does it pay", not "where is it". Geography had
been the heaviest component — heavier than stack and pay combined — and the
list was led by agencies whose only merit was hiring globally.

The search changed on 2026-10-05: legacy and calm stopped mattering; the
order became (1) reachable from abroad and the person fits, (2) pay, (3)
technology only between otherwise equal vacancies.

Two false signals had cost the most: the employer-of-record bonus (the
largest in the rubric) matched "productivity multiplier" and the German
"Mentoring-Programm" — 345 of 592 hits were false; the worldwide vocabulary
had ten phrasings and caught 75 of 9527.

## Implementation
EOR platforms written as domains, 37 worldwide phrases of two words or more.
Caps on each component instead of a `weights` block no code read (deleted).
Thresholds recalibrated: hot_lead 38, the tail admits anything that cleared
the gates. Pay graded by the hourly equivalent; a compensation shape that is
documented and does not crash when missing. Legacy and low-intensity signals
switched off for SHARP (V21); reachability +30.

## Items
- DONE - EOR and worldwide signals without false hits
- DONE - Work over geography (stack 15 -> 25, worldwide 25 -> 6)
- DONE - Legacy inferred from old technologies; engineering support a plus (both off since V21)
- DONE - Pay graded by hourly equivalent; the compensation shape documented
- DONE - Reachability, fit, pay, then technology (SHARP V20-V21)
