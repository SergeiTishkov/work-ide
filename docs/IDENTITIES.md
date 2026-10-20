# The search-identity system

The central architecture document. If you are an agent about to change anything
in the project, read this file second, straight after `CLAUDE.md`.

## Why it exists

The project started as a tool for one person. When several people with different
profiles wanted to use it (a different stack, a different country, different
requirements), it turned out that personal data was smeared across the whole
project: through the configs, the constitution, the documentation and even the
code.

The naive answer — "just copy the folder and edit it" — breaks silently. An
agent working with two identities will sooner or later read the wrong one's
document, apply somebody else's geography rules, and produce a result that looks
fine and is wrong. That failure is invisible in the report, and it accumulates.

So isolation here is not a convenience but a correctness requirement.

## Two layers, split along the git boundary

| Layer | Where | In git | For whom |
|---|---|---|---|
| **The constitution** | `CLAUDE.md` | yes | Every user. Principles, engineering rules, boundaries |
| **Identity template** | `identity-templates/<name>/` | yes | Everyone who searches with this kind of profile |
| **Local identity** | `local-identities/<prefix>-<expansion>/` | **no** | You alone, on this machine |

Plus the data, outside git: `data/workide.sqlite`, the base every identity
shares (a vacancy is stored once, its score per identity), and
`data/identities/<prefix>/`, what is the identity's alone.

## The template copy inside a local identity

```
local-identities/sharp-senior-dotnet-remote-engineering/
  identity.yaml            which template, and which version it is pinned to;
                           tab_position: where its tab goes in the app (1 first)
  template/                a VERBATIM copy of the template, never edited
    sharp_profile.yaml
    sharp_criteria.yaml
    …
  sharp_profile.yaml       YOUR differences, layered on top
  sharp_criteria.yaml
  documents/               your CV, under its own name
  CHANGELOG.md
```

This is the key decision, and it removes text merging altogether:

- **`git pull` cannot change your shortlist.** The template in the repository
  moved on; your copy did not. Silent configuration drift is impossible by
  construction rather than by discipline.
- **An update is a FOLDER REPLACEMENT, not a merge.** Your own settings live in
  separate files and take no part in the operation, so there is nowhere for an
  agent to quietly lose them.
- **A conflict is computed exactly**: the intersection of the keys you overrode
  with the keys that changed between versions. A list, not a judgement call.

A template's version is a number in `template.yaml`, and `CHANGELOG.md` beside
it explains to a person what changed. Comparing versions means comparing numbers
rather than parsing prose.

```bash
python tools/templates.py list                        # what is available
python tools/templates.py clone sharp mine "My Search"
python tools/templates.py check  --identity mine      # has the template moved on
python tools/templates.py update --identity mine      # move onto its version
```

## The folder name: prefix plus expansion

```
local-identities/sharp-senior-dotnet-remote-engineering/sharp_criteria.yaml
                 └──────── folder: explains itself ─────┘ └ file: short ┘
```

A folder is named `<prefix>-<expansion-with-hyphens>`, because six months on,
`sharp` alone gives no way to remember what that search was. The expansion in
the folder name answers that in the project tree, without opening a file.
`identity.py validate` treats a folder with no expansion as a problem.

**The files stay short, and that is not an inconsistency.** A folder name is
seen occasionally; file names appear in every command, in `grep` output, in
editor tabs and in paths inside reports. A long prefix on a file would add no
information (the folder beside it explains everything) while spoiling
readability — the very property the prefix rule exists for.

A hyphen separates the prefix from the expansion; an underscore separates the
prefix from a file name. The different separators are not accidental: the
character alone tells you which level you are at.

## The single-prefix rule

**Every file inside an identity folder begins with `<prefix>_`.**

The reason is specific: an agent will one day confuse two files named `notes.md`
in different folders, and that will be a silent mistake. `sharp_notes.md` and
`jvst_notes.md` are practically impossible to confuse — the name is recognisable
in any context: in a project-wide search, in an editor tab, in `grep` output.

The rule extends to the data:
`data/identities/sharp/knowledge/sharp_insights.md`. A file opened in its own
tab or forwarded to somebody has to identify itself.

Checked automatically: `python tools/identity.py validate`.

### Where no prefix is needed: the folder already belongs to the identity

