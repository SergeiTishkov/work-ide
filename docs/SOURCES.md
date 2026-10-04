# Sources of vacancies

## Which sites answer a plain request

Fetchers read JSON APIs, RSS and HTML over plain HTTP. Measured 2026-08-04,
the same request to each:

| Site | Response | Conclusion |
|---|---|---|
| LinkedIn (guest search) | **200** | Fetched |
| Indeed | **403** | Not fetched |
| Glassdoor | **403** | Not fetched |

The full registry of every source checked, including the rejected ones with
reasons and response codes, is `config/sources.backlog.yaml`. It exists so that
the same boards are not checked again a month later.

## The UK, and why three of its four sources are contract boards

Added 2026-09-08 at the owner's request. The reason to want them is not volume
— LinkedIn already carries UK vacancies — but SHAPE. ContractorUK, JobServe and
Outside IR35 Jobs list **contracts**: a day rate, a duration and an IR35
determination. A contract declared outside IR35 is work somebody invoicing from
another country can take; a payrolled UK job generally is not.

| Source | What one card gives | Measured 2026-09-08 |
|---|---|---|
| **ContractorUK** | title, location, day rate, ~200-char summary, badges for Outside IR35 and Remote/Hybrid | 142 records over four queries; 121 with a rate, 52 badged Remote |
| **Reed** | title, company, location, salary, date | 98 from one keyword; **every one with a stated salary** |
| **JobServe** | title, agency, location ("Remote, UK"), rate, type, a real description | 20 a query; 14 naming the agency, all 20 with a description |
| **Outside IR35 Jobs** | title, company, location, day rate, working mode | 50 in one request, every one outside IR35 |

### The badge is worth more than the prose

ContractorUK and Outside IR35 Jobs both state the working arrangement as their
own field, and it goes straight into `workplace_type` — the same field the
arrangement gate reads. That is a board ticking a box, not a phrase in a
description that has to be matched with a regex and argued about.

### Reed's filters were tested before being trusted

This project spent weeks stamping every LinkedIn vacancy remote because of a
filter that did nothing (see the LinkedIn section above). So Reed's were
checked the same way, on the day they were added:

    /jobs/net-developer-jobs            25 results
    /jobs/remote-net-developer-jobs     25 results, 15 shared with the above
    /jobs/contract-net-developer-jobs   25 results, ZERO shared with the above

They genuinely filter, so the remote slug may set `workplace_type` — and a tag
records that Reed classified it rather than the employer stating it. The
contract slug is fetched too: that inventory is invisible to the plain search.

### Traps, each of which cost time

* **ContractorUK has two listing paths.** `/contract_jobs?q=` silently ignores
  the query and returns building trades; `/all_contract_jobs?q=` filters. And
  its pager is zero-based — a loop starting at 1 skips the best-matching page.
* **"c#" is unsearchable on ContractorUK**, however it is encoded, and so are
  "csharp" and "dotnet". C# work is reached through other words.
* **Reed writes `title=` before `data-qa=`.** A regex assuming the other order
  matches nothing and reports a markup change on markup that never changed.
* **Reed's metadata icons are longer than 200 characters.** A capture window
  sized for the text loses every salary on a board that states nearly all of
  them.
* **JobServe needs its form.** Three requests: GET the page, POST its hidden
  fields with `ctl00$`-prefixed names, GET `JobListing.aspx?shid=...&ovrpp=jl`.
  Without `&ovrpp=jl` the listing came back empty on one run in three.
* **Only `outsideir35jobs.com` resolves.** The `.co.uk` is not in DNS.

## A yardstick for pay: IT Jobs Watch

Not a source of vacancies — it publishes none. It publishes six-month rolling
medians per technology, and the report shows them beside the UK shortlist:

    .NET      £60,000/year permanent (-4.0%)   £525/day contract (+6.6%)
    ASP.NET   £55,000/year (-4.3%)             £475/day (-11.6%)
    Azure     £65,000/year (+8.3%)             £525/day (+1.9%)

That fills the middle of the three levels of trust in a salary (CLAUDE.md
section 5): a person reading "£55,000 - £60,000" cannot otherwise tell whether
it is generous or poor.

