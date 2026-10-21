# 0042 Stretch roles: remote outranks the technology

Commits: 7f77436 63a12f5 (2026-10-20, branch `stretch-roles`)
Source: the owner, 2026-10-20

## Business
A remote role off the stack or the level (forward deployed engineer, AI
engineer, a data-adjacent backend role) is worth reading if the CV can carry
it: for this search, being hireable remotely matters more than the exact
technology. Such roles were refused by keyword. Now the screening model
reads them against the CV and says whether the CV fits, is a stretch, or
does not; a stretch is kept at a lower score and marked in the list.
Machine-learning research, data-heavy roles and AI-training crowdwork stay
out.

Dry runs on samples: kept Sticker Mule (agents/Go), ElevenLabs, Scopic FDE,
Deel, Proxify, Teravision, UpGuard, Oowlish, Lemon.io; rejected ML research
(Kimchi, Jumio, hims, Tether) and data-heavy roles; forward deployed
rejects were all geography (Cloud9, Smartsheet, Stripe, Kong). Doubtful
keeps: Doit Singapore, Camunda Quality, Big Wave.

## Implementation
Criteria `stretch_roles` (off unless enabled) turn stack and title
mismatches into objections the model reads; the model's `cv_fit` and
`work_kind` lift or confirm them; `stretch_points` -4. Up to 400 stretch
reads a run after the top. Template sharp v28 moves data, ML/AI engineer and
forward deployed titles to stretch and adds LinkedIn and HN keywords. The
app shows "a stretch for the CV" or "another stack, fits the CV" with the
model's reason. The scorer's time-zone reading goes to the model as a fact.

## Items
- DONE - Stretch objections read by the model instead of refused by keyword
- DONE - `cv_fit` and `work_kind` in the screen; stretch points
- DONE - Template sharp v28
- DONE - Stretch badge in the app
- DONE - Time-zone fact passed to the model
- DONE - Merge the branch into main once the LinkedIn run has finished (7f77436 and 63a12f5 are on main)
- DONE - Update the local sharp identity to template v28 (`templates.py update --identity sharp`; on v29 by 2026-10-21)
- DONE - Apply the owner's personal stretch settings to the local identity (2026-10-21: `stretch_roles: {enabled: true, stretch_points: -4}` and `stretch_if` on the junior rule for data, ML/AI and forward deployed titles; until then the switch was off, and the base's forward roles stayed refused by title: 341 of 454, the owner asked why none showed)
- TO DO - Full Python and UI suites on main after the merge
- TO DO - Read the stretch backlog: about 1,168 vacancies, about $7, 400 a run (the first `rest` run queued 2026-10-21; the queue holds one `rest` of an identity at a time, so the next is added when it ends)
- TO DO - Review the kept and rejected stretch roles with the owner; tune `stretch_points` and the doubtful kinds
