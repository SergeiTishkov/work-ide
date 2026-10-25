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
`config/ai_screen_prompt.md`, `posting_languages`: a language is named when
the duties or the requirements are written in it; a job board's label line,
a heading or one sentence in another language do not count. A test with a
justjoin.it-shaped text is not possible without the model; the prompt hash
changes, so the re-read follows the 0084 limit (rejects carried over).

## Items
- TO DO - The owner agrees
- TO DO - The prompt line; the limited re-read; the four records out
