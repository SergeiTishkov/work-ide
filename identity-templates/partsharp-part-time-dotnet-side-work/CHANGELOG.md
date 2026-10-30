# Change log for the PARTSHARP template

New versions go on TOP. A section's number must match `version` in
`template.yaml` — that is checked by a test.

Entries are written so that you can tell whether a change affects your local
settings: what changed, where and why.

## V18 — placeholders instead of pay figures, 2026-10-30

**Changed** (`partsharp_profile.yaml` → `goal`, comments only): the example
ranges for `target_compensation` are `[<min>, <max>]`. Nothing to change
locally.

## V17 — ITAR as a word, 2026-10-22

**Changed** (`partsharp_criteria.yaml` → `remote_location_fit.hard_dealbreakers.keywords`):
"itar" becomes " itar" and "(itar". The bare "itar" sat inside "Mitarbeiter"
(German postings) and "military", and refused 11 vacancies on 2026-10-22
that never named ITAR. If your local criteria list "itar" among the hard
dealbreakers, write it the same way.

## V16 — remote on LinkedIn only in words, 2026-10-12

**Changed** (`tools/score.py`, `_score_remote_location`): on a board that
hides the work arrangement (LinkedIn) the employer's schema.org TELECOMMUTE no
longer confirms remote — only the text does. The owner, 2026-10-12: a vacancy
with no explicit sign of remote work goes to "remote not confirmed"; LinkedIn's
markup cannot be checked. Measured on SHARP's base: 66 LinkedIn vacancies in the
confident tiers had TELECOMMUTE and not one word of remote work; the checklist
had found offices in Philadelphia, New York and Kraków among them.

**Changed** (`partsharp_criteria.yaml` → `remote_location_fit.explicit_remote_keywords`):
"location: work from home", "home based position", "home-based position",
"(wfh role)" — the explicit forms without the word "remote" found in the base.

**Added** (`partsharp_criteria.yaml` → `remote_location_fit.remote_word_other_meanings`): "remote" in
another sense is cut out before the remote words are looked for — "local and
remote team members", "remote monitoring systems", "remote office locations",
"remote configuration", "remote employees" (of the company). 25 LinkedIn
vacancies in SHARP's confident tiers had "remote" only in these senses.

## V15 — one state, a country before (remote), clearance fields, 2026-10-12

**Changed** (`partsharp_criteria.yaml` → `remote_location_fit.hard_dealbreakers.patterns`):
four patterns from SHARP's third checklist round of 2026-10-12:
- "remote in one place only": "LOCATION: Remote in CA only" (a hot_lead at 55);
- "location: a country (remote)": "Location: Canada (remote)" — V25 knew only
  the order "Remote – Canada";
- "one country's applicants only": "US applicants only";
- "only candidates who reside": "we are only able to consider candidates who
  reside and work in British Columbia, Alberta, Manitoba, or Ontario".

**Changed** (`partsharp_criteria.yaml` → `remote_location_fit.work_authorization.rules`):
- "security clearance required" also reads "Minimum Clearance Secret" and
  "a government-issued Secret-level clearance";
- "US payroll only (W-2)" also reads "Contract: W2" in a header of fields.

Measured over SHARP's base before adding: 21 location matches and 20 clearance
matches, every one a single country, state or province list, or a clearance.

## V14 — one country, named offices, a second language, 2026-10-12

**Changed** (`partsharp_criteria.yaml` → `remote_location_fit.hard_dealbreakers.patterns`):
eight patterns from the second checklist round of 2026-10-12, quoted from its
vacancies:
- "remote within a named country": "fully remote candidates within New
  Zealand" — the old pattern knew only the US, the UK and Canada;
- "remote, then one country": "Remote (US Region)", "Location: Remote –
  Canada", "fully remote, United States", "Remote UK";
- "partner based in one country": Jobgether's "Our partner is looking for a
  ... based in Switzerland";
- "workplace model says hybrid": "Workplace model: Hybrid";
- "days a week in a named office" and "a named office, days a week": "3 days
  per week in the Espoo office", "at our Coleshill office 2 days per week";
