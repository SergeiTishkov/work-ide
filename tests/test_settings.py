# -*- coding: utf-8 -*-
"""Слоистые настройки: порядок, правила слияния, происхождение, заморозка.

Вопрос владельца 2026-08-05: как сделать переопределения максимально
детерминированными. Детерминизм проверяется здесь — каждое правило слияния
имеет тест, потому что «наверное, побеждает нижний слой» и есть та неявность,
ради устранения которой всё затевалось.
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
    """Три слоя на диске, подменённые под настоящие пути."""
    defaults = tmp_path / "config" / "defaults" / "criteria.yaml"
    identity = tmp_path / "identities" / "aaa" / "aaa_criteria.yaml"
    local = tmp_path / "local" / "aaa" / "aaa_criteria.yaml"
    policy = tmp_path / "config" / "settings_policy.yaml"
    _write(policy, "frozen:\n  identity.kind: нельзя менять вид идентичности\n")

    def fake_paths(document, prefix):
        return [("defaults", defaults), ("identity", identity), ("local", local)]

    monkeypatch.setattr(settings, "layer_paths", fake_paths)
    monkeypatch.setattr(settings, "frozen_keys",
                        lambda: {"identity.kind": "нельзя менять вид идентичности"})
    return defaults, identity, local


def test_later_layer_wins_and_provenance_says_which(layered):
    defaults, identity, local = layered
    _write(defaults, "thresholds:\n  hot: 60\n  cold: 10\n")
    _write(identity, "thresholds:\n  hot: 45\n")
    merged, provenance = settings.resolve("criteria", "aaa")
    assert merged["thresholds"] == {"hot": 45, "cold": 10}
    assert provenance["thresholds.hot"] == "identity"
    assert provenance["thresholds.cold"] == "defaults"


def test_local_layer_beats_identity(layered):
    """Малая Конституция сильнее идентичности — она про конкретного человека."""
    defaults, identity, local = layered
    _write(defaults, "thresholds:\n  hot: 60\n")
    _write(identity, "thresholds:\n  hot: 45\n")
    _write(local, "thresholds:\n  hot: 30\n")
    merged, provenance = settings.resolve("criteria", "aaa")
    assert merged["thresholds"]["hot"] == 30
    assert provenance["thresholds.hot"] == "local"


def test_lists_are_replaced_not_appended(layered):
    """Правило 2. Дополнение выглядит удобным ровно до первого случая, когда
    из унаследованного списка нужно что-то УБРАТЬ."""
    defaults, identity, _ = layered
    _write(defaults, "keywords: ['a', 'b', 'c']\n")
    _write(identity, "keywords: ['b']\n")
    assert settings.resolve("criteria", "aaa")[0]["keywords"] == ["b"]


def test_explicit_null_deletes_an_inherited_key(layered):
    """Правило 3: единственный способ сказать «у меня этого нет»."""
    defaults, identity, _ = layered
    _write(defaults, "gate:\n  enabled: true\n  threshold: 2\n")
    _write(identity, "gate:\n  threshold: null\n")
    merged, provenance = settings.resolve("criteria", "aaa")
    assert merged["gate"] == {"enabled": True}
    assert "gate.threshold" not in provenance


def test_frozen_key_cannot_be_overridden_and_fails_loudly(layered):
    """Заморозка — не предпочтение, а граница. Молчаливое игнорирование было
    бы хуже отказа: человек думал бы, что настройка работает."""
    defaults, identity, local = layered
    _write(defaults, "identity:\n  kind: fixture\n")
    _write(local, "identity:\n  kind: personal\n")
    with pytest.raises(settings.FrozenSettingError) as err:
        settings.resolve("criteria", "aaa")
    assert "identity.kind" in str(err.value)
    assert "нельзя менять вид идентичности" in str(err.value)


def test_conflicts_lists_every_key_set_by_more_than_one_layer(layered):
    """Переопределение — это норма, но каждое должно быть намеренным.
    Молчаливое переопределение и есть способ, которым две части конфигурации
    начинают противоречить друг другу."""
    defaults, identity, local = layered
    _write(defaults, "a: 1\nb: 2\n")
    _write(identity, "a: 10\n")
    _write(local, "a: 100\n")
    found = settings.conflicts("criteria", "aaa")
    keys = {item["key"]: item for item in found}
    assert set(keys) == {"a"}
    assert keys["a"]["winner"] == "local"
    assert [layer for layer, _ in keys["a"]["setters"]] == ["defaults", "identity", "local"]


def test_explain_shows_the_whole_chain_including_missing_layers(layered):
    defaults, identity, _ = layered
    _write(defaults, "thresholds:\n  hot: 60\n")
    _write(identity, "thresholds:\n  hot: 45\n")
    chain = {step["layer"]: step for step in
             settings.explain("criteria", "aaa", "thresholds.hot")}
    assert chain["defaults"]["value"] == 60
    assert chain["identity"]["value"] == 45
    assert chain["local"]["exists"] is False
    assert chain["local"]["has_key"] is False
