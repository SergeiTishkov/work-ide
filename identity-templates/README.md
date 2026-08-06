# Search identity templates

What lives here are **kinds of search**, not anybody's settings. Everything in
this folder goes into the shared repository, so there are no personal facts here
— no residency, no pay expectations, no name, no CV — and there cannot be.

## How they are used

```
identity-templates/<template>/     ← this. In git. CLONED FROM.
local-identities/<my folder>/      ← the working copy. Outside git. Edited.
```

```bash
python tools/templates.py list
python tools/templates.py clone kisel mypx "My Personal Search"
```

Cloning puts the template's files into `local-identities/<folder>/template/`
verbatim and pins the version number. A person writes their own settings in
**files one level up**, and those are layered on top (`tools/settings.py`).

The key property follows from that: **`git pull` changes nobody's behaviour.**
The template in the repository moved on; the copy inside the identity did not.
An update happens only by explicit consent and is a replacement of the
`template/` folder rather than a merge of texts: personal files take no part in
the operation and cannot be lost.

## Versions

Every template has a `template.yaml` with a version number and a `CHANGELOG.md`
explaining the changes, newest first. The rule: if you changed a template file,
raise the version and describe the change. That is checked by the test
`test_template_version_matches_changelog` rather than by memory.

To check whether a template has moved ahead:

```bash
python tools/templates.py check --identity <prefix>
```

## What a search identity is

A complete set of answers to "who is looking for work, and what kind": the
person's profile, the scoring rubric, the sources enabled, the target companies,
and the filled-in questionnaire all of it was derived from.

One identity = one folder `local-identities/<prefix>-<expansion>/`. Inside it, a
verbatim copy of the template in `template/` and the personal files beside it.
Editing one identity physically cannot touch another: they live in different
folders and do not reference each other (`docs/IDENTITIES.md`, on the blast
radius).

## Two levels of naming: a long folder, short files

```
local-identities/
  kisel-keep-it-simple-easy-legacy/     <- FOLDER: prefix plus expansion
    kisel_profile.yaml                  <- FILES: the prefix alone
    kisel_criteria.yaml
    kisel_identity.md
```

The split is deliberate, and the levels should not be confused.

**A folder is named `<prefix>-<expansion-with-hyphens>`.** A folder is seen
rarely, but when it is, `kisel` alone gives no way to remember what that search
was or why it was set up. The expansion answers that right in the project tree,
without opening a file. `identity.py validate` checks it: a folder named by the
prefix alone counts as a problem.

**The files inside stay short: `kisel_criteria.yaml`.** Turning the file prefix
into the full name (`kisel-keep-it-simple-easy-legacy_criteria.yaml`) is a bad
idea, and here is why: file names occur incomparably more often than the folder
name. They are in every command, in `grep` output, in editor tabs, in paths
inside reports and error messages. A long name adds no information there (the
context is clear anyway) while noticeably hurting readability — and the
readability of names is exactly what the prefix rule exists for.

There is no need to turn the expansion into a folder name by hand: the clone
command takes it as an ordinary phrase and does that itself.

```bash
python tools/templates.py clone kisel kisel "Keep It Simple, Easy, Legacy"
# -> local-identities/kisel-keep-it-simple-easy-legacy/
```

## The single-prefix rule

**Every file inside an identity folder begins with `<prefix>_`.**

This is not cosmetic but protection against a specific failure. An agent working
with several identities at once will one day confuse two `notes.md` files from
different folders — and will do it silently. `kisel_notes.md` and
`jvst_notes.md` are practically impossible to confuse: the name identifies
itself in any context — in a project search, in an editor tab, in grep output.

The rule is checked automatically: `python tools/identity.py validate`.

## Rules for choosing a prefix

- 3-6 characters, lowercase Latin letters and digits only, first character a
  letter.
- **Pronounceable and meaningful**: it should describe what the search is about
  rather than name a person. An identity outlives a change of stack and
  employer, while "the search for calm legacy remote work" stays itself.
- The source language does not matter; Latin script on the output does.
  Non-Latin abbreviations are transliterated by sound.
- Better not to take an ordinary English word: a prefix is often looked for with
  grep, and `bore_` would drown in vacancy text where `kisel_` would not.

Some worked examples:

| Prefix | Expansion | Comment |
|---|---|---|
| `kisel` | **K**eep **I**t **S**imple, **E**asy, **L**egacy | Names the point, and happens to be pronounceable |
| `jvst` | **J**a**v**a **St**artup | Stack plus environment |
| `usts` | **US** + **TS** (TypeScript) | Residency plus stack |

### Reserved prefixes

These prefixes must not be taken — they are used in the tests, and a collision
would make a test run write into a live identity's folders:

| Prefix | Taken by |
|---|---|
| `ftf` | The frozen test fixture (`tests/fixtures/ftf-frozen-test-fixture/`) |
| `blank` | The blank template |
| `aaaa`, `bbbb` | The identity isolation tests (`tests/test_identity_isolation.py`) |
| `newp`, `srcp`, `dstp`, `abcd`, `efgh` | The creation and cloning tests |

The list is incomplete by construction: tests get added. So take a
**meaningful** prefix describing what the search is about, and a collision
becomes practically impossible. The clone command refuses a prefix that an
existing folder already uses, but it knows nothing about prefixes that live only
inside the tests.

## What an identity consists of

The required files (checked by `identity.py validate`):

| File | What is inside |
|---|---|
| `<p>_identity.md` | The human-readable description: what this identity is, what the abbreviation means, for whom, which tools and sources it uses and why, how scoring works here in particular, and a log of decisions |
| `<p>_profile.yaml` | Who the identity belongs to and what they seek: residency, languages, stack, expectations about money |
| `<p>_criteria.yaml` | The full scoring rubric (machinery plus personal tuning, with section banners) |
| `<p>_sources.yaml` | Which sources are enabled, and with what parameters |
| `<p>_questionnaire.yaml` | The filled-in questionnaire — the origin story: why the settings are what they are |

Optional: `<p>_ats_targets.yaml` (companies' careers pages), `<p>_notes.md`
(working notes on this identity).

## Folders that are not templates

Folders beginning with `_` are skipped by the loader.

## How to create your own

```bash
python tools/templates.py clone <template> <prefix> "<expansion as a phrase>"
```

The command assembles the folder name from the prefix and the expansion, copies
the template, renames the files to the short prefix and checks the structure
straight away. Do not copy somebody else's folder by hand — the risk of dragging
their settings along without noticing is high.

Scaffolding is not yet an identity: it has to be filled with answers. The full
path is described in `docs/ONBOARDING.md`: the agent asks you for a CV, a
LinkedIn link or a description, fills in the questionnaire together with you,
and generates the identity from the answers. The geography rules and language
filters are **derived** from your residency rather than copied: for a US
resident the phrase "US only" is a plus, for a resident of Georgia total
disqualification. Copy-paste here breaks the search silently.

## Where things live

- These folders are **in git** and are shared. A template can be offered to
  others through a PR.
- Your own searches live in `local-identities/`, outside git.
- Accumulated data is in `data/<prefix>/`, also outside git.
