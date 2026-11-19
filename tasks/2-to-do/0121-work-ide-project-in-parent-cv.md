# 0121 Work IDE as an independent project in the parent CV

Source: the owner, 2026-11-20
Scope: documents (the owner's parent CV)

## Business
The parent CV lists independent projects (CHAD, the multi-agent framework)
but not Work IDE itself. The owner asked for its entry, written like the
other projects: short, achievements from the AI angle, no counts of
vacancies or applications, "multiple job boards" rather than a number.

The owner, 2026-11-20: the application itself is the achievement; its
technology is ordinary, its value is in the business decisions and the
polish. A bullet like "designed a deterministic Python pipeline" says no
more than "closed the tickets the product owner assigned". So every bullet
below is a measurement and the decision taken on it.

Sources read for it: all task files 0000-0120, docs/ARCHITECTURE.md (the
AI check section, the thinking-off measurement, the first top run, the
time-zone fix), tasks 0100, 0109, 0115, 0118, the git history.

## The text (draft of 2026-11-20)

**Work IDE — Job Search System with LLM Screening**
https://github.com/SergeiTishkov/work-ide

Built a desktop system that collects remote vacancies from multiple job
boards, filters them with deterministic rules for recall and an LLM for
precision, and drafts tailored application documents. In daily use; built
with Claude Code over three and a half months, covered by 1,500+ tests.

- Kept the model as a reader, not the judge: it extracts facts, code decides. When it misread a time-zone window in 3 of 4 postings despite an explicit prompt rule, giving it the program's own reading of the window fixed 3 of the 4.
- Measured LLM verdict drift: a prompt change about languages alone flipped 30 of 121 approved postings to rejections on unrelated grounds. Verdicts are now stored against hashes of the posting and the prompt, and re-read only on an explicit decision. Turning extended thinking off cut the screening cost from $0.018 to $0.0059 per posting, with the same verdicts on 15 re-checked postings.
- Verified generated documents in code, not by the model: names, dates, numbers and technologies against the source CV, and a Summary budget the model rewrites to. With the prompt alone Summaries ran 1,200–1,830 characters; with the budget they average about 670, none over.
- Evaluated an LLM reviewer before adopting it: of 12 documents it flagged out of 86, about 5 were real misses; a narrowed prompt lost 3 of those 5, its verdict changed between runs, and its revisions added claims the source did not make. A generation-time rule caught all 5 misses on the first pass instead.

Technologies: Python · SQLite · Electron · Node.js · Claude Code · Claude (Opus, Sonnet, Haiku) · Prompt Engineering · Structured Outputs · pytest · Playwright
AI Systems: LLM Screening · LLM Evaluation · Output Verification · Prompt Versioning · Human-in-the-Loop Review

## Notes on the text
- The Summary average measured on the 85 CVs of 2026-11-17 is 665.8 characters, the maximum 698 (task 0118). The owner asked for 650 instead of 666; 650 is below the measured value, so the draft says "about 670". The alternative wording: "with the budget every one stays under 700".
- "$0.018 → $0.0059" is the price of one screening call; the same verdicts were checked on 15 postings only.
- The last bullet rests on task 0115, which is still open.
- Left out on purpose: the filter audit (one missed regex hid all 754 vacancies with ".NET" in the title — strong, but not about AI; it can replace the last bullet for backend vacancies); the LinkedIn paging fix (1,007 → 4,946 unique vacancies — carries a vacancy count); agent rules moved into tests and hooks (already in CHAD and the multi-agent framework); any vacancy or application counts.

## Items
- DONE - The text, from the task files, the docs and the git history
- TO DO - The owner settles the Summary wording ("about 670" or "under 700")
- TO DO - On the owner's request: the entry goes into the parent CV (documents/) and the cv-workspace copy (docx and PDF)
