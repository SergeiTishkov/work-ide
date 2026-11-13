# 0113 Tailored CVs built from the new parent CV: projects, location, section order by vacancy

Source: the owner, 2026-11-13
Scope: tools, config, docs

## Business
On 2026-11-12..13 the owner and the agent went through the owner's new
parent CV point by point. The review notes and the CV itself are kept
outside the repository, next to the person's other CVs. Tailored CVs come
from this parent CV, including CVs for Forward Deployed Engineer and other
AI roles. The owner asked to put everything the review decided about
generation into one task.

Compared with the old master CV that the generator reads now, the new
parent CV adds the following:

- **An "Independent projects" section, placed before Work experience.**
  It has five projects, three of them public GitHub repositories. Each
  project has a title, a link to the right of the title for the public
  ones, an intro paragraph, 3-4 bullets and a `Technologies:` line. One
  project also has an extra labelled line (`AI Systems: ...`) of concepts
  that are not tools. The owner keeps that line on purpose: it holds
  keywords that appear nowhere else in the CV.
- **A location line in the header.** It is the fourth line of the left
  column, under the stack line: city, country, time zone, "Remote" and
  the English level ("Fluent English").
- **LinkedIn and GitHub in the contacts.** They come next to email and
  phone.
- **A third Summary paragraph about the person's AI work.** Summary also
  carries the two figures the owner calls the strongest: a frame-time fix
  and the drop in QA-reported defects.
- **New skill categories.** "AI Applications", "AI-Assisted Development"
  and "DevOps & CI/CD" are new, and Skills is headed "Technologies".
- **Length.** It is 5 pages long on purpose. It is a store of material,
  not a CV to send.

As it stands, the generator cannot carry most of this:

- **The common CV is the layout model.** `config/cv_tailor_prompt.md` takes
  the sections, their order, the contacts and the skill categories from it,
  and the common CV has no projects section, no location line, no LinkedIn
  and no GitHub.
- **The content schema has no place for projects or a location.** That
  schema is `CONTENT_SCHEMA` in `tools/cv_tailor.py`. The generic
  `sections` holds only a heading and plain lines, so projects can only be
  lost or squeezed in.
- **The prompt pins several things to the common CV.** It says contacts are
  "copied exactly from the common CV", that Skills keeps the common CV's
  categories, and that Summary has 1-2 paragraphs.
- **Checked 2026-11-13: `cv_docx.read_cv_text()` reads the whole new parent
  CV (about 16,500 characters) with nothing missing.** It returns the
  location line, the project titles with their links and every
  `Technologies:` line. Two details of the output:
  - the header contacts come out as two lists, all labels first and then
    all values;
  - bullet markers are not kept, so a bullet and a plain paragraph look the
    same.
- **`cv.parent` in the local sharp profile still names the old master CV.**

The rules the owner agreed for generation, with the reasons given:

- **G1, B2B in the location line.** Add "· B2B contractor" only when the
  vacancy is explicitly a contract, B2B or contractor role; otherwise B2B is
  not mentioned. Reason: an employer that hires staff through an employer
  of record (Deel, Remote.com) can read "B2B" as "contract only" and pass.
- **G2, section order by vacancy type.** For FDE and AI vacancies,
  Independent projects comes before Work experience, as in the parent CV.
  For ordinary .NET and full-stack vacancies, Work experience comes first
  and projects after it.
- **G3, AI lines in Technologies.** Status: *proposed*; the owner has not
  confirmed it yet. For FDE and AI vacancies, "AI Applications" goes right
  after "Back End", and "AI-Assisted Development" moves lower or is
  shortened. For ordinary .NET vacancies, "AI-Assisted Development" stays,
  and "AI Applications" may be shortened or dropped.
- **G4, bullets for employer CVs only.** Several bullets of the current job
  describe the person's own AI tools introduced at that employer. They go
  into CVs sent to an employer and never into public versions (LinkedIn, a
  website, a public PDF). The one exception is the Summary sentence with
  the defects figure, which stays in every version.
- **G5, length.** The parent CV may be longer than 4 pages. A tailored CV
  is 2-3 pages and keeps what the vacancy asks for.
