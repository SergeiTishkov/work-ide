# 0076 HTML and entities in company names and titles

Source: the owner, 2026-10-22 (Spellbook<br>⚲&nbsp;Canada from jobspresso)
Scope: tools

## Business
The app showed "Spellbook<br>⚲&nbsp;Canada" as a company and "AI &amp;
Engineering" in titles. Behind the company string was a second fault: every
jobspresso vacancy got the place "Worldwide", the US-only and Canada-only ones
included, so the region verdict could not refuse them.

Found in the base on 2026-10-22: 20 jobspresso companies with the place glued
on, 16 records with HTML entities in the title, company or place.

## Implementation
- `fetch_rss_boards`: jobspresso is a WP Job Manager board; its feed carries
  `job_listing:company`, `:location`, `:salary` and `:job_category` in a
  namespace equal to the board's address. These are read by local name.
  Without them, `dc:creator` is split at the first `<br>` into company and
  place (`split_creator`).
- `normalize.plain`: title, company and place lose tags and entities and have
  whitespace collapsed, for every source.
- Stored records repaired by a one-off script (split, `plain`, verdicts
  recomputed, a rebuild selection recorded). sharp: 20 companies split and 20
  places taken from them, 81 titles, 11 companies, 8 places cleaned; one
  jobspresso vacancy moved from worth_a_look to rejected by its now-known place.

## Items
- DONE - jobspresso listing fields read; dc:creator split (tests/test_fetch_rss_boards.py)
- DONE - Entities and tags dropped from title, company and place in normalize (tests/test_normalize.py)
- DONE - Stored records repaired in sharp and partsharp
