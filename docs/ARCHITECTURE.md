# Architectural decisions

The format is: decision → why. The "Rejected approaches" section exists so that
a future run or agent does not cover the same ground twice (see CLAUDE.md,
section 6).

## Decisions taken

### The database is a file
No SQL or NoSQL server — the repository has to be both the program and the
knowledge base at once (a requirement of the brief and of CLAUDE.md).

Vacancies and companies live in one SQLite file, `data/workide.sqlite`
(schema: `schemas/db.sql`, access: `tools/db.py`). Until 2026-09-29 they were `vacancies.json` and
`companies.json`; the move came with the desktop app, which records a person's
feedback while the pipeline may be rewriting the base. With a 150 MB JSON file
every click rewrote the whole file and two writers could silently lose each
other's work. In SQLite **each column has exactly one writer** (listed at the
top of `schemas/db.sql`): the pipeline the record and the selections, the app
the feedback, `tools/feedback.py` the review mark. `kb.load_vacancies()` still
returns a dict, so the rest of the code did not change.

### One base for every identity
Until 2026-10-05 each identity had its own file, and the same posting fetched
by two searches was stored, checked and read twice. Now `vacancies` holds what
a posting IS — what the source said, what its page said, whether its link is
alive — and `vacancy_identity` what one identity made of it: the score and
class, the near-duplicate mark (the copy the person answered comes first),
the rows shown in the app, the person's answer and the application funnel.
`load_vacancies()` returns the facts with the active identity's `computed` on
top; a vacancy that identity has not scored yet comes without it and is scored
at the end of its next run (`pipeline.finalize_and_report` rescores the whole
base). Every query of `schemas/queries.sql` takes `:identity`; selections and
pipeline runs carry it. One pipeline run at a time, whichever identity it is
for: a run saves the base it loaded an hour earlier
(`tools/runstate.py`). The per-identity files of versions 1-7 were merged once
by `tools/merge_shared_base.py`.

What is the identity's alone lives in `data/identities/<prefix>/`: insights,
state, feedback packages, run logs. Raw source responses are the sources', in
`data/raw/`.

`state.json` stays JSON (small, one writer), Markdown stays for
`<prefix>_insights.md`, YAML for configuration.

### Selections: what each run showed
Every run records a selection (`tools/selections.py`): the shortlist split by
market (`tools/segments.py`), every listed vacancy with its class and
score at that moment. The app lists vacancies with queries over it
(`schemas/queries.sql`) rather than from files, so marking a vacancy frees its
place in the top at once. Selections are never changed, only added: feedback
remembers the selection it was given in, and `tools/feedback.py` shows the
agent the class then and now, so a fix can be seen to have taken.

The app's four drop-downs (2026-10-07) are check lists, so one query takes
sets: markets, statuses, freshness, boards and classes, as JSON arrays read
with `json_each` (THE VIEW at the top of `schemas/queries.sql`). The queries
share their start, `view_pool`, through `-- include:` lines, which both
readers (`selections.load_queries`, `app/main/queries.js`) expand. "Every
market" is the segment holding the whole shortlist: `selection_segments.everything`,
from the configuration's `everything: true`; schema version 10 added it and
marked it on older selections. Each drop-down's own numbers are counted with
its own choice left aside, so a row that is unchecked still shows how many
it would add.

A fifth drop-down, "Company" (2026-10-14), groups by who stands between the
person and the employer: freelance marketplaces (Proxify, Toptal: a vetting
pool first, one application per marketplace), recruitment agencies, reposters
of other companies' vacancies (Jobgether: the employer unnamed), and every
other company as one row. A board's company field carries the intermediary's
own name, so the "Source" drop-down cannot separate them: Proxify's vacancies
came through workingnomads.com. Which company is which is Python's call
(`tools/company_kinds.py` over `config/company_kinds.yaml`: named entries plus
keywords such as "recruit" and "staffing", measured at 400+ small agencies in
the base). The app reads the database only, so every selection writes the
outcome to meta `company_kinds`, {company: {kind, name}} for the
intermediaries; the queries join it in `view_pool`. The view keeps the kinds
shown and the names hidden, not the names shown: with a shown-list, unticking
one name would freeze the list, and every company a later run brings would be
hidden.

"Category" (task 0049, 2026-10-21) also takes the kind of role under the
classes: on the CV's stack, another stack the CV fits, or a stretch for the
CV, worked out in `view_pool` from the view's `stretch` mark (ROLE in
`schemas/queries.sql`) and counted by `view_roles` with the kinds aside. The
person lists the stretches alone, or hides them, without a sixth drop-down.

A text field after the drop-downs (2026-10-19) takes words: a row stays when
every word is part of its title, company, intermediary's name, board, link,
hiring country or technologies (WORDS in `schemas/queries.sql`). It is applied
in `view_pool`, not beside the drop-downs, so every drop-down's numbers count
under it; the list and the "N more" counts stay right because the database
filters, not the page. Measured on the real base (5000 rows of `sharp`): each
view query 27–84 ms with words, as without. The case is folded by SQLite's
`lower()`, ASCII letters only. The panel is drawn anew on every change, so the
renderer gives the field its focus and caret back after each key
(`textFilterCaret`).

node:sqlite is synchronous, and Electron's main thread also carries the
window's input, so the app reads and writes the base on a thread of its own
(`app/main/store-worker.js`, driven by `store-thread.js`). Before 2026-10-12
the queries ran on the main thread, and a slow one (a pipeline busy on the
base, or the view queries before their `CROSS JOIN` order) froze the window
after a click. The renderer also waits for the clicks to stop for 200 ms
before asking for the list, and shows a spinner in its place until it comes.

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
for the feedback package. The app shows the one picked and
falls back to `view` for a row recorded before `views` existed.

### Boring, minimal dependencies
Only `requests` and `PyYAML` (plus `pytest` for the tests, and `python-docx`
for the CV per vacancy, below). RSS is parsed with
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
file changed*. An edit to `sharp_criteria.yaml` physically cannot touch another
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

**Data lives in `data/` at the repository root, not inside the identity
folder.** Otherwise negative-ignore rules would be needed inside a tracked
directory, and those break the moment any file is added. The file
`data/identities/<prefix>/.identity` records who owns the folder and catches
"the data folder was moved by hand".

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

