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

## Review (2026-10-23)
SHARP, the base of 2026-10-23 (82,504 vacancies), `score_breakdown.stretch_roles`
and the AI answers:

- 22,820 vacancies carry a stretch objection. 21,193 of them are refused for
  something else as well (mostly location) and are never read; 801 wait for
  the read alone, 130 of those wanted by the next run.
- Read: 826. `cv_fit` "no" 712, "stretch" 109, "fits" 5.
- In the list now (kept and not refused for another reason): 5 worth a
  look, 2 long shot, 5 low priority; 1 hot lead (Camunda, Backend - Data
  Layer, 66). The other 97 "stretch" reads are refused for location.
  - Worth a look: Growth Minded Senior Data Engineer (35), Scopic FDE (33),
    ElevenLabs Full-Stack Creative Agents (31), Deel Back-End Engineer (31),
    Deel AI Engineer Backend (31).
  - Long shot: Doit Lead Engineer Singapore (27), Oowlish Vue + Nest (22).
- Work kind of the "stretch" reads: software 47, applied AI 31, data heavy
  25, other 6. Data heavy was meant to stay out (Business above); the model
  keeps it as a stretch (Growth Minded, Plexus).
- Work kind of the "no" reads: other 392 (not development, crowdwork, ERP,
  Salesforce, SAP), software 178 (mostly another main language: Java, Go,
  Kotlin, Python), applied AI 60, ML research 56, data heavy 26.
- The same posting on two boards was read differently on the same day
  (2026-10-21): Deel "AI Engineer, Backend" and "Back-End Engineer", and Doit
  "Lead Engineer - Singapore": one copy "stretch, keep", the other "no,
  reject". Corrected 2026-10-24: the list shows the better-scored copy,
  and that is the rejected one (the kept one lost 4 points as a stretch):
  the kept copies are hidden. Task 0096.
- The three doubtful keeps of the dry run: Doit (above), Camunda Quality
  ("no": production LLM work wanted), Big Wave (a stretch, refused for the US
  market).

Open questions for the owner:
1. Another main language (Java, Go, Kotlin, Python backend): "no" now. Keep,
   or read them as a stretch?
2. Data heavy roles: the model keeps some as a stretch. Leave, or refuse
   them by kind?
3. `stretch_points` -4: the kept ones land at 22-35 (long shot to worth a
   look). Keep the value?
4. Two copies read differently: accept (the better copy shows), or read
   duplicates once and share the answer?

The owner's answers (2026-10-24):
1. Another main language is a stretch: "what if a magic vacancy with PHP
   comes up? I'd gladly take it."
2. Data heavy roles: left to the model; the owner tunes it later if needed.
3. `stretch_points` -4 stays.
4. Asked to explain first; open.

Done for 1 (the local identity, outside git):
- The "no" came from the SHARP brief, not from the shared prompt: the brief
  turned point 5 of the template ("a stack that is neither .NET/C# nor
  JS/TS" is out) into "main stack Python, Java/Spring, Go, Ruby, PHP... =
  no" and "Node as the backend = no". The shared prompt already called
  another mainstream stack a stretch.
- `local-identities/sharp-.../sharp_identity.md`: a section "Another main
  language is a stretch", over point 5 of the template: Java (Spring web
  too), Kotlin, Go, Python, PHP, Ruby, Node as the backend are a stretch,
  "5+ years of X" included; a "no" only for a specialist in the language or
  its runtime, or work that is not development.
- The brief rewritten (`tools/ai_brief.py --identity sharp`) and read: the
  rule is in, nothing contradicts it. A first wording ("years of deep
  expertise ... stays a no") let the brief keep "Java/Spring web = no" and
  add "strong Python backend = no"; the section was reworded.
- The refused reads are asked again because the brief changed (score.py
  `screen_wanted`, ai_screen.worklist checks the brief's hash): the next
  runs re-read the top classes and up to 400 refused or waiting stretches
  a run.

## Items
- DONE - Stretch objections read by the model instead of refused by keyword
- DONE - `cv_fit` and `work_kind` in the screen; stretch points
- DONE - Template sharp v28
- DONE - Stretch badge in the app
- DONE - Time-zone fact passed to the model
- DONE - Merge the branch into main once the LinkedIn run has finished (7f77436 and 63a12f5 are on main)
- DONE - Update the local sharp identity to template v28 (`templates.py update --identity sharp`; on v29 by 2026-10-21)
- DONE - Apply the owner's personal stretch settings to the local identity (2026-10-21: `stretch_roles: {enabled: true, stretch_points: -4}` and `stretch_if` on the junior rule for data, ML/AI and forward deployed titles; until then the switch was off, and the base's forward roles stayed refused by title: 341 of 454, the owner asked why none showed)
- DONE - Full Python and UI suites on main after the merge (2026-10-23, at 554bee3: Python 1489 passed, 1 skipped, the language check failed on Russian in the texts of 0092-0094, fixed in 78a052d and then 11 passed; unit 99; UI 141)
- DONE - Read the stretch backlog (SHARP, 2026-10-21): five `rest` runs screened 459, 443, 417, 400 and 114 vacancies and kept 26, 25, 6, 4 and 2 (1,833 read, 63 kept, USD 21.07). The estimate was 1,168: each run's description fetch (927, then 334) made more vacancies wait for a read. No stretch waits now
- DONE - Review the kept and rejected stretch roles with the owner; tune `stretch_points` and the doubtful kinds (2026-10-24: "Review" above; points and data heavy kept, another language made a stretch)
- DONE - Two copies of one posting read differently: the owner decides after the explanation (question 4; 2026-10-24: the best-filled copy alone, task 0096)
- TO DO - After the next runs, show the owner what the new brief kept among the other-language roles
