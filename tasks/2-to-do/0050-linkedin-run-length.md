# 0050 The LinkedIn run takes six hours and more

Source: the agent, 2026-10-20, during the first paced run

## Business
The paced LinkedIn run reads 168 query pairs (title by country) and took
six hours and more on the first window, with 142 "too many requests" by
pair 112. LinkedIn no longer holds up the top, but new LinkedIn vacancies
reach the list hours later, and a run that long overlaps the next
collection.

## Implementation
Measured on the run of 2026-10-20 (runs/linkedin_queries_2026-10-20_180329.json)
and the base of 2026-10-21:

- 412 queries: 168 top pairs and 244 narrower ones (split at the ceiling);
  4.2 hours of query time, 154 x 429. 7,960 new vacancies of 25,314 cards.
- 31 of the 168 top pairs brought nothing new.
- 42,007 LinkedIn vacancies in the base, 39 of them shortlisted (hot_lead,
  worth_a_look, long_shot). None shortlisted from Australia (2,165),
  France (1,391), Switzerland (1,081), Belgium (890), Austria (637),
  Finland, New Zealand, South Korea, Luxembourg, Saudi Arabia, Norway.
- By title: "architect" titles 5,945 vacancies, 1 shortlisted.

"Nothing new" says little: a pair can bring nothing new because another pair
found the same vacancies first. What decides a cut is whether a search alone
finds what reaches the shortlist, and the base did not say which search found
a vacancy. So each LinkedIn vacancy now carries `found_by`: every search that
ever served it, "<keyword> @ <place>", kept across runs. tools/linkedin_yield.py
lists the searches (or keywords, or countries) by how many shortlisted
vacancies they alone found.

The second paced run (2026-10-22, 0041 "Measured"): 920 queries, 6:42 of
fetch, 7:10 in all, no 429; 19,460 new vacancies, of them 1 long shot and
142 remote unconfirmed for SHARP, and 17,405 rejected because the employer
never states the work is remote (the guest search ignores f_WT). It is the
first full run with `found_by`.

Plan: after one or two full runs with `found_by`, cut the searches and the
countries whose `alone` is 0, with the numbers shown to the owner first.
Candidates from the counts above: the eleven countries with nothing
shortlisted, the "architect" keyword. A missed vacancy costs more than a long
run, so nothing is cut on the old numbers alone.

## Items
- DONE - From the per-query statistics of the first run, find what share of the pairs brought nothing new; write the plan here
- DONE - Each LinkedIn vacancy records the searches that served it (`found_by`), merged across runs
- DONE - tools/linkedin_yield.py: shortlisted vacancies each search, keyword or country found alone
- TO DO - After a full run with `found_by`, show the owner the searches with nothing found alone and cut the ones agreed
