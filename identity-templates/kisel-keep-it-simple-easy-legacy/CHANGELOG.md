# Change log for the KISEL template

New versions go on TOP. A section's number must match `version` in
`template.yaml` — that is checked by a test.

Entries are written so that you can tell whether a change affects your local
settings: what changed, where and why.

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
job fragment and from the page HTML. It renders only for a logged-in session,
and that is over the line this project does not cross.

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
