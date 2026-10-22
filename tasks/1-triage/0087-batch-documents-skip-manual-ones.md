# 0087 The document batch leaves alone a vacancy the person is generating

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

## Implementation
`tools/cv_auto.py` (the batch): before each document, skip a vacancy that
has a document task of the same kind queued or running in the queue, or that
got a version of it since the batch started; check again after a pause. The
log says "left alone: the person generates it". A test with a queued manual
task.

## Items
- TO DO - The batch skips a vacancy with a manual task of the same kind, also after a pause