- "remote on US western hours": "Remote (MST)", "Remote PST Hours";
- "office stated plainly": "We work mainly from the office", "a fully remote
  work policy is not offered", "within commuting distance of our office".

**Changed** (`partsharp_criteria.yaml` → `language_requirement_signal.explicit_requirement_patterns`):
"English and another language" — "Excellent English and Korean verbal and
written communication skills", "both Norwegian and English".

Measured over SHARP's base before adding: 75 location matches and 15 language
matches among the vacancies not yet rejected; every sampled match was a
single country, a hybrid role, US western hours or a demanded language.

**Changed** (`partsharp_criteria.yaml` → `engagement_fit.confirming_patterns`):
"part-time" no longer counts "Salaries for part-time roles will be prorated"
or "full or part-time status" — US benefits text that confirmed Capital One's
full-time Staff role as part-time (a hot_lead at 68). "Full-time or
part-time" still confirms.

## V13 — office days and an Asian language, 2026-10-12

**Changed** (`partsharp_criteria.yaml` → `remote_location_fit.hard_dealbreakers.patterns`):
three patterns for office days written without "in/at/from the office":
- "attend the office": "required to attend the office a minimum of 3 days per
  week";
- "office at least some days": "require office attendance at least 2 days per
  week";
- "work from home some days": "work from home typically two days per week".

**Changed** (`partsharp_criteria.yaml` → `language_requirement_signal.explicit_requirement_patterns`):
"an Asian language demanded" — "Language : Japanese", "native Mandarin
fluency", "Japanese required".

Found by PARTSHARP's checklist on 2026-10-12 (Nuix ×3, Apogee, PerkUP).
Measured over the base before adding: 15 office matches, every one a hybrid
role; 2 language matches, both a demand.

**Changed** (`partsharp_criteria.yaml` → `engagement_fit.contradicting_patterns`):
"a five-day week" — Apogee's "two days per week in a five-day working week"
passed "three days a week or fewer" as part-time.

**Changed** (`partsharp_criteria.yaml` → `extra_signals.ai_training_gig.keywords`):
13 markers — "llm-generated code", "paid per task", "minimum weekly
submission", "golden reference solution" and others. Four of the ten
AI-training gigs among the 19 fresh vacancies carried none of the old markers,
the top of the shortlist among them. "ai-generated code" was measured and left
out: product roles use it too.

## V12 — SHARP's reachability rules, 2026-10-12

**Changed** (`partsharp_criteria.yaml` → `remote_location_fit`): the rules
SHARP gained in its V20 and V23 are here too, word for word.
- `hard_dealbreakers.patterns`: "hybrid remote", "work mode field says
  hybrid", "hybrid as a separate item", "work in a hybrid environment",
  "remote within one country, said at length", "based in one country", "must
  live in a named place", and V23's "anywhere in one country", "open to
  applicants in one country", "remote role based in one country", "some US
  states only", "candidates from one country", "office now and then".
- `work_authorization.rules`: "US or Canadian payroll benefits (401(k),
  RRSP)", lifted for an employer that engages people abroad.
- `language_requirement_signal.foreign_language_posting_indicators`: SHARP
  V23's wider Italian and its new `scandinavian` entry.

**Why.** Both identities belong to one person in one country; where an
employer can hire them is the same question for part-time work. PARTSHARP
had only the patterns of before 2026-10-05.

## V11 — renamed from PJOICE to PARTSHARP, 2026-10-05

**Renamed.** The prefix `pjoice` became `partsharp` (part-time SHARP: the same
CV, the opposite search), the folder `partsharp-part-time-dotnet-side-work`,
the files `partsharp_*`. Nothing in the rules changed. A local identity made
from this template is renamed the same way: folder, files, `prefix` and
`template` in `identity.yaml`, its data (`data/identities/partsharp/`, its rows
in `data/workide.sqlite`) and its reports.

## V10 — crypto by fit; exclusivity is a line on the card, 2026-10-05