The precise statement of the rule: a prefix is mandatory where files of
**different** identities share a folder. When the folder itself belongs to one
identity, repeating the prefix in every name buys nothing.

Hence `data/identities/sharp/runs/pipeline_<time>.log`: the folder is already
sharp, so the file name carries only the time.

The "a file identifies itself" property is preserved another way: every report
starts with the line `# Work IDE [sharp] — report of …`. Even if the file is
forwarded or opened in its own tab, the first line names the identity.

### The rule's boundary: only files the project creates

The rule applies to everything **the project creates itself**: identity configs,
accumulated data, reports, housekeeping files.

It does **not** apply to documents a person brought with them — CVs, portfolios,
covering letters in `local-identities/<prefix>/documents/`. Those keep their own
names: `CV Ivan Petrov Software Engineer.pdf`, not `ivpt_cv.pdf`. The code does
not read them (the path comes from `profile.owner.cv_files`, just a string), so
renaming buys nothing while breaking how the owner recognises and finds them.

### Requirements for a prefix

3-10 characters, lowercase Latin letters and digits, first character a letter,
pronounceable, not a person's name. **The short name does not have to match the
identity's longer description**: it may be built from another name
(`partsharp`, part-time SHARP) or
simply a name (`sharp`, whose description is "Senior dotnet remote
engineering"). The description lives in the folder name and in
`<prefix>_identity.md` (the owner, 2026-10-05). A non-Latin name is
transliterated by sound. Check that `<prefix>_` does not occur in vacancy text —
a prefix is often looked for with `grep`.

## The blast radius of a change

The key property of the architecture, and the reason for a verbatim template
copy plus a personal overlay rather than inheritance from a shared base:

> **A change can affect only the identity whose prefix is on the file changed.**

An edit to `sharp_criteria.yaml` physically cannot affect `jvst`. Under a
"shared base plus overrides" scheme, editing the base for one identity's sake
would silently change the disqualifiers for all the others, and it would not
show in the diff — the file carrying their prefix did not change.

The price: improvements to the machinery do not propagate by themselves. That is
what the template version number and `templates.py check` are for: a local
identity that falls behind is detected by comparing numbers, and a test fails
while it stays behind.

## The boundary: what is personal, what describes the search

The commonest question when creating an identity is "does this go here or in the
personal layer?". There is one test question:

> **Would this change if another person used the same search?**
> Yes — personal, into the local identity. No — it describes the search, and
> belongs in the template.

| Data | Layer | Why |
|---|---|---|
| Name, LinkedIn, CV, email | **Local identity** | Identifies the person and says nothing about the search |
| Country of residence, time zone | **Local identity** by default | Another person with the same search lives somewhere else |
| Years of experience | **Local identity** | Personal; the level (senior/lead) already describes the search |
| Pay expectations | **Local identity** | They follow from a person's circumstances, not from the kind of work |
| Level, stack, employment type | **Template** | That IS the description of what is being looked for |
| Geography rules, language filter, time-zone window | **Template** | They are **derived** from personal data, but in themselves they are scoring rules |
| Target hiring markets | **Template** | Where we look, not where we live |

The key distinction in the last two rows: **the country of residence is personal
data; the rules derived from it are not.** "I live in Georgia" is a fact about a
person; "the phrase *EU Remote* disqualifies" and "the ambiguous place name
Georgia" are search rules that anyone in that situation needs.

### When a country belongs in the template after all

The default is not a dogma. If a search is **tied to a country in substance**,
the country stops being personal data and becomes part of the identity's
definition:

- "I am looking for work in Germany specifically" — an identity about the German
  market;
- "the same search, but separately for Germany, Canada and the Netherlands" —
  three identities, each with its own country;
- a template for other people: "a search for US residents" — here the country is
  part of the condition rather than a fact about one person.

Distinguish **residency** (where a person lives — usually personal) from the
**target market of the search** (always in the template). They need not agree:
you can live in one country and look for work in another.

## Cloning: one search across several countries

```bash
python tools/identity.py clone --from sharp --prefix kde --name "Sharp for Germany"
```

This command exists for that case. The stack, employment type, marks of a
suitable company and list of sources are the same for "the same search in
another country" — what differs is the geography rules, the language filter and
the time zone. Building the second identity from scratch means answering fifty
questions again to change three.

The difference from `new`: `new` gives empty scaffolding, `clone` a filled copy.
Every internal reference to the source prefix is rewritten automatically, or the
clone would break the rule that one identity's files never reference another.

**What to check in a clone** (the command prints this list when it creates one):

1. `display_name`, `abbreviation`, `scoring_philosophy`, target markets;
2. the geography blocks in `criteria.yaml`: `restrictive_region_signal`,
   `acceptable_region_signal`, `hard_dealbreakers`, `timezone_gate`,
   `ambiguous_place_names`; and the language filter;
3. `identity.md` — how this search differs from the original;
4. `questionnaire.yaml` — which answers changed.

Geography rules are **derived** from the tables in `config/derivation/` rather
than edited by eye: for a US resident the phrase "US only" is a plus, for a
non-resident total disqualification. A copied rule with the sign the wrong way
round silently throws away half the market, and the report will not show it.

Data is not copied: a clone gets its own empty base in `data/<new prefix>/`. The
`ftf` fixture cannot be cloned — it is calibrated for the tests.

## What is derived rather than copied

Three things cannot be carried over from somebody else's identity — they are a
**consequence** of a person's circumstances:

1. **Geography rules.** `restrictive_region_signal` is derived from residency.
   The phrase "us only" is total disqualification for a resident of Georgia and
   a plus for a resident of the US. Table: `config/derivation/regions.yaml`.
2. **Language filters.** What goes into the filter is the languages a person
   does **not** know. Table: `config/derivation/languages.yaml`.
3. **Ambiguous place names.** They depend on where the person lives. Starting
   points: `config/derivation/ambiguous_places.yaml`.

One distinction is worth remembering separately, because the project has already
been burned on it: **"the company is in X" ≠ "residency in X is required"**. The
phrase "EU Remote" first landed among the pluses as "a European company",
although it means EU residency is required.

## Resolving the active identity

A strict order of precedence, with no built-in default:

1. `--identity <prefix>` — an explicit intent always wins
2. `WORK_IDE_IDENTITY` — an environment variable (subprocesses, CI, tests)
3. the only folder in `local-identities/`
4. **refusal**

| Identities present | Behaviour |
|---|---|
| 0 | Refusal, with onboarding instructions |
| 1 | Used silently |
| >1 | Refusal, with the list: the agent asks, or works it out from the conversation |

Silently choosing under ambiguity is forbidden deliberately: that is precisely
the failure the whole system was built to prevent.

There is no registry file listing active identities, and there deliberately will
not be: a list can drift away from what is on disk, and folders cannot.

## The prohibition is in code, not only in words

`common.require_identity()` fails any access to config or data without an active
identity. It is called from `identity_config()`, `ensure_dirs()` and all six
loaders in `kb.py`. Rule zero of the constitution is executable.

In addition, `data/identities/<prefix>/.identity` records who owns the folder. If the data
folder was moved or renamed by hand, the mismatch is detected on the first
access rather than after somebody else's data has been written.

## The test fixture

`tests/fixtures/ftf-frozen-test-fixture/` is not an example identity but a
frozen snapshot of the configuration the tests are calibrated against. `kind:
fixture` forbids activation outside the tests.

### The fixture leaves no traces

A test run must end with `data/` holding exactly what it held at the start. The safety net in `tests/conftest.py` sees to that: it compares
the folder contents before and after, **clears** the fixture's traces and
**fails** the run, so that the defect in the test is visible.

To clear anything left over from old runs by hand:

```bash
python tools/clean_fixture_artifacts.py --dry-run   # look
python tools/clean_fixture_artifacts.py             # clear
```

The tool deletes exactly one path, and only for an identity with `kind:
fixture`: `data/identities/<p>/`. It
will not touch a live identity even if you pass its prefix explicitly — mixing
up a flag is easier than restoring an accumulated base.

**It must not be synchronised "while we are at it".** Divergence between the
fixture and live identities is a working mechanism: it turns every change to the
machinery into an explicit, reviewed update to the tests. Details in
`ftf_identity.md`.

## Where to put a change

The routing rule (in full in `CLAUDE.md`, §13):

- Improves the project **for everyone** → the constitution or `tools/`
- Improves a **kind of search**, and makes sense for anyone using it → the
  template
- Concerns **only you and this machine** → your local identity

The test question: *"would this be useful to another person who cloned the
repository?"*

## The CV per vacancy: `cv:`

**Generate CV** (tools/cv_tailor.py) starts from the CV named in
`owner.primary_cv`: the tailored files get its file name, and its `.docx`
beside it (or one in `owner.cv_files`) is the common CV. An optional `cv:`
section in the local profile adds the rest:

```yaml
cv:
  parent: "documents/Master CV Ivan Petrov.docx"  # every achievement: .docx, .md or .txt
  common: "documents/My CV.docx"     # only when it is not beside primary_cv
  model: opus                        # the claude CLI model
  target_pages: 3                    # cut lower-priority bullets above this
  max_pages: 3                       # never above this (2-3 pages)
```

Paths are relative to the identity folder.

**The parent CV** is optional and can be added at any time. It is one document
with every achievement of the person's working life — far longer than any CV,
never sent to anyone. When it is set, the two CVs have different jobs:

- the parent CV is **where the facts come from**: any job, bullet, number or
  skill in it may go into a tailored CV when the vacancy calls for it;
- the common CV is **the example**: of the layout, and of what to include
  first when the vacancy asks for nothing in particular.

The fact check accepts what either CV holds. Without `cv.parent` the CV is
tailored from the common CV alone, and the result says so and that a parent CV
can be added. Each identity sets its own `cv.parent`; two identities of one
person may point at the same file.

### Where the documents go

One folder for every identity, kept outside git in
`local-identities/settings.yaml` and set with
`python tools/documents.py set "<folder>"` (onboarding asks): an existing
folder gets a "Work IDE CVs and CLs" folder inside it, a new path is created
and used as it is. Unset, it is `~/Downloads/Work IDE CVs and CLs`. Inside:
`<prefix>/<vacancy id>/` with the current CV and cover letter (`.docx`,
`.pdf`), a log per document, and `Old versions/` (`V1`, `V2`, … — `V1 failed`
for a version the person rejected as a whole). Details: `tools/documents.py`.

### Generating without a click: `cv.auto`

After each collection the app can queue a CV and a cover letter for the
vacancies matching the identity's filters (tools/cv_auto.py):

```yaml
cv:
  auto:
    documents: [cv, letter]          # what to generate; both when omitted
    filters:                         # a vacancy matching ANY filter is picked
      - markets: [worldwide]         # market slugs, as in the app's Region
      - classes: [hot_lead, worth_a_look, long_shot]
      - markets: [eu]                # inside one filter everything must match
        sources: [weworkremotely.com]
        classes: [hot_lead]
```

A key left out of a filter matches anything. Candidates are the vacancies of
the latest selection with no answer yet; a document already in the vacancy's
folder is not made again, nor one whose vacancy was found gone (a dead link,
or no description — an error in its log instead of files).

After a collection the app makes them in one batch (`tools/cv_batch.py`,
a process of its own, shown in the app's task panel); it can be run by hand:
`python tools/cv_batch.py <prefix>`, `--stop`, `--status`.

A filter already applied picks only the **fresh** vacancies of the run. A
**new** filter — auto-generation just switched on, a filter added, or
`documents` changed — also picks the earlier vacancies of the latest
selection, once, at the end of the next collection. What was applied is kept
in `data/identities/<prefix>/cv_auto.json`; deleting it makes every filter
new again. `python tools/cv_auto.py --identity <prefix>` lists what the next
collection would generate.

## Practical commands

```bash
# what templates exist
python tools/templates.py list

# create your own identity from one
python tools/templates.py clone <template> <prefix> "<expansion as a phrase>"

# which identities are present
python tools/identity.py list

# which one is active right now, and why
python tools/identity.py which

# structural integrity (prefixes, required files, foreign references)
python tools/identity.py validate

# has the template moved ahead of your copy
python tools/templates.py check --identity sharp

# where a particular setting came from
python tools/settings.py criteria classification_thresholds.hot_lead

# every tool accepts --identity
python tools/pipeline.py --identity sharp
python tools/doctor.py --identity sharp
```

## Related documents

- `docs/ONBOARDING.md` — how to create an identity from nothing
- `docs/QUESTIONNAIRE.md` — how to run the interview
- `docs/OVERRIDES.md` — what overrides what between the layers
- `docs/BUILDING_BLOCKS.md` — a catalogue of sources and tools
- `identity-templates/README.md` — rules for template authors