**Two things it must never do**, both easy and both wrong: it must not fill in
a vacancy's own salary — a market median is not what THIS employer pays — and
it must not touch the score, where every UK .NET vacancy would gain the same
points and the number would only get less honest. Both are asserted by tests.

The site is British, so the block is rendered only where UK vacancies appear.
No equivalent of this quality is known for the EU or Canada.

## Part-time and freelance work: which boards say how many hours

Surveyed 2026-09-13 for a search looking for side work. The question that
decides a source for such a search is not how many .NET vacancies it has — our
own gates check the stack either way — but whether it says **how many hours**.
Most boards never do, and several that advertise a part-time filter turned out
not to have one.

| Board | Engagement, as the board states it | Verdict |
|---|---|---|
| **Remote Rocketship** | `employmentType` on every record; `/jobs/<slug>/part-time/` returns only part-time | **Connected** (`fetch_remoterocketship.py`) |
| **Himalayas, search endpoint** | `employment_type=Part Time` / `Contractor` filters for real | **Connected** as a search mode of `fetch_himalayas.py` |
| **LinkedIn vacancy page** | "Employment type: Part-time" in the criteria list | **Read** by the page reader the fetcher already used — and from the guest fragment `jobs-guest/jobs/api/jobPosting/<id>` when the page lacks it: the full `/jobs/view/` page on ae., nl. and il.linkedin.com carries no criteria list at all |
| **Remotive, Jobicy** | `job_type` / `jobType` fields | **Kept** as `employment_types` instead of tags |
| web3.career | part-time pages whose JobPostings all say "Full-time" | Rejected: a filter that does not filter |
| cryptocurrencyjobs.co | one clear sentence per posting — 70 of 75 full-time | Rejected for part-time |
| YC jobs | a `type` field, 29 of 30 full-time | Rejected for part-time |
| HN "Freelancer? Seeking freelancer?" | 23 comments, all SEEKING WORK | Rejected: people offering, not buying |
| CryptoJobsList | Cloudflare challenge | Rejected: no plain-HTTP answer |

The full list with measurements is in `config/sources.backlog.yaml`.

### Remote Rocketship's traps

* **Twenty per listing, and no paging.** `?page=2` repeats 19 of the first 20.
  Breadth comes from more slugs, never from depth.
* **Some slugs lie.** `/jobs/c-sharp/part-time/` claims 2689 results and lists
  pharmacists and adjunct faculty: the slug falls back to everything
  part-time. `/jobs/net/contract/` is real — 115 results, nearly all .NET. Read
  a slug's first page before adding it.
* **An unknown slug is a 404**, reported as a configuration mistake rather than
  as an empty market.
* **Salary periods the scoring does not know.** "$80 per day" read as it is
  would be eighty dollars an hour; the fetcher converts days and weeks to hours
  and years before the amount reaches `salary_raw`.
* **The record's link is Remote Rocketship's page**, where schema.org JobPosting
  holds the full text for the description reader; the employer's own posting
  goes into `company_url`, which the report shows as the place to apply.

### Talent networks are a manual channel

Toptal, A.Team, Braintrust, Arc, Lemon.io, Gun.io, Turing and Contra carry much
of the well-paid part-time contract work, and none publishes openings to an
anonymous request: you apply once and are matched. Braintrust's job pages are
rendered in the browser with nothing in the HTML. Worth a person's hour, once;
not a fetcher. A.Team's openings do reach Remotive, which is connected.

## LinkedIn in particular

An earlier version of this document asserted that LinkedIn was unreachable. That
was true of the main site and of the official API (closed behind a partner
programme since 2015, and it does not serve job search at all), but nobody had
checked the guest endpoint
`jobs-guest/jobs/api/seeMoreJobPostings/search`. It answers 200, returns ten
cards per page and supports pagination. What the fetcher depends on, the live
contract that checks it, and the history of changes are in
[sources/linkedin.md](sources/linkedin.md); the contract/test/doctor scheme
for every source is in [sources/README.md](sources/README.md).

