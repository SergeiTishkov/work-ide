# The Local Constitution — specification (LAYER RETIRED 2026-08-06)

> **This layer is no longer used.** The document is kept to explain what to do
> with a `local-constitution/` folder if you have one from an earlier version.
>
> **What replaced it.** There used to be three layers: the constitution (in
> git), the identity (in git) and the Local Constitution (outside git) — the
> last existing precisely so that personal data did not reach the shared
> repository. The boundary now runs along git itself:
>
> ```
> identity-templates/   the KIND of search, in git, not one personal fact
> local-identities/     YOUR search, outside git, anything goes
> ```
>
> There is no longer anybody to hide personal fields from inside a public file,
> so the `local` sentinel went with the layer, and the whole class of mistakes
> around it: scoring can no longer receive the string `"local"` where a list of
> languages was expected.
>
> The registry of active identities (`active.yaml`) is retired too: the number
> of folders in `local-identities/` IS the answer to "which searches are set
> up", and it cannot drift away from the disk.
>
> **What to do with the folder.** Nothing is required. When migrating, the
> contents move into your local identity:
>
> | was | is now |
> |---|---|
> | `personal/<p>/<p>_owner.yaml` | `local-identities/<folder>/<p>_profile.yaml` |
> | `personal/<p>/<p>_contact.yaml` | the same file, under the `contact` key |
> | `personal/<p>/CV *.pdf` | `local-identities/<folder>/documents/` |
> | `active.yaml` | not needed — the folders are the registry |
>
> The originals are **not deleted**: the project does not touch a person's
> personal files (CLAUDE.md §5). Check that everything you need has moved, then
> delete the folder yourself — or leave it, it gets in nobody's way.
>
> The current architecture is in [IDENTITIES.md](IDENTITIES.md) and
> [OVERRIDES.md](OVERRIDES.md). What follows is the former specification, as it
> stood.

---

## What it was

A local layer: which identities were active on this machine for this person, and
their personal files. The repository is shared; the choice of identity and the
CV are personal.

The name contrasted with the constitution (`CLAUDE.md`): that one sets the rules
for everybody and lives in git, this one was for one person and stayed out of
it.

## The layout

```
local-constitution/
├─ README.md                 # what this is (a copy from docs/templates/)
├─ active.yaml               # MACHINE-READABLE: which identities are active
├─ ACTIVE_IDENTITIES.md      # a human-readable mirror: why these ones
├─ LOCAL_NOTES.md            # personal conclusions unfit for the shared layers
└─ personal/
   └─ <prefix>/
      ├─ CV Ivan Petrov Software Engineer.pdf   # the owner's name, NOT renamed
      ├─ <prefix>_owner.yaml                    # the personal part of the profile
      ├─ <prefix>_contact.yaml                  # a contact for an honest User-Agent
      └─ <prefix>_private_notes.md              # created by the project, so prefixed
```

## Personal preferences that affect the score

A separate case, easy to put in the wrong layer: a reason to prefer something
that has nothing to do with the market or with the search profile.

A case from practice (2026-08-05): remote work for a company in a particular
country was valuable because it let the person pay tax at home and accrue
pension credit. That is not a property of the market (the market is about rates)
nor of the search (an identity for "calm legacy remote work" is reusable by
anyone) — it is a circumstance of one person.

```yaml
# local-constitution/personal/<prefix>/<prefix>_owner.yaml
personal_market_bonus:
  Belarus:
    points: 12
    remote_only: true      # the bonus only makes sense for remote work
    why: "Tax paid at home counts towards pension credit"
```

The identity profile carried `personal_market_bonus: local` — that is, the
identity merely declared such a bonus possible, while its content stayed local.
Another person with the same search profile would have their own reasons, or
none.

**The bonus is soft by construction.** It moves a vacancy up the shortlist but
does not make an unpassable one passable: the gates fire earlier and
independently. That is pinned by a test — otherwise a personal preference would
one day drag through a vacancy the person cannot take.

This mechanism survives the retirement of the layer: the values now live in the
local identity's own `<prefix>_profile.yaml`, which is outside git for the same
reason.

## `<prefix>_owner.yaml` — the personal part of the profile

Under the old scheme the identity in `identities/` lived in the shared
repository and described the **search**: stack, working arrangement, marks of a
suitable company. Everything belonging to a particular person lived here:

| Field | Why it is personal |
|---|---|
| `owner.name`, `owner.linkedin` | They identify the person |
| `owner.cv_files` | A personal document |
| `owner.location` (country, `utc_offset`) | Residency — and the geography rules are derived from it |
| `owner.languages` | The language filter is derived from them |
| `goal.target_compensation` | Money |

The identity file carried the `local` sentinel in those places:

```yaml
# identities/kisel-…/kisel_profile.yaml   (in git)
owner:
  role: "Senior Software Engineer (.NET / C#)"   # part of the SEARCH profile
  name: local                                    # the value lives locally
  languages: local
  location: local
```

