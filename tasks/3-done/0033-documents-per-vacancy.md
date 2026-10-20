# 0033 A CV and a cover letter for one vacancy

Commits: ccbf8a9 cf7b113 (2026-10-13 — 2026-10-18)
Source: the owner

## Business
Applying well means a CV that puts forward what this vacancy asks for and a
letter that says why. The person presses a button on the card and gets
both as .docx and .pdf, made from their own CVs only, every claim checked
against them. Versions are kept, the person's own Word edits are read
before the next version, and a vacancy that is gone gets no documents.
Documents for the top of a new collection can be made without a click.

## Implementation
See the sub-tickets.

## Sub-tickets

### DONE - Tailored CV
From the common CV and an optional parent CV (every achievement); 2-3 pages;
.docx and .pdf through Word; a fact check in code lists claims found in
neither CV; optional instructions for one CV. `tools/cv_tailor.py`.
- DONE - Generation with the fact check
- DONE - Instructions for one CV

### DONE - Cover letter
One page under the CV's header; name, contacts, numbers and technologies
checked against the CVs. `tools/cover_letter.py`.
- DONE - Generation with the check

### DONE - Folder per vacancy with versions
One folder for all identities (default ~/Downloads/Work IDE CVs and CLs),
`<prefix>/<vacancy id>/`, logs and "Old versions/V<n>"; the model reads the
log and the current .docx; a vacancy with a dead link or a description under
100 characters is gone.
- DONE - Folder, logs, versions
- DONE - The person's edits read before the next version

### DONE - Generating without a click
`cv.auto` in the profile chooses documents and filters; a detached batch
makes one document at a time after a collection that succeeds, skipping
made and gone ones; the app's own requests go first.
- DONE - `cv.auto` and `tools/cv_batch.py`
- DONE - Batch started by the app after a collection
