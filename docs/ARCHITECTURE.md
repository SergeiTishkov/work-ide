# Architectural decisions

The format is: decision → why. The "Rejected approaches" section exists so that
a future run or agent does not cover the same ground twice (see CLAUDE.md,
section 6).

## Decisions taken

### The database is a file
No SQL or NoSQL server — the repository has to be both the program and the
knowledge base at once (a requirement of the brief and of CLAUDE.md).

Vacancies and companies live in one SQLite file per identity,
`data/<prefix>/<prefix>.sqlite` (schema: `schemas/db.sql`, access:
`tools/db.py`). Until 2026-09-29 they were `vacancies.json` and
`companies.json`; the move came with the desktop app, which records a person's
feedback while the pipeline may be rewriting the base. With a 150 MB JSON file
every click rewrote the whole file and two writers could silently lose each
other's work. In SQLite **each column has exactly one writer** (listed at the
top of `schemas/db.sql`): the pipeline the record and the selections, the app
the feedback, `tools/feedback.py` the review mark. `kb.load_vacancies()` still
returns a dict, so the rest of the code did not change.

`state.json` and `recruiters.json` stay JSON (small, one writer), Markdown
stays for reports and `insights.md`, YAML for configuration.

### Selections: what each run showed
Every run records a selection (`tools/selections.py`): the shortlist split by
market exactly as the report splits it, every listed vacancy with its class and
score at that moment. The app lists vacancies with queries over it
(`schemas/queries.sql`) rather than from files, so marking a vacancy frees its
place in the top at once. Selections are never changed, only added: feedback
remembers the selection it was given in, and `tools/feedback.py` shows the
agent the class then and now, so a fix can be seen to have taken.

### Whether a run is going: a heartbeat, not a flag
`pipeline_runs` (tools/runstate.py) holds one row per pipeline run. A plain
"running" flag would stay set forever after a hard kill, since the code that
clears it never runs. So a run refreshes `heartbeat_at` every 10 s from a
background thread; readers treat a row silent for 45 s as not running, the app
also checks the pid when the run is on its own machine, and the next run marks
the silent row 'interrupted'. A normal end or an exception clears the row in
`finally`. The same row refuses a second concurrent run of one identity: each
run loads the base, works for an hour and saves it whole, and the second save
would undo the first. Portable by construction — a timestamp in a file.

### One row view, two renderers
`report.vacancy_view()` builds the data of one vacancy row; the Markdown
report and the app both render it. Two copies of the formatting would drift
apart. The refactor that introduced it was checked byte for byte against the
old renderer on 400 real vacancies.

The app's interface has a language switch, so the pipeline stores the row in
every language it can render (`report.vacancy_views()` → `vacancies.views`,
via `i18n.speaking()`); `vacancies.view` keeps the identity's own language
for the report and the feedback package. The app shows the one picked and
falls back to `view` for a row recorded before `views` existed.

### Boring, minimal dependencies
Only `requests` and `PyYAML` (plus `pytest` for the tests). RSS is parsed with
the standard library's `xml.etree.ElementTree`, HTML is cleaned by our own regex
stripper (`tools/common.py:strip_html`), and fuzzy comparison turned out not to
be needed at all (see "Rejected approaches" below). Fewer dependencies means
less risk that in a year or two `pip install` fails to build something on
somebody else's machine.

### The deterministic and the qualitative layers are kept apart
`tools/*.py` is the deterministic, reproducible layer (fetch, normalize, score,
report). The agent in an interactive session is the qualitative layer: it looks
at `needs_manual_review`, searches for companies, checks the real visa and EOR
situation, and enters findings through `tools/ingest_manual.py`. That is a
deliberate division of labour rather than an omission: the automation is a
recall-oriented first filter (better to let through something not quite
relevant than to miss a good vacancy), the agent a precision-oriented second.

### Companies as a derived view
Originally companies were updated incrementally alongside the vacancies.
Testing on real data showed that would desynchronise the counters between runs.
Rebuilt: companies are now **recomputed whole** on every run from the
current vacancies (`kb.build_companies_from_vacancies`), carrying over
only `notes` and `first_seen` from the previous version. That guarantees
`vacancy_ids` and the signal counters can never drift away from the real state
of the vacancy database.

