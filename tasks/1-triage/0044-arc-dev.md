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
Next.js page data (`arcJobs` and `externalJobs`, 9,031 on 2026-09-13). The
path filters are ignored (`/remote-jobs/part-time`, `/freelance`,
`/part-time/.net` returned the same thirty), so the search parameters have
to be found before a fetcher is worth writing.

## Items
- TO DO - Find how the site pages and filters its list; write the plan here as the next items
