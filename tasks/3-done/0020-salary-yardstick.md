# 0020 A yardstick for pay where the vacancy states none

Commits: aa358ea 0c5218a (2026-09-08)
Source: the agent's UK survey

## Business
Most vacancies state no salary, and the middle level of trust in pay — an
approximate range from an external source — was filled by hand, a few
companies at a time. IT Jobs Watch publishes no vacancies but six-month
market medians per technology: .NET £60,000 a year permanent, £525 a day on
contract (contract up 6.6%, permanent down 4%). Shown beside the UK
shortlist, it lets the person judge an unstated offer.

A median is not what this employer pays, so it never writes onto a vacancy
and never moves the score.

## Implementation
`tools/salary_benchmark.py`, read beside the UK report; tests assert it
touches neither vacancies nor scores.

## Items
- DONE - Market medians beside the UK shortlist, outside the score
