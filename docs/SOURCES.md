# Sources of vacancies

## The selection principle

We take anything served to an **ordinary GET request** carrying an honest
User-Agent: JSON API, RSS, HTML. We take nothing that requires circumventing
active protection — faking a browser fingerprint, solving a CAPTCHA, running a
headless browser to fool a detector.

The boundary runs along what the server actually answers rather than along the
format. Measured 2026-08-04, the same request with the same User-Agent:

| Site | Response | Conclusion |
|---|---|---|
| LinkedIn (guest search) | **200** | Open to an anonymous request as designed — we take it |
| Indeed | **403** | Closed — we do not go |
| Glassdoor | **403** | Closed — we do not go |

The full registry of every source checked, including the rejected ones with
reasons and response codes, is `config/sources.backlog.yaml`. It exists so that
the same boards are not checked again a month later.

## LinkedIn in particular

An earlier version of this document asserted that LinkedIn was unreachable. That
was true of the main site and of the official API (closed behind a partner
programme since 2015, and it does not serve job search at all), but nobody had
checked the guest endpoint
`jobs-guest/jobs/api/seeMoreJobPostings/search`. It answers 200, returns 30
cards per page and supports pagination.

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
page HTML. It renders only for a logged-in session. Going there would mean
authenticating in order to scrape, which is over the line in CLAUDE.md §5, so
the project does not — and a person who reads the badge themselves enters it by
hand instead (`workplace_type` on the record).

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

Anything that requires authorisation, a paid subscription or interactive
circumvention of anti-bot protection is left alone by the automation:

- **Indeed, Dice, ClearanceJobs, Glassdoor** — reachable for a person or an
  agent to look at through ordinary web search, but not for programmatic
  scraping in this project: they answer 403 to a plain request.
- **Particular companies' careers pages** — each has its own format, and writing
  a parser per company is pointless; the agent checks, one at a time, the
  companies that have already shown good signals (legacy, enterprise, EOR) in
  the identity's knowledge base.
- **Companies' ATS boards** — the exception to the rule above: Greenhouse,
  Lever, Ashby, Recruitee, Workable and SmartRecruiters have official public
  JSON APIs, and they are read automatically (the `ats` source). There is no
  fence there.

## What we explicitly do not do

- We do not circumvent anti-bot protection or CAPTCHAs for any source.
- We do not log in under an account in order to scrape.
- We do not exceed a reasonable request rate against public APIs (the pipeline
  runs on demand, not from a cron entry every minute).
- We store no credentials or tokens in the repository — none of the current
  sources require any.
