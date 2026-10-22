# 0084 A posting written in neither English nor Russian is refused

Source: feedback review, 2026-10-22: sharp, vacancies b459c1d7, 4312bcc2, 8254e4da
Scope: config

## Business
The person: "JD is in Deutsch. I'm not able to speak this language fluently.
My languages are Russian (native) and English, that's it. Remove the jobs not
written in one of professional languages from the list of jobs completely,
from any statuses." And on a Finnish one: "Unknown language - finnish.
Remove these jobs from any sort of results."

- LichtBlick (b459c1d7): the description is German ("Über LichtBlick:
  Arbeitsmodell: Remote innerhalb Deutschlands ..."). The language gate
  found "bewerbung" and "vollzeit", below its threshold;
  `foreign_language_posting_hits` empty.
- Fennoa (4312bcc2): title "Full-stack ohjelmistokehittäjä", the text
  Finnish; there is no word list for Finnish.
- Crédit Agricole CIB (8254e4da): title "Développeur C#/.Net – Bonds H/F",
  no description (a LinkedIn card), marked wrong pick without a reason.

Related: task 0074 (a posting that asks for Polish).

## Implementation
A check of the posting's own language in `tools/score.py`, next to the
language gate: the share of English (and Russian) function words in the
title and description. A posting below the share is refused as "language:
the posting is in another language", in every class. The person's languages
come from the profile (`owner.languages`). A card with no text is judged by
its title. Tests on the three records.

## Items
- TO DO - The posting-language check, with tests on the German, Finnish and French records
- TO DO - Rescore; count what moves