```yaml
# local-constitution/personal/kisel/kisel_owner.yaml   (outside git)
owner:
  name: "Ivan Petrov"
  languages: ["English", "Russian"]
  location:
    country: "Georgia"
    utc_offset: 4
```

The paths matched exactly, and on activation the values were merged into the
profile (`common.resolve_local_fields`). If a field was marked `local` and was
absent here, the identity counted as **unfinished** and no search would run:
substituting emptiness silently is not allowed, or scoring would run against
empty languages and produce plausible rubbish.

### The owner's personal files are not renamed

The prefix rule applies only to files **the project creates itself**. Documents
a person brings with them — CVs, portfolios, covering letters — keep the name
their owner gave them. No renaming, no "bringing them into line".

The reason is simple: they are somebody else's files. A person recognises them
by name, finds them by name in a file manager, and sends them to employers by
name. Renaming buys the project nothing (the code does not read these files —
the path comes from `profile.owner.cv_files`) and breaks what the person had.
The same principle as "never delete somebody else's files" in the constitution:
inside its own folder the project is in charge; it does not touch other people's
property.

The mistake was made in practice (2026-07-31, during the first move into the
Local Constitution: `CV Ivan Petrov Software Engineer.pdf` → `ivpt_cv.pdf`) and
the owner noticed immediately. Hence the rule is written down explicitly.

The path to the CV in `<prefix>_profile.yaml → owner.cv_files` is written **as
it is**, with spaces and capitals. Nothing breaks: it is just a string the agent
uses to open the file.

## active.yaml — the only file the code read

```yaml
schema_version: 1

# Mandatory once more than one identity is active. Without it the tools refused
# to run and demanded an explicit --identity.
default_identity: kisel

active_identities:
  - prefix: kisel
    activated_at: "2026-07-31"
    relationship: owner          # owner | fork_of:<prefix> | using_shared
    personal_dir: personal/kisel
    note: "The main part-time search."
```

| Field | Meaning |
|---|---|
| `default_identity` | What to use when `--identity` is absent. Mandatory with more than one active |
| `prefix` | The folder in `identities/`; it had to exist |
| `activated_at` | The date — so that six months on you remember when and why it was added |
| `relationship` | `owner` — yours; `fork_of:<p>` — a branch from somebody else's; `using_shared` — using a shared one as it is |
| `personal_dir` | Where this identity's personal files live |
| `note` | What you wanted it for |

The current order in which the active identity is resolved is in
`docs/IDENTITIES.md`.

## personal/<prefix>/<prefix>_contact.yaml

```yaml
user_agent_contact: "you@example.com"
```

Read when the identity profile carried `user_agent_contact: "local"`. That kept
the User-Agent of outgoing requests honest (an engineering commitment of the
project) while the personal address stayed out of the shared repository.

The project works without a contact, but `doctor` warns about it.

## LOCAL_NOTES.md — what belonged here

Observations that should reach neither the shared documentation nor an identity.
The test question: *"would this be useful to another person who cloned the
repository?"* No — then it goes here.

Examples:

- "on this machine the venv is not where it usually is";
- "do not apply to this company, somebody I know works there";
- "applying to X brought spam, do not engage again";
- personal notes on how a negotiation is going.

Not here: improvements to the tools (those are `tools/` plus the constitution)
and refinements to the search profile (that is the identity folder).

## Recreating things on a new machine

```bash
git clone <repo> && cd work-ide
python -m venv .venv
# activating the venv: Windows -> .venv\Scripts\activate
#                      macOS / Linux -> source .venv/bin/activate
python -m pip install -r requirements.txt

python tools/templates.py clone <template> <prefix> "<expansion>"
# put the CV in local-identities/<folder>/documents/ — under its own
# name, without renaming it;
# the personal profile fields go in local-identities/<folder>/<prefix>_profile.yaml

python tools/identity.py which
python tools/doctor.py --identity <prefix>
```

The data (`data/<prefix>/`) and the reports (`reports/`) are not restored by
this — they are outside git too. **There is no need to create them by hand**:
the tools create both folders themselves on the first run
(`mkdir(parents=True, exist_ok=True)`). Their absence in a fresh clone is a
normal state rather than breakage.

The base fills up again over a few runs. If it is specifically the accumulated
history you need (application statuses, company reputation, insights), move the
`data/<prefix>/` folder across by hand, in an archive for instance; it is worth
moving `reports/archive/<prefix>/` with it if you want the history of
shortlists.

## Overriding the paths

Locations can be moved outside the repository with environment variables:

| Variable | What it sets |
|---|---|
| `WORK_IDE_IDENTITIES` | The root of local identities (instead of `local-identities/`) |
| `WORK_IDE_DATA_ROOT` | The data root (instead of `data/`) |
| `WORK_IDE_REPORTS_ROOT` | The reports root (instead of `reports/` at the repository root) |
| `WORK_IDE_IDENTITY` | The active identity |
| `WORK_IDE_LOCAL_CONSTITUTION` | The path to the retired local folder, if you still have one |

Useful if the data is kept on another drive or in a cloud folder.
