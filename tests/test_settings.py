# -*- coding: utf-8 -*-
"""Layered settings: order, merge rules, provenance, freezing.

The owner's question, 2026-08-05: how to make overrides as deterministic as
possible. The determinism is checked here — every merge rule has a test,
because "the lower layer probably wins" is exactly the implicitness this was
all started to remove.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import settings  # noqa: E402


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def layered(tmp_path, monkeypatch):
    """Three layers on disk, patched over the real paths."""
    defaults = tmp_path / "config" / "defaults" / "criteria.yaml"
    identity = tmp_path / "identities" / "aaa" / "aaa_criteria.yaml"
    local = tmp_path / "local" / "aaa" / "aaa_criteria.yaml"
    policy = tmp_path / "config" / "settings_policy.yaml"
    _write(policy, "frozen:\n  identity.kind: the kind of identity must not change\n")

    def fake_paths(document, prefix):
        return [("defaults", defaults), ("template", identity), ("local", local)]

    monkeypatch.setattr(settings, "layer_paths", fake_paths)
    monkeypatch.setattr(settings, "frozen_keys",
                        lambda: {"identity.kind": "the kind of identity must not change"})
    return defaults, identity, local


def test_later_layer_wins_and_provenance_says_which(layered):
    defaults, identity, local = layered
    _write(defaults, "thresholds:\n  hot: 60\n  cold: 10\n")
    _write(identity, "thresholds:\n  hot: 45\n")
    merged, provenance = settings.resolve("criteria", "aaa")
    assert merged["thresholds"] == {"hot": 45, "cold": 10}
    assert provenance["thresholds.hot"] == "template"
    assert provenance["thresholds.cold"] == "defaults"


def test_local_layer_beats_identity(layered):
    """The personal layer beats the template — it is about a specific person."""
    defaults, identity, local = layered
    _write(defaults, "thresholds:\n  hot: 60\n")
    _write(identity, "thresholds:\n  hot: 45\n")
    _write(local, "thresholds:\n  hot: 30\n")
    merged, provenance = settings.resolve("criteria", "aaa")
    assert merged["thresholds"]["hot"] == 30
    assert provenance["thresholds.hot"] == "local"


def test_lists_are_replaced_not_appended(layered):
    """Rule 2. Appending looks convenient right up to the first time something
    must be REMOVED from an inherited list."""
    defaults, identity, _ = layered
    _write(defaults, "keywords: ['a', 'b', 'c']\n")
    _write(identity, "keywords: ['b']\n")
    assert settings.resolve("criteria", "aaa")[0]["keywords"] == ["b"]


def test_explicit_null_deletes_an_inherited_key(layered):
    """Rule 3: the only way to say «I do not have this»."""
    defaults, identity, _ = layered
    _write(defaults, "gate:\n  enabled: true\n  threshold: 2\n")
    _write(identity, "gate:\n  threshold: null\n")
    merged, provenance = settings.resolve("criteria", "aaa")
    assert merged["gate"] == {"enabled": True}
    assert "gate.threshold" not in provenance


def test_frozen_key_cannot_be_overridden_and_fails_loudly(layered):
    """Freezing is a boundary, not a preference. Ignoring it silently would be
    worse than refusing: the person would think their setting was working."""
    defaults, identity, local = layered
    _write(defaults, "identity:\n  kind: fixture\n")
    _write(local, "identity:\n  kind: personal\n")
    with pytest.raises(settings.FrozenSettingError) as err:
        settings.resolve("criteria", "aaa")
    assert "identity.kind" in str(err.value)
    assert "the kind of identity must not change" in str(err.value)


def test_conflicts_lists_every_key_set_by_more_than_one_layer(layered):
    """Overriding is normal, but every override should be deliberate.
    A silent override is exactly how two parts of a configuration start
    contradicting each other."""
    defaults, identity, local = layered
    _write(defaults, "a: 1\nb: 2\n")
    _write(identity, "a: 10\n")
    _write(local, "a: 100\n")
    found = settings.conflicts("criteria", "aaa")
    keys = {item["key"]: item for item in found}
    assert set(keys) == {"a"}
    assert keys["a"]["winner"] == "local"
    assert [layer for layer, _ in keys["a"]["setters"]] == ["defaults", "template", "local"]


def test_explain_shows_the_whole_chain_including_missing_layers(layered):
    defaults, identity, _ = layered
    _write(defaults, "thresholds:\n  hot: 60\n")
    _write(identity, "thresholds:\n  hot: 45\n")
    chain = {step["layer"]: step for step in
             settings.explain("criteria", "aaa", "thresholds.hot")}
    assert chain["defaults"]["value"] == 60
    assert chain["template"]["value"] == 45
    assert chain["local"]["exists"] is False
    assert chain["local"]["has_key"] is False