**Markdown files, then the app (2026-10-20).** Until this date every segment
was also written as `reports/<prefix>_<slug>_latest.md`, with a dated archive.
The owner reads the shortlist only in the app, so the files and the folder
were removed (task 0052); the segments are recorded in the selection and the
app lists them. `default: true` still marks one segment in the configuration
and is recorded as `is_default`; nothing reads it today.

**Worldwide means the location names no place (2026-10-06).** Not "the report
found no country". The country index was the 35 countries of
`market_tiers.yaml`, and a location it could not read ("New York", "Berlin",
"Bucharest, Romania") made the vacancy worldwide: SHARP's worldwide list held
134 devitjobs offices in the US and Canada. Now `tools/places.py` reads every
country, US states and Canadian provinces, and the cities boards name alone
(`config/derivation/countries.yaml`); a place it still cannot resolve goes to
the `rest` segment. Worldwide keeps what names nowhere: an empty field,
"Remote", "Anywhere", a region, a time zone.

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

**Why a search without the block notices nothing.** It is absent from SHARP's
criteria, and every test asserting SHARP's behaviour kept passing unchanged.
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
fixed component zeroes it (PARTSHARP's `legacy_enterprise_signal` weighs 0).

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
SHARP's base, held eight vacancies in the confident tiers on those words alone,
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
candidate. For PARTSHARP, where the gate means "this CV will not be considered", a
Principal Data Engineer sat at 55 in "hours not confirmed".

It is an opt-in, `role_complexity_signal.applies_to_unconfirmed`, rather than a
fix for everybody, because the measurement for SHARP came out the other way: 51
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

### A CV per vacancy (2026-10-06)

**Generate CV** in the app runs `tools/cv_tailor.py --identity <prefix>
--vacancy <id>`. Three inputs: the **common CV** (`owner.primary_cv`, read
from its `.docx`), the **parent CV** (`cv.parent`: every achievement of the
person's working life, far longer than one CV; optional, added at any time)
and the vacancy from the base.

With both CVs given, the prompt splits their roles (2026-10-12): the parent CV
is the source of the material, the common CV the example of the layout and of
the priorities — what goes in when the vacancy asks for nothing special. The
parent CV's own length and layout are no model; the result is 2-3 pages.
Onboarding offers a parent CV as optional and, when there is none, reminds the
person at the end that it can be added later (`docs/ONBOARDING.md`, steps 2
and 6b).

Since 2026-10-12 a fourth, optional: the person's **instructions** for this
one CV. The first click on **Generate CV** opens a text field under the card,
the second click on the same button (or the form's own button, or
Ctrl+Enter) sends what it holds, empty included — as a rejection's reason
works. They reach the tool as `--instructions` and the model as
`<person_instructions>`, apart from the vacancy: unlike the vacancy, they are
instructions, and they outrank the CVs and the prompt's other rules (the
owner, 2026-10-22, task 0086; until then they "never made a fact true"). A
fact the person states in them, or in an earlier message of the log, is a
fact; where it contradicts a CV, it wins; what they ask to rewrite in the CVs
is rewritten. The report lists such facts (`from_instructions`). The prompt's
one rule on
language: the CV is in English, whatever the language of the vacancy or the
CVs, unless the instructions explicitly ask for another language; an
instruction written in Russian is not such a request. Without instructions
the message says so and repeats that the CV is in English.

The steps:

1. `claude -p` with no tools, `config/cv_tailor_prompt.md` as the system
   prompt and a JSON schema for the answer (`--json-schema`): the model
   returns the CV's content, each bullet marked with a priority (1 the vacancy
   needs it, 3 filler) and a source (common or parent), plus a report —
   the vacancy's keywords, which are covered, which are gaps, what came from
   the parent CV. The vacancy is put in the message as data; the prompt says
   it is not instructions.
2. A fact check in code (`check_facts`): name and contacts against the common
   CV; employer, title and dates of every job against both CVs; the jobs in
   reverse chronological order; every number and every technology name found
   in one of the CVs; no job and no skill category of the common CV left out.
   The person's messages (this one and the log's) are a source too: what they
   state is not a finding; what they do not cover is checked as without a
   message. Without a message the check is unchanged: it is there because a
   model's small rewordings add up to a different career.
   What fails is a finding for the person to look at, not a refusal: a
   reworded bullet is often right, and the person reads the CV before sending.
3. `tools/cv_docx.py` renders the content in the common CV's layout (the
   measurements are in its `LAYOUT`), and Word, driven through COM
   (`tools/cv_convert.py`), exports the PDF and reports the real page count.
   Over `cv.target_pages` (3) the bullets marked 3, then 2, of the oldest jobs
   are cut and the CV rendered again; `cv.max_pages` (3 by default, 4 until
   2026-10-12) is allowed only when nothing but priority 1 is left.
4. The pair is built in `data/identities/<prefix>/cvs/<vacancy>/<time>/` with
   the model's input and output, then published to the vacancy's folder under
   the common CV's file name (see "The documents folder" below); the previous
   pair moves to `Old versions/`. A failed run leaves the current pair where
   it was.

**Taken from career-ops** (github.com/santifer/career-ops, its CV mode and
history): the model returns content only, never markup; a requirements →
evidence map before writing; the employer's job description is data; a
reworded keyword sits only where it is true, and an interview or a review
never becomes "developed in"; the real page count is measured, not
estimated; every generated CV is archived per vacancy.

**What differs from career-ops.** career-ops renders HTML through a headless
browser into a PDF only. Here the person edits a CV the model got wrong, so
the `.docx` is the primary output and the PDF is made from it; the layout is
the person's own CV rather than a designed template. career-ops' facts are
checked by the model itself; here the check is code, after the model.

**Alternatives not taken.** The Anthropic API directly: needs a key, and the
project runs on the `claude` CLI already. Filling the person's own `.docx`
in place: its paragraphs carry per-run formatting that a model's text breaks
apart; a fresh document in the same measurements is predictable. LibreOffice
first: Word is what the person edits in and what employers open with, so its
pagination is the one that counts; LibreOffice is the fallback.

**The button after a generation** (2026-10-12, changed 2026-10-13). The
button reads "CV is generated" while the vacancy's folder holds a CV, whoever
made it (a click or the automatic generation), and keeps that state after
other CVs. Pressed in that state it works as before — the instructions, then
another version. A failed generation leaves the button as it was; when the
vacancy was found gone, the error is the button's tooltip.

### A cover letter per vacancy (2026-10-12)

