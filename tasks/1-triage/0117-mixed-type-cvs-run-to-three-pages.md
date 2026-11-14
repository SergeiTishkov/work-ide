# 0117 Tailored CVs for "mixed" vacancies run to three pages

Source: the agent, 2026-11-14 (the check of the CVs regenerated in task 0114)
Scope: tools, config

## Business
The owner's rule (task 0113): a tailored CV is 2 pages, a third only when
what the vacancy needs does not fit in two.

The 86 CVs regenerated on 2026-11-14, by the type the model read:

| Type | 2 pages | 3 pages |
|---|---|---|
| engineering | 28 | 5 |
| ai | 0 | 15 |
| mixed | 3 | 35 |

For an AI-heavy role the projects come first and in full, and a third page
follows from that. For a "mixed" role (a .NET or full-stack role that also
mentions AI), 35 of 38 CVs reached the third page. Example read by the
agent: M-KOPA, "Senior Backend Engineer II & III (.NET)" — nine
Technologies lines, every job kept, the projects after the jobs; nothing
on the third page answers a requirement the first two do not.

The length is decided in code (`fit_length`): bullets of priority 2 and 3
are cut down to the target, priority-1 bullets and whole projects only
past `cv.max_pages`. So a CV whose model marks many bullets priority 1, or
keeps the projects in full, stays at three pages.

## Open question for the owner
Whether "mixed" should get to the third page as rarely as "engineering":
for example, mixed roles get compact projects by default, or the cut goes
on to the projects before it stops at three pages. A change here applies
to new versions; the existing CVs are not regenerated unless the owner
asks.

## Items
- TO DO - The owner decides; then the change and its measurement on the same 38 vacancies
