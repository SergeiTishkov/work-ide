---
name: source-doctor
description: Repair a vacancy source whose live contract fails — the source still answers, but no longer the way its fetcher expects (markup, paging, filters, fields). Use when `tools/source_contract.py` or `pytest --live` reports a source as BROKEN, when the pipeline log says "-> /source-doctor <source>", or when the user asks to check or fix a source such as LinkedIn. Takes the source name as its argument. Works for every source; each source's specifics are in docs/sources/<source>.md.
---

# Source doctor

Source to repair: `$ARGUMENTS` (a name from `config/sources.catalog.yaml`, e.g.
`linkedin`). If it is empty, run `python tools/source_contract.py` and take the
sources it reports as BROKEN, one at a time.

A source is shared machinery: it belongs to no identity, and a repair is a
repair for everybody. So nothing here depends on whose search is running.

## 0. Is it actually broken

```
python tools/source_contract.py --source <source>
```

Act on the status, and only on `broken`:

| status | meaning | what to do |
|---|---|---|
| `ok` | answers as the fetcher expects | nothing to repair — say so and stop |
| `unreachable` | network, timeout, 429, 5xx | nothing to repair — it is today's network, not the code. Stop |
| `blocked` | 401/403/999 or a login wall | **do not repair and never work around it** (CLAUDE.md §5). Tell the person the source closed its door; disabling it is their decision |
| `broken` | answers, but not as expected | continue |
| `no_contract` | the fetcher has no `contract()` yet | write one first (step 4 describes what it checks), then come back to step 0 |

Run the contract twice if it is broken only on one check: a single odd answer
is not yet a changed source.

## 1. Read the source's own instructions

`docs/sources/<source>.md` — what the fetcher depends on, the knobs the source
offers, what was already tried and measured, and the history of earlier
repairs. If the file does not exist, create it from the template in
`docs/sources/README.md` as you go; it is part of the repair.

Then the fetcher itself (`python tools/source_doctor.py scope <source>` lists
its files) and its offline tests.

## 2. Measure "before"

Measure what the fetcher gives TODAY, as it stands, before changing anything:
the number of records, unique ids, how many are new to a knowledge base, the
posting dates. Write the measuring script in the session's scratchpad, never in
the repository, and never let it write into `data/` — it reads the base at
most. Call the fetcher's own functions, with the probe parameters the source's
doc names, and descriptions/enrichment switched off where the fetcher allows.

Keep the request count modest and the pauses the fetcher uses. A long
measurement runs as an independent process, not a background shell, which is
killed after about 30 minutes — and it reports progress as it goes
(`progress.Progress` from tools/progress.py: done/total, an estimate of the
time left, what it found so far, how many 429s), flushed to a log file. A
measurement that prints only at the end cannot be told apart from a hung one.

## 3. Find out what changed, and measure "after"

Ask the source directly, with small probes: one request per question. Save a
raw response in the scratchpad and read it. Typical questions — the source's
doc lists the ones that matter for it:

- does the endpoint still answer an ordinary GET, at the same URL?
- what does one card look like now; where did the field go?
- how many items per page; does the next page start where we think?
- is each filter we send still honoured (compare filtered and unfiltered)?
- is there something new we could use that we did not before?

Then a POC "after": the same measurement as step 2, with the change applied in
the scratchpad copy. Compare the two and keep the numbers — they go into the
source's doc.

## 4. Repair

Inside the scope only (`python tools/source_doctor.py scope <source>`):

- **the fetcher**: the smallest change that matches what the source does now.
  Keep its defences: a record without its required fields is dropped, and
  "cards arrived but none parsed" is an error, never an empty market;
- **the offline tests**: update the snapshot to real markup as served today
  (trimmed, in the test or under `tests/fixtures/sources/<source>/`), and add a
  test for the very thing that changed;
- **the contract** (`contract(c)` in the fetcher): it must now pass, and it must
  check the fact that just changed, so the next change of the same kind is
  caught by the contract and not by an empty shortlist;
- **the source's doc**: what changed, when, the before/after numbers;
- **the catalogue entry** for this source, if what it says is no longer true.

A repair that needs anything outside the scope — normalize.py, scoring, the
pipeline, another source — is no longer a source repair. Stop, keep the change
uncommitted, and describe to the person what is needed and why.

## 5. Verify

```
python tools/source_contract.py --source <source>     # must be ok
python -m pytest -q                                   # must be green
```

## 6. Publish — only for a maintainer

```
python tools/source_doctor.py publish <source> -m "<what changed at the source, in English>"
```

End the message with the attribution lines your session requires for commits.
The script decides, and every outcome except `refused` is a normal end:

| outcome | meaning |
|---|---|
| `published` | a maintainer runs this: committed (the scope only) and pushed |
| `kept-local` | not a maintainer, or no upstream: the fix works in this copy and stays uncommitted. Not a failure — tell the person they can offer it as a pull request |
| `refused` | the contract or the tests are not green: fix that, do not bypass it |
| `push-failed` | committed locally, the push was rejected. Report it; **never force** |
| `nothing-to-publish` | no file in scope changed |

Never commit or push by hand around this script, and never with `--force` or
`--no-verify`.

## 7. Report, and carry on

Tell the person in a few lines: what the source changed, what the fix was,
before/after numbers, the publish outcome. If the doctor was called from a
collection run (`/run`), go back to it and continue — the repaired source is
fetched in that same run.