**Generate Cover Letter**, right of **Generate CV**, runs
`tools/cover_letter.py` with the same inputs: the common CV, the parent CV
when there is one, the vacancy, and the person's instructions (the same
two-click field). It behaves as Generate CV does, its "Cover letter is
generated" state included; the two kinds keep their states apart, so a CV
generated after a letter does not reset the letter's button.

1. `claude -p` with `config/cover_letter_prompt.md` and its own schema
   (`LETTER_SCHEMA`; `cv_tailor.call_model` takes the prompt and the schema):
   name, headline and contacts from the common CV, today's date (given in the
   message), the address block and greeting from the vacancy only, 3-4
   paragraphs of 250-350 words, the technologies the letter names, and a
   report — covered, gaps, from the parent CV, notes. English unless the
   instructions ask for another language, as for the CV. Nothing about the
   company that the vacancy does not say.
2. A fact check in code: name and contacts against the common CV, every
   number and every named technology against both CVs. Findings, not
   refusals, as for the CV.
3. `cv_docx.render_letter` writes the `.docx` under the CV's header (name,
   headline, contacts), so the two read as one set; Word or LibreOffice makes
   the PDF and counts the pages. More than one page is a warning; nothing is
   cut.
4. Archived in `data/identities/<prefix>/cover_letters/<vacancy>/<time>/`,
   then published to the vacancy's folder as the common CV's name with "CV"
   turned into "Cover Letter" (`CV Ivan Petrov.pdf` → `Cover Letter Ivan
   Petrov.pdf`), the previous letter moved to `Old versions/`.

One generation at a time, of either kind (the documents slot of the task
queue, "The task service" below): both tools drive Word through COM, and two at once could share one
Word instance, whose `Quit()` at the end of one run would close the other's
document.

### The documents folder: versions and a log (2026-10-13)

Until 2026-10-13 a generation replaced one pair in Downloads: the previous
vacancy's CV was gone, and a second version for the same vacancy replaced the
first. The owner asked for a folder per vacancy and a history.

`tools/documents.py` keeps one folder for every identity, chosen at
onboarding (`documents.py set`, stored in `local-identities/settings.yaml`;
an existing folder gets "Work IDE CVs and CLs" inside it, a new path is
used as it is; unset, `~/Downloads/Work IDE CVs and CLs`), then
`<prefix>/<vacancy id>/`. Up to six files there: the CV and the cover letter
as `.docx` and `.pdf`, and a log for each (`CV log.md`, `Cover Letter
log.md`). A new version moves the current pair to `Old versions/` as
`<name> V<n>`, or `<name> V<n> failed` when the person's message rejects the
version as a whole (start over, or about ten changes and more); the model
decides that (`previous_version.failed` in its answer) and the log records
it.

The log is the document's history: each version, its time, and the person's
message. The whole log and the current `.docx` (the person's own Word edits
included) go to the model with the next request, so a version keeps every
correction asked for before it.

**A vacancy that is gone.** Old vacancies have dead links or no description
(fewer than 100 characters fetched). The tools then make no files and append
`## Error · <time>` with "Vacancy not found, possibly outdated: …" to the
log; the automatic generation skips that document from then on, and a later
successful version clears the error.

In the app: **Open CV/CL Directory** and **Copy CV/CL Directory Path** on a
vacancy that has a folder; "CV is generated" / "Cover letter is generated"
follow what the folder holds (`app/main/documents.js` reads the logs).

### The task panel and the queue (2026-10-13)

A collection and a generation used to block their buttons, with one log
under the list. Now everything is a task in a queue, shown in a panel at the bottom of the window, as in an IDE: the tasks on the
left, the log of the chosen one (the running one by default) on the right.
The panel's height (20% of the window by default, at least 220px) and the
split are dragged by their sashes and remembered.

The same task queued or running twice is refused (`already_queued`). A
queued task can be cancelled, a running one stopped.

Until 2026-10-21 the queue lived in the app's memory (`app/main/tasks.js`),
with two lanes, collect and documents: closing the app stopped the running
tasks and dropped the rest, and a run the agent or a terminal started never
showed. The queue is now a file run by workers outside the app: "The task
service" below.

**A collection's steps** (`app/main/steps.js`). A collection runs about four
hours (sharp, 2026-10-12: 4:24 in the pipeline alone), and one row said
nothing about where it was. The owner asked for the collection split into
tasks. Its row now has the steps under it, read from its own log: the agent's
preparation (identity, template, source contracts), each pipeline stage as
`tools/progress.py` logs it (`>> name` … `ok name - 5:35 (note)`, the
indented lines in between as its progress), then the agent's checklist and
the reputation lookups. That run, by stage: fetch 2:39:05 (LinkedIn nearly
all of it, 168 query pairs and 429 pauses; the other 18 sources about a
minute), check links 22:00, missing descriptions 53:31, three rescores of
about 6:00, direct channels 10:13, the rest seconds. Steps show while the
collection runs and fold when it ends; the arrow opens them again.

### The task service: a queue in a file, workers under Task Scheduler (2026-10-21)

The owner, 2026-10-20: a collection started under one Windows user stopped
when another user signed in with Fast User Switching; a collection takes
hours (the LinkedIn walk alone six and more). The panel also never showed a
run started by the agent or a terminal. Decided with the owner, 2026-10-21
(task 0056):

- **The queue is a file**, `data/tasks.sqlite` (`schemas/tasks.sql`,
  `tools/taskq.py`), apart from the vacancy base: a 30-second save of the
  base never holds up a task's state, and the queue survives a broken base.
  Logs are files beside it (`data/tasks/<id>.log`). Every task has a kind,
  an identity, a slot, what it needs (`ai`, `desktop`), who added it (app,
  agent, terminal, schedule, auto) and, while it waits, why.
- **Workers, not one daemon** (`tools/taskd.py`). The background worker is
  a Task Scheduler task at system start, "run whether the user is logged on
  or not" through S4U: no password is stored (the owner: if AI does not run
  without a sign-in, it waits for the sign-in). The desktop worker starts at
  the owner's sign-in in the owner's session: Word (COM) needs a desktop,
  so CVs and cover letters run there, and it keeps running while another
  user is active. Each claims, in a transaction, the tasks its
  capabilities allow; a worker that lacks one leaves the task queued with
  the reason ("the owner's sign-in: Word needs a desktop session").
  Registering the S4U task needs an elevated PowerShell, once:
  `python tools\taskd.py install`.
