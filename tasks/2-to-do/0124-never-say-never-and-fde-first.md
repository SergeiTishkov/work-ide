# 0124 Never say never, and forward deployed roles count for the search

Source: the owner, 2026-11-20
Scope: tools, app, identity:sharp

## Business
The ENDGAME vacancy (task 0122; Forward Deployed Engineer, AI-native
consulting, remote Europe, .NET among the languages) scored 8 with its text
read and was not listed: long_shot starts at 10. Its score: stack +14,
the Node.js/Next.js penalty -10, location +4. A forward deployed title was a
"stretch" (task 0042, 2026-10-20: -4 and a read by the screening model), not
a plus.

The owner, 2026-11-20:
- the JavaScript penalty goes;
- a cut at 5 points, and a class of its own between 5 and long_shot,
  "Never say never", with no documents generated for it;
- forward deployed or similar is +20, AI-native +10; forward deployed is no
  minus;
- "no leetcode" is neither a plus nor a minus (there was no such check).

Measured before the change, SHARP, unanswered: 292 vacancies at 5-9 points
in low_priority (70 first seen since 2026-11-01).

## Implementation
- `score.py`: an optional `classification_thresholds.never_say_never`; a
  total from it up to long_shot is class `never_say_never` (not held for the
  screening model). Listed last (`report.LISTED_CLASSES`), its descriptions
  read like the other listed classes (`enrich_descriptions.HEAD_CLASSES`),
  offered by the clean-up; the app names the section.
- The automatic CVs and letters take only the classes an identity's filter
  names; SHARP's names hot_lead, worth_a_look and long_shot.
- The local identity (outside git): `personal_tech_bonus.js_backend` removed;
  `classification_thresholds.never_say_never: 5`; `extra_signals`
  forward_deployed (+20) and ai_native (+10); forward deployed out of
  `role_relevance_signal.stretch_discipline_title_patterns`.

## Items
- DONE - The class: scoring, listing, descriptions, clean-up, the app's labels; tests
- DONE - The SHARP identity's settings above (2026-11-20). ENDGAME rescored with them, read-only: 48 (forward deployed +20, stack +14, AI-native +10, location +4), hot_lead by the scripts, waiting for the AI read
- TO DO - The rescore of the base: the next rest run (no AI re-read; vacancies new to the top classes get their first read)
