# 0129 Read the descriptions of the vacancies left unread

Source: the owner, 2026-11-20
Scope: tools, app, docs

## Business
The owner, 2026-11-20: the vacancies the base holds but never read have to
be processed once; most LinkedIn postings live a short time, so each is
first checked for being still open. The collection runs at night now, so
descriptions may be read without the per-run cap (that change is planned
with the owner first, below).

Measured 2026-11-20, SHARP: 1,010 vacancies not refused by the scripts had
no description: 955 LinkedIn in "remote not confirmed" (read only in the
run that brought them, within 300 pages), 36 LinkedIn in low_priority, 19
of other boards; 851 first seen in October.

The owner, 2026-11-20: LinkedIn's schema.org "remote" (TELECOMMUTE) says
little, since remote within one country carries it too; the text decides,
"remote worldwide" a large plus, a bare "remote" a small one, as in the
usual collection. The score already works so: LinkedIn is
`workplace_hidden`, its TELECOMMUTE not taken.

## Implementation
- `pipeline.py --links --read` (queue: `links` with `{"read": true}`):
  the unread vacancies (no text, not rejected, not a duplicate, not
  closed), newest first, through `availability.check`; a LinkedIn
  posting's guest fragment gives the verdict and, when open, the text and
  the employment types (`enrich_descriptions.apply_facts`), one request;
  other boards' open ones are read by their readers. Rescore of those
  checked, the AI check of what rose to the top, a "rebuild" selection.
  A budget of 300 minutes; five 429s in a row end LinkedIn for the run.
- `enrich_descriptions`: the loop's body split into `read_one` and
  `apply_facts`; `read(records)` reads given vacancies with no worklist.

## Items
- DONE - The one-off run: `pipeline.py --links --read`, its queue argument, tests, docs (ARCHITECTURE, RUNBOOK); the app's step list knows the links run's stage names (since task 0127 they were shown raw)
- TO DO - The one-off run queued for SHARP, its result measured
- TO DO - The nightly runs read every unread vacancy that is not refused, each checked open first, with no cap of pages (the plan, agreed with the owner first)
