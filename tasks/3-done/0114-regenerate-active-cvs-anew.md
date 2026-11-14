# 0114 Regenerate the active vacancies' CVs anew from the parent CV

Source: the owner, 2026-11-14
Scope: tools, identity:sharp

## Business
Task 0113 made the parent CV the one source of tailored CVs. The CVs
already in the documents folder were made from the common CV. The owner
asked to regenerate every CV of the active vacancies with the new process.

Active vacancies are the ones the automatic batch picks:
- in the latest selection;
- with no answer from the person;
- matching `cv.auto`;
- not left alone by task 0087.

The vacancies the person works with keep their documents. On 2026-11-14
SHARP had 87 such vacancies: 86 with a batch-made CV and 1 found gone.
PARTSHARP's 17 have no CV yet, and the batch makes them as usual.

An ordinary new version takes the previous one as its mould: "keep what
it has, change what is asked". Here the previous version came from the
common CV, so the mould would carry the old selection into the new CV.
The regeneration needs a version made anew: the model gets neither the
log nor the previous version.

## Implementation
- `cv_tailor.py --anew`:
  - the model gets no `<log>` and no `<previous_version>`;
  - the version number still grows, and the previous version moves to
    `Old versions/`;
  - the log says the version was made anew.
- The task queue passes `anew` and `auto` from a CV task's args. A
  regeneration the batch would have made counts as the batch's:
  "Made automatically.", so the vacancy is not left alone afterwards.
- One queue task per vacancy, added by the agent.

## Items
- DONE - `--anew` in `cv_tailor.py`, the queue passing `anew` and `auto`; tests
- DONE - Queue the regeneration of SHARP's active vacancies and check the results

## Results (2026-11-14)
- 86 of 86 regenerated, all made anew, none failed. The four made before
  task 0116 got their headline names by hand, with a `File:` log line.
- Pages, by the type the model read: engineering 28 at 2 pages and 5 at 3;
  ai 15 at 3; mixed 3 at 2 and 35 at 3. The mixed share goes to task 0117.
- The fact check flagged 13 CVs, all on Technologies terms: spelling
  variants of terms the parent CV has (EF Core, REST APIs, Angular JS) and
  generic terms it does not have (Algorithms, Data Structures, Design
  Patterns, OOP, Semantic HTML, Data Modeling).
- The agent read 7 CVs against their vacancies: no must-have missed; one
  first-person phrase ("where I became"), one stretch on Scala/Java.