### Retroactive rescoring of the whole base on every run
`pipeline.rescore_all()` recomputes `computed` for **every** vacancy, not only
the new ones. If `criteria.yaml` has become more accurate, old records get the
current verdict immediately. That follows directly from CLAUDE.md's requirement
that "every run must leave the repository better".

### The stack relevance gate
Real runs (see "Rejected approaches") showed that vacancies without a single
match against the technology stack still scored respectably, purely on generic
boilerplate words ("we serve clients in banking, insurance, government..."). A
hard gate was added: if `stack_fit.points == 0`, the classification cannot rise
above `low_priority` regardless of the other components. That sharply reduces
the rubbish in `long_shot` and `needs_manual_review` without needing NLP or LLM
classification inside the pipeline.

### needs_manual_review only for what already passed the filter
The flag was originally set on any vacancy without an explicit
worldwide/US-only/EOR signal — on real data that turned out to be some 85% of
the base, which is useless as a report section. Fixed: general uncertainty about
location is flagged only for vacancies that reached `long_shot` and above, while
an ambiguous "Georgia" (country or state) is flagged always, regardless of
classification, because that check is cheap and always matters.

### role_complexity_signal — an axis of its own, apart from legacy_enterprise_signal
Confirmed by the owner explicitly (2026-07-30) on real findings: "Staff Software
Engineer, Agentic Platform" (tide) and "Principal Machine Learning Scientist"
were passing as `long_shot` only because of generic enterprise/banking/insurance
words in the company description — while the ROLE itself is plainly not "quiet
maintenance" but R&D or new architecture from scratch. This was exactly the
improvement candidate recorded under "Further development" in the previous
version of this file; it is now implemented as its own gate
(`<prefix>_criteria.yaml` → `role_complexity_signal`, `score.py` →
`_score_role_complexity`): a match in the title (Principal/Staff Scientist,
Agentic, Founding Engineer and so on) gates immediately, while matches in the
description (build from scratch, greenfield, cutting-edge, PhD required...) need
at least two, so that a normal role is not gated over one stray buzzword in
boilerplate.

### A hard tie to a region is a dealbreaker, not "lower priority"
A real bug found (2026-07-30): an HN vacancy with "remote LATAM" in its text
scored respectably although it is physically unavailable to a person in Georgia
— such regional restrictions (apart from explicit US-citizenship phrases) did
not count as dealbreakers before, only as `us_remote_only_no_intl_signal` worth
6 points. Rebuilt: `restrictive_region_signal` is a single list of phrases
(US-only, LATAM, APAC, UK only, Canada only, India only and so on), and a match
WITHOUT a simultaneous worldwide or EOR signal makes the vacancy a dealbreaker
with status `rejected`. The list is incomplete in principle — there are
endlessly many regions — and that is a documented limitation rather than an
oversight; `needs_manual_review` and the agent reading the text are the last
line of defence.

**Correction, 2026-07-30 (evening):** "EU Remote"/"remote Europe" were
originally in `acceptable_region_signal` (a plus to the score). That was wrong:
in the real vacancy found, "(EU Remote)" in the title means residency IN the EU
is required, which disqualifies the owner exactly as "US Remote" does (Georgia
is not in the EU). Moved into `restrictive_region_signal`.
`acceptable_region_signal` now holds only descriptions of where the COMPANY is,
not residency requirements.

### Three FULL REJECTIONS added 2026-07-30 (evening) — not merely a low score

The owner read `latest.md` personally and pointed at specific, obvious false
positives. All three below are now genuine dealbreakers (`classification =
"rejected"`) rather than a demotion:

1. **`role_relevance_signal`** — the gate for "is this a developer role at all".
   Real findings: "CFO Controller" (score 60, `worth_a_look`!) and "Product
   Manager, Mapping and Weather Visualization" were passing purely on generic
   legacy/enterprise words in the COMPANY description. It fires on the vacancy
   title (a list of "wrong" professions — CFO/Controller/Product Manager/Sales/
   Customer Support/Recruiter/Webmaster and so on) and is lifted by an explicit
   developer word in the title ("Engineer"/"Developer") or by an explicit "tech
   agnostic" statement from the company anywhere in the text.

2. **`language_requirement_signal`** — the language gate. The owner speaks only
   Russian and English (`<prefix>_profile.yaml` → `owner.languages`). A real
   finding: "Web-Administration / Webmaster TYPO3" required "sehr gute
   Deutschkenntnisse". It catches both explicit English phrases ("fluent
   german") and the heuristic "this whole vacancy is written in German"
   (frequent words plus the standard German markup "m/w/d"/"w/m/d", a threshold
   of 3+ matches) — many vacancies from German boards (arbeitnow) contain no
   English phrase about language at all, being entirely in German.

