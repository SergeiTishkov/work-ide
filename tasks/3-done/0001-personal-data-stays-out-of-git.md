# 0001 Personal data stays out of the repository

Commits: 90d2ea8 529d674 a0057d4 f237853 2f481e9 45ff52f 62616ad 5c3d68d (2026-08-04 — 2026-08-06)
Source: the owner, preparing the repository for public GitHub (2026-08-04)

## Business
The repository is public (Apache 2.0) and was mentioned to an employer. Name,
CV, residency, pay expectations and the reasons behind a search are facts
about a person, not about the search, and must not be in git — including the
history and the wording of examples.

Audits found what a first pass missed: a tagline describing "a second desk
where the same engineer works at half strength for a second salary", a
questionnaire answer to a question named `employment.second_job`, a fixture
saying the main job satisfies the need for interesting problems. The meaning
of each search stays; the person's circumstances go.

## Implementation
First a gitignored "Local Constitution" with a `local` sentinel; on
2026-08-05/06 replaced by the git boundary itself (task 0014): templates in
git hold no personal fact, the person's identity lives outside git. The
sentinel, `active.yaml`, `default_identity` and `init-local` (about 200
lines) were removed once verified inert. Git history was started from
scratch so nothing leaks from earlier commits. Migration text for versions
nobody installed was removed.

## Items
- DONE - Personal values out of every file in git
- DONE - Gitignore rules that do not swallow shipped templates
- DONE - Wording that discloses why a search is wanted removed from templates and docs
- DONE - The Local Constitution layer removed after the git-boundary split
- DONE - History started from scratch before publication
