# 0070 Copying a link or the CV/CL path minimizes the app

Source: the owner, 2026-10-21: "a new setting, a checkbox: copying a
vacancy's link or the CV/CL minimizes the Electron window, to open the window
the link is pasted into; it is most likely right under the app. Turn it on in
our app."
Scope: app

## Business
"Copy URL" and "Copy CV/CL Directory Path" are followed by a paste into
another window: a job board's form, a mail, a messenger. With the setting on,
the app minimizes after the copy and Windows brings forward the window that
was under it. A checkbox in "Settings...", on by default; turned off, a copy
leaves the window as it was.

## Implementation
`app/main/main.js`: an IPC `minimize-window`; `preload.js`:
`minimizeWindow()`. `app/renderer/app.js`: the setting `minimizeOnCopy`
(default true, kept in the app's settings with the others); `copyText()`
minimizes after the copy when it is on. Locales en and ru. UI tests.

## Items
- DONE - The setting, on by default; both copy buttons minimize the app; UI tests