3. **A strict stack relevance gate instead of a soft one.** It used to be
   `stack_points > 0` (low priority on failure). A real bug found: "LESS" (the
   CSS preprocessor, at familiar level) falsely matched the ordinary English
   word "less" in the "CFO Controller" description ("...no less than 5
   years..."), and one such match was enough. Rebuilt as
   `_check_stack_relevance()`: at least one core OR strong hit is required (one
   familiar hit is not enough). That also surfaced and fixed a real find of the
   owner's: "Java Entwicklung" (a pure Java web role) — the owner said outright
   "I am a .NET developer, they will not take me for a Java position". BUT
   Java/Scala FOR DATA PIPELINES (Spark/Databricks/ETL) is something the owner
   explicitly confirmed as wanted (real experience, from a previous job) — so it
   is implemented as a narrow exception (`data_pipeline_language_keywords` plus
   `_context_keywords`) rather than as removing Java/Scala from the stack
   entirely. An explicit "tech agnostic" statement lifts this gate too.

A side effect of the strict stack gate: `LESS` was removed from
`tech_stack.familiar` (the risk of that kind of false positive was not worth the
narrow benefit of a CSS preprocessor), and `Express` was renamed to `Express.js`
(reducing the same risk with the ordinary word "express"). See also the
analogous bug found with "LLM Engineer Freelancer" — not caught by the first
version of `role_complexity_signal`, which had only "Agentic"/"Principal
Scientist" patterns; "llm engineer" and "ai engineer" were added to the title
patterns.

### Three levels of trust in a salary: stated / external estimate / no data
Confirmed by the owner explicitly (2026-07-30). A salary stated in the vacancy
text is the full bonus, as before. What is new: the agent can enter a pay
estimate from an external source (Glassdoor and the like) by hand through
`tools/kb.py set-salary-estimate` — that gives a SMALLER bonus
(`external_estimate_points`), and it is the only reason such an estimate is
stored in the new top-level field `vacancy.external_signals` rather than in
`manual` (unlike `manual`, `external_signals` is explicitly passed into
`score.score_vacancy()` when rescoring — see `pipeline.rescore_all`). No salary
data at all remains strictly neutral (0 points) — do not confuse "no data" with
"bad pay".

### Link checking: conservative, only 404/410 count as "dead"
Confirmed by the owner explicitly (2026-07-30) after dead links turned up in a
report. `tools/link_check.py` checks every non-duplicate vacancy with a HEAD
request, falling back to GET. The only statuses read as "definitely gone" are
404 and 410: they are the only codes that unambiguously mean "the page is no
longer there". Everything else (403/429/999 from a site's anti-bot protection,
timeouts, 5xx) gets status `unknown`, and such records are NOT hidden from the
report: hiding a real vacancy is far worse than occasionally showing a doubtful
link (the same principle as in `kb.mark_duplicates`). The check is cached for 12
hours per vacancy (`recheck_after_hours`) so as not to hammer the job boards on
every pipeline run.

### The search-identity system (2026-07-31)

The project became multi-user. The full description is in `docs/IDENTITIES.md`;
what follows is only the decisions and why they are what they are.

**The paths to config and data depend on the active identity** rather than being
fixed. Implemented by rebinding module-level variables in `common.py` on
`activate_identity()`. The correctness condition, verified: nowhere in the
project reads these constants at import time — all ~30 accesses go through
`common.X` at call time. So rebinding needed no changes at the call sites and
did not break monkeypatching in the tests.

`CONFIG_DIR` was **deleted rather than turned into an alias**: a forgotten call
site should fail with `AttributeError` instead of quietly reading somebody
else's file.

**Templates plus a verbatim copy, instead of inheritance from a shared base.**
The property this buys: *the blast radius of a change equals the prefix of the
file changed*. An edit to `kisel_criteria.yaml` physically cannot touch another
identity.

