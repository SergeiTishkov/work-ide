# PARTSHARP — part-time side work, paid as well as possible

> **PARTSHARP = part-time SHARP**: the same CV as SHARP, the opposite search.
>
> The name is the owner's own (until 2026-10-05 it was PARTSHARP). Like SHARP, it
> names what the search is for rather than a person or a stack, and
> `partsharp_` greps cleanly out of vacancy text.

## What this identity is

A search for a **second, bounded job beside a main one**. Three things decide a
vacancy, in this order:

1. **Can it be done beside a full-time job?** Part-time, freelance, fractional,
   or a stated number of hours well under a working week. A full-time role is
   not a weaker candidate here; it is an impossible one.
2. **How much does it pay?** As much as possible. The rate is graded, not merely
   noted — "$130/hour" and "$45/hour" are different vacancies.
3. **Will this CV be considered?** Interesting work the CV cannot reach is not a
   candidate, however interesting.

After those, a small plus for work that is interesting — crypto, AI products,
microservices, distributed and event-driven systems. Dull work is **neutral**:
it costs nothing, it simply does not earn the plus.

This is SHARP turned round, deliberately. SHARP wants calm legacy work and
treats crypto as a dealbreaker; PARTSHARP wants money and a bit of interest and
treats crypto as a plus. They are two identities rather than one with a filter
because blending them would make both shortlists worse without the report
showing it (CLAUDE.md, rule zero).

## Who it is for

A senior developer in .NET/C# (and JS/TS) with a main job, who wants side work
that pays. Who exactly is searching, where they live, and what money they
expect live in the local identity, outside the repository.

The identity is tuned, like SHARP, for a resident **outside the US and the EU**
working as an international contractor. That is why the geography rules are the
same as SHARP's: they follow from the residency, not from the kind of search.

## Hard disqualifiers (0% chance, not "low priority")

Everything SHARP refuses on the CV's and the residency's account, plus one of
its own:

1. **A full-time engagement, stated by the employer or the board.** "Employment
   type: Full-time", "this is a full-time position", "(Full-time)". A contract
   alone says nothing about hours — a UK day-rate contract is five days a week
   — so it is not a confirmation either.
2. **Not remote**, **a residency requirement elsewhere**, **a language the person
   does not speak**, **not software development**, **a stack outside
   .NET/JS** — as in SHARP.
3. **Beyond this CV** (`role_complexity_signal`, repurposed): research and
   applied scientists, machine-learning and MLOps engineers, data scientists,
   data and analytics engineers, protocol engineers, cryptographers, quants.
   The owner, 2026-09-13: "a data engineer, a model-training developer — they
   will not take me with my CV, no chance, no point trying. Although the work
   would be interesting."

   **Smart contracts only when they are the job** (since V5, 2026-09-14). "Smart
   Contract Engineer" or "Solidity / C# Developer" is ruled out; "Senior .NET
   Developer (Smart Contracts)" is not. The owner: "if the base is .NET and the
   vacancy reads as .NET with smart contracts rather than smart contracts with
   .NET, they must not exclude it." How that is decided is in
   `role_complexity_signal.side_specialisms`.

## What is NOT a disqualifier, and goes to a person instead

**Nobody said whether it is part-time.** Full-time is the default most postings
never write down, so silence is the common case — and refusing on it would be a
refusal by guesswork (CLAUDE.md §5). Those vacancies get their own section,
"Hours not confirmed — check by hand", with the score untouched: a 70 there is
the same 70 it would be among the hot leads.

**AI-training gigs** (Mercor, Outlier and the like). SHARP gates them as "not a
job". Here they pay, sometimes $130 an hour, and whether a paid gig is worth it
is the person's call — so they are shown with a visible minus and a label
rather than hidden.

## How pay is scored

Every stated amount becomes US dollars an hour: an hourly rate as it is, an
annual salary divided by 2080 (part-time postings quote the full-time
equivalent), a monthly one times twelve over 2080. A range counts as its middle.
The result falls into a tier (`compensation_signal.hourly_equivalent_tiers`),
and the tier gives the points. No salary stays neutral — no data is not bad pay.

## Which tools and sources it uses

| Tool | How it is used |
|---|---|
| Remote Rocketship | **The key source.** It filters by part-time and contract for real, with the type as a field and pay in USD |
| Himalayas, search mode | Also filters for real: `employment_type=Part Time` / `Contractor` |
| Remotive, Jobicy | The board's own job type, as a field |
| LinkedIn | Part-time and freelance queries; the vacancy page states "Employment type" |
| WWR, RemoteOK, Working Nomads | Broad remote boards; hours come from the text |
| HN "Who is hiring" | Queried for part-time, contract and freelance |
| Manual entry | Talent networks cannot be read by a script — see below |

**Talent networks are a manual channel.** Toptal, A.Team, Braintrust, Arc, Lemon.io,
Gun.io, Turing and Contra are where much well-paid part-time contract work
actually lives, and none of them publishes openings to an anonymous request:
you apply once and are matched. Worth a person's hour once; not a fetcher.

## Decision log

- **2026-09-13** — created, on the owner's request: "part-time; as well paid as
  possible and fitting my CV; the full opposite of SHARP. Boring work is not a
  plus now but neutral; interesting work a small plus — especially crypto, AI,
  microservices and complex technology, as long as they will still consider me
  with my CV."
- **2026-09-13** — engagement is a gate with a manual section, on the same
  pattern the owner set for remote work on 2026-08-11.
- **2026-09-13** — AI-training gigs shown with a minus rather than gated. An
  assumption, not the owner's words: SHARP's reason for gating them ("not a
  steady position") does not apply to side work that is paid by the hour.
