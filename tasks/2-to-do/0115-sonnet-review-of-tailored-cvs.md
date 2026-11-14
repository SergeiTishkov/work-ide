# 0115 A Sonnet review of tailored CVs, and one regeneration when it finds a real miss

Source: the owner, 2026-11-14
Scope: tools, config

## Business
A tailored CV is checked today in code: its structure, its hard facts and
its page count. Nothing checks how well it answers the vacancy. The model's
own report (covered, gaps, stretched) is written by the model that wrote
the CV.

The idea, discussed with the owner on 2026-11-14:
- A second model (Sonnet) reads the vacancy, the parent CV and the
  tailored CV.
- It answers a narrow question: is there a requirement of the vacancy that
  the parent CV gives evidence for, but that the tailored CV leaves out or
  buries?
- A remark counts only if it quotes three things:
  - the requirement, from the vacancy;
  - the evidence, from the parent CV;
  - where that evidence is in the tailored CV now ("absent", or "the last
    bullet of an old job").
  The quote requirement keeps out remarks of the kind "it could be a little
  better", and it keeps the reviewer from asking for anything the parent
  CV does not have.
- A misread vacancy type (an AI-heavy role read as plain .NET, which drops
  the projects) also counts.
- When a remark is about a must-have requirement, the CV is generated once
  more. The generator gets two things:
  - the remarks, as the reason;
  - what the review found strong, so the new version keeps it.
  That version is final; it is not reviewed again.
- A vacancy that matches poorly is not a miss: when the parent CV has no
  evidence either, it is a real gap, and nothing is regenerated.

The owner's doubt is that this may be engineering for its own sake. So it
is measured before it goes into the pipeline:
1. The agent reads the CVs regenerated in task 0114 against their vacancies
   and the parent CV, and notes the real misses.
2. A one-off script runs the Sonnet review on the same CVs, with no
   regeneration.
3. The two sets of remarks are compared. Does Sonnet find the agent's
   misses, and how much noise does it add?
4. If Sonnet finds the misses, the regeneration with its remarks runs for
   the CVs that need it. The agent then checks whether the new versions
   got better.
5. The result goes to the owner, who decides whether the review becomes
   part of the generation.

## Measured on 2026-11-14
- The agent read 7 of the 86 regenerated CVs in full against their
  vacancies (two Camunda roles, GitLab, Kraken, N-iX, Version 1, M-KOPA):
  no must-have left out or buried; the vacancy type read right in each.
- Sonnet, first prompt, all 86: 74 keep, 12 regenerate. Keep on all 7 the
  agent read. Of the 12, about 5 were real misses: an ed-tech role with the
  educational portal buried; SQL optimization required twice, its one piece
  of evidence in the oldest job's last line; authorization required and
  buried; AWS ownership required, its evidence in a project cut. Six were
  soft skills (communication, proactivity) or "algorithms" answered by an
  indirect quote.
- The prompt was narrowed: soft skills and general computer-science
  phrases are not misses; a miss is a concrete skill, technology, domain
  or kind of work.
- Sonnet, narrowed prompt, on 19 CVs (the 12 above and the agent's 7):
  3 regenerate. Two real (the two SQL ones), one a stretch (an allow/deny
  layer read as role-based access). Keep on all 7 the agent read. It no
  longer flagged three of the five real misses (ed-tech, authorization,
  AWS), and on the same CV its verdict changed between runs.

## The revision, measured on 2026-11-14
The five real misses, revised with `--review` (queue tasks #185-#189);
the version before is V2 in `Old versions/`.

| Vacancy | The miss fixed | Pages | What else changed |
|---|---|---|---|
| GR8_TECH, .NET payments | yes: SQL performance in the Summary, the SQL bullet first | 2 -> 2 | "tuning the query around that schema" added to the SQL bullet; the parent CV says "a performant SQL script" |
| TalentHop, Lead .NET full stack | yes: SQL Server performance in the Summary | 2 -> 2 | "replacing slow reporting over a structure that was never meant for analytics" added; the parent CV has no such claim |
| Crimson, FDE | yes: the educational portal in the Summary and first in its job | 3 -> 3 | the length cut removed the bullet on the team's first Cursor Skills and multi-agent orchestration Skills |
| Softthink, Senior .NET | yes: multi-tenant authorization in the Summary and in Architecture | 2 -> 2 | a code-quality bullet from the parent CV added |
| Notabene, Staff Backend | yes: the news platform project with its own AWS deployment | 3 -> 3 | the length cut removed four job bullets (the ~94% frame-time fix, PO/BA decisions, the tree data model, mentoring) and the freight workspace project |

All five misses were fixed. Two versions gained a claim in prose that the
parent CV does not make; the fact check reads terms, not prose, and passed
both. In the two 3-page CVs the added text pushed other bullets out under
`cv.max_pages`.

## Items
- DONE - Read the regenerated CVs (task 0114) and note the real misses
- DONE - The Sonnet review prompt and a one-off script; run it on the same CVs with no regeneration; compare with the agent's notes
- DONE - `cv_tailor.py --review FILE` and the queue's `review` arg: a version revised with the review's misses and strengths, the current version as the mould; tests
- DONE - Run the revision for the CVs whose review holds a real miss; compare before and after
- DONE - Report to the owner
- TO DO - The owner decides whether the review becomes a step of the generation
