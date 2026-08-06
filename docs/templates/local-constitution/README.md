# The Local Constitution (RETIRED LAYER)

> **This layer is no longer used.** Identities now live in `local-identities/`,
> which is outside git, so there is nowhere left to hide personal fields from.
> The skeleton is kept for machines set up before the change — see
> `docs/LOCAL_CONSTITUTION.md` for what to do with the folder if you have one.
>
> On a fresh clone you do not need this folder at all. Start with
> `python tools/templates.py list`.

This folder is **local**. It is not in git and must not be: it describes a
particular person at a particular computer, while the repository is shared.

The full specification is `docs/LOCAL_CONSTITUTION.md` (which *is* in git,
because without it the folder cannot be recreated on a new machine).

## What used to live here

| File / folder | Purpose |
|---|---|
| `active.yaml` | Machine-readable: which identities are active, and which is the default. Read by the tools |
| `ACTIVE_IDENTITIES.md` | A human-readable mirror: why these identities were chosen |
| `LOCAL_NOTES.md` | Personal observations that should reach neither the shared documentation nor an identity |
| `personal/<prefix>/` | A particular identity's personal files: CV, contacts, private notes |

## The routing rule: what to write here and what not

The layers should not be confused — what other people see depends on it:

- **The constitution (`CLAUDE.md`) and `tools/`** — what improves the project
  for every user: engineering principles, machinery, new sources.
- **An identity template (`identity-templates/<name>/`)** — what makes a
  particular kind of search better and makes sense for anyone using it.
- **Your local identity** — what concerns only you and this machine: where your
  CV is, your email address, your own conclusions.

The test question: *"would this be useful to another person who cloned the
repository?"* No — then it goes in your own layer.

## How to set things up on a new machine

1. Clone the repository.
2. `python tools/templates.py clone <template> <prefix> "<expansion>"`.
3. Put your CV in `local-identities/<folder>/documents/`.
4. Fill in the personal fields in `local-identities/<folder>/<prefix>_profile.yaml`.
5. Check: `python tools/identity.py which`.

If there is no identity yet, do not copy somebody else's folder by hand — go
through onboarding: `docs/ONBOARDING.md`.
