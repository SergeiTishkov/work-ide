# RUNBOOK — what to do on every run

This file is the concrete instruction for an agent that has opened this folder
and been told "run the usual research cycle". The philosophy and the priorities
are in [CLAUDE.md](CLAUDE.md).

In every command below, `<p>` is the active identity's prefix. If there is only
one identity, the `--identity` flag can be omitted: the tools will take the only
one present.

## Step −1 — establish the identity (MANDATORY, before anything else)

```bash
python tools/identity.py which
```

| Result | What to do |
|---|---|
| It named an identity | Work with that one; carry on with the steps |
| There is no identity | **Stop.** Searching is forbidden (CLAUDE.md, rule zero). Run onboarding per [docs/ONBOARDING.md](docs/ONBOARDING.md) |
| Several exist and none is chosen | Ask the person which one is wanted now, or work it out from the conversation. Do not guess |

Mixing two people's data is a silent failure: the report looks fine but is
wrong. So this step is never skipped.

## Step 0 — self-check (if it has been a while, or something looks odd)

```bash
python tools/doctor.py --identity <p>
```

If `.venv` is missing (a new machine or a fresh clone):

```bash
python -m venv .venv
python -m pip install -r requirements.txt
```

If there is no `local-identities/` folder, that is also normal for a fresh
clone: it is created when a template is cloned, see
[docs/ONBOARDING.md](docs/ONBOARDING.md).

## Step 1 — automatic collection and scoring

```bash
python tools/pipeline.py --identity <p>
```

This is the one command mandatory on every run. It:
- collects vacancies from the sources enabled in `<p>_sources.yaml`;
- never fails wholesale, even when one source is unavailable — watch the output
  and the "Source health" section of the report;
- rescores **the whole database** rather than only the new records, so that if
  you improved `<p>_criteria.yaml`, the old vacancies get the current verdict
  too;
- checks the links (`tools/link_check.py`) and removes from the report any
  vacancy with a confirmed broken link (404/410) — see the "🔗 Link check"
  section of the report;
- fetches the vacancy page for anything in the shortlist that arrived without a
  description (`tools/enrich_descriptions.py`), which also picks up the stated
  salary, whether the posting still accepts applications, and whether the
  employer declares the role remote;
- looks for somewhere to apply that is not the board
  (`tools/apply_channels.py`) — the exact vacancy on the employer's own
  applicant-tracking system, their board, or an address they wrote into the
  posting. Only for the top of the shortlist, and "nothing found" is recorded
  as a fact with a date rather than left silent;
- updates `data/<p>/knowledge/*.json` and generates `reports/<p>_latest.md`,
  filing a dated copy in `reports/archive/<p>/<date>.md`. The folders are
  created automatically if absent.

## Step 1.5 — the manual candidate checklist (MANDATORY, never skipped)

Confirmed explicitly by the user (2026-07-30) after a vacancy with an outright
"ONSITE" and "ITAR: must be a U.S. person" in its text passed the automation
(score.py did not know those particular wordings). **The automatic score is not
the final word.** For every vacancy at `long_shot` and above (including
`needs_manual_review`) the agent must:

1. Read its **full** `description_text` from
   `data/<p>/knowledge/<p>_vacancies.json` (locally, no network) — not only the
   `score_breakdown` and highlights in the report.
2. Work through [docs/VACANCY_CHECKLIST.md](docs/VACANCY_CHECKLIST.md) point by
   point, recording each result explicitly rather than by eye.
3. If a genuine inconsistency turns up — something obvious to a person but not
   caught by keyword scoring — that is a systemic problem: update
   `<p>_criteria.yaml` or `tools/score.py`, add a test for the specific case
   found, re-run `tools/pipeline.py`, and repeat the checklist for the remaining
   candidates. This is a loop rather than a one-off: almost every run of the
   checklist finds something new (see `data/<p>/knowledge/<p>_insights.md`).
4. Only vacancies that pass the checklist in full count as confirmed finds.

## Step 2 — manual extension (what the scripts cannot legitimately do)

The automation deliberately stays out of Indeed, Dice and Glassdoor (see
[docs/SOURCES.md](docs/SOURCES.md), which explains why). Here the agent works
itself, with its own tools (WebSearch/WebFetch), as a person would:

