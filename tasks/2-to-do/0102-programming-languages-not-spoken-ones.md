# 0102 A programming language named as a required language refuses the posting

Source: task 0042's review, 2026-10-28: sharp, vacancies 2f95b4ed, 51496080, 92c7a058, 821aaf37, e801cc81
Scope: tools, config

## Business
Task 0084 has the screening model name the languages a posting requires,
and the program refuses a posting that requires one the person does not
know. Five answers named programming languages there: "python" (four),
"php", "scala". ElevenLabs "Full-Stack Engineer (Backend Leaning)"
(2f95b4ed): the model kept it as a stretch, and "ai: language: requires
Python" alone refused it (score 5). The other four are refused for location
as well (Harvey twice, Händlerbund, Jobot).

## Implementation
- `config/ai_screen_prompt.md`, `required_languages` and
  `posting_languages`: human languages only (English, German, Polish);
  never a programming language. Under task 0103 the prompt change reads
  nothing again.
- `tools/ai_screen.py`, `language_refusal`: a name that is a technology of
  `config/tech_vocabulary.yaml` (its canonical names: Python, Go, PHP,
  Scala) is not a language the posting requires, so an answer already
  given decides right without a new read.
- Tests: `tests/test_ai_screen.py`, the five names above.

## Items
- DONE - The owner agrees (2026-10-28)
- DONE - The prompt line, the program's check, tests
- TO DO - The five records rescored
