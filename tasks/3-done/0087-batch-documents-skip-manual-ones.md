# 0087 The document batch leaves alone a vacancy the person works with

Source: the owner, 2026-10-22: two sets of documents, INSO b19ed887
Scope: tools

## Business
On 2026-10-22 the owner ordered a CV and a cover letter for two vacancies
from the app at 20:12-20:13 (queue tasks 9, 16, 17, 18). At 20:12 the app
also caught up the night's schedule, and its document batch (task 13,
`cv_batch`, the documents made without a click for fresh vacancies) picked
INSO (b19ed887) at 20:14:51. The owner's INSO tasks were still queued.

What came out for INSO, all without a message and all for INSO (no mixing
between vacancies, checked in each `model_input.md`):
- CV V1 20:16:42: the batch; CV V2 20:18:35: the owner's task 17;
- CL V1 20:19:38: the owner's task 18; CL V2 20:20:33: the batch.
The batch paused at 20:16:42 ("the app is generating documents") and, on
resuming, made the letter the owner had got one second before. The current
INSO letter is the batch's, not the owner's. The owner saw versions they had
not ordered and could not tell which run made which.

The owner, the same day: no CV or CL is made automatically for a vacancy
with any feedback of the person's, or with a CV OR a cover letter the person
generated. A CV alone means no letter either: the person has most likely
worked with the vacancy already.

## Implementation
- `tools/documents.py`: a version the batch made says "Made automatically."
  in its log (`publish(auto=True)`, `--auto` to `cv_tailor.py` and
  `cover_letter.py`, which `cv_batch.py` passes); every other version is the
  person's, the ones before the mark included (none of the 208 vacancy
  folders had one kind without the other, so nothing is lost).
  `state()` gives `by_person`.
- `tools/cv_auto.py`: `left_alone()` names the vacancies with feedback (a
  status other than "new"), a document of the person's, or a CV or letter
  task queued or running in `data/tasks.sqlite`; `pick()` drops them whole.
- `tools/cv_batch.py`: `check_now()` asks `left_alone()` again before every
  document, after a hold too; the log says "left alone [i/n] ... why", the
  status counts `left_alone`.
- Tests: `test_documents.py`, `test_cv_auto.py`, `test_cv_batch.py`.

## Items
- DONE - A version the batch made is marked "Made automatically." in its log
- DONE - No document for a vacancy with feedback, a document of the person's, or a queued CV or letter task
- DONE - The batch asks again before each document, also after a pause
