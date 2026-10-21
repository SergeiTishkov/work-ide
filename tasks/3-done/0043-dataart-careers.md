# 0043 DataArt's own vacancies

Source: the owner, 2026-10-20 ("add it, let it be; not urgent")

## Business
DataArt is an Eastern European outsourcing company that hires remotely from
a list of countries named in each vacancy. Its site filtered to
"Remote.Georgia" listed 26 of 117 vacancies (AI, Backend, Data & Analytics,
DevOps & SRE and others). The owner's estimate of pay: $4-5k a month for a
developer, $5-7k for a team lead, below the top of the shortlist, but the
company is reasonable and every vacancy states where it hires from.

## Implementation
A fetcher for `https://www.dataart.team/en/vacancies?locations=5770`, if
the site serves its list as data. Nothing measured yet; the entry stays in
`config/sources.backlog.yaml` with what is known.

## Items
- DONE - Measured 2026-10-21: a JSON API under /dataart-team/api, no key, no Cloudflare. filter-fields-page gives the country ids, filter-content-page?countries=<id>&pageSize=200 the list (banner cards mixed in, contentType 1), /vacancy/<slug> the full text. No salary, no posting date. 117 vacancies, 29 open to Georgia, none .NET
- DONE - `tools/fetch_dataart.py` with tests; in the catalogue and the pipeline; off in the SHARP template (the country is the residency); on in SHARP's own sources file with countries [Georgia]
