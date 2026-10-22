# 0080 The word remote about products and support is not remote work

Source: feedback review, 2026-10-22: sharp, vacancies 32041a86, 9512ffb7, bb3f0fb2, d1dadb2a, 3284f0ad, ee0bae05, 6aa298c1, 7beecaca, ae04fee8, db7aeb04
Scope: config

## Business
The person marked these "wrong pick". In each, the only "remote" in the text
is about a product, a server or support work, not about where the job is
done. On LinkedIn (the workplace is hidden, `explicit_remote_keywords`)
such a word let an office job in Redmond, Boston or Austin into the top
classes. The quotes are in our `description_text`: the gate read them and
counted them.

- Microsoft, Redmond (32041a86, 9512ffb7, bb3f0fb2): "connecting to Windows
  365, Azure Virtual Desktop, and remote PCs", "make remote Windows
  experiences secure". The person: "it literally says stuff like you'll be
  working on remote windows features and you deem it worthy to show as
  worldwide remote".
- Anduril, Boston and Quincy (d1dadb2a, 3284f0ad, ee0bae05): "troubleshooting
  and analyzing remotely deployed software systems".
- Dimensional Fund Advisors, Austin (6aa298c1): "third-level support for
  local and remote investment business clients".
- EP Energy, El Paso (7beecaca): "Provides remote support to end users"
  (its other line is in 0081).
- GamblingCareers, Melbourne (ae04fee8): "'Engine' is the remote gaming
  server". The person: remote is the engine's description, the job itself
  is onsite. The AI check rejected it since.
- Fleetworthy, Edmonton (db7aeb04): "ensuring remote teammates are
  included", "in a remote or hybrid environment" (requirements, not the
  arrangement).

Since task 0078 such vacancies wait in "Not processed with AI" instead of
the top classes. The scripts' verdict is still wrong, and each one costs an
AI call.

## Implementation
`remote_word_other_meanings` in
`identity-templates/sharp-senior-dotnet-remote-engineering/sharp_criteria.yaml`
(and the partsharp and blank templates; a template version step): add
`remote (?:PCs?|Windows|support|gaming server|investment|business clients|teammates|clients)`,
`remotely deployed`, `(?:a |in a )remote or hybrid environment`,
`local and remote \w+`. A test in `tests/test_score.py` per quote: the
sentence in a LinkedIn vacancy does not confirm remote.

## Items
- TO DO - Patterns for the quoted senses, with a test per quote
- TO DO - Rescore; count how many LinkedIn vacancies leave the AI queue