The reason inheritance did not fit is specific: the boundary between machinery
and personal settings runs **inside individual lists**. In
`hard_wrong_profession_title_patterns`, universal GTM/sales patterns sit
alongside a personal exclusion of DevOps; in `hard_dealbreakers`, universal
onsite phrases sit alongside things derived from citizenship. An override layer
would have required inventing the semantics of "remove element X from the base
list" and putting them on top of the disqualifier logic — a new, untested
failure surface at the most dangerous point in the system.

The price was accepted deliberately: improvements to the machinery do not
propagate by themselves. It is offset by pinning the template version in
`identity.yaml`, by `templates.py check/update` (an update is a folder
replacement, never a text merge), and by the test that fails when a local
identity falls behind its template.

**Geography rules and language filters are derived, not copied.** They follow
from a particular person's residency and languages: "us only" is a
disqualification for a resident of Georgia and a plus for a resident of the US.
The derivation tables are in `config/derivation/`. Naive copy-paste of somebody
else's config breaks the search silently here, which is why onboarding is built
around a questionnaire rather than around "copy this and edit it".

**Data lives in `data/<prefix>/` at the repository root, not inside the identity
folder.** Otherwise negative-ignore rules would be needed inside a tracked
directory, and those break the moment any file is added. The file
`data/<prefix>/.identity` records who owns the folder and catches "the data
folder was moved by hand".

**The `ftf` test fixture is a byte-for-byte copy of the configuration at the
moment of transition.** A synthetic "neutral" fixture would have meant rewriting
most of the 111 existing assertions during the very refactor that was already
moving every path in the project. The copy let the existing test suite act as
insurance: the refactor demonstrably did not change behaviour (zero
classification differences across 2930 vacancies).

### Layered settings with provenance (2026-08-05)

Overrides used to be hand-written at each place in the code that read them —
twenty-six such places in `score.py` alone. Two consequences followed, both
observed: the only way to learn where a value came from was to read the code,
and two parts of the configuration could contradict each other, with whichever
ran first winning.

Replaced by one resolver (`tools/settings.py`) with a fixed layer order
(defaults → template → local), one set of merge rules, and provenance for every
value. Lists are replaced whole rather than appended to: appending looks
convenient right up to the first time something must be REMOVED from an
inherited list. An explicit `null` deletes a key. Frozen keys
(`config/settings_policy.yaml`) cannot be changed by the local layer, so that a
file outside git cannot quietly lift a boundary.

### One identity, several shortlists (2026-08-12)

A search identity now produces a report PER MARKET rather than one file: which
groups get their own file is configuration (`<prefix>_reports.yaml`), which
countries form a group is shared geography
(`config/derivation/market_groups.yaml`), and the machinery is
`tools/segments.py`.

**Why not one file sorted better.** It was sorted by score already. The
complaint that produced this was that a single list mixes a Singapore agency
posting with a UK contract at four times the rate, and a person reads one list
at a time to decide where to spend an evening. Sorting cannot express "I want
to look only at the UK tonight".

**Why not one file per country.** Because half of them would hold two lines.
The EU and EEA are one group for the same reason a person treats them as one:
a contract with a Dutch or an Irish company reaches the same kind of employer
at the same kind of rate.

**Why `rest` is computed rather than listed.** A catch-all maintained by hand
drifts, and the drift is invisible — the vacancy is simply in no file at all.
`rest` is everything no other segment claimed, so adding a market shrinks it by
itself. There is a test asserting that every vacancy reaches at least one file.

**Why `<prefix>_latest.md` still exists and still means everything.** It is
what RUNBOOK.md, the archive and a person's habit all point at. One segment
carries `default: true` and is additionally written there.

**The cost.** Eight files instead of one, and a person who opens only the UK
file could miss the worldwide one. Paid for by a banner in every file naming
the shortlist and linking to the others.

### Eligibility as a second axis, not more points (2026-08-12)

Every vacancy now carries a verdict alongside its score: CONFIRMED, LIKELY, NOT
STATED or NO — can a contractor sitting where this person sits actually take
the work? It is shown on its own line. It used to order every section ahead of
the score; since 2026-09-13 it only breaks ties — see "Rejected approaches".

**Why not a scoring component.** Because points average away exactly the
distinction that matters:

    "$100/hour — Remote — US"   is worth LESS than
    "$70/hour — Remote Worldwide — Contractor"

to somebody who cannot take the first. A high score with no eligibility cannot
be acted on at all, and as points the two would trade off against each other.

