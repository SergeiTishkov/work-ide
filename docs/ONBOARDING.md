# Onboarding: starting from nothing

The procedure for an agent that has opened this project and has no active
identity. Until an identity exists, **searching is forbidden** (the
constitution, rule zero), and the agent's first task is not to look for
vacancies but to take the person through this procedure.

The exception: work on the tools themselves is always allowed — it is not tied
to an identity.

## Step 0. Establish the state of the system

```bash
python tools/identity.py which
```

| Answer | What to do |
|---|---|
| It named an identity | Everything is ready, no onboarding needed |
| "No search is set up" | Carry on with this document |
| "Several exist and none was chosen" | Ask the person which one is wanted now |

## Step 1. Find out whether a suitable template exists

```bash
python tools/templates.py list
```

A template is a KIND of search — stack, criteria, sources — with not one
personal fact in it. If one fits the person, clone it (step 3). If none fits,
`blank` is a full set of files with comments and no decisions made for you.

## Step 2. Ask the person about themselves

**This is the first thing to ask.** Without it there is no way to assemble a
stack, a level or a set of expectations.

Any one of the three will do, and several are better:

- **a CV file** — ask them to put it in the identity's `documents/` folder
  (outside git) once it exists, or to give a path so the agent can copy it;
- **a LinkedIn link** — with a caveat: the public view without a login is
  incomplete, and once produced wrong data about languages. Where it disagrees
  with the CV or with the person, believe the person;
- **an account in their own words** — a perfectly workable option too.

If the person sent a CV before the folder exists, create the identity in step 3
and put the file there rather than leaving it at the repository root: personal
documents must not reach the shared repository (they are in `.gitignore`, but
better not to test that in practice).

**Do not change the file name.** The prefix rule does not extend to somebody
else's documents: `CV Ivan Petrov Software Engineer.pdf` stays as it is — copy
it, do not rename it. A path with spaces goes into `profile.owner.cv_files`
without trouble.

## Step 3. Choose a prefix and clone the template

The agent offers two or three options with expansions and the person picks one.
The requirements are in `identity-templates/README.md`: 3-6 lowercase Latin
characters, pronounceable, naming **what the search is about** rather than the
person.

```bash
python tools/templates.py clone <template> <prefix> "<expansion as a phrase>"
```

The expansion becomes part of the folder name:
`local-identities/<prefix>-<expansion-with-hyphens>/`. The person can dictate it
as an ordinary phrase — turning it into a folder name is the tool's job. The
files inside stay short (`<prefix>_criteria.yaml`).

The command copies the template's files into `<identity>/template/` verbatim,
renames each to the new prefix, writes `identity.yaml` pinning the template
version, and creates `documents/` for personal files.

Do not copy files by hand, and preferably do not try. This step used to be a
list of six `copy` commands with a rename each — and the project has already
been burned on it: a file referencing `kisel_` ended up inside the test fixture,
which is precisely the copy-paste the prefix rule protects against.

## Step 3a. Separate the personal from what describes the search

Do this at once, as soon as you start filling in the profile, rather than at the
end. Otherwise personal data lands in files that will go to the shared
repository, and cleaning it out afterwards is work.

There is exactly one test question:

> **Would this change if another person used the same search?**
> Yes — into your local identity. No — into the template.

| Local identity (outside git) | Template (in git) |
|---|---|
| Name, LinkedIn, CV, email | Level, stack, employment type |
| Country of residence, time zone | The geography rules and language filter **derived** from them |
| Years of experience | Target hiring markets |
| Pay expectations | Marks of a suitable company, sources |

Personal settings go into files at the root of your identity folder, beside the
`template/` copy: `<prefix>_profile.yaml` holds only your DIFFERENCES from the
template, and they are layered on top (see `docs/OVERRIDES.md`). Until the
required personal fields are filled in, the identity counts as unfinished and
the search will not run: substituting emptiness silently is not allowed.

**The exception is a search tied to a country in substance.** "I am looking for
work in Germany specifically" means the country is not personal data but part of
the identity's definition, and then it is written literally. More, with an
example, in `docs/IDENTITIES.md`, "The boundary: what is personal, what
describes the search".

## Step 4. Fill in the questionnaire together with the person

How to run the conversation is in `docs/QUESTIONNAIRE.md`. In short:

- the questions are asked **together with the person**, not filled in by
  guesswork;
- "I don't mind" is a valid answer; most questions have a sensible default;
- four blocks are mandatory and have no default: **residency, languages, the
  core stack, and the set of sources**. Without them an identity cannot be
  assembled — that is the practical form of "no identity, no search".

The answers fill in `<prefix>_profile.yaml` and `<prefix>_criteria.yaml`.

**Geography rules and language filters are derived**, not copied, from the
tables in `config/derivation/`:

- resident of a region → phrases saying "only in this region" become a **plus**;
- not a resident → the same phrases become a **disqualifier**;
- the language filter gets the languages the person does **not** know.

It is easy to get this wrong, and the consequences are quiet: the system will
either throw away half the market, or fill the shortlist with vacancies the
person will never be hired for.

## Step 5. Personal files

Put the CV in `local-identities/<prefix>-<expansion>/documents/`, under its own
name. The whole folder is outside git.

If the person has an email address to use in the User-Agent, put it in their
`<prefix>_profile.yaml` under `contact.user_agent_contact`. That keeps the
User-Agent honest while the address stays outside the shared repository.

## Step 6. Check

```bash
python tools/identity.py validate --identity <prefix>
python tools/identity.py which
python tools/doctor.py --identity <prefix>
```

