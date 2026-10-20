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

## Items
- DONE - Separate run with a merge into the base
- DONE - Paced fetcher, per-query statistics
- DONE - Lanes in the app
- TO DO - Measure the first paced run and report to the owner: 429s against the old run (392 on 127 pairs), pages given up, new vacancies, run length, the `--rest` result, queries that brought nothing new
- TO DO - Decide with the owner what to do about the run length (0050 in triage)
