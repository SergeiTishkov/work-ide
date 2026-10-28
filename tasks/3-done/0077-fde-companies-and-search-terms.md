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
- DONE - After five full runs with `found_by` (2026-10-28, tools/linkedin_yield.py): none of the three new LinkedIn words found a shortlisted vacancy alone. "deployment strategist" served 17 166, none shortlisted (out in task 0050); "applied AI engineer" 2 shortlisted and "AI deployment engineer" 3 (with their "remote" forms), all found by other searches too: the owner took both out, template sharp v33
- DONE - The 26 company boards, checked the same day: 4 568 postings in the base, none shortlisted (4 517 rejected, 51 low priority); of 402 forward deployed titles, 347 refused on location; the AI check read 375 and kept 9. The boards stay
