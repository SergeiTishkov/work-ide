# 0127 Recheck that listed vacancies are still open

Source: the owner, 2026-11-20
Scope: tools, app, docs

## Business
The owner, 2026-11-20: the list will hold vacancies of a couple of months,
and most of the old ones will have closed. They have to be checked again,
reliably; if there is no reliable way, one has to be made.

Measured 2026-11-20, SHARP:
- The list holds 1,189 vacancies, 1,071 of them LinkedIn; 967 first seen
  in October.
- The link check (`tools/link_check.py`, HEAD then GET, 404/410 = dead)
  got 429 from LinkedIn on 1,041 of the 1,071: "unknown", which keeps
  them listed. In the whole base 118,533 LinkedIn records carry
  "unknown 429".
- A sample of 63 listed LinkedIn vacancies, read one by one with a 2.5 s
  pause, gave 38 verdicts:

  | Verdict | Count |
  |---|---|
  | "No longer accepting applications" | 13 |
  | 404 | 3 |
  | Redirected away from the posting to a LinkedIn jobs search page | 10 |
  | Open | 12 |

  The remaining 25 answered 429; LinkedIn task #296 ran at the same time.
  So 26 of the 38 with a verdict were gone.
- The owner marked 106 vacancies "expired" by hand, 89 of them LinkedIn,
  a median of 13 days after they were first seen.
- A closed posting found by the description reader
  (`enrich_descriptions`: link_check dead, "no longer accepting
  applications") is overwritten by the next link check: 12 hours later a
  HEAD gets 429 and the record becomes "unknown", listed again. Only 76
  such verdicts remain in the base.
- Every rest run calls `link_check.check_links` over the whole base: every
  record not checked in 12 hours, with 12 threads — about 120,000 LinkedIn
  requests, nearly all answered 429.

## Implementation
In outline:
- A reader of "is this posting still open" per source, with three
  verdicts and the evidence for each: open, closed, unknown. LinkedIn
  reads the posting page one by one at a measured pace. The verdicts:
  - closed: the closed marker, 404/410, or a redirect away from
    /jobs/view/;
  - open: a page with the posting;
  - unknown: 429 or anything else.
  Boards with an API (devitjobs, ATS boards) ask the API; the rest keep
  the HTTP check.
- A closed verdict is not undone by an unknown one; only an open verdict
  reopens.
- What to check and when: the listed vacancies, oldest check first, in a
  time budget per run, with intervals by age. The generic HTTP check
  stops sending LinkedIn records over the whole base.
- The queue's "links" run does it; the owner's "expired" answers serve
  as the measurement.

## Items
- DONE - The measurement above
- TO DO - The checker, the sticky verdicts, the budget, tests; the queue's links run; docs
