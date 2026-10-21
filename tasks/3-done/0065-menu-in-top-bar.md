# 0065 The Menu button in the top bar, right of the language

Source: the owner, 2026-10-21, with a screenshot: "the Menu should be to
the right of the language picker, on the same line".
Scope: app

## Business
"☰ Menu" stood on its own line, under the top bar, at the right of the
identity's heading. It moves into the top bar: refresh, theme, language,
then Menu, at the window's right edge; the list opens under it as before.

## Implementation
`app/renderer/index.html`: a slot after the language picker;
`app/renderer/app.js`: the menu is drawn into it (with the panel, from the
same identity data), not into the toolbar. A UI test checks the order and
the line.

## Items
- DONE - Menu in the top bar after the language picker; UI test
