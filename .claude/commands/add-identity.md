---
description: Add another search (a second or subsequent identity)
---

The person is asking to set up **another** search.

**The procedure is `docs/ONBOARDING.md`, "Second and subsequent identities".**

## First make sure this really is a new identity

| Question | If yes |
|---|---|
| Is this a different person (different CV, residency, languages)? | A new identity |
| The same person, but with opposite criteria (part-time versus full-time)? | A new identity |
| Simply a refinement of the current search (add a source, drop a filter)? | **NOT** new — edit the existing one |

The third case is the commonest, and confusing it is expensive: a superfluous
identity splits an accumulated base into two incomplete ones.

## Then

1. Go through steps 2-4 of ordinary onboarding (`/start`): an account of
   themselves, a prefix, the questionnaire. Reuse nothing from the existing
   identity, even for the same person — the two identities' goals differ by
   definition.
2. There is no need to copy the CV: point at the file already on disk.
3. `python tools/templates.py clone <template> <new> "<expansion>"` — or, if the
   new search resembles an existing one, clone the identity itself (below).
4. **Tell the person that commands without `--identity` will now refuse.** With
   one identity the tools pick it silently; with two they stop and name both.
   That refusal is deliberate, but it does mean the habit of typing
   `python tools/pipeline.py` with no flags stops working — including for the
   identity that had been working until now. Check with
   `python tools/identity.py which`.
5. `python tools/templates.py check --identity <new>` — has the template moved
   ahead of the copy.
6. Run it, and check the isolation: `python tools/kb.py stats --identity <each>`
   — the numbers must differ.

## A similar search for another country — clone it

The commonest reason for a second identity: "the same thing, but for Germany".

```bash
python tools/identity.py clone --from <source> --prefix <new> --name "<expansion>"
```

Stack, employment type, marks of a suitable company and sources are shared; the
geography rules, language filter and time zone are not. The command prints the
list of what must be checked in the clone — go through it without skipping the
geography blocks: they are **derived** from `config/derivation/` rather than
edited by eye. A copied rule with the sign the wrong way round silently throws
away half the market.

Suggest this possibility yourself when you can see the new search resembles an
existing one — the person does not know about it.
