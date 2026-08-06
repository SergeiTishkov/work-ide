---
description: Check that everything is in order — environment, identities, sources
---

Run the self-check and explain the result in plain language.

```bash
python tools/identity.py which            # which identity is active, and why
python tools/identity.py validate         # the structure of every identity
python tools/doctor.py --identity <p>     # environment, config, source reachability
python -m pytest -q                       # the tests
```

## How to read the result

- **No identity** — the normal state of a fresh clone, not breakage. Offer
  `/start`.
- **An identity that is not filled in** — also a normal stage. The message lists
  what is missing; offer to finish it.
- **No `data/` or `reports/` folder** — normal: the tools create them on the
  first run.
- **A source is unreachable** — a warning, not an error. The pipeline survives
  any source failing and carries on with the rest.
- **A test failed** — now that is a real problem; get to the bottom of it.

## Separately: the cleanliness of the real folders

After a test run, `reports/` and `data/` must hold exactly what they held
before. The tests run under the `ftf` fixture, and forgotten path isolation
leaves `ftf_latest.md`, `archive/ftf/` and `data/ftf/` behind.

The safety net in `tests/conftest.py` catches that and clears it itself, but if
something is left over from old runs:

```bash
python tools/clean_fixture_artifacts.py --dry-run
python tools/clean_fixture_artifacts.py
```

Only fixture traces are deleted — the tool does not touch live identities.
