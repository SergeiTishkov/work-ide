# 0080 Office jobs with "remote" about a product reached the top

Source: feedback review, 2026-10-22: sharp, vacancies 32041a86, 9512ffb7, bb3f0fb2, d1dadb2a, 3284f0ad, ee0bae05, 6aa298c1, 7beecaca, ae04fee8, db7aeb04
Scope: config

## Business
The person marked ten vacancies "wrong pick": office jobs in Redmond,
Boston, Austin, El Paso, Melbourne and Edmonton shown as remote. On LinkedIn
the workplace is hidden, and the only "remote" in their texts was about a
product, a server or support work ("remote PCs", "remotely deployed
software systems", "the remote gaming server"), which the scripts took for
remote work.

Closed as done without a change of its own (the owner, 2026-10-28): what
the person saw is fixed by task 0078. Nine of the ten first appeared in
selection #49 (2026-10-21 21:22 UTC), the rebuild without the AI step that
task 0078 describes; the tenth (ae04fee8) was listed from 2026-10-05,
before the AI check existed. Since task 0078 nothing reaches the top before
the AI read, and the AI check rejected all ten. The scripts still read
these words as remote; that costs one AI call per such vacancy and puts no
office job in the list, so no patterns were added.

## Items
- DONE - Checked where the ten came from: selection #49 and the time before the AI check; all ten rejected by the AI check (2026-10-28)