`doctor` should be green on the identity, the configuration and writing to
`data/`. Source reachability checks are warnings rather than errors.

## Step 6a. Tell the person there can be more than one identity

A short but mandatory remark — easy to forget, and the person will not think of
it themselves, because they asked to "set up a job search", not for a
multi-profile system.

Exactly two things need saying:

1. **There can be several identities, and they do not interfere.** Each has its
   own vacancy database, its own report, its own filters. There is no overlap,
   in the data or in the settings.
2. **Why that is sometimes wanted.** The typical cases worth naming aloud:
   - the same person looking for **two different kinds of work**: calm work at
     2-4 hours a day and, in parallel, a full-time role. Those are opposite
     criteria: what is a plus for one identity (part-time, contract, "dull") is
     a minus for the other. One rubric cannot express both;
   - the person wanting to **try another stack or region** without breaking a
     search that is already tuned;
   - **somebody else** using the project — a colleague, a friend, a partner:
     they have their own CV, their own residency, their own languages.

Do not push. It is enough that the person knows the possibility exists and can
come back to it later — the procedure for "later" is below, under "Second and
subsequent identities".

## Step 7. The first run

```bash
python tools/pipeline.py --identity <prefix>
```

After that it is the ordinary cycle from `RUNBOOK.md`, including the
**mandatory** manual candidate checklist (`docs/VACANCY_CHECKLIST.md`).

The first run will almost certainly expose inaccuracies in the settings: a
filter too strict, an unwanted source, a missing disqualifier. That is normal
and expected — edit `<prefix>_criteria.yaml` and run again. Write every change
the person confirms into the decision log in `<prefix>_identity.md`, or in a
month nobody will remember why a setting is what it is.

---

# Second and subsequent identities

A separate section, because this is a **different** situation: an identity
already exists, it works, and it has an accumulated base and history. Everything
above is written for "there is nothing", and step 0 there says outright "it
named an identity → no onboarding needed". Here onboarding IS needed, just a
different one.

## Recognising the request

A person almost never says "add an identity". They say:

- "can we set up another filter, another search?"
- "I want to look for a full-time role in parallel"
- "can we do the same for my friend / my wife?"
- "I want to try another stack without breaking the current search"

All of that is a request for a new identity. It is **not** an edit to the
existing one: blending a second goal into criteria that are already tuned makes
both shortlists worse, and the report will make that almost impossible to spot.

## The procedure

**1. Decide whether a new identity is really needed.** Three questions, in
order:

| Question | If yes |
|---|---|
| Is this a different **person** (different CV, residency, languages)? | A new identity, no question |
| Is it the same person but with **opposite criteria** (part-time versus full-time, "dull" versus interesting)? | A new identity |
| Is it simply a **refinement** of the current search (add a source, drop an unwanted filter)? | NOT a new identity — edit the existing one |

The third case is the commonest, and confusing it with the first two is
expensive: a superfluous identity splits an accumulated base into two incomplete
ones.

**1a. If the new search resembles an existing one, clone it rather than
assembling it again.** The typical case: "the same thing, but for another
country".

```bash
python tools/identity.py clone --from <source> --prefix <new> --name "<expansion>"
```

Stack, employment type, marks of a suitable company and sources are shared for
such a search; the geography rules, language filter and time zone are not. The
command prints the list of what must be checked in the clone. More in
`docs/IDENTITIES.md`, "Cloning".

If the new search does not resemble the existing one, take the ordinary route:

**2. Go through steps 2-4 of ordinary onboarding** — information about the
person, a prefix, the questionnaire. Reuse nothing from the existing identity,
even for the same person: the geography rules and languages are derived from the
answers, and the two identities' goals differ by definition.

If it is the same person, whose CV is already in another identity's
`documents/`, there is no need to copy the file: point the new
`<prefix>_profile.yaml → owner.cv_files` at the existing path. Personal
documents are not duplicated.

**3. Check how a run will be launched from now on.** With one identity, tools
pick it silently. With two, a command without `--identity` refuses, naming both:

```bash
python tools/identity.py which     # should name an identity, not a list
```

That refusal is deliberate — silently picking the wrong identity is the failure
the whole system exists to prevent. But it does mean that the habit of typing
`python tools/pipeline.py` with no flags stops working, including for the
identity that had been working for months. Agree with the person which identity
is the usual one and remind them the flag is now needed.

**4. Compare against the template.** The existing identity may have moved ahead
of its template or fallen behind:

```bash
python tools/templates.py check --identity <new-prefix>
```

**5. Run and check.**

```bash
python tools/doctor.py   --identity <new-prefix>
python tools/pipeline.py --identity <new-prefix>
```

A new identity has its own `data/<prefix>/` folder — the base starts from
nothing, and that is normal. The first runs will yield few candidates.

## Checking the isolation

It is worth confirming once, with your own eyes, that the identities really do
not overlap:

```bash
python tools/identity.py list                       # both present
python tools/kb.py stats --identity <first>         # its own base
python tools/kb.py stats --identity <second>        # its own, different
```

The numbers must differ, and `data/<first>/` and `data/<second>/` must be
different folders. The isolation is guaranteed by code
(`common.require_identity()` and the `data/<prefix>/.identity` marker), but
seeing it once is useful.

---

## What must not be done

- Starting a search without an active identity.
- Copying somebody else's identity and editing it to fit (their geography and
  languages are theirs).
- Putting a CV or a personal email address into `identity-templates/` — that
  folder is shared and is in git.
- Synchronising the `ftf` fixture with live identities: it is frozen
  deliberately.
