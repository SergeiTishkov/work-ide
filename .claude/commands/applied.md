---
description: Record an application to a vacancy, and its outcome
---

Record in the knowledge base that the person applied to a vacancy, or how it
turned out.

```bash
python tools/kb.py list --identity <p> --limit 30      # find the id
python tools/kb.py set-status --identity <p> --id <id> \
    --status applied --notes "what exactly was sent, and when"
```

Statuses: `new`, `applied`, `interviewing`, `offer`, `rejected`,
`not_relevant`.

## Why this matters

Applications are the only source of feedback on whether the search is working.
Without them the system knows which vacancies **look like** the right ones, but
not which of them get an answer.

So do not stop at the status: if a rejection came, or conversely somebody
replied quickly, ask what the person makes of it and write the conclusion into
`data/<p>/knowledge/<p>_insights.md`. "Vacancies that quote a range reply more
often" is knowledge worth more than one record in a database.

If it turns out the vacancy was never suitable at all, that is a bug in the
filter. Fix `<p>_criteria.yaml` rather than simply marking it `not_relevant`.