- **G6, languages.**
  - English is written as "Fluent English" at the end of the location line,
    and the generator keeps it there.
  - "Russian (native)" is added only when the vacancy asks for Russian or
    mentions it. Otherwise Russian is not written, and Belarusian never is.
  - Reasons, from the owner's vacancies in the base on 2026-11-13. Of the 62
    the owner applied to, none asked for C1. Of the 91 waiting for an
    answer:
    - 12 asked for B2 or Upper-Intermediate;
    - 14 asked for C1 or higher, from six companies, mostly talent
      marketplaces that test English on a call;
    - 8 said "fluent" or "excellent" with no level;
    - 57 said nothing about English.
  - "Fluent" is the word vacancies use most and names no CEFR level.
  - One waiting vacancy (GR8 Tech) asks for "B2+ Ukrainian/Russian": that is
    the case for adding Russian.

Two further decisions from the review that the generator must respect:

- **Projects carry no dates.** The person fears that an ATS or a recruiter
  reads dates overlapping a full-time job as a second job.
- **Projects carry no "project for a friend" or "client project" labels.**

## Decisions of 2026-11-14

The owner settled the open questions and changed several rules above. Where
this section and the text above differ, this section holds.

- **The common CV is removed.** The parent CV is the one source of tailored
  CVs and cover letters, and their layout. The owner asked to delete the
  common CV and the old master CV from the identity's `documents/` and to
  clean the common CV out of the documentation, "so that it is certainly not
  used". The output files keep the name "CV Sergei Tishkov Software
  Engineer": the parent CV's file name without the leading "Parent".
