# 0011 Where the person can be hired from decides first

Commits: 164a6a2 b9e4112 892007f cd810b7 c72a394 71e74fa a674e99 de9923b 8b6906c 75b85f0 8f464eb (2026-08-04 — 2026-10-06)
Source: the owner; their priorities of 2026-10-05: (1) the employer can hire them remotely from where they live and they fit, (2) pay

## Business
A well-paid job that cannot be taken is worth less than a modest one that
can: "$100/hour — Remote — US" is worth less than "$70/hour — Remote
Worldwide — Contractor" to someone outside the US. The person lives outside
the big markets and contracts across borders, so every location rule decides
reachability, not taste.

The cases that shaped it: Azumo tagged "Anywhere in the World" while its text
said Latin America only; 501 .NET vacancies refused on a guess about their
country although every one was flagged remote by its source (16 of 78 with
text actually restricted hiring); 3281 European vacancies with one in the
report because the market table was never read by scoring; "remote-first
company" taken as worldwide hiring; "Must have authorization to work in the
UK" sitting in hot_lead at 64; "We require U.S. citizenship" and "$100 per
hour on W-2" in the top, while "clearance is preferred" refused vacancies
that refused nobody; a "CET ±3 hours" or "GMT+2 to GMT-3" window; a US
401(k) plan; 134 of 145 "worldwide" devitjobs vacancies being US offices.

## Implementation
`remote_location_fit` in criteria: the employer's own words beat a board's
label; a guess goes to "Remote not confirmed", never to a refusal; work
authorization read sentence by sentence with guards for negation and
preference; time-zone windows parsed and compared with the person's UTC
offset; the hiring country of each vacancy named; eligibility (confirmed,
likely, not stated, no) as an axis that adds +30 when confirmed or likely;
`tools/places.py` reads every country, US state and Canadian province as
whole words. Country no longer earns points; only exporters of development
work cost a little.

## Sub-tickets

### DONE - The employer's words beat the board's label
- DONE - Residency phrases refuse whatever the worldwide marker says
- DONE - A refusal on a guess becomes "Remote not confirmed"

### DONE - Markets from the identity's own table
- DONE - Target markets derived from the tiers the identity chose; "United States only" read as a restriction
- DONE - Geography stops earning points (worldwide 25 -> 6); exporters cost a little

### DONE - The hiring country and eligibility
- DONE - Hiring country per vacancy (342 of 351 resolved; the rest are worldwide)
- DONE - Eligibility verdict on its own line, ordering each section; +30 to the score when confirmed or likely
- DONE - "remote-first", the bare word "contractor" and "freelance" no longer prove hiring abroad; a named employer of record does

### DONE - Work authorization read in its sentence
Measured on the base before the change: 62 vacancies to rejected, 3 back
from wrong refusals, every one read.
- DONE - Citizenship, clearance, sponsorship, W-2 (unless C2C/1099 too), US person
- DONE - A US or Canadian retirement plan refuses unless the employer engages people abroad

### DONE - Time zones
- DONE - "<TZ> ±N hours", "within N hours of", UTC ranges; daylight saving considered

### DONE - Every place read
- DONE - All countries, states and provinces as whole words ("oman" is not in "romania"); worldwide means no place named (SHARP worldwide 314 -> 67)
- DONE - The national_market class removed: "<place> only" from a board is a refusal like any other
