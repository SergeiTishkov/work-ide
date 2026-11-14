# 0116 A tailored CV's file is named after its headline

Source: the owner, 2026-11-14
Scope: tools, docs

## Business
Every tailored CV had the same file name, taken from the parent CV's
name: "CV Ivan Petrov Software Engineer.pdf" for every vacancy, while the
headline in the CV's header was already the vacancy's title. An employer
sees the file name first. The owner asked for the name to follow the
vacancy, without stuffing keywords into it: a vacancy titled "Senior Full
Stack Engineer" gets "CV Ivan Petrov Senior Full Stack Engineer"; the
header's first lines carry the same title.

The headline the model writes is that title already: the vacancy's
wording when the person's level and history support it, one line of at
most 40 characters, a job title and not a list of topics
(`config/cv_tailor_prompt.md`). So the file name is the person's name
plus the headline of that version, and the two always agree. A cover
letter follows the same rule with its own headline.

`cv.output_name`, when the person set it, stays a fixed name for every
vacancy.

## Implementation
- The name: "CV" and the person's name as the parent CV's file name
  spells it ("Parent CV Ivan Petrov Software Engineer" -> "CV Ivan
  Petrov"), then the headline, with the characters a Windows file name
  cannot hold dropped. No headline, or the name not found in the file
  name: the name as before.
- The name changes between versions, so the log records each version's
  file name ("File: ..."), and the next version finds the current files
  by it to move them into `Old versions/`. A log without the line: the
  name as before.

## Items
- DONE - The file name from the headline, recorded in the log; CV and cover letter; tests; docs
