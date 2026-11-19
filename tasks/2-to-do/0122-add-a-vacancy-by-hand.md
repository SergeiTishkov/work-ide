# 0122 A vacancy the person found goes into the list by its link

Source: the owner, 2026-11-20
Scope: tools, app

## Business
The owner found a vacancy on LinkedIn (ENDGAME, Forward Deployed Engineer,
linkedin.com/jobs/view/4474971398) and wanted it in the app with a CV and a
cover letter. The system had no way to put one vacancy there:
`tools/ingest_manual.py` merges a record and then runs `pipeline.finalize`,
a rebuild that rescores, re-checks links and re-reads the whole base for
about half an hour and records a new selection (the owner stopped it on
2026-11-17 for Railway).

The vacancy was already in the base: a LinkedIn card from es.linkedin.com
(the "forward deployed engineer @ Spain" searches), first seen 2026-11-06,
no description. Scored blind it was rejected (4 points: "the employer never
states this is remote", "no description yet", "title suggests a
non-developer profession"), and the description reader only reads cards in
the head classes, so it never got its text. With the page read (3,231
characters: "Remote-First – Europe (including the UK)", GMT-1 to GMT+4, .NET
among the languages) the scripts give it 8 points, class low_priority:
stack +14, Node.js/Next.js -10, location +4. Not listed either way.

The owner's word on a vacancy outranks the scripts' class: a vacancy the
person adds by hand is listed in a section of its own, "Added by hand",
with its real score, in every market, and stays there on later runs.

## Implementation
- `tools/add_vacancy.py --identity <prefix> --url <link>`: finds the
  vacancy in the base (a LinkedIn link by its job number, any copy and
  subdomain; other links by the address), reads its page (LinkedIn: title,
  company, place, description, employment type; another board with a page
  reader: its facts; else `--description-file`), scores that one vacancy,
  saves it, remembers it as the identity's pick
  (`data/identities/<prefix>/added_by_hand.json`) and lists it in the latest
  selection. No AI read, no other vacancy touched.
- `selections.record` lists every pick in class `added_by_hand` in every
  market (unless a near-duplicate or a dead link), so the next run keeps it.
- The app names the section and puts it first.

## Items
- DONE - The tool, the pick list, the selection rows, the app's section name; tests
- TO DO - Add ENDGAME (4474971398) and queue its CV and cover letter
