# 0050 The LinkedIn run takes six hours and more

Source: the agent, 2026-10-20, during the first paced run

## Business
The paced LinkedIn run reads 168 query pairs (title by country) and took
six hours and more on the first window, with 142 "too many requests" by
pair 112. LinkedIn no longer holds up the top, but new LinkedIn vacancies
reach the list hours later, and a run that long overlaps the next
collection.

## Implementation
Options to measure, not decided: drop query pairs that bring nothing new
(the per-query statistics show them), merge countries into regional
queries, a shorter window after the first full one.

## Items
- TO DO - From the per-query statistics of the first run, find what share of the pairs brought nothing new; write the plan here
