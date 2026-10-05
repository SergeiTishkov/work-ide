# SHARP — senior .NET/C# remote engineering

> **SHARP** is a name, not an abbreviation. The longer description is in the
> folder name: senior dotnet remote engineering. The short name and the
> description need not match (`docs/IDENTITIES.md`, requirements for a prefix).

## What this identity is

A search for senior .NET/C# (and JS/TS) engineering roles, remote, for a
person who lives outside the US and the EU.

### Priorities, in order

1. **The employer can hire the person remotely, and the person fits the role.**
   Both halves are needed: a remote role closed to the person's country is
   out of reach, and so is a reachable role in another profession or stack.
   In the score: the reachability bonus (`residency_eligibility.points`, +30
   when the employer is seen to engage people abroad), the location gates, the
   stack fit and the role gates.
2. **Pay.** Graded by the hourly equivalent of the stated amount
   (`compensation_signal.hourly_equivalent_tiers`, from -10 to +34). Pay
   outranks how interesting or how new the technology is.
3. **Technology** decides only between otherwise equal vacancies. Legacy or
   new, enterprise or startup, calm or intense: none of it is a plus or a
   minus in the score.

Set by the owner on 2026-10-05.

## Who it is for

A senior developer in .NET/C# (and JS/TS). The stack and the level are
properties of the search and live here; who exactly is searching, where they
live and what money they expect live in their local identity, outside the
repository.

The identity is tuned for a resident **outside the US and the EU**, in the
UTC+3…+5 band. That is not personal data but a parameter of the search: the
geography disqualifiers and the time-zone window are derived from it. For
another country, see `identity.py clone`.

**A trap for those it concerns**: in vacancies "Georgia" almost always means the
US state rather than the country in the Caucasus. The system tells the cases
apart by context (`ambiguous_place_names` in `sharp_criteria.yaml`), but it is
worth remembering during a manual check.

### Hard disqualifiers (0% chance, not "low priority")

All of them are implemented as gates in `score.py` rather than as a penalty in
points. A lesson bought with experience: a soft penalty drowns in the generic
words of boilerplate, and the vacancy surfaces in the shortlist regardless.

1. **Not remote work.** A vacancy nobody called remote goes to its own section
   to be checked by hand; hybrid and office work is a refusal.
2. **A hard residency requirement in a country the person does not live in.**
   `US only`, `remote LATAM`, `Canada only`, **`EU Remote`**, a US or Canadian
   retirement plan among the benefits — all equally out of reach. The list is
   incomplete in principle; there are endlessly many countries.
3. **A requirement for a language the person does not speak** (the language list
   is in the local identity). German, French and the like are a refusal.
   Vacancies written entirely in something other than English or Russian are
   too — German job boards produce them in bulk.
4. **A role that is not about software development.** CFO, Product Manager,
   Sales, Customer Support, Recruiter, Webmaster… and also **DevOps, SRE,
   platform and infrastructure** — the person is an applied developer, not an
   operations engineer. Scientist, ML and data-science roles are another
   profession too (`role_complexity_signal`).
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

## The skill set

Worked out from the CV, by the actual frequency of technologies across the last
8 roles (2018–2026). A skill set changes slowly, so it is recorded here rather
than recomputed on every run.

**Core** (6–8 roles of 8 — daily work for 7+ years): C#, .NET / .NET Core /
.NET Framework, ASP.NET (MVC / Web API / Core), SQL Server, Angular /
AngularJS.

**Confident, but not constant** (2–4 roles): Entity Framework (EF6 / EF Core),
TypeScript / JavaScript, React, Azure, Docker, microservices, CQRS, DDD, Event
Sourcing, HTML/CSS.

**Peripheral** (1–2 roles across a career — real but narrow experience):
Node.js, MongoDB, Cosmos DB, DynamoDB, Apache Spark, Databricks, Delta Lake,
Python, jQuery, SOAP, XSLT, PHP, GraphQL, DevExpress, Scala, Java, NgRx, Redux,
MobX.

**What the CV does NOT have**, contrary to the first version of the profile:
WebForms, VB.NET, Classic ASP. They give **no personal stack bonus**.

## Which tools and sources it uses

The full list is in `sharp_sources.yaml`; the catalogue of what is available is
`docs/BUILDING_BLOCKS.md`.

| Tool | How it is used |
|---|---|
| All 5 remote boards (WWR, RemoteOK, Remotive, Jobicy, Himalayas) | Enabled. WWR is the best by signal-to-noise |
| Companies' ATS boards | Enabled; the company list in `sharp_ats_targets.yaml` is the **main lever on quality** |
| LinkedIn guest search | Enabled; it covers every market of interest at once |
| HN "Who is hiring" | Enabled with explicit words `.NET, C#, ASP.NET, SQL Server` |
| arbeitnow | Deliberately enabled despite about 6% useful yield |
| Manual entry (`ingest_manual.py`) | **Matters especially**: the public boards cover the combination "worldwide remote + a high rate" poorly |
| `company_intel.py` | Used: company age from Wikidata |
| `kb.py set-company-reputation` | Used: reputation from Glassdoor via web search |
| `link_check.py` | Used: dead links (404/410) are not shown |

## Decision log

All dated and confirmed by the owner in conversation.

- **2026-07-30** — hard disqualifiers must be gates rather than penalties (after
  "CFO Controller" scored 60).
- **2026-07-30** — DevOps excluded: "it is not my kind of vacancy".
- **2026-07-30** — Java/Scala for data pipelines kept as a wanted variant.
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
- **2026-10-05** — reachability from abroad weighs in the score (+30), and a
  board's "<place> only" is a refusal (V20).
- **2026-10-05** — the identity is renamed SHARP and its priorities are set as
  above: can be hired remotely and fits, then pay, then technology. Intensity
  and legacy no longer weigh in the score; pay is graded (V21).
