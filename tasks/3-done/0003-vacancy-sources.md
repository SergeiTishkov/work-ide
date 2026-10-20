# 0003 Vacancy sources: every board that answers a plain request

Commits: 90d2ea8 b854f6e 5f5a5ac 9f58727 164a6a2 9b1357a c1db99d aa358ea 0c5218a 355d965 180fa75 36e387d 2fef421 8f464eb 4f08184 cf7b113 (2026-08-04 — 2026-10-18)
Source: the owner's searches; the agent's surveys

## Business
More boards mean more of the vacancies the person can take — but only boards
that answer a plain request without an account, and only boards the person
can apply through. Volume and usefulness are different things: one source
gave 4368 records and zero candidates. Every board checked is recorded with
its response, whichever way it went, so the same board is not investigated
again a month later (`config/sources.backlog.yaml`).

## Implementation
One `tools/fetch_<source>.py` per board, a shared normaliser, the catalogue
of sources with their site names, a source-usefulness table in the report.
Boards the person cannot apply through are closed per identity
(`closed_sources`) and no longer fetched.

## Sub-tickets

### DONE - The first public boards
We Work Remotely (5 category feeds), RemoteOK, Remotive, Jobicy, Himalayas,
HN "Who is hiring", Arbeitnow and company ATS boards (Greenhouse, Lever,
Ashby, Recruitee).
- DONE - Fetchers and the normaliser
- DONE - Himalayas: its renamed company field silently dropped all 60 records at HTTP 200; then it sent the field names ("name") as values. Both shapes read, 29 records repaired.

### DONE - Six more sources and the registry
Devitjobs UK/US, jobs.ch, MyCareersFuture, Landing.jobs, WorkingNomads,
Jobspresso and Berlin Startup Jobs; Workable and SmartRecruiters as ATS
providers. The base grew from 3924 to 9503. Fourteen rejected boards recorded
with their codes (Indeed 403, Glassdoor 403, Bayt, GulfTalent, Drushim,
NodeFlair).
- DONE - Fetchers
- DONE - `config/sources.backlog.yaml` with every outcome

### DONE - 4dayweek.io: the workload axis
The only source that searches by schedule rather than stack, with
schedule_type as a structured field.
- DONE - Fetcher

### DONE - UK sources, mostly contracts
The owner wanted the UK covered. Nine named sources probed; four built:
ContractorUK, Reed (all three filter variants tested before trusted),
JobServe, Outside IR35 Jobs. Contracts with a day rate are work someone
invoicing from abroad can take. UK tiers a person reads: 28 -> 39.
- DONE - Survey with live requests
- DONE - Four fetchers; the board's remote badge kept as workplace_type

### DONE - Part-time boards
Remote Rocketship (filters by engagement for real) and a Himalayas search
mode; nine part-time boards surveyed, the rejected ones recorded.
- DONE - Fetchers and the survey

### DONE - Boards the person cannot apply through
MyCareersFuture needs a Singapore ID to apply (1175 vacancies in the base, 14
of them hot leads); devitjobs.uk redirected everything to a signup page from
2026-10-04. Their vacancies are rejected with the reason, the boards are no
longer fetched. devitjobs.com links, workplace, liveness and locations read
from the board's own fields.
- DONE - `closed_sources`
- DONE - devitjobs.com links, workplace, apply target and liveness

### DONE - Each board's website in the app
- DONE - The Source drop-down shows the site name
