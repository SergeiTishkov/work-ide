# 0029 The app in the person's language and at a readable size

Commits: a586a59 5f34eb4 57cf6fe c8063cf c038faa 706bc76 938ad02 7c3c66c f3f6bd9 (2026-09-30 — 2026-10-20)
Source: the owner

## Business
The app speaks English and Russian, picked with a flag; a vacancy's own
lines (class, reasons, market names) follow the interface language. English
is the default and first in the list. The interface is 20% larger, cards
have more room, badges are centred, and a theme picker chooses light or
dark.

## Implementation
Interface strings and vacancy lines both from the translation tables;
language and theme kept in the app's settings.

## Items
- DONE - English and Russian, chosen by a flag; English by default
- DONE - Vacancy lines in the interface language
- DONE - Larger interface, more room, centred badges
- DONE - Theme picker
