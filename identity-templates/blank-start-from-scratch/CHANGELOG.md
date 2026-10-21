# Change log for the blank template

New versions go on TOP.

## V6 — ITAR as a word, 2026-10-22

**Changed** (`blank_criteria.yaml` → `remote_location_fit.hard_dealbreakers.keywords`):
"itar" becomes " itar" and "(itar". The bare "itar" sat inside "Mitarbeiter"
(German postings) and "military", and refused 11 vacancies on 2026-10-22
that never named ITAR. If your local criteria list "itar" among the hard
dealbreakers, write it the same way.

## V5 — an optional parent CV, 2026-10-12

**Added** (`blank_questionnaire.yaml`): `person.parent_cv` — an optional file
with every achievement of the person's working life, which Generate CV draws on
(`cv.parent` in the profile; see docs/IDENTITIES.md, "The CV per vacancy").

## V4 — exclusivity can be a line on the card, 2026-10-05

**Changed** (`blank_profile.yaml`): new `employment_type_priority.exclusivity_signals`,
phrases shown on the card rather than refusing the vacancy; the
questionnaire asks which of the two the person wants.

## V3 — the short name need not be an abbreviation

`blank_identity.md` and `blank_profile.yaml` no longer ask for the prefix to
be an abbreviation of the longer description: the short name and the
description are separate things (the owner, 2026-10-05).

## V2 — the template is in English

Every comment, placeholder and question in the scaffolding was translated into
English. Nothing else changed: the file set and the structure are the same.

## V1 — the first version

A full set of identity files with placeholders and comments explaining what
each section is for. It decides nothing on a person's behalf: they set every
substantive value during onboarding.
