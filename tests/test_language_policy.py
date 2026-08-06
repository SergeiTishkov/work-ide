"""
The repository is in English (CLAUDE.md §5).

WHY THIS IS A TEST AND NOT A NOTE

The rule was written down once already, in a session that translated 6339 lines.
A rule written down once decays: the next comment gets typed in whichever
language the conversation is happening in, and nobody notices until somebody who
does not read that language opens the file. This project has watched exactly
that happen to other rules — "clear the fixture's traces" had to move out of
documentation and into code for the same reason.

WHAT IS CHECKED, AND WHAT IS NOT

Non-Latin script is detected exactly. Prose in another Latin-script language —
a comment in German — is not, and no cheap check would catch it. That limit is
stated rather than papered over: this test closes the failure mode that has
actually occurred here (Russian), not every conceivable one.

THE EXCEPTION

The project reads vacancies in any language, so it necessarily holds fragments
of them. Those are the subject matter rather than untranslated comments, and the
test that tells them apart is:

    would translating this fragment into English break what it does?

Yes  -> it is data, and belongs in ALLOWED below with a reason.
No   -> it is an untranslated comment, and this test should fail.

Every entry in ALLOWED carries that reason. An allowlist without reasons grows
silently until it means nothing.
"""
from __future__ import annotations

import subprocess
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Script names, as unicodedata spells them at the start of a character's name.
NON_LATIN = (
    "CYRILLIC", "GREEK", "HEBREW", "ARABIC", "CJK", "HIRAGANA", "KATAKANA",
    "HANGUL", "DEVANAGARI", "THAI", "ARMENIAN", "GEORGIAN",
)

# path -> why non-Latin text in it is data rather than an untranslated comment.
#
# Adding an entry here is a deliberate act: state what the fragment does and why
# translating it would break that. If you cannot write such a sentence, the
# fragment is a comment and wants translating instead.
ALLOWED = {
    "tools/i18n.py":
        "the translation catalogue itself — the values ARE the other language",
    "config/derivation/ambiguous_places.yaml":
        "a Ukrainian phrase matched against vacancy TEXT, which is not always "
        "in English",
    "tests/test_identity.py":
        "a Cyrillic prefix as test data, proving the prefix rule rejects it",
    "tests/test_normalize.py":
        "a vacancy title in mixed scripts, proving normalisation does not "
        "mangle non-ASCII",
    "tests/test_score.py":
        "a Hebrew vacancy text, proving the unreadable-script gate fires",
}


def _tracked_files() -> list:
    """Files in git. The rule is about the REPOSITORY: what is outside git is a
    person's own, and their own files may be in their own language."""
    out = subprocess.run(["git", "ls-files"], cwd=ROOT,
                         capture_output=True, text=True, check=True)
    return [line for line in out.stdout.split("\n") if line.strip()]


def _non_latin_lines(path: Path) -> list:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []          # binary or unreadable: not our business
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        for char in line:
            try:
                name = unicodedata.name(char)
            except ValueError:
                continue
            if any(name.startswith(script) for script in NON_LATIN):
                found.append((number, line.strip()[:100]))
                break
    return found


def test_repository_is_in_english():
    """Every tracked file is English, except the ones ALLOWED names with a reason."""
    offenders = {}
    for rel in _tracked_files():
        if rel in ALLOWED:
            continue
        hits = _non_latin_lines(ROOT / rel)
        if hits:
            offenders[rel] = hits

    assert not offenders, (
        "non-Latin text outside the allowed places (CLAUDE.md §5):\n"
        + "\n".join(
            f"  {path}:{number}  {line}"
            for path, hits in sorted(offenders.items())
            for number, line in hits[:5]
        )
        + "\n\nIf translating the fragment would break what it does, add the file "
          "to ALLOWED in this test with a reason. Otherwise translate it."
    )


@pytest.mark.parametrize("path", sorted(ALLOWED))
def test_every_exception_is_still_needed(path):
    """An allowlist entry that no longer has anything to allow is stale.

    Without this, the list only ever grows: a file gets translated, its entry
    stays, and the next non-Latin line to appear in that file passes unnoticed
    under a reason that no longer applies to it.
    """
    full = ROOT / path
    assert full.exists(), f"{path} is in ALLOWED but does not exist"
    assert _non_latin_lines(full), (
        f"{path} is in ALLOWED but holds no non-Latin text any more — "
        "remove the entry so the file is checked like everything else"
    )
