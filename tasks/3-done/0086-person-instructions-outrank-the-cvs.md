# 0086 The person's instructions outrank the CVs

Source: the owner, 2026-10-22
Scope: config

## Business
The owner asked twice to put their own text into the cover letter for
Northflank (V2, V3). The letters left out its strongest parts: headhunted
with one application, the "Strong Yes", several dozen Go and Java
interviews, side projects on Node.js. The prompts said the person's
instructions "never make a fact true": a claim the CVs do not support stayed
out even when asked for.

The owner: the instructions given for a generation outrank every other
document, up to rewriting what the CVs say. The person is the source of
their own facts; the CVs are documents they wrote.

The fact check stays. Without a message it works as before: a model's small
rewordings ("a bit off here, a bit off there") add up to a different career.
With a message it works too, but where the message states something, the
message wins; a finding the message does not cover stays a finding.

## Implementation
- `config/cover_letter_prompt.md`, `config/cv_tailor_prompt.md`: the
  instructions outrank the CVs and every rule of the prompt; a fact stated in
  them (or in an earlier message of the log) is a fact, the instructions win
  over a contradicting CV, what they ask to rewrite is rewritten. The report
  gets `from_instructions`: each fact taken from them.
- `cv_tailor.person_text()`: the new message and the log. `check_facts()` in
  both tools takes it as a source beside the CVs: a name, contact, company,
  number or technology it states is not a finding. The rest is checked as
  before.
- The app lists `from_instructions` ("Taken from your messages").
- `docs/ARCHITECTURE.md`; tests in `tests/test_cover_letter.py` and
  `tests/test_cv_tailor.py`.

## Items
- DONE - The prompts: the person's instructions above the CVs and the rules
- DONE - The fact check reads the person's messages as a source; without them, unchanged
- DONE - The report and the app show what came from the messages