- **Slots:** collect (the top, the rest of the base, a full pipeline, a
  clean-up), linkedin, documents, reputation; one task each at a time.
  "Collect" is a group: the top and LinkedIn side by side, the rest after
  both (it runs when LinkedIn failed, not when the top did), a CV/CL batch
  after each. The dependencies are rows (`task_after`), not code in the
  app.
- **Reliability.** Task Scheduler starts the workers at boot and sign-in
  and restarts a failed one every minute; one worker per role; each beats
  every 2 s. A task whose worker stopped beating for 45 s is queued again,
  failed after three tries; a run started by hand whose process is gone
  ends "interrupted". After a gap of more than 30 s between two beats (the
  machine slept) no task of another worker is declared dead for a minute:
  all of them slept, and each needs a beat to show it lives. While a task
  runs the worker keeps the machine from sleeping on idle
  (`SetThreadExecutionState`); closing the lid still sleeps it.
- **Runs started by hand are listed too:** `pipeline.py` and `cv_batch.py`
  register themselves as tasks (`taskq.Registered`) unless a worker started
  them (`WORK_IDE_TASK_ID` in their environment). The agent adds its long
  work to the queue instead of running it (CLAUDE.md; the `run-task`
  skill).
- **The app is a client** (`app/main/queue.js`): it adds, lists, stops and
  clears tasks through `tools/taskq.py` and reads the file for the panel;
  it runs nothing, so closing or collapsing it stops nothing. Every 30 s it
  looks at the workers' beats (`app/main/workers.js`): a registered worker
  that does not beat is started through Task Scheduler; with none
  registered, the app starts a desktop worker for the session that ends
  after ten idle minutes.

**A worker the app starts goes through `taskd.py start`.** Node starts a
child with every inheritable handle of its parent, the pipes of Electron's
own stdio among them. A worker spawned straight from the app held those
pipes: Playwright, closing the app in the smoke test, waited 30 s and
failed, and a terminal after `npm start` would wait the worker's ten idle
minutes (2026-10-21). `start` launches the worker detached with only null
stdio, and returns at once.

**Not taken:**
- A Windows service (session 0): no desktop for Word, and the agent's
  `claude` login lives in the owner's profile; a service account would need
  that login copied or a stored password.
- "Run whether the user is logged on or not" with a stored password: the
  owner, 2026-10-21, "the password is never stored".
- A daemon with a socket API: the file already gives every client (the
  app, the agent, a terminal) the same view, with SQLite's locking, and
  nothing to keep listening.

### Generation without a click (2026-10-13)

The profile's `cv.auto` (`docs/IDENTITIES.md`) names filters — markets,
sources, classes, company kinds; AND inside a filter, OR between filters. A
collection queues **one batch** for the identity after its top, another
after its LinkedIn and a third after the rest of the base, whose AI read
raises stretch roles into a class (the task service above):
`tools/cv_batch.py <prefix>`. It
asks `tools/cv_auto.py` what to make and makes the documents one by one. Until 2026-10-13 (the same day) the app queued one task per document;
the first catch-up was 971 documents, so the owner asked for one batch task
instead.

**Why a process of its own.** About 2.4 minutes per vacancy (CV 1.6, cover
letter 0.8): 489 vacancies are some 20 hours. It runs as a task in the
documents slot and outlives the window; a stopped batch started again
skips what is made (`python tools/cv_batch.py sharp` goes on where it
stopped).

**How the app shows it** (`app/main/queue.js`). The batch writes
`data/cv_batch.json` (pid, state, index/total, made/gone/failed, the
document in work) and prints its lines into the task's log; the app lists
the batch as the task "CV/CL batch" with its progress. Its
document in work shows as generating on its card, and the card shows the
result when the batch moves on. The ✕ writes `data/cv_batch.STOP`: the batch
stops after the current document.

**One batch at a time.** Started while one runs, `cv_batch.py` adds the
identity to `data/cv_batch.pending` and exits; the running batch takes it
after its own list.

**The app goes first.** A CV asked for in the app would wait hours behind a
batch. While a CV or a cover letter is queued or running beside a running
batch, the worker keeps `data/cv_batch.HOLD` (its pid): the batch pauses
between documents ("holding" in its status), the queue lets the document
into the documents slot, and it waits only for the batch's current one. The
file is removed when those documents are done; a hold whose process is gone
is ignored.

**The person's vacancies are left alone (2026-10-22, task 0087).** The batch
makes neither document for a vacancy with any feedback, with a CV or a
cover letter of the person's, or with a CV or letter task of theirs queued
or running; it asks again before each document, after a pause too
(`cv_auto.left_alone`). A version the batch made says "Made automatically."
in its log (`--auto` to `cv_tailor.py` and `cover_letter.py`); every other
version is the person's, those made before the mark included. On
2026-10-22 the batch, resuming from a hold, made INSO's CV and letter while
the owner's own two tasks for it were queued: four versions the owner could
not tell apart.

**Every match, not only the fresh ones (2026-10-21).** Every vacancy of the
latest selection with no answer that a filter matches gets its documents;
the documents already in its folder (or its "gone" error) keep it from being
made twice. Until then a filter already applied took only the fresh
vacancies of the run (below), and a vacancy that rose into a class later —
a rescore, a description fetched, the AI read of a stretch role — never got
documents: on 2026-10-21, 14 of the 16 vacancies SHARP's filters matched
had none. The owner: "every such vacancy must have a CV/CL; there are 10-15
a week". `company_kinds` came the same day: a freelance marketplace (A.Team,
Lemon.io) is one application per marketplace, so SHARP's filter leaves it
out.

**Rejected: fresh, and the catch-up (2026-10-13 to 2026-10-21).** A filter
was identified by its content (plus `documents`), the applied ones were kept
in `data/identities/<prefix>/cv_auto.json`, and only a filter not yet there
picked the earlier vacancies of the latest selection; an applied one took
the vacancies new in the run. It made the batch after a collection small,
and missed every vacancy whose class changed after its first run.

**Not taken:** a separate "generate for the backlog" button — the batch of
every collection covers the backlog, and a button would be a second path to
the same thing.

### The top vacancies first: `--top`, then `--rest` (2026-10-17)

