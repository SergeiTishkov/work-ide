# 0000 Search identities: one isolated search per person and goal

Commits: 90d2ea8 529d674 94bd8a4 757e8a6 1ee1311 63a6354 dc4545d f01af75 ce17c4a 4673a39 (2026-08-04 — 2026-08-06)
Source: the owner, 2026-07-31: friends should be able to use the system with their own profiles

## Business
A job search is "who is looking, and for what". Different people — or one
person with two opposite goals — need separate criteria, a separate
knowledge base and a separate report, with nothing leaking between them. The
name Work IDE means work identity: configuring a search is answering
questions about one explicit object rather than editing seven configs.

An identity that exists but is not filled in refuses to run: a fresh
scaffold had produced a 1734-vacancy report from empty settings, which looks
plausible and is worth nothing. No tool runs without a chosen identity.

A second identity for the same search bound to another country should not
mean answering fifty questions again to change three.

## Implementation
Every tool takes `--identity <prefix>` (Rule Zero, `common.require_identity()`).
The active identities are the folders that exist, not a registry file (a
registry drifted from what was on disk). `identity.py clone` copies a search
and changes only geography, language filter and time zone. The agent
commands (`/start`, `/run`, `/add-identity`) walk the same layout.

## Items
- DONE - Identity as an object: criteria, profile, knowledge and report per prefix
- DONE - Refuse to run an identity that is not filled in
- DONE - Clone an identity for another country
- DONE - Active identities from folders, no registry
- DONE - Agent commands and README describe the layout and the name
