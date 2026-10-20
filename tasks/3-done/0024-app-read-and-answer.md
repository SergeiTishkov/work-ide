# 0024 Read the shortlist and answer it in a desktop app

Commits: 919db1b ac6b248 c0ec538 992d543 c9d4249 df6917a f21f535 289ed69 7ab93ea 4d1f42d 1b74c53 3d21cf3 85907fe e9112aa (2026-09-29 — 2026-10-18)
Source: the owner

## Business
A Markdown report is read, not answered. The person wants a window with a
tab per identity, the shortlist of the latest collection, and an answer on
each vacancy — applied, not for me (with a reason), wrong pick, vacancy
expired — that the next run takes into account. The vacancy link opens with
one button, the URL copies with another. A selection shows only the answers
given in its own collection. An answer must not make the list jump: a marked
vacancy folds into a stub in place, with "undo" and "Hide", and goes after
30 seconds with a draining ring and a countdown. A double click on "Not for
me" or "Wrong pick" saves at once; Ctrl+Enter saves a reason. The list shows
"N of M", ten more at a time.

## Implementation
Electron app in `app/` reading the SQLite base through named queries;
answers written to `vacancy_identity`; an answer redraws its own card and its
class count without reloading the list.

## Items
- DONE - Identity tabs, the latest selection, four answers
- DONE - Open and copy the vacancy link
- DONE - Marked vacancies keep their places as stubs, with undo, hide and a countdown
- DONE - Shown-of count, ten more at a time, keyboard saving
- DONE - An answer redraws only its card and count
