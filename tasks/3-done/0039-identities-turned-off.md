# 0039 An identity can be turned off

Commits: 49fb489 039ecdf (2026-10-20)
Source: the owner

## Business
A search the person has paused is not collected or shown. An identity
turned off has no tab, the app opens on an active one, and turning it on
again brings everything back.

## Implementation
`active` per identity, set in the Identities dialog; the tab list and the
starting identity skip inactive ones.

## Items
- DONE - Turn off and on in the Identities dialog
- DONE - No tab for an inactive identity; the app opens on an active one