Geographically it is the project's main source: one fetcher covers Israel, the
UAE, Saudi Arabia, Singapore, Switzerland, Germany and the Netherlands — markets
whose own boards (Bayt, GulfTalent, Drushim, NodeFlair, Glints) answer 403/404,
so there is simply no alternative.

### What its guest endpoint does NOT give you

Measured 2026-08-11, after the owner opened the top three vacancies in his own
shortlist and found them badged Hybrid, On-site and On-site-and-closed.

**The `f_WT` workplace-type filter does nothing.** The query carried `f_WT=2`
("Remote") and the fetcher recorded `remote: True` on that basis. The same job
id comes back under `f_WT=1` (on-site), `f_WT=2` (remote) and `f_WT=3`
(hybrid), and the result sets for remote and on-site were identical. It was not
a weak signal — it was a fabrication, and it was clearing the remote gate for
100% of the LinkedIn vacancies in the base.

**The workplace-type badge is not readable at all.** Checked three ways: absent
from the search results, from the guest `jobPosting` fragment, and from the
page HTML. It renders only for a logged-in session, so a person who reads the
badge themselves enters it by hand (`workplace_type` on the record).

**What the vacancy page DOES give**, all three in the same request that fetches
the description, and all three previously thrown away:

| Field | Where | Note |
|---|---|---|
| `jobLocationType` | schema.org JSON-LD | `TELECOMMUTE` where the employer declares remote, absent otherwise. Absence means silence, NOT onsite — 27 of 28 head vacancies had nothing here |
| `baseSalary` | schema.org JSON-LD | A salary stated in the vacancy is the highest of the three levels of trust; every LinkedIn record was storing `None` |
| "no longer accepting applications" | page HTML | Present for a closed posting, absent for open ones. Of 260 vacancies in view, **36 were already closed** |

The price is the project's only HTML parser that depends on somebody else's
markup. Hence two obligations: the parser returns **zero and an explicit error**
when the markup changes (pinned by a test against a snapshot), and the cards are
enriched with the description from the vacancy page, because without the text
the stack gate rejects three quarters of what was found (measured: 447 of 621).

## Countries: importers and exporters of development work

`config/derivation/market_tiers.yaml` splits markets by the direction the work
flows. Importers (the US, Switzerland, Israel, the UAE, Singapore…) hire from
outside — the rates are higher there and remote contractors are treated better.
Exporters (India, Pakistan, the Philippines…) supply engineers themselves, and
local vacancies there compete downwards on price.

This describes the direction of flow rather than judging people or countries.
Which tiers to use belongs to the identity (`profile.target_markets`); the table
itself is shared.

## Automatic sources (`tools/fetch_*.py`)

