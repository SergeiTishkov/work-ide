# 0084 The screening model names the posting's languages; the person's languages decide

Source: feedback review, 2026-10-22: sharp, vacancies b459c1d7, 4312bcc2, 8254e4da;
the design agreed with the owner 2026-10-25
Scope: tools, config, docs

## Business
The person: "JD is in Deutsch. I'm not able to speak this language fluently.
My languages are Russian (native) and English, that's it. Remove the jobs not
written in one of professional languages from the list of jobs completely,
from any statuses." And on a Finnish one: "Unknown language - finnish.
Remove these jobs from any sort of results."

- LichtBlick (b459c1d7): the description is German ("Über LichtBlick:
  Arbeitsmodell: Remote innerhalb Deutschlands ..."). The language gate
  found "bewerbung" and "vollzeit", below its threshold;
  `foreign_language_posting_hits` empty.
- Fennoa (4312bcc2): title "Full-stack ohjelmistokehittäjä", the text
  Finnish; there is no word list for Finnish.
- Crédit Agricole CIB (8254e4da): title "Développeur C#/.Net – Bonds H/F",
  no description (a LinkedIn card), marked wrong pick without a reason.

The owner, 2026-10-25, on how: two cases. (1) The posting is written in a
language the person does not know (Finnish, Spanish): out. (2) It is written
in one they know but requires one they do not (an English posting asking for
Spanish): out. A check of the share of English function words was turned
down: the person's languages may be ones such a check handles badly, and it
refuses by guesswork. "I would rather throw out a few wrong vacancies by hand
than lose the vacancy of my dreams without ever knowing." The read is the
screening model's (Haiku), with the person's languages named exactly: "state
clearly which languages fit; the others do not".

Measured 2026-10-25 over SHARP's base:
- Kept by the model: 126. None asked for a language the person lacks; two
  (Scalo, justjoin.it) were written entirely in Polish. The model read them
  and kept them: config/ai_screen_prompt.md lists the reasons to reject and
  language is not among them.
- Refused with language as the only reason: 170. Among them, English texts
  refused by one German gender marker, "(m/f/d)": "Senior C#/.NET Engineer
  (m/f/d) Healthcare, Remote" (score 34, German "nice-to-have"), "C# and
  .NET Developer (m/f/d) – November – 6 months" (31, no German asked); and
  bilingual ones: Dropon "[NL] ... " with an English half (49), BLOOMTECH
  in Japanese with "English version is below".
- The script refusal is labelled "posting appears to be in German".

Related: task 0074 (Polish phrases), cancelled for this one.

## Implementation
- `tools/ai_screen.py`: the schema gains `posting_languages` (the languages
  the text is written in; a bilingual text names both) and
  `required_languages` (what the employer requires; a wish is not a
  requirement). The message names the person's languages from the profile
  (`owner.languages`), and the brief hash covers them. `language_refusal`
  compares: no posting language among the person's, or a required one
  outside them, is a refusal. The program decides, not the model.
- `config/ai_screen_prompt.md`: the two fields, and language among the
  reasons to reject.
- `tools/score.py`: the model's language refusal is an `ai: ` dealbreaker.
  The guesses of the language gate (frequent words, the gender marker, the
  share of another script) refuse only where no model reads the posting
  (`ai_screen: {required: false}`); with the model they are recorded and do
  not refuse. The employer's own words ("fluent german", "German C1") still
  refuse. The script refusal says the script.
- The bare "deutschkenntnisse" was to stop refusing ("Deutschkenntnisse von
  Vorteil" is a wish). Measured first: the four vacancies it alone refused
  asked for "C1/C2", "verhandlungssicher", "fließend"; none with a wish
  was refused for it alone. It stays; the templates do not change.
- The re-read is limited: answers the model gave as "reject" under the
  previous prompt stay (new fields can only add a reason to refuse); the
  kept ones and the vacancies the gate no longer refuses are read.

## Results, 2026-10-25, SHARP
The re-read: 1729 "reject" answers carried over to the new brief hash; the
whole base rescored (the first rescore ran outside the queue, and an AI
task that loaded the base before its save wrote the old scores back over
it; the second held the collect slot). The model read 623 vacancies in two
AI tasks (#28: 356, $4.61; #33: 267, $3.80): 514 refused, 109 kept, no
errors. The estimate was about 320; the rest are vacancies the gate's
guesses no longer refuse, which rose into the classes the model reads.
PARTSHARP is turned off; its AI task was skipped.

The list the app shows (hot_lead, worth_a_look, long_shot): 107 before, 87
after; 6 in, 32 out.
- The model's language refusals: 261 vacancies, "posting written in X" or
  "requires X"; German, Dutch, French, Italian, Polish, Spanish, Japanese,
  Norwegian, Swedish, Portuguese, Mandarin. About 95 of them looked at by
  title and the named languages: no wrong one.
- Scalo f9a18ba3 ("posting written in Polish") and SCALO ff8e02cc
  ("requires Polish"): out of the list.
- Keil "C# / .NET Developer (m/f/d) – November – 6 months" 73ceb1b1 and
  145b0ebe: English, refused before by "(m/f/d)"; back in worth_a_look.
- LichtBlick b459c1d7 and Fennoa 4312bcc2: refused, as before. Crédit
  Agricole 8254e4da: remote_unconfirmed, a card with no text, not read
  (task 0085).
- Dropon 7a7d2d73: read as dutch + english, no language refusal; refused
  for hybrid work in Ghent.
- Into the list wrongly: four justjoin.it postings written in Polish
  (3e6e4de1, 35ecb1c9, afe63a3d, 4025f4c3). The site puts an English line
  at the top ("Languages: English skills required (English B2)"), and the
  model named english beside polish. Task 0099.
- Out of the list on other grounds: 30 of the 121 kept answers in the list,
  read again, came back "reject" for location, stack, level or part time.
  Task 0100.
- 258 vacancies the gate guessed to be in another language are in
  remote_unconfirmed, which the app does not list and the model does not
  read; before they were rejected.

## Items
- DONE - Language fields and the program's refusal in the AI screen; the person's languages in the system prompt and the brief hash; prompt; tests
- DONE - The language gate's guesses do not refuse where the model reads; the script label; tests
- DONE - The bare "deutschkenntnisse": measured, stays (no template change)
- DONE - Docs: ARCHITECTURE, IDENTITIES, config/derivation/languages.yaml
- DONE - Rescore and a limited re-read; measure what moved (the three records above, the two Scalo, the two freelancermap "(m/f/d)")
