# 0058 Refresh is a button of its own beside the language and theme

Source: the owner, 2026-10-20 ("take the Refresh button out of the menu and
put it left of the language and theme; the same size, and just the icon, the
same one as now: one arrow in a ring")
Scope: app

## Business
Refresh is pressed often, after every change to the app or the lists, and in
the menu it took two clicks. It is now one click away in the top bar, left
of the theme and language pickers, a button of the same size with the same
ring-arrow icon; its name and hint show on hover.

## Implementation
A `refresh-slot` beside the pickers in `index.html`, drawn with them
(`renderRefreshButton`); the menu item goes. The label loses its glyph and
becomes the button's `aria-label`.

## Items
- DONE - Plan
- DONE - Refresh out of the menu into a top-bar button, left of theme and language, the same size and icon
- DONE - UI tests: order, size, icon, not in the menu; the existing Refresh tests use the button
- DONE - README and ARCHITECTURE describe where it is
