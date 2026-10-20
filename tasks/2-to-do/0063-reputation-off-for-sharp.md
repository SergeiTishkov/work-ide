# 0063 Sharp collects no employer reputation

Source: the owner, 2026-10-21 ("reputation is overrated; remove it from our
main identity, keep it as an option for other pipelines; remote worldwide
vacancies turned out so valuable and rare that their reputation does not
matter")
Scope: identity:sharp, app

## Business
Employer reputation (Glassdoor and the like, `tools/reputation_lookup.py`,
the app's "Collect reputation" button, `company_reputation_signal` in the
criteria) is collected rarely and thinly for sharp, and does not change
what the owner applies to: a remote worldwide vacancy is worth a look
whatever its reviews say. For sharp it goes: no button, no lookups, no
reputation points in the score. The machinery stays for identities that
want it.

## Implementation
An identity-level switch (in the template's settings) that turns reputation
off; the sharp template sets it, with a CHANGELOG entry and a version bump.
The app hides "Collect reputation" for an identity with it off; scoring
skips `company_reputation_signal`. The task service (0056) then has no
reputation slot to carry.

## Items
- DONE - Plan (2026-10-21, with the owner)
- TO DO - The switch, defaulting to on; sharp turns it off (template version, CHANGELOG)
- TO DO - App and scoring follow it; tests
