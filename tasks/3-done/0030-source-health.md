# 0030 A source that breaks is noticed and repaired

Commits: 85dddb8 (2026-10-03)
Source: the agent: boards change their pages and APIs without notice

## Business
A board that changes its markup returns zero vacancies, and zero looks like
a quiet day. Each source states what a healthy answer looks like; before
fetching, the run checks every source against it and says which are broken,
unreachable or blocked. A broken source is repaired inside its own files,
verified, and only then published; a fix made by someone who is not a
maintainer stays local.

## Implementation
`contract()` per fetcher, `tools/source_contract.py`, the `/source-doctor`
skill and `tools/source_doctor.py publish` (commits only the source's files,
with the contract and the offline suite green). Live tests behind
`pytest --live`.

## Items
- DONE - A live contract per source, checked before fetching
- DONE - Doctor that repairs, verifies and publishes one source
