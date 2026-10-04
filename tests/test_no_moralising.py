"""
Facts, never moral judgements (CLAUDE.md §5).

The repository records what was tried and what came back, never a
justification of the project's behaviour by principle.

The phrases below are known phrasings of such judgements. A list cannot catch
every wording; writing facts in the first place is the agent's job.

CLAUDE.md is not scanned: the rule there quotes the wording it forbids, as
examples of what not to write.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP = {
    "CLAUDE.md",                     # the rule itself, with counter-examples
    "tests/test_no_moralising.py",   # this list
}

FORBIDDEN = re.compile(
    r"circumvent"
    r"|impersonat"
    r"|posing as a browser"
    r"|pretend(?:ing)? to be"
    r"|over the line"
    r"|cross the line"
    r"|\bpolite(?:ly|ness)?\b"
    r"|honest User-Agent"
    r"|User-Agent honest"
    r"|boundary of what is allowed"
    r"|project's bounds"
    r"|never work around"
    r"|not to be worked around"
    r"|which we do not do"
    r"|we do not go\b"
    r"|fingerprint games",
    re.IGNORECASE,
)


def _tracked_files() -> list:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT,
                         capture_output=True, text=True, check=True)
    return [line for line in out.stdout.split("\n") if line.strip()]


def _hits(path: Path) -> list:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    return [(number, line.strip()[:120])
            for number, line in enumerate(text.splitlines(), 1)
            if FORBIDDEN.search(line)]


def test_no_moral_judgements_in_the_repository():
    offenders = {}
    for rel in _tracked_files():
        if rel in SKIP or rel.startswith("app/node_modules/"):
            continue
        hits = _hits(ROOT / rel)
        if hits:
            offenders[rel] = hits

    assert not offenders, (
        "a moral judgement where a fact belongs (CLAUDE.md §5):\n"
        + "\n".join(f"  {path}:{number}  {line}"
                    for path, hits in sorted(offenders.items())
                    for number, line in hits[:5])
        + "\n\nRewrite it as what was tried and what came back."
    )


def test_the_pattern_catches_what_it_is_for():
    """A guard that matches nothing guards nothing."""
    for phrase in ("We do not circumvent anti-bot protection.",
                   "an honest User-Agent carrying a contact",
                   "PAUSE_SECONDS = 1.5  # politeness",
                   "that is over the line in §5"):
        assert FORBIDDEN.search(phrase), phrase
    for phrase in ("Tried a plain GET: 403 with a Cloudflare challenge.",
                   "PAUSE_SECONDS = 1.5  # faster runs into 429s",
                   "Data must be honest about its own reliability."):
        assert not FORBIDDEN.search(phrase), phrase