**Why it is derived rather than matched again.** Every signal it uses is
already in `score_breakdown.remote_location_fit`. A second independent
implementation of "is this worldwide" is precisely how two halves of a
configuration end up disagreeing without a test noticing — the project's most
expensive class of mistake (docs/OVERRIDES.md).

**What it immediately found**, none of it hypothetical: "remote-first company"
was being counted as proof of worldwide hiring; work authorization demanded as
a noun ("Must have authorization to work in the UK") went unmatched and sat in
hot_lead at 64; "100% remote in LATAM" led the worldwide shortlist at 76,
because the region tie was cancelled by the word "freelance" elsewhere in the
description.

### Engagement as a gate with a section of its own (2026-09-13)

A second identity for the same person — side work beside a main job — needed a
question no search had asked: how many hours. A full-time role is not a weaker
candidate for that search but an impossible one.

`score._check_engagement` answers it from `employment_types`, a normalised
field fetchers fill from the board's own classification (Remotive `job_type`,
Himalayas `employmentType`, LinkedIn's "Employment type", schema.org), and
from phrases the identity declares in `engagement_fit`.

**Why the same two halves as the remote gate.** Full-time is the default most
postings never write down, so silence is the common case, not the suspicious
one. A statement decides — "Full-time" refuses, "Part-time" or "20 hours a
week" confirms — and silence becomes `engagement_unconfirmed`: its own class,
its own report section, the score untouched. Rejecting on silence would be a
refusal by guesswork (CLAUDE.md §5).

**Why a confirmation anywhere beats a refusal anywhere.** "Full-time or
part-time" offers part-time; a board's default "Full-time" beside an employer
writing "15 hours a week" is the default being wrong. Leaning towards keeping a
vacancy is the cheap direction to be wrong in.

**Why "contract" confirms nothing.** A UK day-rate contract is five days a week.
A contract says who invoices whom, not how many hours.

**Why a search without the block notices nothing.** It is absent from KISEL's
criteria, and every test asserting KISEL's behaviour kept passing unchanged.
When both remote and hours are unknown, the older remote class takes the
vacancy and both objections stay listed, so the report can say what is left to
confirm.

### Axes an identity declares for itself: `extra_signals` (2026-09-13)

Every scoring component used to be a named function with a named block —
legacy, intensity, stack — because the first search needed exactly those. The
second search needed "interesting work" (a plus), "fits beside a main job"
(async against on-call) and "AI-training gig" (a visible minus), and scored
several of the first search's words the other way round.

