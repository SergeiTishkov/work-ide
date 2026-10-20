# 0002 Tests leave the owner's real data and folders alone

Commits: eded2fa 4f2f971 6afa434 (2026-08-04 — 2026-09-30)
Source: the owner found test leftovers in their reports folder

## Business
The reports folder is the one place a person actually looks. The test
fixture created empty `reports/archive/aaaa` and `bbbb` folders there on
every run, and later `ftf_latest.md`, `reports/archive/ftf/` and `data/ftf/`
— found by the owner a day after. Detecting the write was not enough: the
files stayed where a person looks.

The app's smoke test failed at random while the real app was open, because
two Electron processes shared one profile folder.

## Implementation
The fixture redirects both data and reports roots; a session guard fails the
run when a test writes under the real roots and removes the traces itself.
`tools/clean_fixture_artifacts.py` refuses to touch anything not marked
`kind: fixture`. Test instances of the app get their own Electron profile
(`WORK_IDE_USER_DATA`).

## Items
- DONE - Tests write only into temporary roots
- DONE - A session guard that fails and cleans up fixture traces
- DONE - A test app instance with its own profile folder
