# 0134 One title for the CV and the cover letter

Source: the owner, 2026-11-20
Scope: tools, config, docs

## Business
The owner, 2026-11-20: a CV's file name and the title inside it follow the
vacancy, a cover letter's do not. The CV and the letter carry one title,
the same inside and in both file names. By default "Senior Software
Engineer"; for some vacancies another role, "AI Engineer", "Forward
Deployed Engineer" and the like. A CV once came out named with two titles
("... Senior Software Engineer Software Engineer" or similar): find it and
other naming bugs, fix them, without over-engineering; a rare slip of a
cheap model is acceptable.

Found, 2026-11-20 (sharp): the letter's model wrote its own headline,
"Senior Full-Stack Software Engineer" in 368 of 372 letters. The latest CV
of 76 vacancies out of 365 had "/", "|" or ":" in its headline; a file name
cannot hold them, so the name and the title inside differed. The doubled
case: AnywhereNow, "AI Engineer", ad8e82115665038273dd, headline "AI
Engineer / Senior Software Engineer", file "CV Sergei Tishkov AI Engineer
Senior Software Engineer". It was applied on 2026-11-18 with PDFs renamed by
hand, so its files stay as they are.

## Implementation
- `cv_tailor.file_title`: the headline as a file name holds it; the CV and
  the letter put this text inside too.
- `cv_tailor.current_title`: the headline of the vacancy's latest finished
  CV run; `cover_letter.write_letter` tells the model and puts it in as the
  letter's headline (the batch makes the CV before the letter). With no CV
  the model picks the title by the CV's rule.
- The headline rule in both prompts: "Senior Software Engineer" unless the
  vacancy hires for a role of its own kind; one title, no second after "/".
- Documents already made are not regenerated.

## Items
- DONE - The shared title, file-safe headline, prompts; tests; docs (ARCHITECTURE)
