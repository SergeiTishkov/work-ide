# 0031 Narrowing the list

Commits: aa9b9e9 55095b5 a098f03 4f08184 85907fe 7ab214d e4d39dc 758e57e 706bc76 6a2517f c0ded48 ccbf8a9 cf7b113 82c7bae f0d55fc 26a0b24 (2026-09-30 — 2026-10-20)
Source: the owner

## Business
The shortlist holds hundreds of vacancies; the person narrows it to what
they want to read now: region, status of their own answer, age, source,
kind of company, category. Choices are kept between sessions. Filters whose
values are stable (categories, statuses) stay listed and ticked at zero;
filters whose values come and go (sources, company names) show only what is
there. A text field narrows by words, in any case and alphabet, accents
ignored.

## Implementation
One view over named queries; six drop-downs of one width in one row; counts
from the same query as the list.

## Sub-tickets

### DONE - Status and freshness
Answers and freshness in one drop-down, later named "Status"; whole counts,
capped classes say "N more".
- DONE - One drop-down for status and freshness
- DONE - Whole counts

### DONE - Source
Which board brought the vacancy, shown by its website.
- DONE - Source drop-down applied together with the others

### DONE - Names and order
"All without feedback"; names and order made consistent; "Category" label;
sections start with 10.
- DONE - Names, order, label

### DONE - Look
Region moved from tabs to a drop-down; outlined fields with the name on the
top edge; our own drop-downs of one width, long options wrap.
- DONE - Region drop-down
- DONE - Outlined, one-width drop-downs

### DONE - Company kind and Age
Freelance marketplaces, recruitment agencies, reposters, other companies;
age from the posting date, else first seen.
- DONE - Company drop-down
- DONE - Age drop-down

### DONE - Text filter
Words narrow the list together with the drop-downs; any case in every
alphabet, accents ignored.
- DONE - Text field
- DONE - Case and accent folding

### DONE - Stable categories
Hot lead, worth a look, long shot and remote unconfirmed stay listed and
keep their tick when nothing is left in them.
- DONE - Stable classes always listed
