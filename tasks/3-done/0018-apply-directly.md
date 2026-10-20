# 0018 Where to apply directly, for the top of the shortlist

Commits: d6de014 (2026-08-12)
Source: the owner

## Business
A vacancy in the report is a link to a job board; applying there means an
account, a queue and a form somebody may never read. For the hot leads (and
anything scoring as high in another class) the person wants the employer's
own way in — the vacancy on the company's applicant-tracking system, the
company's board, or an address written in the posting — and a plain "none
found" when there is none. Personal contacts of named people are not
collected: a recruiter's private email is data about a third party.

A 200 means nothing here: every ATS answers 200 to a slug nobody owns. Each
version was wrong in a new way before being measured (a channel for 18 of 18
companies, including a typo; Accenture offered a two-posting board with
"Senior Marketer (Sample)"; "ITS Group Benelux" given another company's
board).

## Implementation
`tools/apply_channels.py`: a hit is earned twice — the board lists real
openings, and either our vacancy is on it by title or the board's declared
name shares something with the company's. Over 122 vacancies: 5 direct
links, 4 company boards, 25 addresses, 88 with nothing found and saying so.

## Items
- DONE - ATS, company board and posting address per top vacancy
- DONE - Ownership proved, never assumed from a 200
