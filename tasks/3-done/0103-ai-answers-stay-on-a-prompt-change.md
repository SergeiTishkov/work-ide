# 0103 AI answers stay when the prompt or the brief changes

Source: the owner, 2026-10-28, while closing task 0042
Scope: tools, rules, docs

## Business
Until now a stored answer of the screening model was valid only for the
prompt, the brief and the languages it was given with (`brief_hash`). Any
change there read the whole top and the waiting stretches again: a brief is
rewritten by itself when the CV or the identity documents change. A re-read
costs tokens, and the model's verdicts drift: after a prompt change about
languages alone, 30 of 121 kept vacancies came back rejected on other
grounds (task 0100).

The owner keeps the list empty and applies at once, so what the list held
before a change has been seen already. The owner's rule: after a change to
the pipeline, the prompt or the brief, existing vacancies are not read by the
AI again. The re-read is offered, and only an explicit "yes, read them again"
from the owner starts it. The rule is about the AI read only: the free
rescoring of the base by the scorer (every rest run) stays as it is.

## Implementation
- `tools/ai_screen.py`, `worklist`: an answer stays while the posting's text
  holds (`text_hash`); a different `brief_hash` asks again only with
  `reread`.
- `tools/pipeline.py --ai --reread`, queued as `taskq.py add ai --args
  '{"reread": true}'`: the one way to read the answered vacancies again.
- `CLAUDE.md` and `docs/ARCHITECTURE.md`: the rule.

## Items
- DONE - `worklist` keeps answers given under another brief; `reread` asks again
- DONE - `--reread` on `pipeline.py --ai`, through the queue's `ai` task
- DONE - The rule in CLAUDE.md and docs/ARCHITECTURE.md
