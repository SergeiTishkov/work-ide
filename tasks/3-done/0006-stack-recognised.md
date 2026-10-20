# 0006 The person's stack is recognised, another stack is refused

Commits: 9b1357a b9e4112 0b0b9e6 e2b62da 32d1a98 892007f a44601e 7337c6b (2026-08-04 — 2026-10-01)
Source: the owner, reading the report and asking where the .NET vacancies are

## Business
The owner asked how a shortlist built from eleven thousand vacancies held
essentially no .NET. Plain ".NET" was in no keyword list: "Senior .NET
Backend Developer" scored zero on stack and was refused — 325 vacancies. The
first explanation offered ("worldwide remote is a JavaScript market") was
circular, and the owner rejected it; three defects were found instead
(task 0011 holds the location half). Shortlist 12 -> 41, with 26 .NET roles
against one.

The other direction: "Senior Ruby on Rails Developer", "Senior Fullstack
Developer (Python)" and "Senior Vue Developer" passed because their texts
list HTML, CSS and JavaScript. "Java Engineer" passed because "java" is
inside "javascript". An agency listing five web technologies outscored a
pure C# posting.

## Implementation
Shared vocabulary `config/tech_vocabulary.yaml` (every .NET developer
benefits, so not in an identity); contacts stripped from the text before
matching (".net" is in every email domain); regex where a keyword cannot
express a technology; exact comparison, never substring. Rules written up in
`docs/TECH_MATCHING.md`.

## Sub-tickets

### DONE - A title naming another stack is refused
- DONE - Title stack gate (core and strong only; the Scala/Java data-pipeline exception kept)
- DONE - Exact comparison: "java" is not "javascript", ".NET" is not "VB.NET"

### DONE - .NET recognised
- DONE - ".NET" and "Dot Net" match; contacts removed before matching
- DONE - A title naming the core stack passes (".NET and Umbraco Developer")

### DONE - Stack score rewards fit, not list length
- DONE - Without a core match the stack score stays below a real core match
- DONE - Advertising paragraphs ("NOT YOUR TECH STACK?") and outstaff boilerplate cut before scoring

### DONE - A stack nobody has read is not a stack that does not fit
Of 1510 new vacancies, 1100 had no description and 238 developer titles were
refused unread. They now wait for their text (STACK_UNREAD) and are read in a
queue of their own.
- DONE - STACK_UNREAD and description_wanted

### DONE - Keyword edges are word boundaries
" je " matched inside "jede": 18 of 72 Dutch detections were German.
- DONE - Edge spaces kept; a test checks keywords against ordinary words hiding them
