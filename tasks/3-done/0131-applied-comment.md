# 0131 A comment on "Applied"

Source: the owner, 2026-11-20
Scope: app, tools, docs

## Business
The owner, 2026-11-20: "Applied" gets an optional text input with the same
logic as "Not for me": one click opens it, a double click saves at once.
The owner writes there what they told the employer about themselves, the
answers an application form asks for and no CV holds; later these feed the
parent cover letter.

## Implementation
- `vacancy_identity.applied_comment` (schema 12, `db._to_12`); NULL for an
  empty text and for the applications before.
- The app: "Applied" opens the reason form (four rows), Save, Ctrl+Enter or
  a second click within 500 ms saves; the "Applied" step of the timeline
  shows the comment and edits it; undoing the application clears it.
- `python tools/feedback.py --identity <p> applied [--id X]`: every
  application with its comment, newest first, as YAML (the reader for the
  cover letter). The AI screening brief does not read it.
- `merge_shared_base.py` does not carry it: the per-identity files of
  versions 1-7 it reads never had the column.

## Items
- DONE - The column and its migration, the app's form and timeline, `feedback.py applied`; tests (pytest, unit, UI, Electron smoke); docs (ARCHITECTURE)
