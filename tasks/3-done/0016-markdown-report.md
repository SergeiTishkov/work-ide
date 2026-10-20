# 0016 A report a person can read over coffee

Commits: 90d2ea8 8dda5a1 c1db99d 0b0b9e6 c72a394 355d965 (2026-08-04 — 2026-09-13)
Source: the owner reads the report by hand and catches what tests miss

## Business
The report is where the person decides. Its manual-review section held every
flagged vacancy, already-refused ones included: twenty-five entries, four of
them worth reviewing. Sections looked unsorted ("46, 40, then 60") because a
hidden grouping ordered them. A vacancy says what it expects (technologies,
including ones the person does not know — that tells them to skip without
opening) and where the contract is (the hiring country, not the "acceptable
region"). Which sources are worth keeping is a table, since volume and
usefulness differ.

## Implementation
`tools/report.py` with one row view (`report.vacancy_view`) later shared with
the app; sections sorted by score, reachability only breaking ties; the
manual-review section holds only undecided vacancies; the technology line
from the shared vocabulary; a source-usefulness table.

## Items
- DONE - Manual review lists only what is undecided
- DONE - Expected technologies and the hiring country per vacancy
- DONE - Sections sorted by score
- DONE - Source usefulness table
