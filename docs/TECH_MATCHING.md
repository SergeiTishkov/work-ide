# How to look for technology names in vacancy text

A shared document, for every user of the project. It is about the mechanics of
matching rather than about anybody's particular stack: that a vacancy writes
`.NET`, `C++` or `Go` is equally true for any identity.

Read it before adding a technology to an identity's stack, or before fixing "the
filter is not finding something".

---

## The central rule

> Substring matching is the default behaviour, and it fails silently.

A false positive is visible: a spurious line appears in the report, a person
reads it and complains. A false **negative** is visible to nobody: the vacancy
simply never arrives, and nobody knows it existed. So misses cost more, and they
have to be hunted with measurements rather than waited for as complaints.

The most expensive mistake in the project's history was exactly a miss — below.

---

## The `.NET` case: how one missing line hid 754 vacancies

**The symptom.** The owner asked: ".NET is a popular platform, there is plenty
of work, why is none of it in the shortlist?" Measured 2026-08-05 across a base
of 11,414 vacancies:

| | |
|---|---|
| `.NET` in the title | 754 |
| reached the shortlist | **0** |
| rejected with the wording "not a .NET/JS role" | **325** |

That is, a .NET vacancy was being rejected for not being .NET.

**The cause.** A bare `.NET` was in no key list at all. Only longer forms were:
`.NET Core`, `.NET Framework`, `ASP.NET`, `C#`. The title "Senior .NET Backend
Developer" contains none of them:

```
normalize("Senior .NET Backend Developer") = "senior .net backend developer"
   contains ".net core"      -> no
   contains ".net framework" -> no
   contains "asp.net"        -> no
   contains "c#"             -> no
```

**Why `.net` was not simply added.** Because the substring `.net` is in every
mail domain and every link. The database holds a real record from Hacker News
that arrived as a vacancy title:

```
Please email me so I know which role ... (firstname)@harnly.net
```

Add `.net` to the key list and records like that become .NET vacancies.

---

## A two-part solution

Both parts are mandatory. The first does not work without the second, and the
second is dangerous without the first.

### 1. Email addresses and links are stripped BEFORE matching

`tools/textclean.py`. Each word of the text is examined separately, and a word
that looks like an email address or a link is replaced by a space.

**This is shape recognition, not address validation.** The difference is
fundamental, and it was tested on live data:

* `email.utils.parseaddr` from the standard library **did not recognise**
  `(firstname)@harnly.net` — the very record this was all started for: the
  parentheses are read as an RFC comment, leaving the local part empty;
* `email-validator` (the one inside Pydantic) would reject it all the more
  firmly: it checks that an address is real and deliverable, and `(firstname)`
  is a template.

What is wanted is not an answer to "can mail be sent here" but to "does this
word look enough like an address that searching it for a technology is
pointless". A validator answers the first and therefore keeps getting the second
wrong: everything non-standard — templates, fragments, addresses with typos — it
declares not-email, and their `.net` goes back into the search.

The boundary of caution: only unambiguous cases are removed — a word with `@` in
the shape of an address, and a word with a scheme (`http://`, `https://`) or
with `www.`. A bare domain `harnly.net` with no `@` and no scheme is **left
alone**: it is indistinguishable from `asp.net`, and the cost of the two
mistakes is not symmetric.

To check by hand:

```bash
python tools/textclean.py --show "write to jobs@example.net about asp.net"
python tools/textclean.py "write to jobs@example.net about asp.net"
```

### 2. A technology is matched by regex, not by substring

`config/tech_vocabulary.yaml`, the `matching_patterns` section:

```yaml
matching_patterns:
  ".NET":
    substring_unsafe: true
    patterns:
      - '\.net\b'
      - '\bdotnet\b'
    redundant_if: [".NET Core", ".NET Framework", "ASP.NET", "ASP.NET Core"]
```

Three fields, each closing its own failure:

| field | what happens without it |
|---|---|
| `patterns` | `.NET` is not found at all (the original bug) |
| `substring_unsafe` | `.NET` starts being found inside `asp.net` — the same bug inverted |
| `redundant_if` | one platform is counted twice: as `ASP.NET` and as `.NET` |

---

## Why this lives in `config/` rather than in an identity

By CLAUDE.md §13. The test question: "would anyone who cloned the repository be
better off?" How `.NET` is written in vacancy text is a fact about the world,
the same for everybody. Whether `.NET` is the core of somebody's stack is a fact
about a person.

Hence:

* **an identity** names the technology by its canonical name in its
  `tech_stack` — and gets correct matching for free;
* **an identity holds no regexes at all.** Pinned by the test
  `test_dotnet_pattern_lives_in_the_global_vocabulary_not_in_identities`.

The first draft of this fix put the regexes in `kisel_profile.yaml`, that is,
into one person's layer. Wrong layer: the owner and their friends share .NET,
and every new identity would have started with the same bug.

---

## The rule for short and generic words

Bought with experience; no need to repeat it. Already caught:

| key | falsely matched inside | the cost |
|---|---|---|
| `ssis` | `ai-assisted` | 1057 matches; a vacancy with no SSIS came first |
| `ssas` | the Portuguese `nossas` | vacancies in the wrong language |
| `java` | `javascript` | the Java gate never fired at all |
| `.net` | `harnly.net`, `asp.net` | 754 vacancies |
| `LESS` | `no less than` | a false stack match |
| `eor` | `theoretical` | a false hiring signal |
| `G-P` | `Mentoring-Programm` | a false EOR |
| `expo` | `exposure`, `export` | false mobile development |

Hence the rules for `technologies` in the vocabulary:

* forms shorter than 4 characters only with a qualifier (`.net core`, not
  `.net`);
* acronyms written out in full (`sql server integration services`, not `ssis`);
* homonymous names with a suffix (`.js`, ` framework`, ` language`);
* if no variant is safe, the technology moves into `matching_patterns` and gets
  a regex.

---

## Checklist: adding a technology to a stack

1. Write down every form vacancies use for it.
2. For each, ask: **is it a substring of an ordinary word or of another name?**
   Check by measurement rather than in your head:

   ```bash
   python - <<'PY'
   import json, sys; sys.path.insert(0, "tools")
   import common; common.activate_identity("<prefix>")
   v = json.load(open(common.VACANCIES_PATH, encoding="utf-8"))
   needle = "<form>"
   hits = [r for r in v.values()
           if needle in common.normalize_for_matching(
               (r.get("title") or "") + " " + (r.get("description_text") or ""))]
   print(len(hits), "matches")
   for r in hits[:15]:
       print("  ", r["title"][:70])
   PY
   ```

   Reading down the list shows at once whether the word is being caught inside
   another.
3. Safe — into `technologies`. Unsafe — into `matching_patterns` with
   `substring_unsafe: true`.
4. If the name is nested inside another (`.NET` inside `ASP.NET`), fill in
   `redundant_if`.
5. Write a test against a real string from the database, not an invented one.

---

## How to spot a hole like this without waiting for a complaint

The measurement that found the `.NET` case is worth repeating on any noticeable
change to the filters. The idea is simple: **take a technology, count its
vacancies in the base, and see how many reached the shortlist.** Zero out of
hundreds is always a reason to investigate, even when "that is just the market"
sounds plausible.

Especially when it sounds plausible: the market can be made to explain anything,
and that is exactly the mistake already made here once.
