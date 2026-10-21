# 0067 The text filter's label reads "Search text"

Source: the owner, 2026-10-21, with a screenshot of the field labelled
"Text": "the label should be Search text".
Scope: app

## Business
The free-text filter over the vacancy list (company, board, title) was
labelled "Text", which does not say what the field does. It reads "Search
text" ("Поиск по тексту" in Russian).

## Implementation
`app/renderer/locales/en.js` and `ru.js`: `filter.text_legend`.

## Items
- DONE - The label "Search text" in both locales