**Changed** (`pjoice_criteria.yaml`): new `domain_fit_signals` with `crypto`.
A crypto project scores +20 where the core stack is what it requires and
nothing this CV lacks is (Solidity, Rust, EVM, smart-contract development,
years in crypto); where it requires those and the core stack is at most a
plus, it is rejected. Sentences with "a plus", "nice to have", "preferred"
and lines under such a heading are read as wishes, not requirements.

**Changed:** the crypto words left `extra_signals.interesting_work` (up to
+8), so that crypto is counted in one place.

**Changed** (`pjoice_profile.yaml` → `employment_type_priority`): the exclusivity
phrases ("exclusive employment", "moonlighting prohibited", ...) moved from
`dealbreaker_signals` to the new `exclusivity_signals`. A vacancy with such a
clause is no longer refused; its card says "requires exclusivity".

**Why.** The owner, 2026-10-05, for both searches.

## V9 — LinkedIn counts as remote only where it says so, 2026-10-04

**Changed:** `pjoice_criteria.yaml` → `remote_location_fit`: new
`explicit_remote_keywords` ("remote", "telecommute", "telework"). For a board
marked `workplace_hidden` in the shared catalogue (LinkedIn) only these words
or the employer's TELECOMMUTE confirm remote; worldwide, contractor and region
phrases no longer skip the question for it.

**Why.** LinkedIn shows Remote/Hybrid/On-site to logged-in visitors only. In
SHARP's base 14 LinkedIn vacancies sat in the confident tiers on "WFH 3 Days
per week" (hybrid), "an allowance when you work from home", "a distributed
team", "work from any location in Belarus ... or our offices", or a named EOR
platform on a Rome posting with three office days a week. They now wait in
"remote not confirmed", scores unchanged.

## V8 — mycareersfuture is closed: applying needs a Singapore ID, 2026-10-04

**Changed:**
- `pjoice_criteria.yaml`: new `closed_sources`, boards the person cannot apply
  through. Every vacancy from one is rejected with the reason as its
  dealbreaker, including those already in the base.
- `pjoice_sources.yaml`: `mycareersfuture` was already off; a comment says why.

**Why.** The owner's feedback: mycareersfuture.gov.sg wants a Singpass login
to apply, and Singpass is for Singapore residents. Turning the board off only
stops new vacancies; for this identity the base had none, so the rule only guards against the board being turned back on.

## V7 — LinkedIn is read to the end of every list, 2026-10-03

