# 0009 Postings in a language the person does not read are refused

Commits: b0d6a4b 7337c6b 355d965 (2026-08-05 — 2026-09-13)
Source: the agent, reading the top twenty against the CV

## Business
The owner reads English and Russian. Ten postings in the top were Dutch or
Hebrew, all with .NET in the title, one third in the list; arbeitnow brings
many German ones. A posting in a language the person cannot read, or one
demanding fluency in it, is not a vacancy for them. An English posting from
an Israeli company that writes its own name in Hebrew is.

## Implementation
`language_requirement_signal`: word lists per language, plus a script check
(anything but Latin and Cyrillic above a 15% share is refused). French and
demands stated in context added with the part-time search. Keyword edge
spaces kept as word boundaries after " je " matched inside "jede".

## Items
- DONE - Script share check
- DONE - Dutch, French and in-context language demands
- DONE - Keyword edges as word boundaries
