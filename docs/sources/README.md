# Sources: contract, test, doctor

Every source the pipeline fetches is somebody else's server, and it can change
under its fetcher any day. Loud changes look after themselves — a fetcher that
gets cards it cannot parse returns an error instead of rubbish. The dangerous
ones are quiet: a page grows shorter, a filter stops filtering, a field moves.
Nothing fails, the shortlist just gets thinner, and nobody can tell that apart
from a slow week on the market.

So each source has three parts, none of them tied to an identity:

| Part | Where | What it does |
|---|---|---|
| **Contract** | `contract(c)` in the fetcher module | States, and checks live, the facts the fetcher stands on: the endpoint answers, a card parses, the next page starts where expected, each filter we send is honoured |
| **Test** | `tools/source_contract.py`, `pytest --live` | Runs the contracts. Also run by the pipeline before every fetch, and by `/run` for the identity's enabled sources |
| **Doctor** | the `source-doctor` skill + `docs/sources/<source>.md` | When a contract is broken: measure, find what changed, repair the fetcher, its tests and its contract, publish |

The skill is one for all sources; what differs between sources lives in that
source's own `docs/sources/<source>.md`.

## Statuses

| Status | Meaning | Who acts |
|---|---|---|
| `ok` | answers as the fetcher expects | nobody |
| `broken` | answers, but not as expected | the doctor repairs the fetcher |
| `unreachable` | network, timeout, 429, 5xx | nobody: it is today's network |
| `blocked` | 401/403/999, a login wall | the owner decides |
| `no_contract` | the fetcher has no `contract()` yet | whoever touches the source next |

## Who publishes a repair

A repair is shared machinery, so it should reach every copy of the project —
but only a maintainer can push. `tools/source_doctor.py publish` commits and
pushes when `git config user.email` is in `config/maintainers.yaml`, and
otherwise leaves the fix in the working copy: the person's collection works
today, and they can offer the change as a pull request. That is a normal
outcome, not a failure, so a run never stalls on a push that could not succeed.

It commits only the source's own files (`python tools/source_doctor.py scope
<source>`), only with the contract and the whole offline suite green, and never
forces a push. A repair that needs shared code is not a source repair; it goes
to a person.

## Commands

```
python tools/source_contract.py                    # every source with a contract
python tools/source_contract.py --identity sharp   # the sources sharp has enabled
python tools/source_contract.py --source linkedin
python -m pytest --live tests/test_source_contracts_live.py
python tools/source_doctor.py scope linkedin
python tools/source_doctor.py can-publish
```

## A source's doc

`docs/sources/<source>.md`, in this shape — the doctor reads it first and adds
to it after each repair:

```markdown
# <Source>

## What the fetcher depends on
One line per fact, each matching an expect() in contract().

## The knobs
Parameters and filters the source offers, and which of them are honoured
(measured, with the date). The ones that are ignored, too — so nobody
"discovers" them again.

## The probe
The fixed query the contract and the measurements use, and why that one.

## How to measure
What "before" and "after" compare: records, unique ids, new to a base,
posting dates, requests and seconds.

## History
Dated entries: what changed at the source, what the repair was, the numbers
before and after.
```

## Coverage

LinkedIn has a contract and a doc. The other sources have neither yet: they
report `no_contract`, and each gets both the next time somebody works on it.
