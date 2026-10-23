# 0095 The search field and the filters take most of the width

Source: the owner, 2026-10-23
Scope: app

## Business
The owner, 2026-10-23: the search field and the filters' card at least 80%
of the available width; more, up to all of it, when the window is narrower
than the full screen.

## Implementation
- `app/renderer/styles.css`, `.search-block`: `max(80%, min(100%, 1440px))`.
  A full screen of 1843px gives 80% (1474px); a window narrows towards
  1440px and the share grows; at 1440px and below, the whole width. The
  four columns of drop-downs widen with the card.
- Test: `app/test/ui/dropdown.spec.js` at 2400, 1700 and 1200px.

## Items
- DONE - At least 80% of the width, all of it on a narrower window
