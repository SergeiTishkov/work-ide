# A catalogue of building blocks: sources and tools

What an identity is assembled from. Read when filling in the questionnaire and
when revisiting the set of sources.

The technical details of each source are in `config/sources.catalog.yaml`. Which
ones are enabled, and with what parameters, is in
`<prefix>_sources.yaml`.

## Sources of vacancies

All measurements are from one run, 2026-07-30/31. The numbers depend on the
profile: "useful yield" below was counted for a .NET developer looking for
remote work.

### Remote-only boards

Marked `remote_only: true` in the catalogue. The flag matters for scoring: being
published on such a board is itself confirmation that the work is remote, and
without it the "not confirmed as remote" gate would produce mass false
negatives.

| Source | Volume | Strengths | Weaknesses |
|---|---|---|---|
| **weworkremotely** | ~242 | The best signal-to-noise ratio. The structured `region` field is the most dependable geography signal. English-language | It keeps the application funnel to itself: in 71% of vacancies "To apply" leads back to WWR. The fetcher extracts the company site from the "Headquarters/URL" block |
| **remoteok** | ~100 | A large flow, remote only | Noisy: content turns up that is not a vacancy at all. Returns only the latest ~100; no depth in time |
| **jobicy** | ~100 | Structured salary and geography | The `industry=dev` filter is mandatory, or there is a lot of non-IT |
| **remotive** | ~35 | An explicit `candidate_required_location` field | Not many. The `limit` and `search` parameters are ignored in practice |
| **himalayas** | ~20 | `locationRestrictions` — the most explicit geography signal of any source | Very few; returns ~20 regardless of `limit` |

### Straight from employers

| Source | Volume | Comment |
|---|---|---|
| **ats** | depends on the list | The official public APIs of hiring systems (Greenhouse, Lever, Ashby, Recruitee, Workable, SmartRecruiters) — the ones the vacancy widgets on company sites run off. No intermediary, no third party's application funnel. Measured: Stripe 546, Cloudflare 284, GitLab 185, Notion 111 |

**The main lever on quality here is the list of companies**, not the source
itself. `<prefix>_ats_targets.yaml` should hold employers relevant to your
profile. A starting list of technology companies gave 1526 vacancies and zero
candidates for a .NET profile: the mechanism worked, the list was wrong.

Where to find candidates: companies with high legacy/enterprise signals in
`data/<prefix>/knowledge/<prefix>_companies.json`, or by searching the industry.
A board token can be checked with one request:
`curl https://boards-api.greenhouse.io/v1/boards/<token>/jobs`

### Niche and country-specific

| Source | Volume | Comment |
|---|---|---|
| **linkedin** | depends on the query | The guest job-search endpoint: 200 to an ordinary GET, 30 cards per page, filterable by country. The one source that covers every market of interest at once — and the only HTML parser in the project, so it returns zero and an explicit error if the markup changes |
| **hn_whoishiring** | ~22 | The monthly Hacker News thread. Legacy and enterprise vacancies often land here rather than on job boards, and quiet, uncontested positions occasionally turn up. The format is free-form, and company and location are parsed heuristically. The keywords are a parameter, and each costs one HTTP request |
| **arbeitnow** | ~175 | **In practice the German market.** It gave 68% of the base at about 6% useful yield: most vacancies are German-language and are cut by the language filter. Disabled by default in the template; enable it if you read German |
| **manual** | as much as you enter | Not automatic. The agent's finds from sites that cannot be read programmatically (Indeed, Glassdoor — 403 behind anti-bot protection) are entered through `tools/ingest_manual.py`. For narrow profiles this is often the most valuable channel: public boards cover rare combinations of requirements poorly |

## The tools

| Tool | What it does | When it is needed |
|---|---|---|
| `pipeline.py` | The full cycle: collect → normalize → score → deduplicate → check links → report | The main command of every run |
| `doctor.py` | Self-check: identity, dependencies, configuration, source reachability | After cloning, and when something looks odd |
| `identity.py` | List, validate, resolve an identity; clone one | Onboarding and diagnosis |
| `templates.py` | List templates, clone one, check for and apply updates | Onboarding, and when the template moves on |
| `settings.py` | Where a value came from; which keys more than one layer sets | When "why is this number what it is" comes up |
| `kb.py` | The knowledge base: statuses, notes, pay and reputation estimates | Working with finds by hand |
| `reputation.py` | Which shortlist companies are still unchecked; recording "we looked and found nothing" | The reputation step of RUNBOOK |
| `ingest_manual.py` | Enter finds obtained by web search | After the manual stage of RUNBOOK |
| `company_intel.py` | Company age and size from Wikidata | Automatically inside the pipeline, for shortlist companies |
| `link_check.py` | Checking that links are alive | Automatically inside the pipeline |
| `report.py` | Rebuild the report without collecting again | After editing the criteria |
| `textclean.py` | Strip email addresses and links out of text | Inside scoring; also useful by hand when debugging a match |
| `migrate_to_identity.py` | Move the old layout into an identity | Once, historical |

## Manual enrichment of the base

Not automated on principle — the sources sit behind anti-bot protection the
project will not circumvent (see the constitution). The agent gathers it by
ordinary web search, as a person would.

```bash
# employer reputation (Glassdoor and the like)
python tools/kb.py set-company-reputation --identity <p> --company "Acme" \
    --rating 4.2 --wlb 4.4 --source "Glassdoor" --retrieval web_search --reviews 257

# a pay range, when the vacancy states none
python tools/kb.py set-salary-estimate --identity <p> --id <vacancy-id> \
    --low 60000 --high 80000 --period year --source "Glassdoor"

# the status after applying
python tools/kb.py set-status --identity <p> --id <vacancy-id> --status applied --notes "..."
```

On `--retrieval`: `web_search` means "the numbers came from search results, the
primary source was not opened". That is second-hand data, and the report says so
honestly. Before actually applying, it is worth opening the primary source with
your own eyes.

The system compiles the list of what remains to check itself:

```bash
python tools/reputation.py worklist --identity <p>
python tools/reputation.py mark-insufficient --identity <p> --company "Acme"
```

## Choosing a set

More sources is not always better. A source with a low yield for your profile
litters the base on every run with rubbish that then has to be filtered out, and
every new filter risks cutting too much.

A sensible sequence: enable all the `remote_only` boards, add `ats` and fill its
company list to suit you, and keep `manual` on always. Connect narrow sources
deliberately, measuring their yield after a couple of runs (`python tools/kb.py
stats` and the "Source health" section of the report).
