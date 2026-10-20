# 0014 Search templates in git, the person's search outside it, updates by version

Commits: c72a394 9cb0d5b dc4545d 4796798 a54be01 07056cb (2026-08-05 — 2026-08-06)
Source: the agent put things in the wrong layer twice in one session

## Business
A search type (what a senior .NET remote search refuses and why) is shared;
the actual search of one person is not. When the shared part improves, a
`git pull` must not quietly move anyone's results, and updating must not
include a step where an agent decides which personal setting to keep.

## Implementation
`identity-templates/<name>/` in git with no personal fact;
`local-identities/<prefix>-<expansion>/` outside git holds a verbatim copy of
the template in `template/` plus personal files layered on top. Updating
replaces `template/` only; the conflicts are a computed list of keys the
person overrode that the new version touched. Versions are numbers in
`template.yaml`, each bump with a CHANGELOG entry (a test checks), and a test
fails while a local identity is behind its template. The run command stops
and asks when the template moved. Verified: rescoring 11414 vacancies after
the split changed nothing.

## Items
- DONE - Templates and local identities split at the git boundary
- DONE - `templates.py check / update` with computed conflicts
- DONE - Version numbers, changelog required, "behind its template" test
- DONE - doctor reads the layered settings instead of one file per document