A new axis is now configuration: `extra_signals` is a list of named keyword
signals with points, cap and floor, summed into the score, listed in the
breakdown under its own name, and printed in the report with the identity's
own label. The fixed components stay: they carry measured history, and turning
them into list entries would lose it for no gain. A search that does not want a
fixed component zeroes it (PJOICE's `legacy_enterprise_signal` weighs 0).

### Graded pay (2026-09-13)

`compensation_signal` gave a flat plus for a stated salary and a small
adjustment below or above a target range. For a search where money is the point
that cannot rank "$130/hour" above "$45/hour" — both are simply "stated".

With `hourly_equivalent_tiers` set, every amount becomes US dollars an hour (an
annual figure over 2080 hours, a monthly one times twelve over 2080, a range as
its middle), and the tier gives the points, replacing the below/above
adjustment. The board's own salary field outranks amounts found in prose,
which also hold stipends and prices; implausible amounts are ignored rather
than trusted. No salary stays neutral, as the constitution requires.

### A contractor word is not a location (2026-09-13)

"freelance", "contractor" and "1099" sat in one list with named
employer-of-record platforms, and a hit on that list skipped the check that a
vacancy is remote at all. The first part-time run surfaced a Brussels "freelance
mission, 50% remote" in its worth_a_look; the same override, measured over
KISEL's base, held eight vacancies in the confident tiers on those words alone,
not one of them remote — including a Stripe posting whose "1099" is a tax form.

Only a NAMED platform now exempts (`eor_platform_hits`), as it already did for
the region-tie override since 2026-08-12. The words keep their points; they
prove nothing about location. The affected vacancies go to remote_unconfirmed
with their scores unchanged — a person decides, nothing vanishes.

The general lesson, now paid for twice: **a word that describes the contract
does not describe the place or the hours.** "Contract" is five days a week in
the UK, "freelance" is a full-time assignment at a client in Belgium and France.

### A ruled-out role is not parked for a person — where the identity says so (2026-09-13)

The classification checks "is this only unconfirmed?" before "has the
complexity gate ruled the role out?", so a gated role can wait in a
check-by-hand section even though confirming it could never make it a
candidate. For PJOICE, where the gate means "this CV will not be considered", a
Principal Data Engineer sat at 55 in "hours not confirmed".

It is an opt-in, `role_complexity_signal.applies_to_unconfirmed`, rather than a
fix for everybody, because the measurement for KISEL came out the other way: 51
vacancies would leave its check-by-hand sections, the top ones ordinary ".NET
Developer" postings gated by a single "agentic" in a consultancy's boilerplate.
Hiding those would trade a small inconsistency for real false negatives.

### A specialism beside the core stack is not the role (2026-09-14)

The complexity gate refused on a title pattern, so "Senior .NET Developer
(Smart Contracts)" was ruled out as surely as "Smart Contract Engineer". The
owner: smart contracts must exclude a vacancy only when they are the job — ".NET
with smart contracts" is his work, "smart contracts with .NET" is not.

`role_complexity_signal.side_specialisms` (score._side_specialism) decides that
per specialism: a title naming only the specialism rules the vacancy out, a
title naming only the core stack keeps it, a title naming both follows whichever
it names first, and a neutral title leaves it to the posting — ruled out only
if the specialism is mentioned more often than the core stack, a tie keeping it.

**Why order in the title rather than counts everywhere.** A .NET posting about
integrating smart contracts naturally repeats "smart contract", "Solidity",
"EVM"; counting would refuse exactly the vacancy the owner described. The title
is where an employer says what the job is.

## Rejected approaches

### Reachability ahead of score inside a section (2026-08-12 → 2026-09-13)

When eligibility became its own axis, sections were sorted by it first and by
score second, so a CONFIRMED 46 came before an unstated 60. The reasoning was
sound — "$100/hour, US" is worth less than "$70/hour, worldwide" to somebody who
cannot take the first — and the result was unreadable: nothing on the page said
why a 46 preceded a 60. The owner, opening the UK shortlist: "46, 40, then 60 —
they must be sorted."

An order whose reason is invisible reads as no order. Sections are now sorted
by score, eligibility breaks ties only, and the preference for reachable work
lives where it can be seen: the verdict on every vacancy, and the worldwide
shortlist first among the files. `tests/test_report_order.py` holds the owner's
exact case.

### The Local Constitution: a third layer, retired (2026-08-06)

For a while there were three layers, not two: the constitution, the identity
(in git) and a "Local Constitution" outside it. The third existed for one reason
— identities lived in git, so residency, pay expectations and a CV path had to
be hidden somewhere. The mechanism was a `local` sentinel: the shared file held
the string `local`, and the real value was merged in from
`local-constitution/personal/<prefix>/<prefix>_owner.yaml`.

It also held a registry of active identities (`active.yaml`) and a
`default_identity`.

**Why it went.** When identities themselves moved outside git
(`local-identities/`), the layer lost its only reason to exist: there is nobody
left to hide a personal field from in a file that is not published. What
remained was cost:

  * a whole class of bug where scoring received the string `"local"` where a
    list or a dict was expected;
  * a registry that could drift away from what was on disk — the folders cannot;
  * `default_identity`, whose absence broke the commands of the identity that
    had been working, not of the new one;
  * about 200 lines of code and 10 tests serving none of it.

**What replaced what:**

| was | is now |
|---|---|
| `personal/<p>/<p>_owner.yaml` | `local-identities/<folder>/<p>_profile.yaml` |
| `personal/<p>/<p>_contact.yaml` | the same file, under `contact` |
| `personal/<p>/CV *.pdf` | `local-identities/<folder>/documents/` |
| `active.yaml` | nothing — the folders are the registry |
| `default_identity` | nothing — with several identities, `--identity` is required |

**When to revisit.** If identities ever need to go back into git — to be shared
through a PR, say — the problem returns and so does the need for a mechanism.
It should not be this one: a sentinel inside a shared file is a value that lies
about its own type. A separate file with an explicit overlay, or simply keeping
personal identities out of git, both cost less.


### Fuzzy deduplication of titles (difflib, threshold ~0.92)
The first version of `kb.mark_duplicates` grouped a company's vacancies and
collapsed similar titles with `difflib.SequenceMatcher`. On real data that
produced serious false positives: "Software Engineer - Manchester" and "Software
Engineer - Newcastle" (one role, different cities at one company), or "(Native
Danish) Support Consultant" / "(Native Finnish) Support Consultant" (separate
vacancies for separate languages) matched at >90% and were wrongly collapsed
into one record — that is, **genuinely different open positions were hidden**
from the owner. That is worse than occasionally showing a harmless exact repeat.
Replaced by a strict exact match on the normalised (company, title) pair. If
smarter deduplication is ever needed, do it by comparing (company, city or
location, title with the geographic token removed) rather than a bare fuzzy
ratio over the whole string.

