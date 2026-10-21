# 0047 Where remote .NET contract work is posted

Source: the agent, 2026-08 (commit 32d1a98, "the next step", never taken)

## Business
Of 754 vacancies with .NET in the title, three were on worldwide-remote
boards; the rest were national LinkedIn jobs. Worldwide remote contracting
is mostly a JavaScript market, and .NET is hired locally. Where remote .NET
contract work is posted is Eastern European B2B boards and German and Dutch
freelance platforms; neither was surveyed.

## Implementation
Surveyed 2026-10-21 with live requests. "Open on paper": no Polish or
German asked, no residence in Poland, Germany or the EU asked; a posting
silent on location counts as open, though on a Polish board many silent
ones still expect a Polish sole-trader contract.

| Board | Plain request | Remote .NET contract postings | Open on paper |
|---|---|---|---|
| justjoin.it | 200, JSON API | 118 remote B2B | all read: 66 Polish, 15 PL/EU residence, 40 silent, 4 anywhere: about 45 |
| freelancermap.de | 200, JSON in the page | 96 fully remote contracting | 22 read: 9 German, 3 DACH, about 9 English with no location rule: about 40% |
| djinni.co | 200, JobPosting on the page | 47 remote .NET; 4 with country=GEO; 7 worldwide | structured countries: 16 Ukraine, 19 Europe, 7 open, 4 Georgia: 11 sure, up to 30 |
| nofluffjobs.com | 200, POST JSON API | 54 remote B2B | all read: 38 Polish, 7 residence: about 12 |
| jobs.dou.ua | 200, RSS and HTML | 71 remote .NET | 20 read, nearly all assume Ukraine: 5-8 |
| freelance.de | 200 HTML, full search needs a session | 62 C# | company hidden without a paid account; mostly freelancermap's postings |
| dev.bg | 200 HTML | 16 fully remote | Bulgarian employment: about 2 |
| GULP | 200, POST API | 8-15 C#/.NET of 846 | DACH on-site: about 0 |
| bulldogjob.pl | 200, Next.js data | 5 remote B2B | all Polish: 0 |

403 or no listing without a browser: theprotocol.it, Malt, Upwork,
ejobs.ro (403); twago (404), SOLCOM (503); Hays.de and freelance.nl render
in the browser. Local only: cv.ee (2), jobs.ge and hr.ge. Freelancer.com:
37 low-budget gigs, mostly unrelated.

justjoin.it and nofluffjobs were rejected on 2026-08-04 (404, 400/405);
both answer now, through other endpoints.

Plan: fetchers for justjoin.it, freelancermap.de and djinni.co, in that
order of expected yield, each with the trap the survey found:
- justjoin.it: `categories=net&remoteWorkOptions=remote&employmentTypes=b2b`,
  `itemsCount`/`from` paging (`workplaceType` and `perPage` are ignored; a
  keyword search returns thousands unrelated); the detail's `languages`
  names Polish when it is required.
- freelancermap.de: the ProjectSearch JSON in the page; paging does not
  work, so several queries (.net, c#, asp.net, blazor) and a daily run; a
  stack check, since `.net` matches unrelated roles.
- djinni.co: three searches (plain, country=GEO, region=worldwide); stop
  paging when no .NET title comes, since later pages fill with unrelated
  jobs; `applicantLocationRequirements` is the geography.

Live, 2026-10-22, scored for sharp:
- justjoinit: 118 records; 5 hot_lead, 17 worth_a_look, 22 long_shot, 74
  rejected (64 by the language gate: Polish beside English).
- freelancermap: 67 records from four queries in two sort orders (paging
  still returns page 1); 2 worth_a_look, 2 long_shot, 63 rejected (57
  German).
- djinni: 47 records, 15 unrelated postings left out; 12 hot_lead, 8
  worth_a_look, 6 long_shot, 21 rejected. Written "Remote; candidates in
  ...", with " only" when the list names countries and not the residency.

## Items
- DONE - Survey Eastern European B2B boards and German and Dutch freelance platforms; write the result and the plan here
- DONE - Fetcher for justjoin.it
- DONE - Fetcher for freelancermap.de
- DONE - Fetcher for djinni.co
- DONE - Registry: justjoin.it and nofluffjobs answer again; the rejected boards above recorded
