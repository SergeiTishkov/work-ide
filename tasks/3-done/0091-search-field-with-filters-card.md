# 0091 The search field shows the filters in a card

Source: the owner, 2026-10-23
Scope: app

## Business
The owner, 2026-10-23: the eight drop-downs and the search field in one
wrapping row look poor. Wanted (a sketch in Paint):
- a search field, square-cornered as before, with a filter button inside
  its right corner;
- the button shows the filters under the field, in a card framed like a
  field, named "Filters" on its top edge;
- the button looks pressed while the filters are shown;
- the filters in four columns of two;
- the search field much wider: as wide as the card.

## Implementation
- `app/renderer/app.js`, `renderFilters()`: the search field first, then
  a `<fieldset>` "Filters" with the eight drop-downs. The button
  (`filters-toggle`, a funnel of three lines) shows and hides the card;
  `aria-pressed` and the `pressed` look while it is shown. Hiding the card
  closes an open list; the choices stay and keep filtering.
- Hidden at the first start; shown or hidden, it stays so across a refresh
  and a restart (localStorage `work-ide-filters-open`).
- `app/renderer/styles.css`: the card is a grid of four columns; it and
  the field are 4 x 205px + gaps wide (886px), or the window's width if
  narrower.
- Locales: `filter.card_legend`, `filter.show`, `filter.hide`.
- `app/test/unit/i18n.test.js`: a key written twice in a locale file
  fails. A new `filter.legend` ("Filters") had silently renamed "Status".
- Tests: the helper `check()` shows the card first; the mock starts with
  it shown (`filtersHidden` in a fixture: the app's own start).

## Items
- DONE - The search field with the filter button in its right corner
- DONE - The filters in a card, four columns of two, as wide as the field
- DONE - The button pressed while the card is shown; the state kept
- DONE - Tests: UI 140, unit 99
