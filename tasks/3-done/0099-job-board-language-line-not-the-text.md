# 0099 A job board's English line does not make a Polish posting bilingual

Source: task 0084's measurement, 2026-10-25: sharp, vacancies 3e6e4de1, 35ecb1c9, afe63a3d, 4025f4c3
Scope: config

## Business
Four justjoin.it postings written in Polish reached the list (worth_a_look,
long_shot) after the language read moved to the screening model (task
0084). Their text starts with the site's own line in English, "Languages:
English skills required (English B2).", and goes on in Polish ("Jako Senior
Software Engineer będziesz projektować ..."). The model named
`posting_languages: ["english", "polish"]`, so English counted as a
language the posting is written in. Before 0084 the gate's Polish word list
refused all four.

## Implementation
`config/ai_screen_prompt.md`, `posting_languages`: a language counts when
the duties or the requirements are written in it; a text with versions in
two or more languages still names each, so a posting with an English
version stays (the owner, 2026-10-28). A job board's label line, a heading,
technology terms or one sentence in another language do not count. A test
of the wording needs the model, so there is none.

The four were answered by the owner already (one marked bugged, three
rejected); under task 0103 the prompt change reads nothing again.

## Items
- DONE - The owner agrees (2026-10-28), with the rule that a text given in several languages keeps each of them
- DONE - The prompt line