### rapidfuzz / feedparser / beautifulsoup4 as dependencies
Considered for fuzzy string comparison, RSS parsing and HTML cleaning
respectively. Rejected in favour of the standard library (`difflib` turned out
not to be needed either — see above; `xml.etree.ElementTree`; our own regex
stripper). Minimising the dependency surface matters more than a small gain in
convenience, especially for a project that should `pip install` without trouble
years from now.

### Scraping LinkedIn's main site, Indeed or Glassdoor
Deliberately not done in any form — not through requests plus BeautifulSoup, not
through a headless browser, not by circumventing anti-bot protection or
CAPTCHAs. Those sites answer 403 to an ordinary request, and getting in would
take impersonation. See `docs/SOURCES.md`. (LinkedIn's guest job-search
endpoint is a different matter: it answers 200 to an ordinary GET, and
`tools/fetch_linkedin.py` reads it.)

### An override layer instead of full config copies (2026-07-31)

Considered as a way to propagate machinery improvements to every identity
automatically: a shared `criteria.base.yaml` plus personal overrides.

Rejected because the boundary between machinery and personal settings runs
inside individual lists (see the decision above). It would have required
inventing directives like `__remove:` and `__append:` and writing a merge
engine, all on top of the disqualifier logic, where a mistake means "the person
did not see a suitable vacancy" or "saw an obviously impossible one".

The decisive argument against: with overrides, an agent fixing a false positive
for one identity would edit the shared file and silently change the
disqualifiers for everyone else — and it would not show in the diff, because the
file carrying their prefix did not change. That is precisely the class of silent
cross-user failure the whole system was built to prevent.

**When to revisit:** if there are ever more than five or six identities and
carrying machinery across by hand becomes noticeable drudgery, come back to the
question — but only for purely mechanical blocks (`structured_location_gate`,
`role_complexity_signal`) and only in "add, never remove" mode.

(Partly superseded 2026-08-05: layered settings with a fixed order and frozen
keys were introduced, but for VALUES rather than for list membership. The
argument above still holds for the disqualifier lists themselves.)

### A context object instead of rebinding module-level variables (2026-07-31)

The "cleaner" alternative to global state: pass an object holding the paths as
an explicit argument.

Rejected for two reasons. First, it would have meant threading the object
through some 30 call sites and rewriting every monkeypatch in the tests — a
large risk inside a refactor that was already moving every path. Second, it does
not solve the main problem: `tests/test_score.py` reads config at module level,
that is, during test collection, when there is nobody yet to pass an object to.

The objection to mutable global state — concurrency — does not apply here: the
tools are single-threaded and single-session, and one active identity per
process is exactly the constraint wanted.

## Further development (candidates for the next cycle)

- Add Dice.com as a source (RSS or public search), if a legitimate public
  endpoint exists that needs no circumvention.
- ~~A gate for "not a simple" role (Principal Scientist/Agentic/R&D)~~ — done
  2026-07-30, see `role_complexity_signal` above.
- ~~A hard regional tie as a dealbreaker~~ — done 2026-07-30, see
  `restrictive_region_signal` above. The region list is incomplete in principle;
  extend it as new wordings turn up ("remote DACH only" and the like) that it
  does not yet catch.
- Smarter geographic deduplication (see "Rejected approaches" above) — if enough
  data accumulates, it is worth comparing (company, title-without-city).
- `recruiters.json` is not populated automatically yet — fill it in as the agent
  or the owner runs into particular recruiters.
- `link_check.py` treats only 404/410 as "dead" and deliberately does not try to
  detect "200 OK, but the page says 'vacancy closed'" (that would need brittle
  per-site content sniffing). If it becomes a frequent problem, collect concrete
  examples and consider narrow per-domain rules rather than a general solution.
