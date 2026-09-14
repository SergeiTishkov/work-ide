# Change log for the PJOICE template

New versions go on TOP. A section's number must match `version` in
`template.yaml` — that is checked by a test.

Entries are written so that you can tell whether a change affects your local
settings: what changed, where and why.

## V5 — smart contracts rule a vacancy out only when they are the job, 2026-09-14

The owner, reading the list of what this search cuts: "if smart contracts are
not the main thing — if the base is .NET and the vacancy reads as .NET with
smart contracts rather than smart contracts with .NET — they must not exclude
it."

`smart contract` and `solidity` left `role_complexity_signal`'s hard title and
description lists for a new block, `side_specialisms` (score._side_specialism):

    title names only smart contracts / Solidity / EVM   -> ruled out
    title names only .NET / C# / ASP.NET                -> kept
    title names both                                    -> the one named first
    title names neither                                 -> ruled out only if the
                                                           posting mentions them
                                                           MORE often than .NET;
                                                           a tie keeps it

Protocol, zero-knowledge and cryptography engineering stay in the hard list: a
separate profession, not something beside a .NET role.

Measured over this search's base before the change: 18 vacancies mention smart
contracts, Solidity or EVM — mostly once, inside an agency's list of every
technology — and the old rule had ruled out none of them. Nothing in the
shortlist moves; the refusal the owner described is closed before it happens.

## V4 — full-time said in words the patterns did not know, 2026-09-13

The second run's "hours not confirmed" section was read by hand, posting by
posting, and its top entries said full-time in so many words:

    Jimmy Technologies  "Work Conditions Type: Full-time & Long-term contract"
    Lemon.io            "ability to work full-time remotely with no supervision"
    Korn Ferry          "a contract to hire opportunity in Chicago"

Four contradicting patterns cover those forms; a confirmation anywhere still
beats them. One AI-training marker added ("expertise to help train", micro1).
The measurement before the change is in the section below the patterns.

## V3 — three words hiding inside ordinary ones, 2026-09-13

Reading the rendered report: G2i's AI-evaluation gigs carried "interesting
work: defi" — from "defining engineering standards". Two more keywords in
`extra_signals.interesting_work` had the same flaw:

    "defi"       inside "defining", "definitely", "deficit"
    "llm"        inside "enrollment"
    "anthropic"  inside "philanthropic"

Replaced with forms that cannot occur inside a word (" defi ", "(llm",
"anthropic api", ...). A test now checks every template's extra_signals against
a list of ordinary words known to hide technology tokens, so the next one is
caught before a run rather than in a report.

That test failed on the fix itself, and found the deeper fault: the matcher
stripped a keyword's edge spaces, so " defi " was still "defi". Fixed in
`score.keyword_needle` for every identity (the KISEL template's V14 has the
measurement); two comments about language markers in this file are corrected
to match.

## V2 — what the first run taught, 2026-09-13

The first run (1836 vacancies) was read line by line against the CV, and five
things were wrong in `pjoice_criteria.yaml`:

    freelance      Confirmed hours in 60 postings. In European IT contracting a
                   "freelance developer" is a contractor on a FULL-TIME
                   assignment ("long-term, until 31/12/2026, 50% remote"). Now
                   in neither list, like "contract": silence goes to a person.
    hours          "minimum 30 hours a week" matched "thirty hours or fewer".
                   The ceiling is now 25, and never after "minimum"/"at least".
    AI training    G2i led the shortlist with "not a traditional engineering
                   role ... evaluating coding agents" — the markers wanted the
                   word "software". Eleven markers added; still a minus, not a
                   gate.
    not a job      Interns, working students, co-ops and visiting professors
                   passed as developers because a board labelled them
                   part-time. Now in hard_wrong_profession_title_patterns.
    beyond the CV  A "Principal Data Engineer" sat at 55 in "hours not
                   confirmed". role_complexity_signal.applies_to_unconfirmed:
                   true keeps gated roles out of the check-by-hand sections.

Three more, shared with the KISEL template (its V13 has the measurements):
French postings recognised by functional words at threshold 4; language demands
read in context (`explicit_requirement_patterns`); "50% remote" is hybrid. And
one change in shared code: "freelance" no longer counts as proof that work is
remote — a Brussels freelance mission reached this shortlist's worth_a_look on
that word alone.

## V1 — a search for side work, 2026-09-13

Built from the KISEL template, because the person, the CV and the residency
are the same — and then turned round on almost every axis KISEL scores:

    money          KISEL: one consideration, below calm.
                   PJOICE: the priority, graded by the hourly rate
                   (compensation_signal.hourly_equivalent_tiers).
    hours          KISEL: intensity matters, hours do not.
                   PJOICE: part-time, freelance or fractional is REQUIRED —
                   a full-time role cannot be done beside a full-time job
                   (engagement_fit). Silence goes to its own section.
    dull work      KISEL: a plus (legacy_enterprise_signal).
                   PJOICE: neutral — the block is present and weighs nothing.
    interesting    KISEL: crypto was a dealbreaker, startups a penalty.
                   PJOICE: crypto, AI and distributed systems are a small plus
                   (extra_signals.interesting_work).
    complexity     KISEL: "not simple work" is gated.
                   PJOICE: complex work is welcome; what is gated is work THIS
                   CV will not be considered for — research, machine learning,
                   data engineering, smart contracts (role_complexity_signal,
                   repurposed).
    AI training    KISEL: a gate.
                   PJOICE: a visible minus — it pays, and whether a paid gig is
                   worth it is the person's call (extra_signals.ai_training_gig).

What is carried over unchanged: the stack gates, the geography rules, the
language filter, the profession filters, the talent-pipeline gate and the
mobile gate. They describe the CV and the residency, not the kind of search.

Sources are chosen for engagement rather than stack: Remote Rocketship and the
Himalayas search filter by part-time and contract for real, Remotive, Jobicy,
Himalayas and LinkedIn state the type as a field. The survey that chose them —
including the boards that advertise a part-time filter and do not have one — is
in config/sources.backlog.yaml.