The owner, after a day of applying: the best remote vacancies close within
hours, and a full run took 4:24 on 2026-10-12 (fetch 2:39 of it, LinkedIn
2:35; links 22:00; descriptions 53:31; three whole-base rescores of about
6:00). They asked for the top vacancies in about an hour, daily, in this
order: collect, check remoteness by script, check the remote ones with AI,
polish, CVs; everything else afterwards; remote_unconfirmed gets nothing
after its remote check; and the steps visible in the task panel.

`pipeline.py --top` (`run_top`):
1. fetch every enabled source; LinkedIn for the window of
   `linkedin_window` (below). Since 2026-10-20 every source but LinkedIn,
   which has a run of its own ("LinkedIn beside the other sources");
2. rescore the top classes (`TOP_CLASSES`: hot_lead, worth_a_look,
   long_shot, engagement_unconfirmed) and what this run brought — not the
   whole base;
3. the remote check by script: the pages of those vacancies that have no
   text (`enrich_descriptions`, at most 300 plus 200 "description wanted"),
   then a rescore;
4. the AI brief (written when the CV or the identity documents changed) and
   the AI check of the top (at most 1000 a run, so the CV batch after
   it gets read vacancies), then a rescore;
5. near-duplicates, links of the top classes only, companies, direct
   application channels, Wikidata facts of the top companies, a rescore;
6. save, a "run" selection, the reports.

The app's "Collect" runs `/top <p>` (`.claude/commands/top.md`: identity,
template check, source contracts, `pipeline.py --top`, a summary; no
checklist and no reputation lookups). The CV/CL batch and the task "rest"
are tasks of the same collection in the queue ("The task service"): the
rest is `pipeline.py --rest` with no agent, in the collect slot after the
top and LinkedIn; a rest still waiting for its LinkedIn lets the next
identity's top run first.

`pipeline.py --rest` (`run_rest`): the full tail (`finalize_and_report`)
with a "rebuild" selection, so what the top run
marked fresh stays fresh. Its description stage leaves out
remote_unconfirmed. The full cycle (`pipeline.py` with neither flag) is
unchanged except for the AI stage.

#### How far back a collection reaches (2026-10-17)

LinkedIn is the one source that can be asked for a date window (`f_TPR`);
the others serve their whole current feed in seconds to a minute. Every
mode (full, top, rest) asks it for `linkedin_window`:
- the days from the local date of `linkedin_covered_to` (the start of the
  last LinkedIn fetch that went through) to today, both included: a
  collection yesterday afternoon means yesterday and today, for what was
  posted after it;
- the full window, `LINKEDIN_FULL_DAYS` = 7, when there was no collection,
  or when no LinkedIn vacancy is left in the base (it was cleaned up); also
  the cap. It was 30 for a day; the owner, 2026-10-18: a week takes hours
  already (a 7-day rest run of 2026-10-17 read 126 of 168 pairs in about
  3 h), a month is out of reach.

The owner asked for it: a first top run that asked for a day or two missed
the long-open roles that always take CVs. Before, every run asked for 7 days
and the top run for at most 2.

LinkedIn is read to the end of its window in every mode, the top run
included, however long it takes. **Not taken: a time budget.** On 2026-10-17
the top run had one (`TOP_LINKEDIN_MINUTES` = 25: past it
`fetch_linkedin.fetch` stopped between pages and the rest run read the
window again), after its first run met 40 answers 429 in half an hour and
read 4 of 168 (keyword × country) pairs. The owner had it removed on
2026-10-18.

`note_linkedin_window` moves `linkedin_covered_to` to the fetch's start when
the fetch did not fail. Otherwise it keeps the value read before the fetch —
the fallback, `sources.linkedin.last_success`, has just moved to now and
would hide the gap — and sets `linkedin_gap`. Until 2026-10-20 the rest run
read the window again on a gap; since, the next LinkedIn run asks for those
days by the coverage left ("LinkedIn beside the other sources").

Every mode's result has `collected`: the window in words ("LinkedIn: posted
in the last 2 days - the days since the last collection, both included",
with a failure when there was one). The summary to the
person names it after every collection (`/top`, `/run`, RUNBOOK step 1);
`last_run_stats.linkedin_days` keeps the number.

### LinkedIn beside the other sources (2026-10-20)

The owner, 2026-10-20: LinkedIn is the largest source and the slowest — the
7-day run of that day had read 111 of 168 pairs after 14 hours, most of them
waiting out 429s — and the other sources' vacancies, fetched in half an
hour, waited for it. They asked for LinkedIn to run apart, side by side with
the rest.

Two runs cannot hold the base at once (`tools/runstate.py`: each loads the
whole base and saves it whole), so only the network part runs beside the
others:

- `pipeline.py --linkedin` fetches LinkedIn's window without holding the
  base (`fetch_linkedin_apart`): the window is read from the state, the base
  is only asked whether it holds a LinkedIn vacancy (`db.any_from_source`),
  and the records go to `data/identities/<p>/runs/linkedin_fetched.json`.
  Then it waits for the base (`PipelineRun(wait=True)`, the stage "wait for
  the base") and merges (`merge_linkedin`): the records, the window
  (`note_linkedin_window`), and the top run's steps on the top classes and
  what LinkedIn brought (`process_top`, shared with `run_top`). The
  selection is a "rebuild", so the top run stays the baseline of what is
  fresh: its vacancies stay fresh, and LinkedIn's new ones are fresh too. A
  fetch that brought nothing records its failure in the state without
  loading the base; the coverage stays, so the next run asks for those days.
- `pipeline.py --top` fetches every source but LinkedIn; its `collected`
  line says LinkedIn is fetched apart.
- `pipeline.py --rest` fetches nothing. It read LinkedIn's window again after
  a failed fetch; the LinkedIn run does that now, by the coverage it leaves.
- The full cycle (no flag) still fetches LinkedIn inline.
- One LinkedIn fetch at a time on the machine, whichever identity
  (`runstate.LinkedInFetch`): the address and its rate limit are shared. The
  full cycle takes the same lock.

"Collect" queues the top (`/top`, the collect slot) and "linkedin" (a slot
of its own, which does not ask whether the base is free: the run waits for
it itself) side by side. The rest of the base waits for both and runs if
the top ended done; a CV/CL batch follows each that ends done. The
collection is going until the last task of its group ends: a click or a
schedule queues no second one meanwhile (`taskq.active_collection`, task
0089). Until 2026-10-23 only the top counted; that night the top was done
while LinkedIn ran its sixth hour and the rest and two batches waited.

**The top's session waits for its pipeline (2026-10-22, task 0088).** The
agent ran the pipeline, Claude Code moved the command into the background
after its 2-minute timeout, the agent ended its turn "watching the log", and
`claude -p` ended 28 s after the pipeline started; the pipeline died in the
fetch, saved nothing, and the task was marked done. Now the worker starts the
session with `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` and a 3-hour Bash
timeout (`taskd.AGENT_ENV`), and `/top` says to run the pipeline as one
foreground command. The pipeline's first line names its queue task
("started (queue task 10)"); the worker follows only that task's logs (it
used to mirror a LinkedIn run beside it too), and a session that ends with a
log of its task lacking "pipeline finished" is queued again, up to
`MAX_ATTEMPTS` starts, then failed with the log's last line.