1. Read `reports/<p>_latest.md` — the "🔎 Needs a manual check" section. For
   each such vacancy: resolve the ambiguity (is "Georgia" the country or the US
   state?) and update the record:
   ```bash
   python tools/kb.py set-status --identity <p> --id <id> --status not_relevant --notes "why it does not fit"
   ```
   (or leave it as it is and raise the priority if the check came out positive —
   then just add a note through `--notes`).

2. Make two to four targeted web searches along the lines of:
   `site:linkedin.com/jobs "<stack keywords>" remote contractor` — across all
   the markets the identity is interested in, not only the most desirable one.
   Search for specific companies from `ideal_company_traits` that may hire
   through an EOR (Deel/Remote.com/Oyster/Papaya/Multiplier/G-P). Put the finds
   into a JSON file (the format is in the docstring of
   `tools/ingest_manual.py`) and run:
   ```bash
   python tools/ingest_manual.py --identity <p> --file <path-to-file.json> --source-name linkedin
   ```
   That puts the finds through the same normalize + score + report path as the
   automatic sources, and regenerates the report.

3. **Check employer reputation** for the companies in `hot_lead` and
   `worth_a_look` (and `long_shot` where possible). This is a separate,
   important step: what a person is actually looking for — calm, culture, pace —
   is never written in a job posting, whereas former employees write about it
   honestly. Look it up with ordinary web search (Glassdoor, Indeed and
   Trustpilot cannot be scraped automatically — they answer 403 behind bot
   protection) and record it:
   ```bash
   python tools/kb.py set-company-reputation --identity <p> --company "Acme Corp" --rating 4.2 --wlb 4.4 --source "Glassdoor" --retrieval web_search --reviews 257 --red-flags "layoffs,unpaid overtime" --notes "..."
   ```
   Reputation is stored per company and applies at once to all of its vacancies;
   the score is recomputed immediately. Pay particular attention to work-life
   balance (it weighs more than the overall rating) and to red flags: any red
   flag sets `needs_manual_review`, so that a person definitely reads the reason
   before applying.

   The list of companies still to check is compiled by the system itself:
   ```bash
   python tools/reputation.py worklist --identity <p>
   ```
   If nothing credible was found about a company, record that too — it is a full
   result, not the absence of one:
   ```bash
   python tools/reputation.py mark-insufficient --identity <p> --company "Acme Corp"
   ```

4. If, for a particular promising vacancy that quotes no salary, an approximate
   range was found on an external source (Glassdoor and the like), record it (it
   gives a small but honest plus to the score):
   ```bash
   python tools/kb.py set-salary-estimate --identity <p> --id <id> --low 60000 --high 80000 --period year --source "Glassdoor" --note "..."
   ```

5. If a non-obvious pattern about the market turns up along the way (for
   instance: "companies with word X in their description are nearly always
   willing to hire a contractor outside the US"), append it to
   `data/<p>/knowledge/<p>_insights.md` — appending, not rewriting the file.

## Step 3 — self-examination (see CLAUDE.md, section 10)

After steps 1-2, ask yourself "which improvement would do the project the most
good next?" and implement it straight away. Things worth looking at:
- `python tools/kb.py stats --identity <p>` — are there many
  `needs_manual_review` records or duplicates? If it has grown again, improve
  `score.py` or `kb.py` (this has happened before, see `docs/ARCHITECTURE.md` →
  "Rejected approaches").
- `data/<p>/<p>_state.json` → `sources` — has a source degraded
  (`consecutive_failures` climbing)? Find out what changed in its API or feed.
- Has a new public source of vacancies appeared that is not here yet? Add
  `tools/fetch_<name>.py` following the existing ones.
- Has the `<p>_criteria.yaml` rubric become less accurate on real data? You can
  see it when plainly irrelevant vacancies reach `hot_lead`/`worth_a_look`, or
  when plainly good ones stay in `long_shot`.

## What a run must leave behind

Every run must leave the repository better than it was — even if that is only a
more accurate score or a cleaner report. If steps 1-3 turned up no obvious
improvement, that is a legitimate outcome too, but a rare one; check whether
something from "Further development" in `docs/ARCHITECTURE.md` has been missed.
