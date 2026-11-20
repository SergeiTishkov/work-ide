# 0132 The person's texts outlive their status

Source: the owner, 2026-11-20
Scope: app, tools, rules, docs

## Business
The owner, 2026-11-20: applied, undone, applied again: the text of the
"Applied" input must still be there; the same for the "not for me" and
"wrong pick" reasons. An analysis of these texts reads only the texts of
the status the vacancy has: with an applied comment and a "not for me"
reason on a vacancy now "not for me", the applied comment is ignored as
off-status. Off-status texts are read only when the owner tells the agent
to include them, or to read them alone. "All the applied comments" means
all those that are not off-status.

## Implementation
- `set_feedback` writes a text only to its status's column and keeps the
  others; "Undo" (funnel.stepBack) keeps them; the form opens with the
  text kept for that status, and a double click saves it as it is.
- Readers by status: `feedback.TEXT_STATUSES` (the applied comment counts
  for every status of the funnel), `feedback.applied_items(off_status=)`
  and `feedback.py applied --off-status skip|include|only`,
  `ai_brief.feedback_reasons`, the review package's `reason`;
  `feedback.reject` no longer erases the "wrong pick" reason.
- The rule in CLAUDE.md (§5).

## Items
- DONE - Texts kept, readers by status, the rule; tests (pytest, unit, UI); docs (CLAUDE.md, ARCHITECTURE)
