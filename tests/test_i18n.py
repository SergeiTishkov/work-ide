# -*- coding: utf-8 -*-
"""Report language: the catalogue must not drift away from the code.

The design trade-off of "message key IS the English text" is that editing an
English string silently drops its translation. That is acceptable only because
this test finds it, rather than the owner finding a half-translated report.
"""
import ast
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))
import i18n  # noqa: E402


def _keys_used_in_code() -> set:
    """String literals passed to t() / translate() anywhere in tools/."""
    found = set()
    for path in TOOLS.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name not in ("t", "translate"):
                continue
            if node.args and isinstance(node.args[0], ast.Constant):
                value = node.args[0].value
                if isinstance(value, str):
                    found.add(value)
    return found


@pytest.mark.parametrize("lang", sorted(i18n.CATALOGUES))
def test_every_message_has_a_translation(lang):
    missing = sorted(_keys_used_in_code() - i18n.catalogue_keys(lang))
    assert not missing, (
        f"no {lang} translation for {len(missing)} message(s); the report would "
        f"render them in English: {missing[:5]}"
    )


@pytest.mark.parametrize("lang", sorted(i18n.CATALOGUES))
def test_catalogue_has_no_entries_the_code_no_longer_uses(lang):
    """Stale entries are harmless at runtime but they rot: nobody knows whether
    a line is still needed, so nobody dares delete it."""
    stale = sorted(i18n.catalogue_keys(lang) - _keys_used_in_code() - i18n.DYNAMIC_KEYS)
    assert not stale, f"{lang} catalogue has unused entries: {stale}"


def test_an_unknown_language_falls_back_to_english_rather_than_to_keys():
    assert i18n.translate("Worth a look", "xx") == "Worth a look"
    assert i18n.translate("Something never translated", "ru") == "Something never translated"


def test_language_comes_from_the_identity_and_defaults_to_english():
    assert i18n.language({}) == "en"
    assert i18n.language({"preferences": {"language": "RU"}}) == "ru"
    assert i18n.language({"preferences": {"language": "ru-RU"}}) == "ru"
    assert i18n.language({"preferences": {}}) == "en"
