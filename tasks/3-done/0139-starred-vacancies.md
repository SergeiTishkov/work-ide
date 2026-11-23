# 0139 Starred vacancies

Source: the owner, 2026-11-24
Scope: app, tools

## Business
The owner, 2026-11-24: a vacancy can be added to the favourites. A star icon
on the title's line, at the card's right edge; when the card narrows, the
star stays in its top right corner. A new identity fit, "Starred", first of
all, holds only the vacancies the person starred.

A starred vacancy leaves its own class for "Starred" and comes back to it
when the star is clicked again. It is listed from any collection and any
market, like an application, so a later run does not take it off the list;
the statuses drop-down still applies, and a dead link is not listed unless
it is an application. The clean-up never deletes a starred vacancy.

## Items
- DONE - The table `stars` (no schema version step), the queries (`view_pool` STARRED, `star`, `unstar`), `store.setStar`, the IPC
- DONE - The star on the card, the "Starred" section and fit option first (every identity), the labels in English and Russian
- DONE - The clean-up keeps a starred vacancy (`kept_starred`); `selections.STAR_CLASS` first in the listed classes
- DONE - Tests: store unit test, UI tests (the move and back, the position wide and narrow), pytest (clean-up, vocabulary, listed classes); ARCHITECTURE
