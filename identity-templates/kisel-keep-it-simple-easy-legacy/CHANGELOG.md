# Change log for the KISEL template

New versions go on TOP. A section's number must match `version` in
`template.yaml` — that is checked by a test.

Entries are written so that you can tell whether a change affects your local
settings: what changed, where and why.

## V2 — the template is in English

Every comment and every explanatory string in the template was translated into
English. **No value changed**: the thresholds, weights, keyword lists and gates
are byte-for-byte what they were, which was confirmed by rescoring the whole
accumulated database — 11,414 vacancies, 0 differences in class or score.

**Does this affect your local settings?** No. Your own files sit beside the
`template/` folder and take no part in the update. If you overrode a key, the
override keeps winning.

**What you will notice.** The comments in `template/` become English. If you
read the report in another language, it does not change: the report language
follows `preferences.language` in your own profile.

## V1 — the first version

A template for a calm legacy search, assembled from a working identity after
two weeks of tuning against live data (more than 11,000 vacancies).

**What defines the search**

- The goal is INTENSITY rather than a number of hours: an undemanding
  full-time role suits as well as a moderately loaded part-time one. Reduced
  hours and a four-day week are forms of low intensity, not ends in themselves.
- The stack: .NET/C# at the core, JS/TS as a strong suit; the legacy edition of
  that stack (WebForms, EF6, jQuery, SOAP) is an advantage, not a drawback.
- Legacy and enterprise signals (`legacy`, `mainframe`, `cobol`, `bank`,
  `government`) are a plus; `greenfield`, `fast-paced`, `move fast` a minus.

**Hard rejections**, each added after a real finding in the shortlist

- not a developer role (management, sales, pre-sales, DevRel, analytics);
- infrastructure roles and DevOps, including behind a neutral title;
- QA and mobile development;
- AI-training crowdwork disguised as an engineering vacancy;
- industries the search does not go into;
- vacancies not in English.

**Mechanics that came at a price**

- technology names are matched per `docs/TECH_MATCHING.md`: short and generic
  forms are forbidden;
- the depth of a stack match matters more than the breadth of a list;
- a board's location field carries more authority than marketing phrases in the
  text, but less than the employer's own words.