| Source | Kind | Vacancies per run | Why it is enabled |
|---|---|---|---|
| [We Work Remotely](https://weworkremotely.com/) — **5 category RSS feeds** | public RSS | **242** | The project's best source. Remote vacancies only, in English, with a `region` field ("Anywhere in the World" / "USA Only") — the most dependable structured geography signal. **Important**: we use all five feeds (programming / full-stack / back-end / front-end / devops-sysadmin). Only `remote-programming-jobs` used to be used, which gave 25 vacancies instead of 242 (see the identity's `insights.md`, 2026-07-30). |
| [RemoteOK](https://remoteok.com/api) | public JSON API | ~100 | Remote only. **Note**: the feed periodically returns irrelevant content that is not a vacancy, so the parser validates required fields strictly. It returns only the latest ~100 vacancies; there is no depth in time. |
| [Jobicy](https://jobicy.com/api/v2/remote-jobs) | public JSON API | ~100 | Remote only. Filtered by `industry=dev`. Gives structured salary (`salaryMin/Max/Currency/Period`) and geography (`jobGeo`). The `tag=` parameter returns nothing in practice — do not use it. |
| [Remotive](https://remotive.com/api/remote-jobs) | public JSON API | ~35 | Remote only. The `candidate_required_location` field is an explicit structured geography restriction. The `limit`, `search` and `category` parameters are ignored in practice. |
| [Himalayas](https://himalayas.app/jobs/api) | public JSON API | ~20 | Remote only. `locationRestrictions` is a list of permitted countries (empty = worldwide), the most explicit geography signal of any source. Returns ~20 vacancies regardless of `limit`. |
| [Hacker News "Who is hiring?"](https://hn.algolia.com/) | public Algolia HN Search API | ~22 | Legacy and enterprise vacancies often land here rather than on the ordinary job boards. The format is free-form and noisy — but sometimes this is where the quiet, uncontested vacancies are. |
| [Arbeitnow](https://www.arbeitnow.com/api/job-board-api) | public JSON API | ~175 | **NOT a primary source, contrary to the initial assumption.** Measured 2026-07-30: in practice this is predominantly the German labour market — the overwhelming majority are German-language ("m/w/d", "Deutschkenntnisse") and are cut immediately by the language filter, and remote is a minority among them. It gave 68% of the whole base at about 6% useful yield. Left enabled for the occasional English-language European remote vacancy. |
| [LinkedIn guest search](https://www.linkedin.com/jobs/) | undocumented HTML page, 200 to an ordinary GET | varies by query | See the section above. The one source that covers every market of interest at once. |

### We Work Remotely: a check on good faith (2026-07-30)

The user noticed that WWR charges money and reasonably wondered whether it was
bait — posting excellent vacancies in order to sell subscriptions. Checked:

- **The site is not a scam.** Created by 37signals (Basecamp, Ruby on Rails) in
  2013, running for more than ten years. The employer pays to post (~$299),
  which is the business model and also the filter against rubbish postings.
- **A candidate does not have to pay.** A basic account is free: browsing,
  applying, a CV, saved vacancies. The paid Pro tier ($14.95/month) only adds
  extras (an AI copilot, extended alerts).
- **But the Pro subscription has a dark pattern.** The price "$2.95 for the
  first month" is presented so as to look monthly, while in fact it is an annual
  contract billed monthly. According to Trustpilot (March 2026), 34% of reviews
  are one star, and the dominant theme of the complaints is billing and the
  inability to cancel; there are reports of charges after an account was
  deleted. **Conclusion: do not take out the Pro subscription.**
- **The vacancies are real.** Our 242 records include direct links to corporate
  sites and real ATS instances: `career.proxify.io`, `lemon.io`,
  `redditinc.com`, `careers.tether.io`, `tether.recruitee.com`,
  `wevote.applytojob.com`, `mindrift.ai`. These are not invented postings.
- **An important wrinkle: WWR keeps the application funnel to itself.** In 71%
  of vacancies the "To apply:" field leads back to weworkremotely.com rather
  than to the employer. So the fetcher extracts the company's official site from
  the structured block of the description ("Headquarters: … / URL: …") into the
  `company_url` field, and the report shows it on its own line — so that the
  same vacancy can be found on the company's careers page and applied to
  directly, without opening a WWR account at all. Coverage: about 24% of
  vacancies (58 of 242 in the last run).

### The `remote_only` flag

Sources that publish **only** remote vacancies (WWR, RemoteOK, Remotive, Jobicy,
Himalayas) are marked in `config/sources.catalog.yaml` as `remote_only: true`.
That matters for scoring: the "not confirmed as remote" gate does not apply to
them. A real bug found (2026-07-30): vacancies from such boards were being
rejected purely because the English word "remote" did not appear in the
description text — a pure false negative that cut dozens of live candidates.

## The manual source (`tools/ingest_manual.py`)

What the fetchers do not read automatically:

- **Indeed, Dice, ClearanceJobs, Glassdoor** — they answer 403 to a plain
  request; a person or the agent looks through them with web search.
- **Particular companies' careers pages** — each has its own format, and writing
  a parser per company is pointless; the agent checks, one at a time, the
  companies that have already shown good signals (legacy, enterprise, EOR) in
  the identity's knowledge base.
- **Companies' ATS boards** — the exception to the rule above: Greenhouse,
  Lever, Ashby, Recruitee, Workable and SmartRecruiters have official public
  JSON APIs, and they are read automatically (the `ats` source).
