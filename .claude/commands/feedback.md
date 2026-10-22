---
description: Review the person's feedback from the desktop app and turn it into tickets
---

In the desktop app the person answers each vacancy with "applied", "not for
me" (`rejected`) or "wrong pick" (`bugged`), with an optional reason. This
command reads the last two and turns them into tickets for the search.

The identity is given as the argument (`/feedback sharp`): `$ARGUMENTS`. If it is not, ask.

The person starts this in a session of their own, to follow and steer the
review; the desktop app only counts what is pending (2026-10-07). Ask when a
reason is unclear.

## What this review may change (the owner, 2026-10-22)

The review never changes code. Every change it finds necessary to code or
configuration becomes a ticket; the owner decides which to take into work.

- **May:** read anything; run the project's tools and tasks
  (`tools/feedback.py`, `tools/kb.py`, `tools/report.py`, `tools/pipeline.py`,
  `tools/taskq.py add ...`); change data under `data/` through those tools or
  by hand (`data/identities/<p>/knowledge/<p>_insights.md`, a vacancy's
  record); create new triage tickets.
- **May not:** edit anything else: `tools/`, `tests/`, `app/`, `config/`,
  `schemas/`, `identity-templates/`, `local-identities/` (criteria, profile,
  sources), `docs/`, the rules files, existing tasks. No git command that
  changes anything (add, commit, stash, checkout, reset, merge, push).
- **A ticket** is a new file in `tasks/1-triage/` named
  `<NNNN>-review-feedback-<slug>.md`, made with

  ```
  python tools/tasks.py new triage review-feedback-<slug> "<title>" \
      --source "feedback review, <date>: <identity>, vacancies <id>, <id>" --scope <scope>
  ```

  and then filled in: **Business** (what the person said, with the vacancy
  ids and the quotes that settle them), **Implementation** (the proposed fix:
  which file and which pattern or rule, and a test built on the vacancy's
  text), **Items** (`TO DO` lines). One ticket per shared cause, not per
  vacancy. When an open task already covers the cause
  (`python tools/tasks.py find <words>`), name it in the outcome instead of
  writing a second ticket.

## The order

1. Gather everything pending into a package:

   ```
   python tools/feedback.py --identity <p> collect
   ```

   It prints the path of `data/identities/<p>/feedback/pending_<time>.yaml`, or "Nothing
   to review" — then say so and stop.

2. **Read every reason as one of two things.** A reason is either the
   person's own words or text pasted from the vacancy page. For example:

   ```
   What's on Offer

   Hybrid working model
   ```

   That is not the person writing; it is a quote from the posting. The
   employer said the job is hybrid, so it is not remote. The person shows
   which line settles the vacancy and leaves the conclusion to you.

   - **How to tell a quote.** Section headings ("What's on Offer", "About
     you", "Benefits"), the employer's voice ("we offer", "you will"), list
     fragments, or text that matches the `description`. The person's own
     words are usually short and first-person ("too far", "Java, not .NET").
     When unsure, search the `description` for the text.
   - **Read a quote as the employer's statement and apply its consequence.**
     "Hybrid working model" means not remote. "Must hold active SC
     clearance" means a residency/authorization dealbreaker. "Salary:
     £25,000" means pay below the floor. Work out what the quote rules out
     against the identity's criteria, as if the employer had written it in
     the posting, which they did.
   - **Then find why the filter missed it.**
     - If the quote is in our `description`, a gate failed to read it, and
       that is a matching bug: the ticket proposes the pattern and a test on
       the quoted text.
     - If the quote is not in our `description`, we never had that text. The
       description is missing or cut, or comes from a card (LinkedIn), or
       the posting changed after we downloaded it. Then the fix is about
       getting the text, or about how the gate treats a vacancy without it.
       A pattern for words we never saw would change nothing. Say which case
       it was in the ticket.
     - If the AI check read the vacancy and kept it (`ai_screen` in the
       breakdown), the ticket says so and quotes the model's reason: the
       brief or the screening prompt missed it.
   - **Do not read a quote as the person's preference.** "Hybrid working
     model" pasted under "not for me" is not a person who dislikes hybrid
     for this one job. It is the posting saying the job is outside a remote
     search.

3. **Start from `summary`**, not from the first item. Look for what the
   pending items share: a source, a class, a signal that fired in most of
   them. One shared cause found is worth more than a ticket per vacancy.

4. **Every `bugged` item is a bug report against the filter**: the vacancy
   should never have been shown. For each:
   - read the person's reason, the `description`, `dealbreakers` and the
     `score_breakdown` — which signals let it through;
   - work out the cause in `<p>_criteria.yaml`, `tools/score.py` or the AI
     check — systemically, as the constitution asks, never by discarding the
     one vacancy — and write it into a ticket;
   - compare `then` and `now`: a class that already changed means an earlier
     fix took, and there may be nothing left to do.

5. **`rejected` items are preferences**, not bugs. Propose a filter change
   (a ticket) only when a pattern is clear and the person's reasons support
   it; otherwise record the observation in
   `data/identities/<p>/knowledge/<p>_insights.md`. One "not for me" is an
   opinion, five with the same reason are a rule. The exception is a quote
   from the posting (step 2). A quote is a fact about the vacancy, and if it
   breaks the criteria, handle it the way step 4 handles `bugged`, even when
   it is the only one.

6. Record the conclusions in `data/identities/<p>/knowledge/<p>_insights.md`, then mark
   what you handled:

   ```
   python tools/feedback.py --identity <p> mark-reviewed --id <id> --id <id> \
       --outcome "ticket NNNN-review-feedback-<slug>: <what it proposes, in one sentence>"
   ```

   Items you could not resolve stay unmarked — say why in the summary.
   **Mark every item you reviewed**, including a review done without this
   command (reading the database by hand). An unmarked item stays in the
   app's count as pending: on 2026-10-04 a retune built from 46 answers
   (commit 8b6906c) left all 46 there.

## At the end

Tell the person: how many items were reviewed, which tickets were written
(file name and the fix each proposes), what was only recorded as an
observation, which open tasks already cover a cause, and what is left
pending. The tickets stay as files; the review commits nothing.