The pacing of the fetch changed the same day (docs/sources/linkedin.md, "429
and dropped connections"; "What each query brought").

### The AI check of the top (2026-10-17)

The owner's feedback of 2026-10-17 (137 wrong picks): keyword gates miss
what a reader sees at once — a Hacker News comment that is not a posting,
"remote first (1 day per month in Manchester)", "at least 50% of the time in
their local office", a Go or Shopify role with .NET in the company blurb, a
US-only role with "Remote Work" in an award name. They asked for a cheap
model reading each top posting with a digest of the person written by a
strong model, kept in the local identity and rewritten when the CV changes.

- `tools/ai_brief.py`: Opus writes `<identity folder>/<p>_ai_brief.md` from
  the CV text, the identity description (template and local), the personal
  profile and criteria, and the owner's reasons for turning postings down.
  The first line holds the hash of the documents and the prompt
  (`config/ai_brief_prompt.md`); the reasons are not in the hash, so new
  feedback alone does not rewrite it.
- `tools/ai_screen.py`: Haiku, with `config/ai_screen_prompt.md` plus the
  brief as its system prompt, answers a fixed schema per posting (is it a
  posting, arrangement, location, role fit, verdict, reason, quote). Answers
  are stored per identity in `ai_screens` with the hash of the text read and
  of the brief; a new text or brief asks again.
- On the top classes it only removes: `score.py` turns a "reject" into the
  dealbreaker `ai: <reason>`; a "keep" changes nothing. The reason and the
  quote show in the app's Details. A stretch role is the one place a "keep"
  lets a vacancy in (see "Remote outranks the technology" below).
- Through the `claude` CLI (`-p`, no tools, an empty working folder, so no
  project instructions in its context), with `MAX_THINKING_TOKENS=0`:
  measured on one posting, $0.018 and 2566 output tokens with thinking,
  $0.0059 and 237 without. On the 43 feedback items the scripts still kept,
  Haiku rejected all 43 with thinking; 15 asked again without it gave the same
  15 verdicts.
- The first top run (sharp, 2026-10-17): 400 read, 388 rejected, $3.14.
  Reading the 185 rejects with a fitting stack: nearly all name a US, Canada,
  UK or single-country limit, IR35, or office days. Two were wrong — "CET
  ±3 hours" taken to exclude UTC+4, and a posting hiring "elsewhere" through
  Remote.com taken as Ireland-only. `config/ai_screen_prompt.md` now says to
  work time zones out in UTC offsets and that hiring elsewhere through an
  employer of record is not "no"; asked again, both were kept and three
  rejects from the control sample stayed rejected. The prompt is part of
  `brief_hash`, so a prompt change reads the top again.
- 2026-10-20, the same misreading again: "CET ±3 hours" taken to exclude
  UTC+4 in 3 of 4 Proxify postings, both with the rule above and with the
  window spelled out as "UTC−2 to UTC+4". Now `ai_screen.model_message` puts
  the scorer's own reading of the window (`timezone_requirement` in the
  breakdown) above the posting as a line "time-zone window, checked by a
  program"; the same 4 asked again: 3 read the location as fitting, the 4th
  was rejected for asking 5+ years of Python. The line is not part of
  `text_hash`, which stays on the posting alone.

Two script rules came from the same feedback, as personal settings:
`remote_location_fit.unstated_remote_after_reading: reject` (a text of 600+
characters that never says remote is rejected; 99 of 107 wrong picks in
remote_unconfirmed had their text read), and `reject: true` on
`title_role_penalty` rules (sharp: front-end, UI and junior titles).

### Remote outranks the technology: stretch roles (2026-10-20)

The owner, 2026-10-20, after applying to Cloud9's "Forward Engineer" (a Node
role the screening model had refused as "not .NET"): remote comes first; a
remote role the real CV can reach is wanted whatever its stack; Node, Go,
Python and applied AI are a plus, .NET is good too; pay ranks above the
technology. Not wanted: ML research, training models, data-heavy roles the
CV cannot cover without inventing experience; junior is fine unless it is a
junior developer.

Measured that day on SHARP's base: 2 506 vacancies were refused only for
their stack or title with no location objection, 1 450 of them posted in
October; 347 of the 350 "forward engineer" ones were refused (244 by the
title rule "forward deployed is not a developer").

- `stretch_roles: {enabled, stretch_points}` in criteria (SHARP sets it in the
  personal layer). With it, the stack relevance gate, the title stack gate,
  a title in `stretch_discipline_title_patterns` (data, ML/AI, forward
  deployed) and a `title_role_penalty` rule's `stretch_if` stop refusing on
  their own: the vacancy waits with STRETCH_UNREAD and `screen_wanted`.
- Remote first: only a vacancy whose sole objection is that wait is sent to
  the model; one whose remote is unconfirmed waits for its description.
- The model answers `cv_fit` (fits / stretch / no) and `work_kind` (software,
  applied_ai, ml_research, data_heavy, other). "fits" lifts the objections,
  "stretch" lifts them at `stretch_points`, "no" is a reject. A stretch the
  model read is past the role complexity gate: its "no" covers ML research,
  which is what that gate's titles catch.
- A vacancy held only by a model's reject is `screen_wanted` too, so a new
  prompt or brief reads it again (before, a reject left the top classes and
  was never asked again).
- `ai_screen.STRETCH_LIMIT` (400 a run, highest score first) after the top
  classes: about 1 100 were waiting the first time, $0.006 a read.
- The card shows "a stretch for the CV" or "another stack, fits the CV", with
  the model's reason on hover (`stretch` in the row view).
