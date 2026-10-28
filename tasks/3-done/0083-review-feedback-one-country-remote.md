# 0083 A remote posting whose location names only a country

Source: feedback review, 2026-10-22: sharp, vacancies 73edbe59, 9f951777, 4c8a561e, 2ee2d149, 9de51ee3, a5b9e75b, 4b2a50f1, 92ed55cf, 348863e1, 7e564b71, c7754b2b
Scope: tools

## Business
The person wants remote work open to where they live (Georgia), "worldwide
remote" in their words on 2026-10-22. These postings are remote and name a
single country or a list of countries, with nothing about hiring elsewhere:

- Spellbook (73edbe59, RSS): location "Canada", description 363 characters.
  The person: "It's stating 'Canada (Remote)' without any signs of worldwide,
  fully remote or whatever".
- LastPass (9f951777, Jobicy): the person pasted Jobicy's page markup
  "Remote from: Portugal". Our record has location "Portugal" and no such
  line: the fetcher drops "Remote from". The AI check kept it:
  location_ok "yes", "remote-first culture".
- Oowlish (4c8a561e, Jobicy): "Remote from: Brazil, Mexico, Argentina". The
  AI check kept it, reading "engage in remote collaboration for a worldwide
  presence" as worldwide hiring.
- emagine (2ee2d149, LinkedIn): location "Denmark", "Location: Remote".
  The AI check kept it (location_ok "yes"); the person rejected it.
- NMI (9de51ee3, "Canada", "Work Remotely" among benefits), BigHand
  (a5b9e75b, "Greater Montreal", "Fully remote working"), American Specialty
  Health (4b2a50f1, "United States", "This remote/WFH position"), Conduent
  (92ed55cf, Lynnfield MA, "Remote work: Enjoy the convenience of working
  from home"), Ledgent (348863e1, Houston, "Location: Remote ... Type:
  Contract"), AppLab (7e564b71, "Location: Raritan, NJ || Remote"), World
  Food Programme (c7754b2b, Rome, "DUTY STATION (City, Country): Remote"):
  marked wrong picks with no reason; each names one country only.

Two rules meet here:
- `tools/score.py` (2026-08-05, the owner): a named country is not an
  objection; only the employer's explicit limits refuse.
- `config/ai_screen_prompt.md`: location_ok is "no" when the posting limits
  who can apply to places the person is not in. The model answered "yes"
  for the location fields "Portugal", "Argentina, Brazil, Mexico" and
  "Denmark".

## Implementation
The owner's decision (2026-10-28): left to the AI check, not refused by the
scripts. Among the AI-kept top on that day, vacancies whose location names
one place: 13 applied, 4 marked bugged, 5 rejected (2 for the stack), 7
new, 13 expired. A script rule refusing them would have taken out the 13
the person applied to.

What remained: the Jobicy fetcher dropped "Remote from". Jobicy's page says
"Remote from: Portugal"; the record had location "Portugal", and the model
kept LastPass (9f951777) and bf2f8959 ("Portugal, USA"), both marked bugged
with that page markup. Now the fetcher sends `remote_from` beside
`location_raw`, and the model's message has the line "remote work allowed
from (the board says): Portugal". `location_raw` stays bare: with the
prefix in it the scorer read 64 of 574 Jobicy records differently
("Australia" no longer refused, for one). The prompt is unchanged. The
answers already given stay; a Jobicy posting the board still lists gets the
line on its next fetch, and its new text is read again.

## Items
- DONE - The owner decides: left to the AI check (2026-10-28)
- DONE - Jobicy sends "Remote from" to the model (`remote_from`), with tests
