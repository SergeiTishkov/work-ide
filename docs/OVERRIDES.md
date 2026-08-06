# Overriding settings: what beats what

A shared document. It answers the question that comes up every time a general
rule does not suit a particular person: **where do I fix this, and will the
override actually take effect?**

---

## Two kinds of setting, and that is the central distinction

The project holds settings of two fundamentally different kinds, and trying to
serve both with one mechanism is a source of confusion.

| | **Data** | **Instructions** |
|---|---|---|
| What it is | thresholds, lists, weights, keywords | CLAUDE.md, docs/, `<prefix>_identity.md` |
| Who reads it | `tools/*.py` | the agent |
| Format | YAML | prose |
| Merging | deterministic, mechanical | impossible: prose does not merge |
| Conflicts resolved by | the layer order | the agent's judgement |

**For data, determinism is fully achievable**, and it is implemented:
`tools/settings.py` applies the layers in a fixed order and returns the
provenance of every value. What won and why is a question for a tool rather than
for somebody's memory:

```bash
python tools/settings.py criteria classification_thresholds.hot_lead
python tools/settings.py criteria --conflicts
```

**For prose, determinism in the same sense is unattainable** — and not worth
chasing. Instructions are read by an agent, and an agent is not a merge
function. But the problem can be turned into a solvable one by two moves:

1. **Shrink the area where judgement is needed.** Every decision that moves out
   of prose and into YAML becomes deterministic. That is the main lever, and it
   was proven at a price: the decision "Israel and the UAE are acceptable
   regions" lived as its own keyword list instead of being derived from the
   markets table. For a week two parts of the configuration contradicted each
   other, and of 3281 European vacancies exactly one reached the shortlist.

2. **Make conflicts visible rather than resolved.** `--conflicts` shows every
   key set by more than one layer. A silent override is precisely the mechanism
   by which a configuration starts contradicting itself.