- **English is "English B2+"** (overrides G6's "Fluent English"). The owner
  changed it in the parent CV: "Fluent English" read as an overstatement.
  The generator keeps the location line as the parent CV writes it.
- **Russian comes from the profile** (sub-ticket 4a): `owner.languages` with
  a level (`{name: Russian, level: native}`); the model adds it to the
  location line only when the vacancy asks for Russian.
- **Tailoring is free in form, fixed in facts.** The owner: fit the CV to
  the vacancy as far as it is true; mirror the vacancy's keywords; a small
  reach is fine, inventing is not. Fixed: name, contacts, location line,
  companies, titles, dates, every number, which technologies were used.
  Free: selection, order and wording. The Summary is written per vacancy (a
  management ask → the juniors the person managed; a PostgreSQL ask → SQL
  Server); its two strongest figures stay as numbers, with free words around
  them (replaces sub-ticket 6's "word for word"). Each reach is listed in
  `report.stretched` for the person to check; `check_facts()` checks the
  hard facts only.
- **Projects: placement and form by vacancy type.** Before or after the
  jobs; full, compact (a few bullets and one Technologies line) or none. For
  a plain .NET vacancy they may be cut to compact or dropped. A job of
  little relevance may be one paragraph with 2-3 technologies inline.
- **G3: the agent decides** the Technologies categories and their order by
  vacancy type; no fixed rule.
- **G4: the public mode is not built.** Every generated CV goes to an
  employer.
- **G5: 2 pages, 3 at most** (`target_pages` 2, `max_pages` 3).
- **The Innowise management bullet is the owner's own edit** to the parent
  CV, outside the repository: the person managed and mentored a junior
  developer there during a project handover.

## Implementation
In outline. Each sub-ticket gives the detail.

- **`tools/cv_tailor.py`:**
  - `CONTENT_SCHEMA` gets `location`, `projects` and the section order;
  - `check_facts()` covers the new fields;
  - `fit_length()` can cut project bullets and whole projects.
- **`config/cv_tailor_prompt.md`:**
  - the parent CV becomes the source of the layout parts the common CV
    lacks (projects, location, contacts, skill categories);
  - the rules G1-G4 and the no-dates rule.
- **`tools/cv_docx.py`:**
  - renders a project block the way the parent CV has it;
  - renders the location line in the header's left column, with an explicit
    column break before the contacts;
  - renders the project and GitHub links as real hyperlinks.
- **Cover letters (`tools/cover_letter.py`):** they share the CV's header,
  so they pick up the location line and the new contacts. Check them.
- **Tests:** `tests/test_cv_tailor.py`, the `cv_docx` rendering checks in it,
  and `tests/test_cover_letter.py`.
- **Docs:** `docs/ARCHITECTURE.md`, and "The CV per vacancy: `cv:`" in
  `docs/IDENTITIES.md`.

The person's own messages still outrank all of this (task 0086).

## Items
- DONE - Settle the open choice with the owner: the common CV is removed, the parent CV is the one source (Decisions of 2026-11-14)
- DONE - Confirm G3 with the owner: the agent decides (Decisions of 2026-11-14)
- DONE - The parent CV the one source in code: `cv_tailor`, `cover_letter`, `ai_brief`, the prompts, the free-form tailoring with `report.stretched`, the app's report label; tests
- DONE - The common CV cleaned out of the docs, the onboarding commands and the blank template (V8)
- DONE - The owner tightened the parent CV's bullet spacing (2026-11-14, 01:42): 2 pt after a bullet, 6 pt after a block's last one; `LAYOUT["bullet_space_pt"]` follows, 3 → 2
- TO DO - After the owner adds the Innowise bullet: generate the same two vacancies with the new code and show the before/after pair

## Sub-tickets

### TO DO - 1. The new parent CV in the profile
The sharp profile (`cv.parent`, local, outside git) still names the old
master CV; the partsharp profile points at the same file through
`../sharp-.../documents/`. The new parent CV goes into the identity's
`documents/` folder, and `cv.parent` names it in both profiles. Before
switching, generate a CV for one FDE vacancy and one plain .NET vacancy
with today's code. That shows what is lost before the other sub-tickets
land, and gives a before/after pair.
- TO DO - Copy the new parent CV into `documents/` and point `cv.parent` of sharp and partsharp at it
- DONE - Generate two reference CVs (one FDE or AI vacancy, one plain .NET vacancy) and keep them for comparison

### DONE - 2. Independent projects in the tailored CV
A `projects` list in the schema. Each project has:
- `title`;
- `link`, which may be empty;
- `intro`, one paragraph;
- `bullets`, each with `text`, `priority` (1-3) and `source`, as job
  bullets have;
- `tech_stack`;
- `extra_lines`: zero or more labelled lines such as `AI Systems: ...`,
  each with a label and items.

What the prompt says about projects:
- Take projects only from the parent CV, choose them and order them by
  relevance to the vacancy. A project the vacancy does not need may be left
  out.
- Never add dates. Never add "for a friend" or "client" labels.
- Keep a project's own numbers exactly as written, the same rule as for
  jobs.

The layout follows the parent CV:
- the title, with the link in a second column on the same line;
- the intro with space after it;
- the bullets;
- `Technologies:` in bold, then its items;
- any extra lines.

`fit_length()` cuts project bullets by priority together with job bullets.
Projects have no dates, so "oldest first" does not apply to them: they are
cut from the end of the list. A project left with no bullets goes whole.
The fact check reads project titles, links and numbers against the CVs.
- DONE - Schema, prompt rules and `cv_docx` rendering of the project block, links as real hyperlinks
- DONE - `fit_length()` cuts project bullets and whole projects; `check_facts()` covers projects; tests

### DONE - 3. Section order by vacancy type (G2)
The model decides the vacancy type from the text:
- FDE, AI engineer, LLM or agents roles, and any vacancy where AI work is
  the core;
- or an ordinary .NET or full-stack role.

It returns the section order, for example `projects_first: true|false`,
and gives its reason in `report.notes`. The prompt's "order of sections
from the common CV" gives way to this rule for the projects section only.
The person's message can override it ("projects after experience").
- DONE - The schema field (`projects.placement`), the prompt rule and the renderer following it; tests for both orders

### DONE - 4. Location line, B2B only for contract vacancies (G1)
The header's left column gets the parent CV's location line as its fourth
line: 10 pt, not bold, under the stack line.
- A column break goes before the contacts, so they never flow into the
  left column. The parent CV needed that fix too.
- "· B2B contractor" is appended only when the vacancy text explicitly says
  contract, B2B or contractor. Otherwise B2B never appears.

- The line ends with the English level, "Fluent English" (G6). If the
  line with the B2B suffix no longer fits one line of the half-page column,
  the English level moves to its own line under it.

The fact check accepts the line only if it equals the parent CV's line,
with or without that suffix. The cover letter header shows the same line.
- DONE - Schema `location`, prompt rule G1, header rendering with the column break; the fact check; tests
- DONE - The English level keeps its place as the parent CV writes it; a location line too long for the column is a warning (58 characters), not a move; tests
- DONE - Check the cover letter header with the location line

### DONE - 4a. Russian only when the vacancy asks for it (G6)
The parent CV does not mention Russian.
- When the vacancy text asks for Russian or mentions it (for example
  "B2+ Ukrainian/Russian"), the tailored CV adds "Russian (native)" after
  the English level.
- If that line gets too long, the languages go on a line of their own under
  the location line.
- `report.notes` says that Russian was added and why.
- Belarusian is never added.

The fact check needs Russian as a known fact. It can come from the local
profile (the identity's languages) or from a line in the parent CV that the
renderer does not print. That choice is part of this sub-ticket.
- DONE - Prompt rule, the fact "Russian, native" from `owner.languages`, rendering; tests: a vacancy asking for Russian gets it, a plain vacancy does not

### DONE - 5. Contacts and skill categories from the parent CV
Contacts come from the parent CV when it has them: LinkedIn and GitHub as
well as email and phone. GitHub matters most, because the projects link to
it. In the parent CV's text the labels and values come as two lists (see
Business); the prompt or the reader has to pair them in order.

Skill categories: the prompt says "keep the common CV's categories (rename
none, drop none)". With the new parent CV, its categories are the ones to
keep: "AI Applications", "AI-Assisted Development", "DevOps & CI/CD" and
"Testing & Quality". Its heading is "Technologies". The category rule
should name the parent CV's categories, or whichever CV the open choice
above makes the model.
- DONE - Contacts from the parent CV, pairing labels and values; tests
- DONE - Skill categories and heading from the parent CV; prompt and tests

### DONE - 6. Summary keeps the AI paragraph and the strongest figures
The parent CV's Summary has three paragraphs; the third is about the
person's AI work. It also has the two figures the owner named as the
strongest (2026-11-13): the frame-time fix in the second paragraph and the
QA-defects drop in the third. Today's prompt allows 1-2 paragraphs, so the
AI paragraph and the figures can silently disappear.

The rule to write:
- For FDE and AI vacancies, the AI paragraph stays.
- For other vacancies it may be shortened to one sentence.
- Both figures stay in every tailored CV, word for word as in the parent
  CV, unless the person's message says otherwise.

The length budget allows 3 paragraphs when the third is the AI one.
- DONE - Prompt rule for the AI paragraph and the two figures (as numbers; words free, Decisions of 2026-11-14); a test that the figures survive a plain .NET vacancy

### DONE - 7. AI lines in Technologies by vacancy type (G3, proposed)
This waits for the owner's confirmation (Items above).
- For FDE and AI vacancies, "AI Applications" goes right after "Back End",
  and "AI-Assisted Development" moves lower or is shortened.
- For ordinary .NET vacancies, "AI-Assisted Development" stays in place, and
  "AI Applications" may be shortened or dropped.

This is an exception to "rename none, drop none" for these two categories
only.
- DONE - G3 settled as "the agent decides": the prompt reorders or trims the categories by vacancy type

### DONE - 8. Bullets for employer CVs only (G4)
Every CV the generator makes today goes to an employer, so nothing has to
be dropped yet. The rule matters as soon as a public version is generated
(LinkedIn, a website, a public PDF). Then the generator needs two things:
- a way to know which parent-CV bullets are for employer CVs only, for
  example a marker in the parent CV, or a list in the local profile;
- a public mode that leaves those bullets out but keeps the Summary
  sentence with the defects figure, which the owner wants in every version.

Ask the owner whether a public mode is wanted before building it.
- DONE - Asked: no public mode for now (Decisions of 2026-11-14); was if yes, the marker and the public mode, with tests

### DONE - 9. Length 2-3 pages (G5)
This already holds and needs no change:
- `cv.target_pages` is 3 and `cv.max_pages` is 3, set by the owner on
  2026-10-12 when the parent CV came in;
- the prompt says the parent CV's length is not a model, and that the
  result is 2-3 pages.

The new parent CV's 5 pages change nothing here. Re-check it once the
projects section (sub-ticket 2) adds material.
- DONE - Checked: `DEFAULTS` in `tools/cv_tailor.py` and the "Length" section of the prompt already give 2-3 pages
- DONE - 2 pages, 3 at most (`DEFAULTS`); the section printed second is cut first, priority-1 bullets and then whole projects only past 3 pages; tests
