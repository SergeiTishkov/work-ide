# 0123 A card rejected for having no text gets its text read

Source: the agent, 2026-11-20 (from the ENDGAME vacancy, task 0122)
Scope: tools

## Business
A LinkedIn card arrives without a description. Scored blind, it can be
rejected on "no description yet" with "the employer never states this is
remote" and a title gate beside it, and the description reader
(`enrich_descriptions`, HEAD_CLASSES) reads only cards in the head classes.
A rejected card therefore never gets the text that could have kept it, and
the AI check never sees it either.

The case: ENDGAME, Forward Deployed Engineer (linkedin.com/jobs/view/4474971398),
first seen 2026-11-06 from es.linkedin.com. Blind: 4 points, rejected
("location: the employer never states this is remote", "stack: no
description yet, and the title names no technology", "stretch: off the
stack or level"). With its page read: 8 points, every dealbreaker gone
(remote Europe, GMT-1 to GMT+4, .NET among the languages, the
forward-deployed title gate exempted by the text). The owner found it by
hand and called it the kind of vacancy they want.

Measured 2026-11-20 on SHARP: 9,484 vacancies first seen since 2026-11-01
are rejected with `description_wanted` set and no description (22,109 in
the whole base), not split by source yet.

## Items
- TO DO - Measure which of them a page reader can read (by source) and how many leave "rejected" once read, on a sample, before choosing what the reader takes
- TO DO - Decide with the owner: read the rejected cards whose only objections are "no text"-type ones (within the reader's limit and pause), or another rule
