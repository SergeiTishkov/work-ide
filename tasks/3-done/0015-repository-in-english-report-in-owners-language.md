# 0015 The repository in English, the report in the owner's language

Commits: 2c3b6df e598c30 27695d0 9e26638 ce38cc2 b7f3cd6 a54be01 07056cb 7b6286a 051c0bf fcfc4bd 02d0ecb bc8231d 4796798 8e5092d cad1f2c (2026-08-06)
Source: the owner, before publication

## Business
The repository is public: anyone should be able to read it. The report is the
file its owner opens every morning, and it should be in the language they
talk to the agent in. Two different requirements that looked like one.

The comments were the most valuable part of the code — each exists because
something measurable went wrong once — so they were rewritten, not
translated, keeping the measurement and the reason.

## Implementation
`preferences.language` in the personal profile; `tools/i18n.py` keyed by the
English text, with a test that fails on a message without a translation or a
catalogue entry no code uses. Every module, test, doc, config and template
rewritten in English (514 Russian lines in score.py alone); rescoring 11414
vacancies after each step showed 0 differences. `tests/test_language_policy.py`
enforces the rule; non-Latin text stays only where translating it would break
what it does (vacancy fragments, the catalogue).

## Items
- DONE - The report follows the person's language
- DONE - All code, tests, docs, configs and templates in English
- DONE - The rule in CLAUDE.md and a test that enforces it
