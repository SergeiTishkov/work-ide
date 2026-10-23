# 0097 The search field's label names what it does

Source: the owner, 2026-10-24
Scope: app

## Business
The owner, 2026-10-24: "Search text" reads as the field's content, not its
function; "Search" or "Search by text".

## Implementation
- `filter.text_legend`: "Search", and the Russian locale the same word. What is searched is already in
  the hint inside the field ("Company, board, title…"), so "by text" adds
  nothing.

## Items
- DONE - The label is "Search"
