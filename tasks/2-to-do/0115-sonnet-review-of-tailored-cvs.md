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

## Items
- TO DO - Read the regenerated CVs (task 0114) and note the real misses
- TO DO - The Sonnet review prompt and a one-off script; run it on the same CVs with no regeneration; compare with the agent's notes
- TO DO - If it finds real misses: the regeneration with the review's remarks and strengths, run for the CVs that need it; compare before and after
- TO DO - Report to the owner; the decision on a pipeline step
