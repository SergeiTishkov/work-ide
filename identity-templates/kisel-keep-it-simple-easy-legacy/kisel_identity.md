# KISEL — calm, low-intensity legacy remote work

> **KISEL = Keep It Simple, Easy, Legacy.**
>
> The abbreviation deliberately names **what the search is about** rather than a
> person or a stack: the identity outlives a change of technology, while "I am
> looking for quiet legacy work" stays itself. Spelled with a `k` so that
> `grep kisel_` does not drown in vacancy text, which is full of the word
> *calm*.

## What this identity is

A search for **easy work**. Not part-time work — easy work: what matters is the
intensity rather than the number of hours in a contract. An undemanding
full-time role suits exactly as well as a moderately loaded part-time one;
reduced hours, a four-day week and a part-time contract are variants of the same
thing rather than a goal in themselves.

Interesting problems, growth and ambitious projects are not wanted here. What is
wanted is predictable, dull, well-documented routine that can be done calmly and
with active help from AI.

Hence all the settings that look strange from outside: `legacy`, `mainframe`,
`cobol`, `enterprise`, `bank`, `government` are **pluses**, while `greenfield`,
`fast-paced`, `startup`, `move fast` are minuses. An ordinary job search is
arranged the other way round.

## Who it is for

A senior developer in .NET/C# (and JS/TS) who wants calm, low-intensity remote
work. The stack and the level are properties of the search and live here; who
exactly is searching, where they live and what money they expect live in their
local identity, outside the repository.

The identity is tuned for a resident **outside the US and the EU**, in the
UTC+3…+5 band. That is not personal data but a parameter of the search: the
geography disqualifiers and the time-zone window are derived from it. For
another country, see `identity.py clone`.

**A trap for those it concerns**: in vacancies "Georgia" almost always means the
US state rather than the country in the Caucasus. The system tells the cases
apart by context (`ambiguous_place_names` in `kisel_criteria.yaml`), but it is
worth remembering during a manual check.

### Hard disqualifiers (0% chance, not "low priority")

All of them are implemented as gates in `score.py` rather than as a penalty in
points. A lesson bought with experience: a soft penalty drowns in the generic
words of boilerplate, and the vacancy surfaces in the shortlist regardless.

1. **Not remote work.** By default a vacancy must be *confirmed* as remote. The
   absence of any remote signal is a refusal, not "unknown, but let it through".
2. **A hard residency requirement in a country the person does not live in.**
   `US only`, `remote LATAM`, `Canada only`, **`EU Remote`** — all equally out
   of reach. The list is incomplete in principle; there are endlessly many
   countries.
3. **A requirement for a language the person does not speak** (the language list
   is in the local identity). German, French and the like are a refusal.
   Vacancies written entirely in something other than English or Russian are
   too — German job boards produce them in bulk.
4. **A role that is not about software development.** CFO, Product Manager,
   Sales, Customer Support, Recruiter, Webmaster… and also **DevOps, SRE,
   platform and infrastructure** — the person is an applied developer, not an
   operations engineer.
5. **A stack that is neither .NET/C# nor JS/TS.** A chance match on one
   secondary word is not enough. Java and Scala on their own are out (a Java web
   position will not take them), **but Java/Scala for data pipelines** (Spark,
   Databricks, ETL) is a wanted variant — there is real experience of it.

### Geography

Which markets are a "dream" for you and which are realistic depends on your
residency, your contacts and your existing experience with companies in a
particular country. The template does not decide that: the shared markets table
is `config/derivation/market_tiers.yaml`, while the choice of tiers and any
individual additions live in your local identity.

It matters not to confuse "the company is based in X" (neutral) with "residency
in X is required" (disqualification). That difference cost one debugging
iteration and holds true for any user.

### Money against calm

The specific amounts are personal and live in your local identity. But THE RATIO
ITSELF is part of this kind of search and so lives here: calm matters more than
money. Guaranteed dull work for less money beats stressful work for more —
otherwise this would be a different search, and a different template would be
the right one.

That is why `low_intensity_signal` in `kisel_criteria.yaml` weighs 20 with a
±20 range, twice `compensation_signal` (10, roughly +2..+10). A deliberate
decision rather than an oversight — not something to "fix".

## What "simple work" means for this skill set

Worked out from the CV, by the actual frequency of technologies across the last
8 roles (2018–2026). A skill set changes slowly, so it is recorded here rather
than recomputed on every run.

