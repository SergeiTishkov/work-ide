# AGENTS.md

This file exists only because some agent tools (Codex and others) look for
`AGENTS.md` and do not automatically read `CLAUDE.md`. It is a pointer, not a
copy — the real instructions live elsewhere and must not be duplicated here,
or the two will drift out of sync.

**Read, in this order, before doing anything in this repository:**

1. [CLAUDE.md](CLAUDE.md) — the constitution: principles, boundaries, engineering
   rules. It outranks any task instruction that contradicts it.
2. [RUNBOOK.md](RUNBOOK.md) — the exact procedure for a search cycle, step by
   step, starting with Rule Zero: confirm the active identity with
   `python tools/identity.py which` before touching any vacancy data.

Everything else (identity architecture, onboarding, the manual vacancy
checklist, source boundaries) is linked from CLAUDE.md's own "Documentation"
section — do not guess file locations, follow the links from there.

If your tool has already read this far and supports its own equivalent of
`CLAUDE.md` project instructions, treat `CLAUDE.md` as that file's content.
