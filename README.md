# Work IDE

An autonomous job search driven by an AI agent. You describe the kind of work
you are looking for; the system continuously collects vacancies from open
sources, discards the ones that are plainly unsuitable, ranks the rest, and
produces a report you can read in ten minutes.

## Why "Work IDE"

**Work IDE = work identity.** It reads as "IDE", a development environment, and
the pun is apt: this really is a working environment, just for finding work
rather than for code. But the expansion is something else, and the expansion
matters more than the pun.

**The identity** is the project's central entity. It is one explicit object
answering the question "who is searching, and for what": stack, working
arrangement, geography, languages, pay expectations, target companies and the
scoring rubric. Not a scattering of settings across files that you have to hold
in your head, but a single folder you can open, read, copy whole or throw away.

Everything else the project is named for follows from that:

- **Setting up the filters is simple.** Not "edit seven configs in different
  places" but "answer nine questions and the agent assembles the identity". The
  geography and language filters are **derived** from your answers rather than
  rewritten by hand: the phrase "US only" is a plus for a US resident and a
  disqualification for everybody else, and that is for the machine to work out,
  not for your memory.
- **There can be several searches, and they do not interfere.** Calm,
  low-intensity work and an ambitious full-time role have opposite criteria; one
  rubric cannot express both. Those are two identities, each with its own
  vacancy database and its own report. The blast radius of any edit is one
  folder.
- **Different people's data does not get mixed.** Not by agreement but by
  construction: with no active identity the tools simply refuse to run. Mixing
  produces a plausible but wrong result — the kind of failure nobody notices,
  and those are the most expensive kind.
- **You can share your search without sharing yourself.** What lives in the
  repository are identity **templates** — kinds of search, with not one personal
  fact in them. You clone a template for yourself, and your copy, with its
  residency, pay expectations and CV, stays outside git.

The project is meant to be used through an AI agent (Claude Code and the like)
rather than by typing commands by hand. So the documentation is written for the
agent first — it is both the developer here and the runtime. The identity is
what turns a general-purpose agent into an agent that knows your search in
particular.

## Getting started

**If this is your first time:** open the project in an agent environment and say
something like "I want to set up a job search for myself". The agent will walk
you through [docs/ONBOARDING.md](docs/ONBOARDING.md): asking about your
experience (a CV, LinkedIn, or just an account of it), showing you the search
templates on offer, cloning the one that fits, and filling in the personal part
together with you.

**Without an identity the search does not run** — not a limitation but a
protection: mixing two people's data produces a plausible but wrong result that
nobody notices.

**There can be more than one identity**, including for one person: calm
low-intensity work and an ambitious full-time role have opposite criteria, and
one rubric cannot express both. You can add another at any time without
disturbing a search that is already tuned — see
[docs/ONBOARDING.md](docs/ONBOARDING.md), "Second and subsequent identities".

### Installation

You need Python 3.9+ and three libraries. Nothing else: no API keys, no paid
subscriptions, no external services.

```bash
git clone <repo> && cd work-ide
python -m venv .venv
```

Activating the environment depends on your system:

| System | Command |
|---|---|
| macOS / Linux | `source .venv/bin/activate` |
| Windows (PowerShell) | `.venv\Scripts\Activate.ps1` |
| Windows (cmd) | `.venv\Scripts\activate.bat` |

```bash
python -m pip install -r requirements.txt
python -m pytest -q          # optional, but it shows everything is intact
```

Then tell the agent "I want to set up a job search" and it will run onboarding.

### After onboarding

```bash
python tools/identity.py which     # which identity is active
python tools/doctor.py             # is everything in order
python tools/pipeline.py           # the search cycle
```

**Before onboarding these commands refuse deliberately** — there is no identity
yet, and the system will not search on behalf of "somebody". The refusal
explains what to do next.

The result is `reports/<prefix>_latest.md`. The `reports/` folder sits at the
repository root: the report is opened by hand, and hunting for it in a tree of
accumulated data is a nuisance. It is not in git and not in a fresh clone — the
tools create it themselves on the first run.

## How it works

1. **Collection.** Several sources needing no authorisation: remote-work
   aggregators (WeWorkRemotely, RemoteOK, Remotive, Jobicy, Himalayas), company
   careers pages directly through their ATS (Greenhouse, Lever, Ashby,
   Recruitee), the Hacker News "Who is hiring" thread, and LinkedIn's guest job
   search. Plus a manual channel: the agent searches the ordinary web where
   scripts must not go, and enters what it finds.
2. **Hard filters.** Everything plainly impossible is discarded outright: wrong
   location, wrong language, wrong profession, wrong stack. These are gates
   rather than point penalties — otherwise the impossible floats up the
   shortlist on the strength of generic words.
3. **Scoring.** What passes is ranked against a transparent rubric, and every
   vacancy shows its score broken down by component.
4. **Enrichment.** Link liveness checks, company age from Wikidata, employer
   reputation and pay ranges. The review sites are closed to scripts, so the
   agent looks the ratings up — but the LIST of what remains to check is
   compiled by the system itself, which complains until it is empty. Every
   company at the head of the shortlist has a result: either ratings, or an
   honest "we looked and found no credible reviews".
5. **The report.** Candidates by class, with pay and **its source named
   explicitly**, a link to the company's own site so you can apply directly, and
   reputation.

