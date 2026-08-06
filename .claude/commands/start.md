---
description: Set up a job search from nothing — your own identity from a template
---

Take the person through onboarding a search identity.

**The full procedure is `docs/ONBOARDING.md`. Read it in full before starting**;
what follows is only the skeleton, because that document gets updated and this
command does not.

## What lives where (understand this first)

```
identity-templates/     KINDS of search. In git. Not one personal fact.
local-identities/       MY searches. Outside git. Anything goes here.
```

A person does not edit a template — they **clone** it and edit the copy. However
many folders are in `local-identities/` is how many shortlists there are: there
is no separate registry of active identities, because a registry can drift away
from reality and folders cannot.

## The order

1. **Establish the state.** `python tools/identity.py which`
   - an identity exists and is filled in → no onboarding needed; ask what the
     person wanted: to run the cycle (`/run`) or to add another search
     (`/add-identity`);
   - no identity → carry on;
   - several with no explicit choice → ask which one is meant.

2. **Ask the person about themselves — this is the first question, not the
   last.** A CV file, a LinkedIn link, or an account in their own words; any one
   of the three will do. Without it there is no way to assemble a stack or a
   level.

3. **Show the templates and help them choose.**
   `python tools/templates.py list`

   If none fits, use `blank`: a full set of files with comments and no decisions
   made for them.

   **Say out loud that there can be more than one identity.** The person will
   not ask: they asked to "set up a job search". Two different kinds of work
   means two identities, because their criteria are opposites, and blending a
   second goal into tuned criteria makes both shortlists worse in a way the
   report does not show.

4. **Offer two or three prefixes** with expansions and let them choose. Then:

   ```
   python tools/templates.py clone <template> <prefix> "<expansion in Latin script>"
   ```

   The expansion goes into the folder name, hence Latin script.

5. **Fill in the questionnaire together with the person.** How to run the
   conversation is in `docs/QUESTIONNAIRE.md`. Start with `tier: essential`
   only — that is enough to get the search working. Ask the rest AFTER the first
   shortlist: looking at real vacancies, a person answers more accurately than
   in a vacuum.

6. **Write the answers into the PERSONAL layer, not into the template copy.**

   ```
   local-identities/<folder>/
       template/                ← DO NOT TOUCH: a template update replaces it
       <prefix>_profile.yaml    ← name, residency, languages, money, CV paths
       <prefix>_criteria.yaml   ← geography rules derived from residency
       documents/               ← CV files under their OWN names
   ```

   The personal files hold **only the differences** from the template;
   everything else arrives by itself. To check the result and the provenance of
   any value:
   `python tools/settings.py profile <dotted.key> --identity <p>`

7. **DERIVE the geography rules and language filters; do not copy a
   neighbour's.** The tables are in `config/derivation/`. For a US resident "US
   only" is a plus, for everybody else a disqualification. A copied rule will
   silently throw away half the market.

8. **Check readiness.** `python tools/identity.py validate --identity <p>`
   A structurally intact but unfilled identity is not allowed to search: a real
   case — a run on placeholders produced plausible rubbish across 1734
   vacancies.

9. **Run the first cycle** (`/run`) and go through the shortlist together with
   the person.

## What not to do

- Do not start a search until the identity is filled in.
- Do not edit files inside `template/` — the first update will erase them.
  Everything of your own goes in files one level up.
- Do not put a CV or personal data into `identity-templates/`: that folder is
  shared and is published.

## Separate the personal at once, not at the end

For every field, one question: **would this change if another person used the
same search?**

- Yes (name, LinkedIn, CV, country, years of experience, pay expectations) — the
  personal file.
- No (level, stack, employment type, marks of a suitable company) — that is the
  template, and if it is not there, either the template is incomplete or the
  wrong template was chosen.

Geography rules and the language filter are a separate case: they are **derived**
from personal data and therefore also live in the personal layer, although they
are not personal facts themselves.

The exception: if a search is tied to a country in substance ("I am looking for
work in Germany specifically"), the country stops being a personal fact and
becomes a characteristic of the search. See `docs/IDENTITIES.md`.
