# 0140 A bare ".NET" in the title earns the personal .NET bonus

Source: the agent, 2026-11-24 (the owner asked why "Senior .NET Software Engineers - Remote, EST/CST Based" got 7 points)
Scope: tools

## Business
A card without a description is scored on its title alone. "Senior .NET
Software Engineers - Remote, EST/CST Based" (Robert Half, LinkedIn, no text)
got 7: remote +4, stack +3 (one core hit ".NET"), personal tech bonus 0.

`stack_fit` finds a bare ".NET" through the tech_matching patterns
(`\.net\b`, `\bdotnet\b`, `\bdot[ -]net\b`, `\bnet framework\b`).
`_score_personal_tech_bonus` (tools/score.py) matches only substrings from
the identity's keyword list (".net core", "asp.net", "c#", ...), which has no
bare ".net" because of mail domains (docs/TECH_MATCHING.md). So the +12
dotnet group never fires on a title like "Senior .NET Developer".

Measured 2026-11-24 on SHARP: 875 vacancies have ".NET" in the title by the
patterns and no dotnet bonus: 676 remote_unconfirmed, 177 rejected,
22 never_say_never (869 new). Most are blind LinkedIn cards scored 7.

## Items
- TO DO - The personal tech bonus also matches a keyword's tech_matching patterns, as stack_fit does (`_pattern_specs_for`, `_matches_patterns`), so a title ".NET" earns the dotnet group
- TO DO - Rescore (no AI re-read) and report how many cards change class
