---
description: Run the ordinary research cycle and produce a shortlist of vacancies
---

Run the full search cycle.

Identity, when given: `$ARGUMENTS` (empty means: establish it in step 1).

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

3. **Check that the sources still answer as their fetchers expect:**
   `python tools/source_contract.py --identity <p>`

   It checks, live, the sources this identity has enabled that carry a
   contract. Act on each status:
   - `broken` — the source changed under its fetcher. Repair it first with the
     `source-doctor` skill (`/source-doctor <source>`), then continue here: a
     source repaired now is fetched in this same run. The doctor publishes the
     repair only when a maintainer runs it; otherwise the fix stays local, and
     that is fine.
   - `blocked` — the source refuses anonymous requests. Tell the person in the
     final summary and carry on.
   - `unreachable` — today's network; carry on.

4. `python tools/pipeline.py --identity <p> --skip-contracts` — collection,
   scoring, report. (Without `--skip-contracts` the pipeline checks the
   contracts itself; it is skipped only because step 3 just did.)
5. **Work through `docs/VACANCY_CHECKLIST.md` for every candidate at long_shot
   and above — this is a mandatory step, not a recommendation.** Read the full
   `description_text` from the base, not only the score breakdown:
   `python tools/kb.py --identity <p> dump --min-class long_shot`.

Employer reputation is not part of this cycle (the owner, 2026-10-17: not
worth the time of every collection). The person looks it up for one vacancy
with its "Collect reputation" button in the app (`tools/reputation_lookup.py`).

## Why step 5 cannot be skipped

Keyword scoring finds only what somebody put on a list in advance, and the
wordings in job postings are endlessly varied. Every run of the checklist so far
has exposed new classes of mistake: "Anywhere in the World" vacancies with
"Headquarters: US Remote" in the first line; a platform's total payout read as
an hourly rate; design roles passing as development.

Fix what you find **systemically**: edit `<p>_criteria.yaml` rather than
discarding one vacancy by hand. And record the conclusions in
`data/identities/<p>/knowledge/<p>_insights.md` — the next run should be more accurate than
this one.

## Feedback from the app

The pipeline ends with a line like `pending feedback: 3 wrong picks, 1 not for
me` when the person has marked vacancies in the desktop app. Do not review it
in this run: the person starts `/feedback <p>` in a session of their own, to
follow and steer the review (2026-10-07). Name the count in the summary.

## Started from the desktop app (headless)

The app runs this command as `claude -p "/run <p>"`, with the identity given.
Nobody is there to answer, so:

- **Do not ask anything.** The identity is the one given; do not look for
  another.
- **The template question in step 2 is answered "not now"**: report in the
  summary that the template moved ahead and what changed, and leave the update
  to the person.
- **Do not commit.** Edit code, criteria and tests as usual and run pytest;
  the person reviews the changes. The one exception is a source repair:
  `tools/source_doctor.py publish` decides by itself whether to commit (only
  for a maintainer) — leave that decision to it.
- The app shows your text as a live log, so say briefly what each step is
  doing as you go.

## At the end

Tell the person plainly: how many days of vacancies were collected (the
pipeline's `collected` line), how many candidates are confirmed, what you
discarded by hand and why, and what changed in the filters. Do not present an unchecked
list as a shortlist.
