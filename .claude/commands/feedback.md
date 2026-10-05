---
description: Review the person's feedback from the desktop app and fix the filter
---

In the desktop app the person answers each vacancy with "applied", "not for
me" (`rejected`) or "wrong pick" (`bugged`), with an optional reason. This
command turns the last two into improvements of the search.

The identity is given as the argument (`/feedback sharp`): `$ARGUMENTS`. If it is not, ask —
unless you run headless (see below).

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
       that is a matching bug: fix the pattern and test it on the quoted
       text.
     - If the quote is not in our `description`, we never had that text. The
       description is missing or cut, or comes from a card (LinkedIn), or
       the posting changed after we downloaded it. Then the fix is about
       getting the text, or about how the gate treats a vacancy without it.
       A pattern for words we never saw would change nothing. Say which case
       it was in the outcome.
   - **Do not read a quote as the person's preference.** "Hybrid working
     model" pasted under "not for me" is not a person who dislikes hybrid
     for this one job. It is the posting saying the job is outside a remote
     search.

3. **Start from `summary`**, not from the first item. Look for what the
   pending items share: a source, a class, a signal that fired in most of
   them. One shared cause fixed is worth more than a patch per vacancy.

4. **Every `bugged` item is a bug report against the filter**: the vacancy
   should never have been shown. For each:
   - read the person's reason, the `description`, `dealbreakers` and the
     `score_breakdown` — which signals let it through;
   - fix the cause in `<p>_criteria.yaml` or `tools/score.py` — systemically,
     as the constitution asks, never by discarding the one vacancy;
   - add a test built on this vacancy's text, so the mistake cannot return;
   - compare `then` and `now`: a class that already changed means an earlier
     fix took, and there may be nothing left to do.

5. **`rejected` items are preferences**, not bugs. Fix the filter only when a
   pattern is clear and the person's reasons support it; otherwise record the
   observation in `data/identities/<p>/knowledge/<p>_insights.md` and leave the filter
   alone. One "not for me" is an opinion, five with the same reason are a rule.
   The exception is a quote from the posting (step 2). A quote is a fact about
   the vacancy, and if it breaks the criteria, handle it the way step 4
   handles `bugged`, even when it is the only one.

6. Run `pytest`. Then, if the filter changed, re-select without fetching:
   `python tools/report.py --identity <p>` — the app shows the result at once.

7. Record the conclusions in `data/identities/<p>/knowledge/<p>_insights.md`, then mark
   what you handled:

   ```
   python tools/feedback.py --identity <p> mark-reviewed --id <id> --id <id> \
       --outcome "what was done about it, in one sentence"
   ```

   Items you could not resolve stay unmarked — say why in the summary.

## Started from the desktop app (headless)

The app runs this as `claude -p "/feedback <p>"`. Do not ask anything; do not
commit (the person reviews the changes); say briefly what each step is doing,
since the app shows your text as a live log.

## At the end

Tell the person: how many items were reviewed, what was wrong and what changed
in the filter (with the tests added), what was only recorded as an
observation, and what is left pending.
