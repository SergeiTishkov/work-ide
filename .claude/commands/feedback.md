---
description: Review the person's feedback from the desktop app and fix the filter
---

In the desktop app the person answers each vacancy with "applied", "not for
me" (`rejected`) or "wrong pick" (`bugged`), with an optional reason. This
command turns the last two into improvements of the search.

The identity is given as the argument (`/feedback kisel`): `$ARGUMENTS`. If it is not, ask —
unless you run headless (see below).

## The order

1. Gather everything pending into a package:

   ```
   python tools/feedback.py --identity <p> collect
   ```

   It prints the path of `data/<p>/feedback/pending_<time>.yaml`, or "Nothing
   to review" — then say so and stop.

2. **Start from `summary`**, not from the first item. Look for what the
   pending items share: a source, a class, a signal that fired in most of
   them. One shared cause fixed is worth more than a patch per vacancy.

3. **Every `bugged` item is a bug report against the filter**: the vacancy
   should never have been shown. For each:
   - read the person's reason, the `description`, `dealbreakers` and the
     `score_breakdown` — which signals let it through;
   - fix the cause in `<p>_criteria.yaml` or `tools/score.py` — systemically,
     as the constitution asks, never by discarding the one vacancy;
   - add a test built on this vacancy's text, so the mistake cannot return;
   - compare `then` and `now`: a class that already changed means an earlier
     fix took, and there may be nothing left to do.

4. **`rejected` items are preferences**, not bugs. Fix the filter only when a
   pattern is clear and the person's reasons support it; otherwise record the
   observation in `data/<p>/knowledge/<p>_insights.md` and leave the filter
   alone. One "not for me" is an opinion, five with the same reason are a rule.

5. Run `pytest`. Then, if the filter changed, re-select without fetching:
   `python tools/report.py --identity <p>` — the app shows the result at once.

6. Record the conclusions in `data/<p>/knowledge/<p>_insights.md`, then mark
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
