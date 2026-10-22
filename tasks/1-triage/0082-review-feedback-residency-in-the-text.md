# 0082 A remote role for residents of one country, stated in the text

Source: feedback review, 2026-10-22: sharp, vacancies 9525bbbb, d5a6ea8c, f8f93245, e7769851, 2ab4f689, 02237ac0, 022658d3, b459c1d7, 4312bcc2
Scope: config

## Business
These postings are remote and say in the text that the person must live in
one country. The person lives in Georgia. The quotes are in our
`description_text`; `absolute_residency_phrases` has none of these
phrasings, so they scored as remote with a named country (no objection since
2026-08-05) and reached the top classes.

- STERIS (9525bbbb): "This is a remote role. Qualified candidates must
  currently live in the Continental U.S. living in Eastern or Central Time
  zones." (the person's own quote)
- Quest Software (d5a6ea8c, f8f93245, e7769851): "100% remote job -
  Candidate must be located in Canada", "This is a remote role. Candidate
  must be located in Canada." The timezone check saw "must be located in"
  and left it as `unparsed_requirement`.
- Jobot (2ab4f689): "100% Remote Position (U.S.)".
- Commence (02237ac0): "we are open to remote candidates in the following
  states: AZ, AR, CO, ...".
- MMD Services (022658d3): "MUST have: Located in the United States".
- LichtBlick (b459c1d7): "Arbeitsmodell: Remote innerhalb Deutschlands".
- Fennoa (4312bcc2): "remote work is possible only with permanent residence
  status in Finland".

## Implementation
`restrictive_region_signal.absolute_residency_phrases` in the sharp template
(and partsharp's; a template version step): `must (?:currently )?(?:live|reside)
in the (?:continental )?u\.?s`, `candidate must be located in <country>`,
`remote position \(u\.?s\.?\)`, `remote candidates in the following states`,
`must have:? located in the united states`, `remote innerhalb deutschlands`,
`only with permanent residence status in`. In `tools/score.py`, a "must be
located in <a country the person is not in>" that the timezone check leaves
unparsed becomes a residency refusal. A test per quote.

## Items
- TO DO - The phrases and the "must be located in <country>" rule, with a test per quote
- TO DO - Rescore; count what moves
