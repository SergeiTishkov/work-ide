# The manual vacancy checklist

Confirmed in practice (2026-07-30): automatic keyword scoring regularly misses
things a person sees immediately on reading the text (a literal "ONSITE" without
the word "required", "ITAR: must be a U.S. person" and the like). So for every
vacancy that passed the automation and landed in
`hot_lead`/`worth_a_look`/`long_shot`/`needs_manual_review` — **before treating
it as a real find** — the agent must read its description in full
(`data/<p>/knowledge/<p>_vacancies.json` → `description_text`, locally, no
network) and work through this checklist point by point. The checklist lives in
a file deliberately, rather than in the agent's memory, so that every point can
be seen to be closed rather than relying on "it looked all right".

Record the result of each check explicitly (in a scratch file for the run, or
directly in the reply to the person), not silently. If even one point is not
closed, the vacancy does not count as a confirmed find, whatever its score.

## The checklist

For vacancy `<id>` / `<title>` @ `<company>`:

- [ ] **The working arrangement is confirmed explicitly in the text** (not only
      by score.py's classification). For a remote profile: no "onsite",
      "on-site", "in-office", "hybrid" or "must work from our office" anywhere in
      the description.
- [ ] **No requirement of citizenship, residency or clearance** that the person
      does not have (US citizen, EU resident, ITAR "U.S. person", security
      clearance, a particular country) — read the whole text, not only the
      structured fields.
- [ ] **If a specific region is named (rather than "worldwide")**, it is where
      the COMPANY is rather than a requirement to live there. The difference is
      fundamental: "a company from X" is acceptable; "you must live in X"
      disqualifies if the person does not.
- [ ] **The role is real software development**, not an adjacent profession
      (management, sales, support, administration) — by common sense, not only
      by the job title.
- [ ] **The stack really is yours** (see `tech_stack` in the identity profile)
      rather than a chance match on one secondary word.
- [ ] **The character of the role matches the profile.** If the identity avoids
      R&D and "build it from scratch", check that this really is maintenance or
      extension of something existing. Read titles of the form "(AI ...)"
      carefully: they can mean "AI as an ordinary tool" or "a research role" —
      work out which from the context.
- [ ] **The language matches the ones the person speaks** (see `languages` in
      the profile). No requirement for an unfamiliar language, and the text is
      not written entirely in one.
- [ ] **The workload is compatible with the goal** (see `hours_per_day_target`)
      — no clear signs of an arrangement that does not suit: mandatory on-call,
      strict attendance, constant deadlines.
- [ ] **The link really does lead to the vacancy** (not to a general company
      page, not to a 404) — if `link_check.status` is not `ok`, look at the link
      separately where possible.
- [ ] **It is clear where the reputation data came from.** If the report says
      "data from search results — the primary source was not opened", that is
      second-hand: the numbers come from search snippets, and the agent never saw
      the Glassdoor or Trustpilot page itself (they answer 403 to scripts). For a
      vacancy the person really intends to apply to, it is worth suggesting they
      open the primary source with their own eyes — especially if there are red
      flags, or the rating is near a threshold.

## How to use it

1. `python tools/kb.py list --identity <p> --limit 50` (or read the base
   directly) to get the list of candidates at `long_shot` and above.
2. For each, read the full `description_text` — not only the score breakdown.
3. Work through the checklist above point by point, recording each result
   explicitly.
4. If every point is closed, the vacancy is confirmed and can go into the final
   selection.
5. If even one point is not closed, update `<p>_criteria.yaml` (add the missing
   keyword or pattern, if the problem is systemic) and/or mark the vacancy with
   `tools/kb.py set-status --identity <p> --id <id> --status not_relevant
   --notes "why"`, and explain to the person what was wrong and how it was
   fixed, so that next time the automation catches it itself.

Put criteria edits in the file of THE identity the search is running under.
Editing another identity's file will do nothing, and editing the shared
machinery affects everybody.
