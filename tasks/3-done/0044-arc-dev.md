# 0044 arc.dev: remote contract marketplace

Source: the agent, 2026-08-04 and 2026-09-13

## Business
Arc is a marketplace for remote contract work, the same kind as Proxify and
Lemon.io, which yield well for this search (3 of 18 in an early shortlist,
from two companies out of a thousand). Its vacancies carry exactly what the
scoring needs: time-zone restriction, overlap hours, job type, hourly rate
range and level. With stretch roles accepted, more of its listings are in
reach.

## Implementation
Measured 2026-10-21: the page's data comes from a JSON API at api.arc.dev,
open with the header `x-requested-from: arc-next` (422 without it). Arc's
own requests: POST /job-requests/public-search, per_page up to 100,
filtered by country_code; GET /job-requests/<key> for the text, the
locations and the hours a week. 67 requests, 45 open to Georgia, one .NET
(a part-time C#/.NET trading-system contract, worldwide, $40-$70 an hour).
The second list (/p/job-posts, about 9,000) re-indexes LinkedIn postings
with about zero worldwide .NET, so it is not fetched.

tools/fetch_arcdev.py, source `arcdev`: off in the template, on for sharp
with country_code GE. A country list holding the identity's country is
written "N countries including country of Georgia" (" only" reads as a
refusal to the scoring); time zones as UTC offsets; 25 hours a week or less
adds part-time, 35 or more full-time. Live, 2026-10-21: 45 records.

## Items
- DONE - Find how the site pages and filters its list; write the plan here as the next items
- DONE - tools/fetch_arcdev.py with tests, wired into the pipeline, the catalog and the registry; on for sharp
