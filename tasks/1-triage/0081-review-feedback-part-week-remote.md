# 0081 Remote on some days or with a manager's leave is hybrid

Source: feedback review, 2026-10-22: sharp, vacancies 68e1a0b9, 7beecaca, 8de4ad67, e572d781, 2b94b453, 47eb65d5, 5f0fbcd5
Scope: config

## Business
The person, on 2026-10-22: remote work on some weekdays "if the manager
allows" is not worldwide remote. These postings put the job in an office
and make remote work a part of the week, a perk or a favour; the scripts
took the word as remote work. The quotes are in our `description_text`.

- Valitana, Plano TX (68e1a0b9): "Employees in this role will work in the
  office Mondays through Wednesdays with the flexibility to work remotely
  Thursdays and Fridays." The person: "IT IS NOT REMOTE".
- EP Energy, El Paso TX (7beecaca): "Remote work could be granted by
  supervisor, if deemed appropriate."
- Metropolitan Transportation Authority, New York (8de4ad67, e572d781):
  "LOCATION: 2 Broadway, New York", "This position is eligible for
  teleworking, which is currently 2 days per week."
- Acxiom (2b94b453): "This position is not located in the aforementioned
  locations but applications for remote work may be considered."
- DailyPay, Belfast (47eb65d5): "#BI-Remote" (a LinkedIn recruiter tag) is
  the only remote word.
- Contacx, New Zealand (5f0fbcd5): "Flexibility: Remote-first working
  arrangements" in a list of perks. The person: the job is onsite. The AI
  check rejected it since.

## Implementation
In the sharp template's criteria (and partsharp's; a template version step):
- hybrid phrases that refuse remote: `in the office <weekday> through
  <weekday>`, `remotely <weekday>s? and <weekday>s?`, `teleworking, which is
  currently \d days`, `remote work (?:could|may) be (?:granted|considered)`,
  `applications for remote work may be considered`;
- `#\w+-Remote` (LinkedIn recruiter tags) in `remote_word_other_meanings`;
- "eligible for telework(ing)" alone does not confirm remote.
A test in `tests/test_score.py` on each quote.

## Items
- TO DO - The phrases, with a test per quote
- TO DO - Rescore; count what moves