- The brief prompt now says the description of the search wins over older
  reasons: the owner's earlier "Go role", "Node only" refusals would
  otherwise have written "Go, Node: reject" next to "Go, Node: a stretch".

### Schedules: the queue's work on a timetable (2026-10-21)

The owner, 2026-10-21: with the task service running outside any session,
it can start collections and clean-ups itself, on a timetable set in the
app. A schedule is a row in `data/tasks.sqlite` (`schedules`,
`tools/schedules.py`): what (a collection as its group, LinkedIn, the rest,
a clean-up with its filters, a CV/CL batch, a re-check of the shortlist's
links — `pipeline.py --links`), for which identities (named, or every
active one at the time), a cron line in local time, on or off, and what a
missed run does.

- **The workers queue it.** Every worker looks every 20 s; the run is
  claimed in one transaction, so two workers never queue it twice. What it
  queues is an ordinary task, origin "schedule", in the panel like any
  other. No new process, no Task Scheduler entry per schedule: one
  `schtasks` line per schedule would be a second place to look for what
  runs, outside the queue's file and its tests.
- **A run missed while off or asleep** (found more than 10 minutes late):
  caught up once, or skipped, per schedule (the owner: both ways). Several
  missed run times are one run caught up, not a burst at wake-up.
- **One run at a time.** A schedule whose previous run is still queued or
  going skips the next, and says so in its last note.
- **A changed timetable, or a schedule turned on, counts from then**: the
  run times before it were not asked for, so nothing is caught up for them.
