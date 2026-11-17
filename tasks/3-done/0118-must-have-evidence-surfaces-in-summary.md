# 0118 A must-have's buried evidence surfaces in the Summary

Source: the owner, 2026-11-14 (after the Sonnet review of task 0115)
Scope: config

## Business
The Sonnet review of the 86 CVs regenerated in task 0114 found five real
misses (task 0115). In all five the parent CV had the evidence, and the
CV had it too, or could have, but where a recruiter does not look: the
last line of the oldest job, mid-sentence in a job description, a
project cut for length. A version revised after the review fixed each of
them by moving the evidence into the Summary; in the 3-page CVs the
added text pushed other strong bullets out (task 0115, "The revision").

The owner's decision: the generation does this itself, the first time.
A must-have the parent CV answers but the top of the CV does not show
gets one short clause in the Summary. At most three per CV, so a vacancy
with ten requirements does not turn the Summary into a keyword list. An
ATS reads the whole CV; a recruiter reads the top.

## Implementation
- `config/cv_tailor_prompt.md`, the Summary section: the rule, with its
  limits:
  - only a requirement the vacancy states as required;
  - only when the evidence is not already visible in the Summary or
    Technologies;
  - one short clause each, at most three, the ones that weigh most for
    the screening;
  - the parent CV's fact; the vacancy's term only when the fact is that
    thing.

## Measured on 2026-11-14
Twelve CVs made anew with the rule (queue tasks #190-#201), against their
V2, made anew without it the same day (task 0114):
- The five misses of task 0115: all five in the Summary at the first
  generation (SQL performance for GR8_TECH and TalentHop, the educational
  portal for Crimson, multi-tenant authorization for Softthink, AWS
  deployment for Notabene). No job bullet or project was lost the way the
  revision lost them in Notabene.
- Summary length: from -10% to +35%, about +15% on average; Notabene
  1372 -> 1826 characters.
- Pages: 10 unchanged; two engineering CVs went from 2 to 3 (Camunda
  backend, N-iX), each with a Summary longer by about 250-300 characters.
- Prose the parent CV does not state: "AWS S3, DynamoDB and Cosmos DB in
  Technologies and in independent projects" (a sentence about the CV
  itself, Camunda backend); "Remote since 2019" (Camunda backend);
  "C#/.NET, a statically typed backend language" and "high-volume product
  environments" (Notabene). The fact check reads terms only; all passed.

## Items
- DONE - The rule in the CV prompt
- DONE - Measure: the five CVs of task 0115 and the agent's seven, made anew with the rule; compare with the versions made anew without it
- DONE - The owner decides on the follow-up (2026-11-17, below)
- DONE - The Summary budget, `cv.summary_chars` (700): a longer Summary goes back to the model to be shortened, two rounds, then the run fails; the prompt's Summary rules; tests
- DONE - The parent CV's bullet on the AI code review workflow in the short form, its time spans and the PBI figures kept (local, the owner's files: `documents/`, and the docx and PDF in the owner's cv-workspace)
- DONE - Notabene's CV made anew with the new rules (queue task #202, V5): Summary 660 characters with no shortening round, 2 pages instead of 3, no findings; AWS stays in Technologies only, the self-deployed AWS project is not in the CV
- DONE - Three shortening rounds; past them the last answer is used with a warning, the run does not fail (the owner, 2026-11-17); tests
- DONE - The owner reads Notabene's V5 and decides whether the other CVs are regenerated with these rules: yes, after the weekly AI limit resets on 2026-11-18 21:59 (the run of 2026-11-14 cost $68 at API prices for about 85 CVs, the week stood at 96%). Then, the same evening, the owner asked to start at once with the week's remaining 4%: the one-off Windows task planned for 2026-11-18 was removed; the CV files of the 86 active vacancies not applied to (456 files: current pair, log, old versions; cover letters left in place) were moved to `data/identities/sharp/cv_backup_2026-11-17/`, so the app shows no CV until a new one is published; 86 anew CV tasks queued, the highest score first (#204-#289, scores 74 to 10). Notabene, applied to, kept its V6 (queue task #203, made with the Technologies rule of task 0120)
- DONE - Read the regenerated CVs (2026-11-17, tasks #204-#289, #250 failed: the vacancy lost its description; #263 failed on a dropped API connection and was made as #290): 85 CVs. Summary 666 characters on average (1,316 before), at most 698; 8 shortened, none still over after three rounds. Pages: 2 in 46, 3 in 38 (28 and 56 before); every ai CV at 3 (12), mixed 22 of 36 (task 0117), engineering 4 of 36. Findings in 15 CVs, all Technologies terms: 7 "Entity Framework Core" against the parent's "EF Core", generic terms (OOP, REST APIs, Clean code, Design Patterns, Debugging), one item with a comment in it ("Python-adjacent: Apache Spark", #279)

## The owner's decisions of 2026-11-17
After the measurement, the owner read Notabene's CV: "C#/.NET, a
statically typed backend language" and a 1,826-character Summary. Samples
of strong CVs the owner keeps run 560-720 characters; career advice
agrees on 2-4 lines, 40-80 words.
- The Summary is at most 700 characters, every paragraph together. Code
  counts it after the model answers; a longer one goes back to the model
  to be shortened (its own small prompt, no new facts), up to three
  times; still over after the third, the last answer is used and the run
  goes on with a warning, it does not fail. Code never cuts it.
- The vacancy's term names the person's fact; its descriptions, reasons
  and adjectives are not copied ("a statically typed backend language",
  "where correctness matters more than features", "high-volume").
- A surfaced must-have clause takes the place of a sentence that weighs
  less; it never makes the Summary longer.
- At most two achievements with figures, short, their numbers and time
  spans exact; the model picks which for the vacancy, and the same two may
  appear in every CV.
- A word about the person's character stands only with a fact that shows
  it, or when the parent CV's own Summary says it; at most one beyond the
  parent CV's own. The owner: such words from the vacancy would do more
  harm than good.
- The Summary never speaks about the CV ("in Technologies").
