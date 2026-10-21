# 0046 Y Combinator jobs for the full-time search

Source: the agent, 2026-09-13 (rejected for part-time); reconsidered 2026-10-20

## Business
ycombinator.com/jobs was rejected for the part-time search: 29 of 30 remote
engineering postings were full time. That is what the full-time sharp search
wants, and startups are where forward deployed and applied AI roles appear.
"US citizen/visa only" is common, so the share that is reachable from
outside the US decides whether it is worth a fetcher.

## Implementation
Measured 2026-10-21. ycombinator.com/jobs has no paging: 133 distinct remote
postings across every role page, 32 engineering, 21 of them "US
citizen/visa only", about 3-4 reachable from UTC+4. Not fetched.

The same companies post on workatastartup.com (2,923 postings). Its search
answers JSON, up to 30 a keyword, no paging; 20 keywords gave 437 postings,
160 remote, 65 not tied to one country other than Georgia, among them
forward deployed and applied AI roles (Datafold, kapa.ai).

tools/fetch_workatastartup.py, source `workatastartup`: off in the
template, on for sharp with countries [GE] and the default keywords. A
posting remote in one other country only is left out; several countries,
or none named, stay for the scoring. Live, 2026-10-21: 57 records of 368
found; none .NET in the title, three mention C#.

## Items
- DONE - Measure the share of remote postings not limited to the US; write the plan here or drop the ticket
- DONE - tools/fetch_workatastartup.py with tests, wired into the pipeline, the catalog and the registry; on for sharp