The automation is only the first filter. Before treating a vacancy as a find,
the agent must read it in full and work through
[docs/VACANCY_CHECKLIST.md](docs/VACANCY_CHECKLIST.md): keyword scoring finds
only what somebody put on a list in advance, and the wordings in job postings
are endlessly varied.

## Layout

The boundary runs along git: on the left, what is shared and impersonal; on the
right, what is yours.

```
CLAUDE.md              the constitution: principles shared by everyone
RUNBOOK.md             what to do in each search cycle

identity-templates/    KINDS of search. In git. Not one personal fact.
  README.md              how to clone one, the naming rules
  blank-.../             an empty starting point if none of the others fit
  <prefix>-<expansion>/  the folder explains itself by its name:
    template.yaml            the template version number
    CHANGELOG.md             what changed, newest first
    <prefix>_profile.yaml    kisel-keep-it-simple-easy-legacy/
    <prefix>_criteria.yaml   while the files inside stay short: kisel_profile.yaml

config/                shared machinery (nothing personal)
  sources.catalog.yaml   which sources exist and what they can do
  tech_vocabulary.yaml   how technologies are named in vacancies
  derivation/            tables for deriving geography and language rules
  settings_policy.yaml   what the local layer may NOT change

tools/                 CLI tools, each solving one problem
docs/                  documentation (see below)
.claude/commands/      ready-made agent commands: /start, /run, /add-identity…

local-identities/      OUTSIDE GIT: YOUR searches. Anything goes here.
  <prefix>-<expansion>/
    identity.yaml          which template, and which version
    template/              a verbatim copy of the template — never edited
    <prefix>_profile.yaml  your DIFFERENCES from the template, layered on top
    documents/             your CVs, under their own names
    CHANGELOG.md           a log of your changes

reports/               OUTSIDE GIT: finished shortlists, created automatically
  <prefix>_latest.md     each identity's latest shortlist — this is what to open
  archive/<prefix>/      history: 2026-07-31.md, 2026-08-01.md, …

data/<prefix>/         OUTSIDE GIT: the accumulated base, raw dumps, state
```

**However many folders are in `local-identities/`, that is how many shortlists
the system produces.** There is deliberately no separate registry of active
identities: a file holding a list can drift away from what is on disk, and
folders cannot.

The template copy inside your identity is not a duplicate left there by
oversight. Because of it, `git pull` cannot change your shortlist: the template
in the repository moved on, and your copy did not. An update happens by explicit
consent and is a replacement of the `template/` folder rather than a merge of
texts — your own settings sit elsewhere and cannot be lost.

## Documentation

| Document | About |
|---|---|
| [CLAUDE.md](CLAUDE.md) | The project's constitution. Read this first |
| [docs/IDENTITIES.md](docs/IDENTITIES.md) | The identity architecture. Read this second |
| [docs/ONBOARDING.md](docs/ONBOARDING.md) | How to create your own identity |
| [docs/QUESTIONNAIRE.md](docs/QUESTIONNAIRE.md) | How to run the interview |
| [docs/BUILDING_BLOCKS.md](docs/BUILDING_BLOCKS.md) | A catalogue of sources and tools |
| [docs/OVERRIDES.md](docs/OVERRIDES.md) | What overrides what between layers, and what cannot be overridden |
| [docs/TECH_MATCHING.md](docs/TECH_MATCHING.md) | How to look for technology names in vacancy text |
| [docs/VACANCY_CHECKLIST.md](docs/VACANCY_CHECKLIST.md) | The mandatory manual check on candidates |
| [docs/SOURCES.md](docs/SOURCES.md) | The sources, and the boundary of what is allowed when collecting |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Decisions and rejected alternatives |

## Language

The repository is in English — code, comments, documentation, templates. The
**report** is written in the language you speak to the agent in: it is taken
from `preferences.language` in your identity, and you can ask for another
language at any time. The split is deliberate: the repository is shared, while a
report is read by one person.

## Boundaries

The project freely reads anything served to an ordinary HTTP request, and does
so politely: an honest User-Agent carrying a contact, pauses between requests,
caching.

The project **does not circumvent** active bot protection — no faked browser
fingerprints, no CAPTCHA solving, no headless browser run to fool a detector.
Sites closed off that way (Glassdoor, Indeed) are reachable only through the
agent, which searches them as an ordinary person would and enters what it finds
by hand. More detail, with measured response codes, in
[docs/SOURCES.md](docs/SOURCES.md).

## Agent commands

If you work through Claude Code, the project ships some ready-made entry points:

| Command | What it does |
|---|---|
| `/start` | Onboarding: assemble an identity from nothing and make the first run |
| `/run` | The ordinary search cycle, including the mandatory manual check on candidates |
| `/add-identity` | Add another search without breaking the one already tuned |
| `/check` | Self-check: environment, identities, sources, tests |
| `/applied` | Record an application and its outcome |

These are thin wrappers over the documentation rather than a duplicate of it:
they guarantee the right document gets read and the mandatory steps are not
skipped.

## Licence

Apache License 2.0 — see [LICENSE](LICENSE). Use it, change it, share it.

## Requirements

Python 3.9+ and three dependencies (`requests`, `PyYAML`, `pytest`). No API
keys, no paid subscriptions, no external services.