- **The cron parser is our own** (fields, lists, ranges, steps, names,
  @daily and the like, cron's either-day rule): about 80 lines, against a
  new dependency (`croniter`) for the same.
- A schedule is due only while a worker runs: with the workers registered
  (`taskd.py install`) from system start; without, while the app's worker
  is up. Waking the computer for a schedule is not done.

### Nothing reaches the top before the AI read (2026-10-22)

The owner, 2026-10-22: the selection of the night before held 40 new
vacancies, five times a usual week, and most were office jobs with "remote
on Wednesdays if the manager agrees". The scripts had put them in the top
classes; the AI check had never read them. The cause that night was a
one-off repair (task 0076) that rescored the base with newer criteria (the
ITAR fix of task 0073 freed 37 vacancies refused for "itar" inside
"military") and recorded a selection without the AI step. Any rescore
outside the pipeline's AI stage could do the same, and so could a run whose
AI stage failed.

- **A fifth class, `ai_unscreened`** ("Not processed with AI"), between the
  long shots and "remote not confirmed". `score.py` puts there what the
  scripts would put in a top class (`ai_screen.TOP_CLASSES`) while the
  model has no answer for its current text; the scripts' class is kept in
  `computed.script_class`. A "keep" moves it to that class, a "reject" out.
  A new text (the description arrived) sends it back to wait. An identity
  may take the scripts' verdict alone with `ai_screen: {required: false}`
  in its criteria.
- **A failed call is sent again**: `ai_screen.RETRY_ROUNDS` (2) more rounds
  after `RETRY_PAUSE_SECONDS` (20); `errors` counts what failed every time.
- **What a run leaves unread is queued**: when a run saves with vacancies
  waiting, `pipeline.queue_ai_read` adds the task `ai` (`pipeline.py --ai`:
  the AI check of what waits, the top rescored, a "rebuild" selection),
  once per identity; at the usage limit the queue runs the run itself
  again instead. An `ai` run that leaves vacancies waiting exits 1, so the
  task list shows it failed. Every later run reads them too.

### The AI usage limit stops the AI work, and the queue waits for the reset (2026-10-21)

The owner, 2026-10-20: when AI refuses because the limit is used up, the
scripts must stop, not keep calling. Before this a refused call was an
ordinary error: `ai_screen` counted it and went on to the next posting, so
at the limit it sent one refused call per posting left, and the run ended
looking finished with an error count.

- **One recogniser** (`tools/ai_limit.py`). Every `call_model` (`ai_brief`,
  `ai_screen`, `reputation_lookup`, `cv_tailor` and through it
  `cover_letter`) passes its finished process to `ai_limit.check`, which
  raises `UsageLimit` with the reset time when the answer gives one. It
  reads only a refused call (`is_error` or a non-zero exit), so a posting
  or a CV that mentions a limit is never taken for one, and only the
  wordings of the AI limit: LinkedIn's "rate limit reached" is not it. The
  exact shape of the answer at the limit was not captured on this machine
  (no refused call in any log, 2026-10-21); the recogniser takes the
  wordings Claude Code is known to print, and is to be checked against the
  first real one.
- **The stage stops and keeps what it did.** `ai_screen` sends no call after
  the first refusal (the calls already in flight finish), saves the
  answers given, and raises with its stats. The pipeline goes on without
  AI: links, channels and the selection are made, and it exits with
  `ai_limit.EXIT_CODE` (75) and the line `AI usage limit reached; resets at
  <time>`. Run again after the reset, the screen asks only what was not
  answered. `cv_tailor`, `cover_letter` and `reputation_lookup` exit 75; a
  CV/CL batch stops before its next document.
- **The queue waits.** A tool that meets the limit records it in the queue
  (`taskq.block_ai`), and so does a worker whose task exited 75 or printed
  the line; the task goes back to the queue (not failed), and every task
  that needs AI waits, "the AI usage limit; tried again at 17:05". At that
  time one worker makes one minimal `claude -p` call (haiku, in a thread,
  so the beats go on): answered, the tasks go on; refused, they wait for
  the new reset. A refusal with no reset time is checked again after 8
  hours (the owner, 2026-10-21). Until the check has answered, a task is
  not started only to meet the limit an hour into a run.

### Reputation on request, not in every collection (2026-10-17)

The owner: reputation lookups did not pay for their time. Until then /run
step 6 made them mandatory for every company in hot_lead and worth_a_look,
the report had a "Company reputation checks" section listing the gaps, and
doctor.py warned about them. All three are gone; the pipeline no longer
records `reputation_coverage` and `reputation_worklist` in the state.

Instead the vacancy has a "Collect reputation" button in the app while its
company has no result (`reputation_collected` in the vacancy's view: found,
or "too few sources"). The button queues the task "reputation" in a lane of
its own, so it does not wait for a collection: `tools/reputation_lookup.py
--identity <p> --vacancy <id>` asks a model with web search only (`claude -p
--tools WebSearch,WebFetch`, Sonnet, an empty working folder) for the ratings
on Glassdoor, Indeed, Trustpilot and the like, records "found" or
"insufficient_sources" as the hand commands do, rescores this identity's
vacancies of the company and renders their rows again. A company with a
result is not looked up again — the tool only rescores and renders, which an
identity rendered before the other identity's lookup needs.

A pipeline that loaded the companies hours before would overwrite such a
result when it saves the companies table whole; `db.save_companies` keeps a
stored reputation newer (by `checked_at`) than the one being saved.

The scoring is unchanged: a reputation, when there is one, still adds or
removes points and a red flag still asks for a person's review.

### Clean up: deleting, not hiding (2026-10-17)

The app's "Clean up" (`tools/cleanup.py`, `app/main/cleanup.js`) deletes
vacancies by age, feedback status and class, with every row that names them,
and compacts the file. A vacancy goes only when it matches in every identity
holding it; the funnel and feedback not yet reviewed are kept. The owner
weighed a shadow ban and chose deletion: a vacancy deleted and still live
comes back as a new one on the next collection, and the disk space returns.
The first run (2026-10-17, older than a month) deleted 22 209 vacancies; the
file went from 818 MB to 535 MB.

### An answer redraws one card, not the list (2026-10-18)

Until 2026-10-18 every answer (Apply, Not for me, Undo, a funnel step, a
comment) wrote, then waited for the whole list to load again — six view
queries, one after another in the store thread — before anything changed on
screen. The owner measured 1.5 s a click. Two causes, two fixes:
- the queries: `company_kinds` was parsed again for every row of the pool
  (`schemas/queries.sql` says how; 250-560 ms a query, 30-75 ms after);
- the wait itself: the store answers each write with the vacancy's record
  read back after it (the backend's confirmation), the renderer redraws that
  card, its stub and its class's "Shown 10 of 660" from it at once, and the
  list catches up behind (`answered`, `undo` in `app/renderer/app.js`). The
  count is set to what the list that catches up will say: an answer that
  takes a card out of the view takes one off the total, its row staying under
  the stub until the next card moves up; an Undo puts it back and, in a
  capped class, pushes the last unanswered card out.

A pipeline writing the base (the end of a collection rescores and saves it)
still makes a write wait for its lock (busy_timeout 60 s): the confirmation
is the write itself.


### An identity turned off, and the commands in one menu (2026-10-20)

The owner, 2026-10-20: an identity can be inactive, and an inactive one is
not collected. The flag is `identities.active` in the shared base (schema
version 11), not a line in the identity's folder: the app already writes the
base, and both sides read it. The "Identities" window in the app's menu
switches it (`store.setIdentityActive`, query `set_identity_active`);
`python tools/identity.py set-active --identity <p> on|off` does the same by
hand.

The block sits where collecting starts, so every path through it is covered:
`tools/pipeline.py` (`--top`, `--rest`, the full cycle) and the single-source
fetchers (`identity.standalone_main`) return at once, exit 0, with a
`SKIPPED: identity '<p>' is inactive` line (`identity.skip_if_inactive`). A
skip, not a failure: a queue of runs goes on to the next. The app also
refuses to queue a collection for one (`main.js`, `enqueueTask`) and greys out
"Collect" with the reason. The flag is read read-only, without upgrading the
base (`identity.inactive_identities`): a test that lists the identities must
not migrate the real base. An inactive identity keeps its tab, dimmed, and
its vacancies.

The same day the toolbar's commands moved into one menu: Refresh, Collect
(and Stop, for a collection the app started), Review feedback with the way to
start it, Clean up, Identities. A collection going shows in the menu as
Collect's spinner and stage, wrapping to two or three lines when long. The
menu's own button spins while anything runs — a task of the app, a pipeline
run of any identity started anywhere, a clean-up — and its tooltip names
what (`busyWith`), so it is seen with the menu closed. Until the owner's
second request that day, Refresh and the collection's status stood beside
the menu. Later that day Refresh left the menu again (task 0058): a button of
its own in the top bar, left of the theme and language pickers and the same
size, with the same ring-arrow icon.

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

### The best-scored copy as the canonical one (until 2026-10-24)
`kb.mark_duplicates` kept the best-scored copy of a posting and hid the rest
from the list, the description fetch and the AI. The work on a copy then moved
the choice: the Israel copy of Deel's "AI Engineer, Backend" was read as a
stretch, lost 4 points, the UAE copy (35) became canonical, was read in a later
run, and the model said "no": the kept copy was hidden and the canonical one
refused, so neither showed (the same for two more, 2026-10-21). Unread copies,
"remote unconfirmed" for want of a text, were also counted as hidden listed
vacancies (948 for SHARP) behind a read refusal. Since task 0096 the canonical
is the best-filled copy (`kb._filled`): the one the person answered, a read
text, more facts, a longer text, the earliest seen; nothing the scoring or the
model made of it. Measured before the change: of 918 groups with two read
copies, 849 had the same location verdict, and the other 69 differed in the
location field ("Remote" on an aggregator against "Remote, United Kingdom" at
the employer), not in the employer's offer.

### rapidfuzz / feedparser / beautifulsoup4 as dependencies
Considered for fuzzy string comparison, RSS parsing and HTML cleaning
respectively. Rejected in favour of the standard library (`difflib` turned out
not to be needed either — see above; `xml.etree.ElementTree`; our own regex
stripper). Minimising the dependency surface matters more than a small gain in
convenience, especially for a project that should `pip install` without trouble
years from now.

### Scraping LinkedIn's main site, Indeed or Glassdoor
Not done: those sites answer 403 to a plain request. See `docs/SOURCES.md`.
(LinkedIn's guest job-search endpoint answers 200, and
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

## Further development

The list of work, done and waiting, is `tasks/` (format in `tasks/README.md`):
ideas nobody has agreed to yet are in `tasks/1-triage/`, agreed work in
`tasks/2-to-do/`, work decided against in `tasks/4-cancelled/`. The candidates this section listed until 2026-10-20 were
either done (the role-complexity gate, the regional dealbreaker) or dropped:
Dice.com answers 403 (`docs/SOURCES.md`); the region list is extended as
wordings turn up, not as a task; near-duplicates are already merged; closed
pages are recognised per board where a board needs it.
