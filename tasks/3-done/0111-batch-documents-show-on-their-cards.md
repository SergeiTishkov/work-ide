# 0111 The CV/CL batch's documents show on their vacancies' cards

Source: the owner, 2026-11-02
Scope: app, tools

## Business
While a CV/CL batch runs, the vacancies waiting in it look untouched: their
"Generate CV" and "Generate Cover Letter" buttons read as usual. On
2026-11-02 a batch of 52 documents for 26 vacancies ran, and the owner saw
no sign of it on the cards ("the batch does not show a spinner on the
buttons of the vacancies it works on"). The document the batch makes at
the moment reads "Generating CV…" on its button, with no spinner; the app
knew nothing of the rest, since the batch's status file
(`data/cv_batch.json`) named only the current document.

## Implementation
`tools/cv_batch.py` writes the documents still waiting into its status
(`waiting`: identity, vacancy, kind). The app (`main/queue.js`) passes them
on with the batch task. A card's button for a document waiting in the batch
reads "In the batch…" and stays clickable: a document asked for by hand
goes to the queue with the person's instructions, and the batch leaves that
vacancy alone (`cv_auto.left_alone`, task 0087). A document being made, by
the batch or by its own task, shows a spinner beside "Generating…".

## Items
- DONE - `cv_batch.py`: `waiting` in the status; tests
- DONE - The app: "In the batch…" on the waiting documents' buttons, a spinner on the one being made; unit and UI tests. The Electron smoke test (`test/smoke/electron.spec.js`, "segment-filter-value") fails on main before this change as well
