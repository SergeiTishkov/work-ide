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
For the owner to decide first: is a remote posting whose location field
names only countries the person is not in, with no word of hiring elsewhere,
refused by the scripts, or left to the AI check?
- Either way: the Jobicy fetcher keeps the region as `Remote from: <list>`
  in `location_raw` (as `fetch_dataart.py` does), and the screening prompt
  says that a location field naming countries on a remote posting limits it
  to them unless the text says it hires elsewhere. A test on the LastPass
  and Oowlish records.
- If refused by the scripts: a verdict `country_only` in
  `_structured_location`, a dealbreaker in score.py, the 2026-08-05 comment
  rewritten with the owner's new word; tests.

## Items
- TO DO - The owner decides: refused by the scripts, or left to the AI check
- TO DO - Jobicy keeps "Remote from"; the screening prompt reads a country-only location as a limit
