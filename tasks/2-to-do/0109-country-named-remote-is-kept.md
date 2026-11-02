# 0109 A remote posting that names one country reaches the list; only a stated limit refuses it

Source: the owner, 2026-11-02
Scope: identity:sharp, config

## Business
In the week of 2026-10-26, the scripts passed 445 new postings to the AI
check, and it kept 14. It rejected 383 on location. Among the remote ones
it rejected on location alone, 30 fit the CV and 52 were stretch roles: for
example "Senior .NET Engineer (Banking)" (Scottsdale, AZ) and ".Net Software
Developer - Remote - £85,000" (Birmingham).

The cause is one sentence in `config/ai_brief_prompt.md`, there since the AI
check started on 2026-10-18: "a posting naming one country, without saying
it hires abroad, is not reachable". The brief written from that prompt
repeats it. The model therefore answers `location_ok: "no"` for any "Remote"
posting tied to one country, even when the text states no limit. The
scripts follow the opposite rule (2026-08-05, the owner): a named country is
not an objection, and only the employer's stated limits refuse. Before the
AI check, the scripts separated the two kinds: remote within one country,
and remote for anyone. On 2026-10-12..18 the person applied to 29
postings. Under today's rules 21 of them are rejected, 13 of these on
location.

The owner, 2026-11-02:
- The pipeline turns from negative prejudice to positive prejudice. The
  person can reject what does not fit by hand. Missing a good posting is
  much worse.
- A posting is refused on location only for a limit the text states. A
  country named with no such limit keeps the posting.
- There is no separate "unclear" status, section or mark for these
  postings. The score separates them instead: roughly 0 without a mention
  of worldwide remote, +20 with one. That figure was the owner's rough
  guide, and the plan below works out the best form.

What already exists: since 2026-10-05 the scripts add
`residency_eligibility.points` (30) when the text shows the employer engages
people abroad. That covers worldwide, "from any country", international
contractors and employers of record. The owner chose 30 then, after a
rescore of the whole base: +20 put 3 of 22 such vacancies among the first
twenty of hot_lead, +30 put 16 of 33 (`sharp_criteria.yaml`,
`remote_location_fit.residency_eligibility`). That bonus is the "+20" the
owner describes. Whether it still ranks worldwide postings first, once the
country-named ones are back, has to be measured.

The rule in `tasks/README.md` and CLAUDE.md §5 (task 0103) still holds:
answers already given are not read again without the owner's explicit yes.
The change acts on postings the AI check reads after it.

## Implementation
`config/ai_brief_prompt.md` loses the "naming one country" sentence. It
then names what does refuse:
- "only" or "must be based/reside in" a place;
- a right to work or a clearance;
- "Remote (US)", "Remote UK";
- the board's "Remote from: <place>";
- US or Canadian payroll benefits such as 401(k) or RRSP;
- a list of states;
- a time zone the person does not cover.

`config/ai_screen_prompt.md` → `location_ok` says the same: "no" for a
stated limit only, and a country in the location fields alone is not a
limit. After that the brief is rewritten (`tools/ai_brief.py --identity
sharp --force`).

## Items
- DONE - `config/ai_brief_prompt.md` and `config/ai_screen_prompt.md`: location refuses only on a limit the text states; the sentence on naming one country goes; a country with no stated limit is `location_ok` "unclear", which does not reject; tests
- DONE - The principle (positive prejudice: keep when in doubt, the person rejects by hand) written at the top of both prompts and in the sharp template's description ("Keep when in doubt", V35; hard disqualifier 2 now says "a residency requirement the posting states")
- TO DO - Rewrite the sharp brief and check that it no longer says a named country is unreachable
- TO DO - After the next collections: where the country-named postings land against the worldwide ones in the classes, and whether the reachability bonus (30) still puts the worldwide ones first; tune it with the owner if not
- TO DO - Ask the owner whether to read again the remote postings already rejected on location (about 1 100, roughly $15-20); only on an explicit yes
