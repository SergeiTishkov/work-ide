# 0077 FDE companies in the ATS targets, FDE titles in the search terms

Source: the owner, 2026-10-22, after the FDE research
Scope: config

## Business
The owner wants forward deployed roles found where they are posted: on the
careers boards of the companies that hire for them, and by the role's other
names (deployment strategist, applied AI engineer, AI deployment engineer).
The criteria already take these titles as stretch roles (task 0042).

Measured in the sharp base on 2026-10-22: 454 forward deployed titles, 449
refused, almost all on location (not remote, on-site, client site), not on
title. Solutions engineer titles are refused as pre-sales and stay out of
the search.

## Implementation
- Template sharp v31, `sharp_ats_targets.yaml`: 26 boards (15 Ashby, 10
  Greenhouse, Palantir on Lever), each checked on 2026-10-22: about 5 500
  postings, about 600 FDE-like by title. Left out: Mistral (empty Lever
  board, no other answered), Gorgias (no such roles), Jobgether (an
  aggregator). GitLab was already there.
- LinkedIn keywords: "applied AI engineer", "AI deployment engineer",
  "deployment strategist" (84 more pairs a run).
- HN keywords: "applied AI" (9 new threads in a trial), "deployed engineer"
  (12 new); "deployment strategist" found none.
- Work at a Startup: unchanged. Its defaults already hold "forward deployed",
  "applied ai" and "ai engineer"; "deployed engineer", "deployment engineer"
  and "deployment strategist" found nothing new in a trial.
- The owner's own `sharp_sources.yaml` got the same keywords (a template
  update does not reach it); the local identity updated to v31.

## Items
- DONE - FDE companies' boards checked and added to the template's ATS targets
- DONE - FDE titles added to the LinkedIn and HN keywords, template and the owner's sources file
- DONE - Template sharp v31, local identity updated
- TO DO - After the next full run: per-query statistics for the three new LinkedIn words (task 0050's follow-up); keep the ones that bring vacancies the others do not
