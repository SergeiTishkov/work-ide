# 0133 Filters list every option; a new source or company starts checked

Source: the owner, 2026-11-20
Scope: app

## Business
The owner, 2026-11-20, for later: the filters' checkboxes are always all
shown, however many there are, including those with zero vacancies under
them. A new source or company that appears is checked by default; from then
on it is as the person sets it.

## Implementation
- "Source": `store.sources` lists every board, the catalogue's (meta
  `source_sites`) and every one the selection holds, 0 where the view leaves
  it none. The view keeps the boards switched off (`hiddenSources`), so a
  new board comes in checked; `viewParams` turns it into `:sources`. A saved
  view with the old `sources` list is converted once, the same boards
  checked.
- "Company": every intermediary the selection holds and the "Other
  companies" row are listed, 0 where the view leaves none; the view already
  kept hidden names, so a new company comes in checked.
- "Fit": every class listed (remote_unconfirmed never).
- Tests (unit, UI) and ARCHITECTURE.

## Items
- DONE - Every option listed, zero counts included
- DONE - A new source or company checked by default