**Changed:** `pjoice_sources.yaml` → `linkedin`. `max_pages: 2` is gone (the
fetcher's own bound applies), `posted_within_days: 7` is new, and
`enrich_limit` went from 150 to 0. If your local file overrides the LinkedIn
parameters, compare it with this version.

**Why.** The fetcher read ONE page per (word x country) pair. It stepped by an
assumed 25 cards and stopped when fewer came — and LinkedIn serves ten a page,
so every pair ended after its first. A POC on 2026-10-02/03 with this
identity's words and countries:

| | before | every page, last week |
|---|---|---|
| unique vacancies | 1 007 | 4 946 |
| new to the base | 168 | 4 741 |
| requests / time | ~170 / 6 min | 1 389 / 53 min |

The anonymous search also stops at 100 results per query; a query that
reaches it is now split into "remote ..." and regional queries (in the UK, one
query at the ceiling became 322 vacancies). Descriptions are read after
scoring, by verdict, instead of by title before it. Details:
`docs/sources/linkedin.md`.

## V6 — work authorization is read in its sentence, and W-2 is US payroll, 2026-10-01

**Changed:** `pjoice_criteria.yaml` → `remote_location_fit`. The citizenship,
permit, clearance and sponsorship rules left `hard_dealbreakers` (patterns and
keywords) and `absolute_residency_phrases` ("eligible to work in", "authorized
to work in", "residency in" and the like). They now live in a new
`work_authorization` block that `score.py` reads one sentence at a time. If
your local file overrides `hard_dealbreakers` or `absolute_residency_phrases`,
compare it with this version.

**Why.** Every vacancy in this identity's base that mentions citizenship, a green
card, work authorization, a clearance, sponsorship or W-2 was read on
2026-10-01. That is 11,714 vacancies with a description. The old rules matched
phrases anywhere in the text, and they failed in both directions:

- **missed:**
  - "We require U.S. citizenship" (hot_lead, 56);
  - "USC OR GC ONLY", "Visa: H1B, GC, USC";
  - "Singapore Citizen (mandatory)";
  - "legally entitled to work in Canada", "UK working rights required";
  - "No visa sponsorship available";
  - "SC Cleared" in a title (hot_lead, 51), "BPSS";
  - "$100–$120 per hour on W-2" (worth_a_look). W-2 had no rule at all.
- **refused nobody:**
  - "nor will [we] require … lawful permanent residency in the U.S.". This
    matched "residency in" and rejected nine vacancies, one of them at 69;
  - "security clearance is preferred";
  - "some positions require the ability to obtain a security clearance";
  - "we do not provide visa assistance" from a company that works with
    developers in 75+ countries. A remote contractor never needs a visa.

Now a rule refuses only when nothing in the same sentence cancels it. These
cancel a refusal: a negation; a company-wide caveat; "the country where you
live"; an offer of help with a visa; a product for citizens; this person's own
country. "Georgia" counts as that country only without US-state context, such as
"Atlanta". An equal-opportunity list and a preference ("preferred",
"prioritizing", "encouraged to apply") cancel a refusal only when they are next
to the term they qualify. In "must be an Australian citizen … an active NV1
clearance is preferred", the citizenship requirement still stands.

New rules: **W-2** (US payroll; not a refusal when C2C or 1099 is offered as
well, unless that offer is refused too), US work statuses ("H1B, GC, USC"), and
US person / export control.

A residency eligibility of "likely" no longer comes from the bare words
"contractor", "freelance" or "1099". In the last selection, 36 such verdicts
were London IR35 contracts and US staffing roles. It now needs a named
employer-of-record platform or an explicitly international arrangement
(`international_hiring_patterns`).

An optional `owner.citizenships` list in the local profile counts like the
country of residence.

**Effect, measured before the change on this identity's base:**

- 5 vacancies move to rejected ("SC Cleared", "US CITIZEN AND GC ONLY",
  "Visa: H1B, GC, USC", "Poland or Romanian residents only", "US work
  authorization required"); each was read.
- The same rewrite was measured on the SHARP base: 62 vacancies move to
  rejected and 3 come back from wrong refusals.

Rescoring the whole base takes about 14% longer.

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
`score.keyword_needle` for every identity (the SHARP template's V14 has the
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

Three more, shared with the SHARP template (its V13 has the measurements):
French postings recognised by functional words at threshold 4; language demands
read in context (`explicit_requirement_patterns`); "50% remote" is hybrid. And
one change in shared code: "freelance" no longer counts as proof that work is
remote — a Brussels freelance mission reached this shortlist's worth_a_look on
that word alone.

## V1 — a search for side work, 2026-09-13

Built from the SHARP template, because the person, the CV and the residency
are the same — and then turned round on almost every axis SHARP scores:

    money          SHARP: one consideration, below calm.
                   PJOICE: the priority, graded by the hourly rate
                   (compensation_signal.hourly_equivalent_tiers).
    hours          SHARP: intensity matters, hours do not.
                   PJOICE: part-time, freelance or fractional is REQUIRED —
                   a full-time role cannot be done beside a full-time job
                   (engagement_fit). Silence goes to its own section.
    dull work      SHARP: a plus (legacy_enterprise_signal).
                   PJOICE: neutral — the block is present and weighs nothing.
    interesting    SHARP: crypto was a dealbreaker, startups a penalty.
                   PJOICE: crypto, AI and distributed systems are a small plus
                   (extra_signals.interesting_work).
    complexity     SHARP: "not simple work" is gated.
                   PJOICE: complex work is welcome; what is gated is work THIS
                   CV will not be considered for — research, machine learning,
                   data engineering, smart contracts (role_complexity_signal,
                   repurposed).
    AI training    SHARP: a gate.
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
