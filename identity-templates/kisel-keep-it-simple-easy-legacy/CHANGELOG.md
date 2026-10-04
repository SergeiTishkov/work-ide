# Change log for the KISEL template

New versions go on TOP. A section's number must match `version` in
`template.yaml` — that is checked by a test.

Entries are written so that you can tell whether a change affects your local
settings: what changed, where and why.

## V17 — mycareersfuture is closed: applying needs a Singapore ID, 2026-10-04

**Changed:**
- `kisel_criteria.yaml`: new `closed_sources`, boards the person cannot apply
  through. Every vacancy from one is rejected with the reason as its
  dealbreaker, including those already in the base.
- `kisel_sources.yaml`: `mycareersfuture` is off.

**Why.** The owner's feedback: mycareersfuture.gov.sg wants a Singpass login
to apply, and Singpass is for Singapore residents. Turning the board off only
stops new vacancies; 1 175 were already in the base, 14 of them as hot leads.

## V16 — LinkedIn is read to the end of every list, 2026-10-03

**Changed:** `kisel_sources.yaml` → `linkedin`. `max_pages: 2` is gone (the
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

## V15 — work authorization is read in its sentence, and W-2 is US payroll, 2026-10-01

**Changed:** `kisel_criteria.yaml` → `remote_location_fit`. The citizenship,
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

- 62 vacancies move to rejected:
  - 5 from hot_lead, 8 from worth_a_look, 7 from long_shot, 42 from
    remote_unconfirmed;
  - each was read, and in each the employer's own sentence restricts who can
    be hired.
- 3 vacancies come back from wrong refusals.
- "Software Engineer" (hot_lead, 49) stays where it was: it offers W-2 **or**
  corp-to-corp, and nothing in its text says that a contractor abroad cannot
  take the C2C option.

Rescoring the whole base takes about 14% longer.

## V14 — a space at the edge of a keyword now means a word boundary, 2026-09-13

No setting changed; two comments in `kisel_criteria.yaml` were wrong and are
corrected, because the machinery under them was.

Keywords such as the Dutch markers " je ", " het ", " in de " were written with
spaces to match whole words. The matcher stripped those spaces, so they matched
inside other words: 18 of 72 "Dutch" detections were German postings ("jede",
"in der"), and V13's French " des " and " les " matched inside "design" and
"sales". `score.keyword_needle` now keeps a keyword's edge spaces.

Measured over this identity's base before the change: Dutch detections 72 ->
54, French 86 -> 83, and not one vacancy a person sees changed its verdict —
every lost detection was also refused for another reason, except a single
French tutoring post with broken encoding.

## V13 — what a part-time search found in this one, 2026-09-13

A second identity for the same person — paid part-time side work (PJOICE) —
ran for the first time, and reading its shortlist exposed four gaps that are
this template's too. Each was measured over THIS identity's base before being
changed, because the owner's standing rule is that no mass of real vacancies
may quietly vanish.

    French postings   The markers missed LinkedIn's French wording. Widened,
                      threshold 3 -> 4: 60 detections -> 86, none lost; every
                      newly caught shown vacancy had a French title.
    language demands  explicit_requirement_patterns, read in context. Five new
                      refusals among shown vacancies, all genuine ("fluency in
                      English and French is required"); "Dutch or French is
                      desirable" still passes.
    percentage remote "up to 50% telework permitted" is hybrid. Two shown
                      vacancies, both hybrid.
    interns           Interns, working students, trainees, faculty. Three shown
                      vacancies, all internships.

Beside these, one change in shared CODE moves this identity's shortlist:
"freelance", "contractor" and "1099" no longer exempt a vacancy from confirming
it is remote — only a named platform does. Eight vacancies in the confident
tiers stood on those words alone (freelance missions in Brussels, Lille and
Stevenage; Stripe, whose "1099" is a tax form). They move to
remote_unconfirmed with their scores unchanged.

Not changed here, deliberately: the complexity gate still lets a vacancy it
rules out wait in remote_unconfirmed. For this identity a single "agentic" in
a consultancy's boilerplate gates an ordinary ".NET Developer", and turning on
`role_complexity_signal.applies_to_unconfirmed` would hide 51 vacancies on that
thin a signal.

## V12 — the UK, and four sources that are mostly CONTRACTS, 2026-09-08

Four new boards, and the reason to want them is the same in three cases: they
list **contracts** rather than employment. A day rate with an outside-IR35
determination is work somebody invoicing from another country can take; a
payrolled UK job is not.

    contractoruk    142 records over four queries. 121 with a day rate, 52
                    badged Remote. The badge goes straight into workplace_type
                    — the board ticking a box, not a phrase in prose.
    reed            98 from one keyword, EVERY ONE with a stated salary. The
                    largest UK board. Its remote and contract filters were
                    tested before being trusted (see below).
    jobserve        20 a query, and the richest card of the four: the agency's
                    name, a rate, "Remote, UK" as a location, and a real
                    paragraph of description rather than a snippet.
    outside_ir35    50 contracts in one request, every one outside IR35. Tiny,
                    and almost everything in it is the right KIND of work.

**Reed's filters were tested the way LinkedIn's should have been.** This
project stamped every LinkedIn vacancy remote on the strength of a filter that
did nothing. So before trusting Reed's: the remote slug shares 15 of 25 results
with the plain search, and the contract slug shares NONE. They work. All three
variants are fetched, because the contract inventory is otherwise invisible.

**A yardstick for pay.** IT Jobs Watch publishes no vacancies — it publishes
six-month market medians, and the report now shows them beside the UK
shortlist: .NET £60,000 a year permanent, £525 a day on contract, and the
contract figure is up 6.6% while the permanent one is down 4%. It is never
written onto a vacancy and never scored: a market median is not what THIS
employer pays, and confusing the two is exactly what CLAUDE.md section 5
forbids in the other direction.

**One repair that came with it.** Description enrichment called LinkedIn's page
parser for every source. Pointed at a Reed page it finds nothing, returns
empty — and RECORDS AN ATTEMPT, so the vacancy is marked as tried and never
looked at again. Reed contributes about a hundred vacancies a run and none has
a description on the card, so all of them would have been scored on a title for
ever. Enrichment now knows which sources it can read, and reads Reed through
the schema.org markup its pages publish.

**Does this affect your local settings?** Only if you kept your own
`kisel_sources.yaml`: lists are replaced rather than merged, so a local copy
must name the new sources to receive them.

## V11 — the exemptions in V10 had to be earned, 2026-08-12

Reading the shortlist V10 produced, twice more.

**One stray word was enough to switch the discipline filter off.** V10 let a
data or ML title through when the posting mentioned data-pipeline work, so that
your Spark and Databricks experience would not be filtered away. But a single
"ETL" anywhere counted. Measured: 64 vacancies in the shortlist carry exactly
one such word against 45 carrying two or more. Two are now required, and a real
data role names several.

**"Solutions Consultant, Enterprise" @ Ramp** sat in long_shot at 21. Added to
the hard tier — but only "solutions consultant" and "sales consultant", because
".Net Technical Consultant" @ alfanar is a real .NET role and a broader pattern
would have thrown it away.

## V10 — a different branch of engineering is not a different stack, 2026-08-12

You opened your own UK shortlist, reached line 39 and found **"Senior Security
Engineer, Security Incident Response Team (SIRT)"** at 15. Security incident
response is somebody else's profession; your CV is .NET end to end.

**Why nothing caught it.** The soft profession filter is cancelled by any
developer word in the title, and the override list holds a bare "engineer" —
so the very word naming the wrong profession disarmed the rule. The hard filter
would have caught it, but that one fires whatever the stack says, and measuring
first showed what a blanket rule would cost: fifteen wrong vacancies removed
and **five real ones with them**, including ".NET AppSec Engineer" and "Senior
Software Engineer (WPF, Firmware & Systems)". A .NET job with an unusual title
is still a .NET job.

**So there is now a third tier.** `wrong_discipline_title_patterns` — security,
data science, ML/AI, embedded and firmware, forward-deployed and support
engineering — which fires UNLESS the vacancy names your core stack, or is data
work over Spark/Databricks/ETL, which you confirmed on 2026-07-30 is wanted and
which your CV carries. The employer's own word outranks the title's discipline.

Two more went into the hard tier, where no stack could rescue them: "Vice
President, Data & Insights" and "Sales Enablement | SDR", both of which had
reached long_shot at 22. The list already held `vp`, and neither posting
spells it that way.

**What you will notice.** Titles that were never your work stop appearing —
and the ones that only look like somebody else's work stay.

## V9 — the word "freelance" no longer cancels a continent, 2026-08-12

V8 taught the filters to see "100% remote in LATAM". The vacancy stayed at the
top of the worldwide shortlist anyway: a region tie is outranked by evidence
that a company can engage somebody across a border, and the word "freelance"
elsewhere in the description was counting as that evidence.

It is not evidence. A NAMED employer-of-record platform — Deel, Oyster,
"Employer of Record" — is; a posting can say "freelance" and still be tied to
one continent, which this one was: "100% remote in LATAM working EST Time Zone,
1-Year Assignment".

Measured before changing: exactly one vacancy in the entire shortlist rested on
that override, and it was this one. The generic words keep their scoring role;
they simply no longer overrule a continent.

## V8 — a region tie written with a preposition, 2026-08-12

Found by reading the shortlist V7 had just produced. The vacancy leading the
**worldwide** file at 76 was NTT DATA's "100% remote in LATAM".

The keyword list held "remote latam". The posting said "remote **in** LATAM".
One preposition, and the vacancy went from unreachable to top of the list that
is supposed to hold only the roles where geography is not in the way.

Region ties are now matched by pattern as well as by literal — 57 postings in
the base use the "in" form, across LATAM, EMEA, APAC, North America and the
Middle East. Deliberately alongside the region keywords rather than in
`hard_dealbreakers`, so that an explicit worldwide offer still outranks them: a
company saying "work from anywhere, and we already have contractors in LATAM"
is not restricting anybody, and there is a test for it.

## V7 — one search, several shortlists; and eligibility as its own axis, 2026-08-12

Two changes, and they answer the same complaint: a single list sorted by score
mixes a Singapore agency posting with a UK contract at four times the rate, and
puts a well-paid job that cannot be taken above a modest one that can.

**Several shortlists, one per market.** `kisel_reports.yaml` — a new file,
layered like every other setting — says which market groups get a file of their
own. This search now produces eight:

    kisel_worldwide_latest.md   geography is not in the way at all
    kisel_uk_latest.md
    kisel_eu_latest.md          the EU and EEA as one group, not 30 files
    kisel_canada_latest.md
    kisel_usa_latest.md
    kisel_anz_latest.md         Australia and New Zealand
    kisel_rest_latest.md        everything the others did not claim
    kisel_full_latest.md        all of it, also written to kisel_latest.md

Worldwide is first on purpose. It is not the leftovers: it is the only group
where being outside every market above is not an obstacle to begin with.

Which countries form a group is shared geography
(`config/derivation/market_groups.yaml`); which groups deserve a file is this
search's judgement, and lives here. `rest` is computed from what the other
segments claimed rather than listed, so adding a market can never quietly
orphan another one.

**Eligibility as a separate axis, not more points.** Every vacancy now carries
a verdict: can a contractor sitting where this person sits actually take the
work? CONFIRMED (the employer names this country among where they hire), LIKELY
(worldwide, or an international contractor arrangement), NOT STATED (remote,
but from where?), NO (restricted somewhere else). It is shown on its own line
and it now orders every section ahead of the score, because:

    "$100/hour — Remote — US"  is worth LESS than
    "$70/hour — Remote Worldwide — Contractor"

to somebody who cannot take the first. The score is still shown; only the
order changed.

**Three things the same work found and fixed:**

* "remote-first company" was counted as proof of WORLDWIDE hiring. It describes
  how a company organises itself, not who it can engage. Removed — measured
  first: 16 vacancies rested on it alone, all Canonical, all already rejected.
* Work authorization demanded as a NOUN went unmatched. Yesterday's patterns
  wanted the verb; every real posting used the other form. "Must have
  authorization to work in the UK without sponsorship" was sitting in hot_lead
  at 64. 43 postings in the base use it.
* "Remote within the United States" and its family matched nothing. 31 in the
  base; each happened to be caught by something else, which is luck, not a rule.

**Does this affect your local settings?** Only if you had overridden
`remote_location_fit`. If you keep your own `kisel_reports.yaml`, remember that
lists are replaced rather than merged: name every segment you want.

**What you will notice.** Eight files instead of one, each saying which
shortlist it is and linking to the others — and within each, the vacancies you
could actually take are at the top.

## V6 — hybrid named in brackets, 2026-08-11

Caught by re-running the manual checklist over the head V5 had just rebuilt.
The V5 rule wanted the brackets to hold the word and nothing else, "(hybrid)".
A real title in the shortlist put the salary in there with it:

    Backend Developer (C# - SSIS) - (hybrid, 36-40k)      scored 38

Now any bracket that names hybrid disqualifies — unless it also names a
technology ("hybrid cloud") or offers remote, which one real posting does:
"(hybrid and options for remote work)". 61 matches across the base, every one
about a place of work.

## V5 — where the work actually happens, 2026-08-11

The owner opened the top three vacancies in his own shortlist and read the
badges LinkedIn shows a logged-in person. Capgemini at 80: **Hybrid**. Emdad By
Elm at 71: **On-site**. Jobstronaut at 65: **On-site, and no longer accepting
applications**. All three were in the base marked remote.

**Why.** The remote flag was hardcoded true for every LinkedIn vacancy, on the
reasoning that the search query carries LinkedIn's own "Remote" filter. That
filter does nothing: measured this day, the same job id comes back under
`f_WT=1` (on-site), `f_WT=2` (remote) and `f_WT=3` (hybrid), and the result
sets for remote and on-site were identical. It was not a weak signal, it was a
fabrication — and it cleared the remote gate for 100% of the LinkedIn base.

The badge itself cannot be read: absent from the search results, from the guest
job fragment and from the page HTML. It renders only for a logged-in session.

**What changed, in two halves.** The split is the whole design:

* **The employer's own word disqualifies.** The board's structured location
  field saying "Hybrid" or "In-Office" (272 vacancies), and the arrangement
  stated in the description — "Location: London (Hybrid)", "Work Arrangement:
  Hybrid (3 Days/week)", "in the office four days a week". Never the bare word:
  58 vacancies say "hybrid cloud" or "hybrid architecture" and none of them is
  a commute.
* **Silence disqualifies nothing.** 109 vacancies have a full description that
  never mentions the arrangement. They now go to a class of their own,
  `remote_unconfirmed`, with a section of their own in the report — and their
  **score untouched**. A 70 there is the same 70 it would have been in
  hot_lead. What is missing is the confirmation, not the quality.

**Two more things the vacancy page was giving away for free**, in the same
request that fetches the description: the salary stated in the posting (every
LinkedIn vacancy was storing none), and whether it still accepts applications.

**Does this affect your local settings?** Only if you had overridden
`remote_location_fit`. The new `unconfirmed_remote_policy` is a per-identity
choice — `manual_check` (the default), `reject` (the old behaviour), or
`accept` for somebody who does not mind commuting.

**What you will notice.** The head of the shortlist gets much smaller and every
vacancy left in it is one somebody actually called remote. The rest are not
gone — they are one section further down, waiting for you to judge them.

## V4 — work authorization, matched by pattern rather than by substring, 2026-08-11

Found by the manual checklist on the head of the shortlist as rebuilt by V3.

The dealbreaker list already held "must be a us citizen". Two vacancies were
sitting in the shortlist anyway — one of them **second overall at 69** — because
their own text said it differently:

    "the person(s) hired must be a U.S. Citizen or Green Card holder"   the dots
    "Must be US Citizen."                                              no article

Adding two more literal strings would have been the same mistake a third time.
Instead the dealbreakers now also accept regular expressions, and work
authorization is expressed as seven of them: citizenship, green card, refusal to
sponsor a visa, required existing authorization, security clearance. Every one
demands a REQUIRING context, so an equal-opportunity footer that merely mentions
citizenship still passes — there is a test for each direction.

Measured across 13605 vacancies: 32 postings say "U.S. Citizen" with the dots,
6 without them, 43 refuse sponsorship, 31 require existing authorization.

**Does this affect your local settings?** No — it adds a `patterns` list beside
the keywords you may already have overridden.

**What you will notice.** Vacancies that were never open to you in the first
place stop taking up room at the top.

## V3 — four gaps found by the manual checklist, 2026-08-11

Every one of these was found by reading candidates in the shortlist by hand,
and measured across the whole base before being closed.

**Onsite in the employer's own words.** A vacancy can arrive through a board's
remote filter and still say "Job Location: Client Site" in its own text — one
did, and led the shortlist at 62. Added to `hard_dealbreakers`: client site,
client premises, at client end, driving licence (only ever required of somebody
who commutes), and interviews that must happen in person. Measured: 20 + 9 + 13
vacancies across the base.

**Advertisements with no vacancy behind them.** New `talent_pipeline_gate`: an
employer collecting CVs against roles that may open later matches a profile
more tidily than a real vacancy does, because it was written to. Measured: 51
postings.

**Five languages that were missing from the derivation table entirely** —
Arabic, Hebrew, Swedish, Turkish, Portuguese. A requirement for any of them
produced no rule for anybody, in any identity. Measured: 19 vacancies, two of
them in the head of a shortlist.

**Does this affect your local settings?** No. These are additions to the
template's own lists; anything you overrode keeps winning.

**What you will notice.** The head of the shortlist gets smaller and cleaner.

## V2 — the template is in English

Every comment and every explanatory string in the template was translated into
English. **No value changed**: the thresholds, weights, keyword lists and gates
are byte-for-byte what they were, which was confirmed by rescoring the whole
accumulated database — 11,414 vacancies, 0 differences in class or score.

**Does this affect your local settings?** No. Your own files sit beside the
`template/` folder and take no part in the update. If you overrode a key, the
override keeps winning.

**What you will notice.** The comments in `template/` become English. If you
read the report in another language, it does not change: the report language
follows `preferences.language` in your own profile.

## V1 — the first version

A template for a calm legacy search, assembled from a working identity after
two weeks of tuning against live data (more than 11,000 vacancies).

**What defines the search**

- The goal is INTENSITY rather than a number of hours: an undemanding
  full-time role suits as well as a moderately loaded part-time one. Reduced
  hours and a four-day week are forms of low intensity, not ends in themselves.
- The stack: .NET/C# at the core, JS/TS as a strong suit; the legacy edition of
  that stack (WebForms, EF6, jQuery, SOAP) is an advantage, not a drawback.
- Legacy and enterprise signals (`legacy`, `mainframe`, `cobol`, `bank`,
  `government`) are a plus; `greenfield`, `fast-paced`, `move fast` a minus.

**Hard rejections**, each added after a real finding in the shortlist

- not a developer role (management, sales, pre-sales, DevRel, analytics);
- infrastructure roles and DevOps, including behind a neutral title;
- QA and mobile development;
- AI-training crowdwork disguised as an engineering vacancy;
- industries the search does not go into;
- vacancies not in English.

**Mechanics that came at a price**

- technology names are matched per `docs/TECH_MATCHING.md`: short and generic
  forms are forbidden;
- the depth of a stack match matters more than the breadth of a list;
- a board's location field carries more authority than marketing phrases in the
  text, but less than the employer's own words.
