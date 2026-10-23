# 0041 LinkedIn runs apart and paces itself

Commits: dd43a29 (2026-10-20)
Source: the owner: the top run waited on LinkedIn, and LinkedIn answered with 429s

## Business
LinkedIn is the slowest source by far and the one that pushes back: the run
before this change met 392 "too many requests" on 127 query pairs and gave
pages up. The other sources finish in minutes, so the top of the shortlist
should not wait for LinkedIn, and LinkedIn should slow down when asked
instead of losing pages. One LinkedIn fetch at a time on the machine, for
any identity.

## Implementation
`pipeline.py --linkedin` fetches its window without holding the base, then
waits for it and merges; `--top` fetches everything else. The pause between
pages doubles after a 429 (up to 12 s) and comes back down; a 429 is waited
out 30, 60, 120 s before the page is given up. Per-query statistics in
`runs/linkedin_queries_<time>.json`. The app queues the collection and the
LinkedIn task in separate lanes; the rest of the base follows the later of
the two.

## Measured (2026-10-23)
Two paced runs of SHARP: `runs/linkedin_queries_<time>.json` and the
pipeline logs beside them, and the base of 2026-10-23.

| | Before the change | 2026-10-20 18:03 | 2026-10-22 20:12 |
|---|---|---|---|
| Window | | 4 days | 3 days |
| Queries (pairs + narrower) | 127 pairs | 412 (168 + 244) | 920 |
| Pages read / cards | | 2,646 / 25,314 | 7,784 / 76,314 |
| 429s | 392 | 154, in 95 queries; 1 dropped connection | 0 |
| Pages given up | some | 0 | 0 |
| Fetch time | | 4:12:40 (5.7 s a page) | 6:42:27 (3.1 s a page) |
| LinkedIn run, fetch to report | | 4:40:35 | 7:10:29 |
| New to the base | | 5,836 of 7,960 | 19,460 of 23,119 |
| Queries with nothing new | | 60 | 82 |
| Queries at the 10-page ceiling | | 167 | 632 |
| The `--rest` after it | | 1:48:13, AI kept 9 of 434 | 1:43:37, AI kept 1 of 78 |

- The second run had twice the keywords (24, template sharp v28 added
  stretch titles such as "applied AI engineer") and no 429 at all.
- What the new vacancies became for SHARP: of 5,836 (10-20), 2 long shot,
  109 remote unconfirmed, 5,713 rejected; of 19,460 (10-22), 1 long shot,
  142 remote unconfirmed, 19,303 rejected. 17,405 of those rejects: "the
  employer never states this is remote" (the guest search ignores LinkedIn's
  remote filter f_WT, tools/fetch_linkedin.py:176-190).
- Nothing new, by keyword: "contract C# developer" (30 and 24 queries),
  "senior .NET engineer" (17 and 15), "applied AI engineer" (12 in the
  second); by place: Iceland, Russia, Belarus.
- The run's length goes on to 0050: the 10-22 run went on past the next
  scheduled collection (01:00; task 0089).

## Items
- DONE - Separate run with a merge into the base
- DONE - Paced fetcher, per-query statistics
- DONE - Lanes in the app
- DONE - Measure the first paced run and report to the owner: 429s against the old run (392 on 127 pairs), pages given up, new vacancies, run length, the `--rest` result, queries that brought nothing new (2026-10-23, both paced runs: "Measured" above)
- DONE - Decide with the owner what to do about the run length: handed to 0050, which holds the plan and its numbers
