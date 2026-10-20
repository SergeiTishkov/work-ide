# 0004 LinkedIn: every target market through its guest search

Commits: b854f6e 5f5a5ac 990a2b8 7337c6b a2928c9 85dddb8 6d9a9e4 65ab782 ccbf8a9 cf7b113 4ce4b86 (2026-08-04 — 2026-10-18)
Source: the agent's survey; the owner's checks of the shortlist

## Business
The country boards of the markets that matter (the Gulf, Israel, Singapore)
answer 403/404. LinkedIn's guest search answers a plain request, and one
fetcher covers every country of interest. It became the largest source.

What a person sees logged in and what the guest endpoint returns differ, and
the gap cost real mistakes: the owner opened the top three of their
shortlist and found Hybrid, On-site, and On-site no longer accepting
applications — all stored as remote.

## Implementation
`tools/fetch_linkedin.py` reads the undocumented HTML, validates every field
and returns zero with an error rather than broken records when the markup
changes. Details in `docs/sources/linkedin.md`.

## Sub-tickets

### DONE - The fetcher and the job pages
Cards carry no description; without one the stack gate refused 447 of 621.
Job pages answer the same request, so promising cards get their full text.
- DONE - Search fetcher over keyword x country pairs, market tag per country
- DONE - Job page reader for the description

### DONE - LinkedIn's remote filter is not believed
Measured: the same job id comes back under the on-site, remote and hybrid
filters. The badge is shown to logged-in visitors only. The employer's own
word disqualifies ("Hybrid" in the location: 272 vacancies); silence goes to
a class of its own with the score untouched (109 vacancies). The job page
also gives: still accepting applications (36 of 260 were not), the stated
salary (17), TELECOMMUTE (8). Later, TELECOMMUTE alone stopped confirming
remote; explicit words in the text do.
- DONE - Remote only where the posting says so
- DONE - Closed postings, salary and employment type from the job page

### DONE - Read to the end of every list
The fetcher stepped by an assumed 25 cards; LinkedIn serves ten, so every
pair ended after its first page. Same words and countries: 1007 unique
vacancies before, 4946 after. Queries at the 100-result ceiling are split
into narrower ones.
- DONE - Paging by cards received, the ceiling split, one retry after a 429
- DONE - A live contract for the source doctor

### DONE - How far back a collection reaches
From the day of the last good LinkedIn fetch to today, at most 7 days (a
week already takes hours: 126 of 168 pairs in about 3 h). The 25-minute
budget of the top run was removed at the owner's request: every run reads
its window to the end.
- DONE - The window and its state
- DONE - No time budget (the owner, 2026-10-18)
