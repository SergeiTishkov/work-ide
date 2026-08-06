---
description: Run the ordinary research cycle and produce a shortlist of vacancies
---

Run the full search cycle.

**The instructions are in `RUNBOOK.md`; read it in full.** What follows is only
the skeleton, plus the parts most often skipped.

## The order

1. `python tools/identity.py which` — establish the identity. If several exist
   and it is unclear which is meant, ask; do not guess.

2. **Check whether the template has moved ahead:**
   `python tools/templates.py check --identity <p>`

   If it has, **stop and ask the person** whether to update, showing the short
   list of changes from the command's output. An update
   (`templates.py update`) replaces the template copy; personal settings live in
   separate files and are untouched, but the person should know their search
   criteria changed BEFORE they see the shortlist, not after.

   "Not now" is a perfectly good answer: the pinned version keeps working and
   the shortlist does not move. Do not ask again in the same session.

3. `python tools/pipeline.py --identity <p>` — collection, scoring, report.
4. **Work through `docs/VACANCY_CHECKLIST.md` for every candidate at long_shot
   and above — this is a mandatory step, not a recommendation.** Read the full
   `description_text` from the base, not only the score breakdown.
5. **Close out the reputation of the shortlist companies — also mandatory.**

   ```
   python tools/reputation.py worklist --identity <p>
   ```

   For each company on the list: an ordinary web search (Glassdoor, Indeed and
   Trustpilot are closed to scripts, 403, so the agent searches as a person
   would), then ONE of two:

   ```
   python tools/kb.py set-company-reputation --company "<name>"        --rating N --wlb N --source Glassdoor --reviews N
   python tools/reputation.py mark-insufficient --company "<name>"
   ```

   The second is a full result rather than an excuse: a small company may simply
   have no reviews, and it matters to a person to see "we looked and found
   nothing" rather than "not checked". Those are different things: the first is
   a property of the company, the second a gap in the process.

   The list has to end up empty. To check:
   `python tools/reputation.py coverage --identity <p>` → "NOT CHECKED: 0".

6. The report is `reports/<p>_latest.md`. The "Company reputation checks"
   section must have nothing unchecked left in it — if it does, step 5 is not
   finished.

## Why step 4 cannot be skipped

Keyword scoring finds only what somebody put on a list in advance, and the
wordings in job postings are endlessly varied. Every run of the checklist so far
has exposed new classes of mistake: "Anywhere in the World" vacancies with
"Headquarters: US Remote" in the first line; a platform's total payout read as
an hourly rate; design roles passing as development.

Fix what you find **systemically**: edit `<p>_criteria.yaml` rather than
discarding one vacancy by hand. And record the conclusions in
`data/<p>/knowledge/<p>_insights.md` — the next run should be more accurate than
this one.

## At the end

Tell the person plainly: how many candidates are confirmed, what you discarded
by hand and why, and what changed in the filters. Do not present an unchecked
list as a shortlist.
