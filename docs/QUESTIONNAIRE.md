# How to run the questionnaire

Instructions for the agent: how to talk to a person in order to assemble a
working identity. The list of questions itself is in each template's
`<prefix>_questionnaire.yaml`.

## Principles

**This is a conversation, not a form.** A person is not obliged to know what
`restrictive_region_signal` is. They say "I live in Georgia, English and
Russian, I want calm work a couple of hours a day" — turning that into
configuration is your job, not theirs.

**Guessing is forbidden.** An unfilled answer is better than an invented one: an
empty field is visible and can be clarified, while an invented one quietly
spoils the shortlist for years.

**"I don't mind" is a valid answer.** Most questions have a sensible default. Do
not push.

**Explain why you are asking** when a question looks odd. "Why does residency
matter rather than citizenship" is a fair question, and answering it makes the
conversation meaningful.

## Order

Ask in the order of the template file: it goes from general to specific, and
later questions build on earlier ones. The exception is §1, "who you are": ask
that **first**, before anything else, because a CV or LinkedIn profile often
already answers half of what follows, leaving only confirmation.

## The four mandatory blocks

These have no safe default. Without them an identity cannot be assembled, and
that is the practical form of "no identity, no search":

| Block | Why it cannot be guessed |
|---|---|
| **Residency** | ALL the geography disqualifiers are derived from it. A mistake either throws away half the market or fills the shortlist with unreachable vacancies |
| **Languages** | The filter gets the languages the person does not know. A wrong list silently cuts perfectly good vacancies |
| **The core stack** | The basis of the relevance gate: with no match, a vacancy is rejected outright |
| **Sources** | An empty set means an empty shortlist |

## Questions that need care

### Residency vs citizenship vs the right to work

Three different things, and people confuse them.

- *Residency* — where the person physically lives. It determines which "X only"
  vacancies are unavailable to them.
- *Citizenship* — determines whether they pass tests like "US citizen required".
- *The right to work* — flips the sign: with the right to work in the US, the
  phrase "us only" turns from a disqualifier into a plus.

Ask all three separately. "I am from Russia, I live in Georgia, and I have a
Polish visa" is three different answers, each with its own consequences.

### Ambiguous place names

A person usually does not suspect the problem. Prompt them:
`config/derivation/ambiguous_places.yaml` holds the frequent cases (Georgia,
Cambridge, Washington, Ontario, Odessa, Birmingham, Victoria).

The wording: "is your city or country called the same as somewhere else? It
regularly confuses search systems."

### The central trade-off: calm versus money

The most substantive question in the whole questionnaire — it sets the ratio
between the weights of `low_intensity_signal` and `compensation_signal`.

Do not ask it abstractly ("what matters more, money or comfort?"); that yields a
useless answer. Ask as a concrete choice:

> "Which would you take: guaranteed calm, predictable work at the bottom of your
> range — or noticeably more money, with signs of stress and a high pace?"

The answer should be quotable in the decision log.

### The stack, at three levels

People tend to list everything they have ever touched. Ask about **frequency in
recent roles** rather than about acquaintance:

- core — "it was in most of your recent jobs";
- strong — "regularly, but not always";
- familiar — "you came across it once or twice".

If there is a CV, offer your own breakdown from it and ask them to confirm. That
is faster and more accurate than recalling on the spot.

### Substring traps

A cheap question that saves a debugging cycle. The project has been burned three
times: `.NET` matched `VB.NET`, `LESS` matched "no less than", `eor` matched
"theoretical".

The wording: "are any of your technologies named in a way that is part of an
ordinary word, or part of another technology's name?"

### Roles to exclude

Here it particularly matters not to carry over somebody else's settings: for one
person DevOps is a disqualifier, for another it is the goal of the search. Ask
outright: "which job titles are definitely not you, even if everything else
fits?"

## After it is filled in

1. Generate `profile.yaml` and `criteria.yaml`; **derive** the geography and
   languages from the tables in `config/derivation/` rather than copying them.
2. Write `<prefix>_identity.md` from the template: what this identity is, for
   whom, which disqualifiers, which tools.
3. Check: `python tools/identity.py validate --identity <prefix>`.
4. The first run, and go through the results together with the person.

The first run almost always exposes inaccuracies. That is normal: edit the
criteria, run again, and **write every confirmed decision into the log in
`<prefix>_identity.md`** — in a month the reason for a setting will be
forgotten, and reconfiguring from memory breaks what was already fixed.