**Simple** (6–8 roles of 8 — literally daily work for 7+ years): C#, .NET /
.NET Core / .NET Framework, ASP.NET (MVC / Web API / Core), SQL Server, Angular
/ AngularJS.

**Confident, but not constant** (2–4 roles): Entity Framework (EF6 / EF Core),
TypeScript / JavaScript, React, Azure, Docker, microservices, CQRS, DDD, Event
Sourcing, HTML/CSS.

**Peripheral** (1–2 roles across a career — real but narrow experience):
Node.js, MongoDB, Cosmos DB, DynamoDB, Apache Spark, Databricks, Delta Lake,
Python, jQuery, SOAP, XSLT, PHP, GraphQL, DevExpress, Scala, Java, NgRx, Redux,
MobX.

**What the CV does NOT have**, contrary to the first version of the profile:
WebForms, VB.NET, Classic ASP. They remain a useful signal that "this vacancy is
about legacy", but they give **no personal stack bonus** — two different axes,
and confusing them is not allowed.

### Legacy is not the same as simple: a separate axis

Legacy maintenance in a bank and an R&D team at the same bank are different
things. A role can be stuffed with `enterprise` and `banking` words from the
company description and still be research work.

The red flags (the `role_complexity_signal` gate): in the title — Principal or
Staff Scientist, Research or Applied Scientist, ML Engineer, Founding Engineer,
anything with "Agentic"; in the description — build from scratch, greenfield, 0
to 1, own the entire architecture, cutting-edge, PhD required.

The real examples the rule came from: "Staff Software Engineer, Agentic
Platform" at the neobank tide, and "Principal Machine Learning Scientist" at
tripadvisor — both scored well on the banking context of the company.

## Which tools and sources it uses

The full list is in `kisel_sources.yaml`; the catalogue of what is available is
`docs/BUILDING_BLOCKS.md`.

| Tool | How it is used |
|---|---|
| All 5 remote boards (WWR, RemoteOK, Remotive, Jobicy, Himalayas) | Enabled. WWR is the best by signal-to-noise |
| Companies' ATS boards | Enabled; the company list in `kisel_ats_targets.yaml` is the **main lever on quality**, to be filled with mature enterprises |
| LinkedIn guest search | Enabled; it covers every market of interest at once |
| HN "Who is hiring" | Enabled with explicit words `.NET, C#, ASP.NET, legacy, SQL Server` |
| arbeitnow | Deliberately enabled despite about 6% useful yield |
| Manual entry (`ingest_manual.py`) | **Matters especially**: the public boards cover the combination "legacy + worldwide remote + a high rate" poorly |
| `company_intel.py` | Used: company age from Wikidata (10+ years is a plus) |
| `kb.py set-company-reputation` | Used: reputation from Glassdoor via web search; work-life balance matters more than the overall rating |
| `link_check.py` | Used: dead links (404/410) are not shown |

## Decision log

All dated and confirmed by the owner in conversation.

- **2026-07-30** — calm matters more than money: the weight of intensity is
  twice the weight of pay. The specific amounts are personal, in the local
  identity.
- **2026-07-30** — hard disqualifiers must be gates rather than penalties (after
  "CFO Controller" scored 60).
- **2026-07-30** — DevOps excluded: "it is not my kind of vacancy".
- **2026-07-30** — Java/Scala for data pipelines kept as a wanted variant.
- **2026-07-30** — remote positions only; the absence of a remote signal is a
  refusal.
- **2026-07-31** — "EU Remote" moved from the pluses into the disqualifiers: it
  is a requirement of EU residency rather than "a European company".
- **2026-07-31** — the classification thresholds were lowered: once the hard
  gates existed, the score should rank rather than reject.
- **2026-07-31** — the CV was given back its original name: it had been renamed
  to the prefix when moved into the personal folder, and the owner asked for
  that not to be done. The prefix rule does not extend to documents a person
  brought with them; the general rule is recorded in CLAUDE.md §5.
- **2026-08-04** — the identity was depersonalised: name, LinkedIn, CV,
  residency and pay expectations moved out of the shared repository. The reason:
  this folder describes a SEARCH, not a person.
- **2026-08-05** — geography stopped weighing in the score. On the owner's
  direct instruction: "what matters is not geography but the work itself". A
  non-target region (net exporters of development work) still takes a penalty.
- **2026-08-06** — the repository was translated into English. The report
  language now follows `preferences.language` in the local identity.
