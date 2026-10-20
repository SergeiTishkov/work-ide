# 0010 Remote counts only where the employer says so

Commits: b0d6a4b 990a2b8 355d965 65ab782 8b6906c ccbf8a9 cf7b113 (2026-08-05 — 2026-10-18)
Source: the owner, opening vacancies from their shortlist

## Business
The search is for remote work. Eight postings in the top were hybrid or
office-based, written as "Hybrid Position", "hybrid working model",
"Location - Dubai (WFO)" — not the "hybrid required" the list held. LinkedIn
vacancies were all marked remote on the strength of a filter that does
nothing (task 0004). "50% remote" is hybrid; "WFH 3 days per week", a
work-from-home allowance and "a distributed team" do not make a job remote.

Silence is a different case from a stated office: a posting that does not
say goes to "Remote not confirmed" with its score untouched, so the person
can decide (the owner's direction). Where the description was read in full
(600+ characters) and never says remote, the owner chose to refuse it.

## Implementation
Hard patterns for hybrid and office wording as written in the market (never
the bare word: 58 postings say "hybrid cloud"); a class and a section for
unconfirmed remote; on boards that hide the workplace badge only explicit
words in the text confirm remote; the option
`unstated_remote_after_reading: reject` in the personal settings.

## Items
- DONE - Hybrid and office wordings from real postings
- DONE - The board's flag is not believed where it was measured to do nothing
- DONE - "Remote not confirmed" as a class with the score untouched
- DONE - A read description that never says remote is refused (personal option)
