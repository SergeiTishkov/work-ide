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
- TO DO - Measure the site (data behind the list, paging, the countries field) and write the plan here as the next items