What is left to prose is what data cannot express: principles, boundaries,
explanations of why. There the priority is declared outright in CLAUDE.md ("if
the instructions for a task contradict this file, this file wins"), and there
should be no other resolution rules.

---

## Layering is not absolute: some keys are frozen

The natural consequence of "the specific beats the general" is that a personal
file can override anything. For preferences that is true. For boundaries it is
not.

`config/settings_policy.yaml` lists the keys the upper layers cannot change: the
marker of a test fixture, the ban on circumventing anti-bot protection, the ban
on personal data in git. An attempt to set them **fails the load with an
explanation** rather than being ignored silently: silent ignoring is worse than
a refusal, because the person goes on believing their setting works.

The specific beating the general is a rule about preferences, not about
boundaries.

---

## The layers, and the direction of priority

```
config/defaults/<document>.yaml                  the general rule    ← weakest
   ↓
local-identities/<folder>/template/<p>_<doc>.yaml   the kind of search
   ↓
local-identities/<folder>/<p>_<doc>.yaml            your own settings
                                                    ← strongest, outside git
```

The more specific layer wins. The logic is the same as in CLAUDE.md §13: the
narrower the layer, the closer it is to the particular case and the more rights
it has.

**The merge rules** (`tools/settings.py`), each closing a known trap:

| rule | why |
|---|---|
| dictionaries merge deeply | a layer changes one threshold without rewriting its neighbours |
| **lists are replaced whole** | appending is convenient right up to the first time something must be REMOVED from an inherited list — and there is no syntax for that |
| an explicit `null` deletes a key | the only way to say "I do not have this" |
| frozen keys fail the load | see the section above |

The template copy inside a local identity is what makes the middle layer
trustworthy: it is taken verbatim at clone time and never edited, so `git pull`
cannot move it, and a template update replaces the folder rather than merging
texts. Your own file holds only the differences.

---

## What is overridable today

| What | Shared layer | What overrides it | Can it become a plus |
|---|---|---|---|
| The weight of a company red flag | `config/derivation/company_red_flags.yaml` | `company_red_flag_severity` in the profile | **yes** |
| A market preference | — | `personal_market_bonus` | yes |
| A technology preference | — | `personal_tech_bonus` | yes |
| Target markets of the search | `config/derivation/market_tiers.yaml` | `target_markets.tiers` plus `extra_locations` | — |
| Geography rules | `config/derivation/regions.yaml` | `<p>_criteria.yaml` | — |
| How technologies are written | `config/tech_vocabulary.yaml` | — (global by design) | — |
| Any scoring weight and any list | — | `<p>_criteria.yaml` in full | yes |

### Template text that reaches the REPORT

One row of the table above is easy to miss, and it was found by regenerating the
report after the repository was translated: `identity.scoring_philosophy` is a
template value, so it is written in English like everything else in git — and it
is printed at the head of every report, which follows the person's language.

So the line came out English in an otherwise Russian report.

The fix is an override rather than an edit to the template: the identity's own
file sets `identity.scoring_philosophy` in the person's language, and the layer
order does the rest. The general rule follows:

> Template text that reaches the REPORT is English in git, and is translated by
> an override in the personal layer — never by editing the template.

`tools/i18n.py` handles the report's own fixed strings; this is for the ones
that come from configuration and are therefore different for every identity.

### Changing the sign is a legitimate case

The least obvious property, and the whole point of the exercise. The shared
catalogue rates how bad a thing is **in itself**. How bad it is **for a
particular person** depends on their circumstances, and sometimes the sign flips.

A real example, 2026-08-05: the review phrase "unpredictable work availability".
The catalogue rates it −8: for somebody living on that money, unpredictable
workload is the risk of having no income. For somebody for whom this is not the
only source, the very same phrase means "they will not load me up constantly" —
which is exactly what they are looking for. Their own file says `+6`, and the
vacancy rises instead of falling.

The absence of a clamp to non-positive values in the code is **deliberate**.

---

## What the mechanism CANNOT do, and why

> **Overrides change the SCORE. The hard gates work independently of the score.**

No personal bonus turns a rejected vacancy into a passing one. That is not an
omission but a boundary by design: a gate means "0% chance" — the wrong stack,
the wrong profession, a residency requirement, a dead link. If personal weights
could lift gates, one generous bonus would be enough to return everything
rejected on the merits back into the shortlist, and the person would never know.

Pinned by the test
`test_an_override_cannot_rescue_a_vacancy_killed_by_a_gate`.

**What to do if a gate really is wrong.** That is not a case for an override;
it is a case of a wrong gate, and the gate is what needs fixing rather than
bypassing:

1. measure how many vacancies it cuts, and how many of those it cuts ALONE (a
   measuring script below);
2. read a dozen of the rejected ones with your own eyes;
3. if it is wrong, edit `<p>_criteria.yaml` or the shared layer.

```bash
python - <<'PY'
import json, sys, collections; sys.path.insert(0, "tools")
import common; common.activate_identity("<prefix>")
v = json.load(open(common.VACANCIES_PATH, encoding="utf-8"))
solo = collections.Counter()
for r in v.values():
    d = r["computed"]["dealbreakers"]
    if len(d) == 1:
        solo[d[0].split("(")[0].strip()] += 1
for k, n in solo.most_common(15):
    print("%5d  %s" % (n, k))
PY
```

A gate that cuts a great deal **on its own** is the first candidate for review:
it alone is deciding those vacancies' fate.

---

## The trap the project has already fallen into twice

**Two parts of the configuration that do not know about each other.** Formally
nothing is broken, the tests are green, and the behaviour contradicts the
intent — with whichever part runs first winning.

| case | what one part said | what the other did | the cost |
|---|---|---|---|
| 2026-08-05 | the profile: Israel and the UAE are target markets | the location gate: "the vacancy is tied to a country" → rejected | the whole Middle East |
| 2026-08-05 | `market_tiers.yaml`: Germany, Switzerland, Britain are `importer_prime` | the same gate | 3281 European vacancies, 1 in the shortlist |

In the second case the header of `market_tiers.yaml` asserted outright that
scoring read the tiers. In fact only the LinkedIn fetcher and `markets.py` did.
**The documentation described a link that did not exist.**

Hence the rule: when adding a table to `config/`, grep for who really reads it,
and do not write presumed consumers into the header — only real ones.

---

## Checklist: a person asks for a change in behaviour

1. **Is this about the search or about the person?** About the search — the
   template. About the person (tax, family, other commitments, plans to move)
   — their own file in the local identity.
2. **Is it useful to everyone who clones the repository?** Then `config/` or
   `tools/`.
3. **Is it about the score or about rejection?** Score — override a weight.
   Rejection — that is a gate, and an override will not help; see the section
   above.
4. **Does the new setting contradict an existing one?** Grep for who reads the
   neighbouring tables. That is exactly the trap from the previous section.
5. **Measure before and after.** How many vacancies changed class is the only
   honest answer to "did it work".
