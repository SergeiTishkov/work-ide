# LinkedIn (guest search)

`tools/fetch_linkedin.py` reads the search LinkedIn serves to a visitor who is
not logged in: `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search`.
It answers a plain request with HTML cards, no login needed. If it ever stops
answering an anonymous request, the contract reports the source as `blocked`.

## What the fetcher depends on

Each line is an `expect()` in `contract()` at the bottom of the fetcher.

- **The search answers with cards** for a common query.
- **Cards parse** into title, company and link (at least 80% of a page).
- **Cards carry a posting date** (`<time datetime>`, at least 80%).
- **The posted-within filter is honoured**: with `f_TPR=r604800` at most one
  card is older than the window plus two days.
- **The next page starts where this one ended**: `start` advances by the number
  of cards received (ten), and the next page brings mostly new cards.
- **A query is served its first 100 results**: `start=90` still has cards. The
  contract also notes what `start=100` returns, so the day the ceiling lifts
  shows up in the log.
- **A region query stays inside its country**: the first entry of
  `SPLIT_REGIONS` returns cards located in that country (70% or more).
- **A vacancy page carries its description** (200+ characters) **and a
  schema.org `JobPosting`**. The employment type is noted, not required:
  several country subdomains render no criteria list, and the reader falls
  back to the guest fragment `jobs-guest/jobs/api/jobPosting/<id>`.

## The knobs

Measured 2026-10-02/03.

| Parameter | Effect |
|---|---|
| `keywords`, `location` | Honoured. A location is a free-text name that LinkedIn resolves; a region is written as "Region, Country". "Washington, United States" resolves to D.C., so Seattle is used for the state |
| `start` | Honoured. Ten cards a page; the next page is `start + cards received` |
| `f_TPR=r<seconds>` | Honoured. `r604800` is a week, `r86400` a day |
| `f_WT` (remote), `f_JT` (job type), `sortBy`, `f_E` (experience) | **Ignored** by the guest search: the same cards come back with and without them |
| `geoId`, `position`, `pageNum`, `trk` | Do not lift the ceiling below |

**The ceiling.** An anonymous request is served at most 100 results per query:
`start=100` comes back empty however long the list is. The page marks such a
request `data-is-bot="true"`. LinkedIn's own counts for a week of postings,
against the 100 served:

| Query | LinkedIn says | Served |
|---|---|---|
| C# developer, United Kingdom | 736 | 100 |
| C# developer, Germany | 540 | 100 |
| .NET developer, United States | 4 000+ | 100 (once deeper, likely an IP warmed by a person's own browsing; not reproducible) |

A browser session gets further. A 24-hour window does not help: big pairs
reach 100 within a day.

**Splitting at the ceiling.** A query that reaches 100 is asked again in
narrower forms, each with a ceiling of its own:

- `"remote <keyword>"` in the same country: the word is matched in the text,
  so it brings country-level, remote-shaped postings (38 new ones on the
  first probe across 12 countries);
- the regions in `SPLIT_REGIONS` (US states, UK regions, German Länder,
  Canadian provinces, Dutch provinces, Australian states). Mostly local, on-site
  work, but the full list: "C# developer, United Kingdom" went from 100 to 322
  with six regions.

A region query that also reaches 100 is not split further. Vacancies found
through a region are tagged with the country (`market:<country>`), because
segments and the hiring country read that tag.

**Empty pages.** The search sometimes returns an empty page in the middle of a
list that goes on after it (10 holes in 100 pages of one deep walk). One empty
page is stepped over; two in a row end the list.

**429 and dropped connections.** One retry after 30 seconds, counted in the
progress line. The pause between pages is 1.5 seconds; the description reader
(`tools/enrich_descriptions.py`) keeps the same pause between vacancy pages.

## The probe

`CONTRACT_PROBE = (".NET developer", "United Kingdom")`: a query that always
has well over 100 postings a week, so paging, the ceiling and the date filter
are all exercised; and the UK has regions to test the split with.

## How to measure

Use one identity's real words and countries, run as an independent process,
with progress in the log:

- unique vacancy ids, and how many are new to that identity's base;
- posting age (within a day, a week, older);
- requests and seconds;
- pages read per query, and how many queries hit the ceiling;
- where the new vacancies land after scoring, and how many wait for a
  description.

## History

**2026-10-03: read to the end of every list.** The fetcher stepped by an
assumed 25 cards and stopped when fewer came. LinkedIn serves ten, so every
(word × country) pair ended after its first page. Fixes:

- paging by cards received, up to `MAX_PAGES = 100`;
- a week's window (`posted_within_days: 7`);
- holes stepped over;
- the ceiling detected and split;
- progress every 15 seconds;
- one retry on 429 and on a dropped connection.

The fetcher no longer reads vacancy pages by title before scoring
(`enrich_limit: 0` in the templates). `enrich_descriptions.py` reads them after
scoring, by verdict, and its budgets went from 120/300 to 300/1000.

The POC used kisel's 6 words × 28 countries:

| | before | every page, last week |
|---|---|---|
| unique vacancies | 1 007 | 4 946 |
| new to the base | 168 | 4 741 |
| posted within a day | 148 | 2 168 |
| new, waiting for a description | 57 | 1 985 |
| requests / time | ~170 / 6 min | 1 389 / 53 min |

The POC had no split yet: 92 of the 168 pairs stopped at the ceiling of 10
pages. The split adds their remote and regional queries, so a full run takes
longer than 53 minutes. Its numbers belong in the next entry.

**2026-10-03: the first full runs.** With the split:

| | kisel | pjoice |
|---|---|---|
| pairs (word x country) | 168 | 140 |
| queries, at the ceiling / narrower | 446, 92 / 278 | 378, 83 / 238 |
| pages / cards | 3 401 / 33 122 | 2 937 / 28 716 |
| vacancies / new to the base | 10 045 / 9 841 | 9 598 / 9 483 |
| 429 (each retried once) | 0 | 8 |
| LinkedIn time / whole run | 2:24 / 3:40 | 2:08 / 3:18 |

Where kisel's 9 841 new ones landed after the run: 8 797 rejected, 982 in
"remote not confirmed", 9 hot leads, 5 worth a look. Of the rejected, 4 305
have a developer's title and are waiting for their page to name the stack
(`description_wanted`). The queue reads 1 000 a run, so a one-off pass read
the rest. The other rejected ones are refused for their title or language
(not a .NET/JS role, German, intern, ML, data, or platform engineering).
