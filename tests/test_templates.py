# -*- coding: utf-8 -*-
"""Шаблоны: версии, changelog, клонирование, обновление.

Главное, что здесь проверяется: обновление шаблона НЕ ТРОГАЕТ личные
настройки. Именно ради этого свойства копия шаблона лежит отдельной папкой, а
не сливается с личными файлами — слияние текстов было бы местом, где агент
однажды тихо потеряет чужую правку.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import common  # noqa: E402
import identity  # noqa: E402
import settings  # noqa: E402
import templates  # noqa: E402


@pytest.mark.parametrize("name", sorted(templates.template_folders()))
def test_template_version_matches_changelog(name):
    """Правило «поднял версию — опиши изменение» проверяется, а не помнится.

    В этом проекте правила, державшиеся на памяти агента, уже ломались:
    «убирать следы фикстуры» пришлось переносить из документации в код.
    """
    version = templates.template_version(name)
    entries = templates.changelog_entries(name, after=version - 1)
    assert entries, (
        f"шаблон '{name}' объявляет v{version}, но в CHANGELOG.md нет раздела "
        f"'## V{version}'. Версия без записи бесполезна: по ней нельзя понять, "
        "затрагивает ли обновление локальные настройки."
    )


@pytest.mark.parametrize("name", sorted(templates.template_folders()))
def test_template_has_no_leftover_local_sentinels(name):
    """Сентинел `local` — механизм прошлой архитектуры. Оставшийся в шаблоне,
    он доедет до скоринга строкой 'local' вместо значения."""
    folder = templates.template_dir(name)
    offenders = []
    for path in folder.glob("*.yaml"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip().endswith(": local"):
                offenders.append(f"{path.name}:{number}")
    assert not offenders, f"остались сентинелы local: {offenders}"


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Свой набор шаблонов и своя папка локальных идентичностей."""
    templates_root = tmp_path / "identity-templates"
    (templates_root / "aaa-test-template").mkdir(parents=True)
    monkeypatch.setattr(common, "TEMPLATES_DIR", templates_root)
    monkeypatch.setattr(common, "IDENTITIES_DIR", tmp_path / "local-identities")
    monkeypatch.setattr(common, "FIXTURES_DIR", tmp_path / "no-fixtures")
    return templates_root / "aaa-test-template"


def _write_template(folder, version, threshold):
    (folder / "template.yaml").write_text(
        f"name: aaa\nversion: {version}\nsummary: тестовый шаблон\n", encoding="utf-8")
    (folder / "CHANGELOG.md").write_text(
        "".join(f"## V{v} — изменение {v}\n\nтекст\n\n" for v in range(version, 0, -1)),
        encoding="utf-8")
    (folder / "aaa_criteria.yaml").write_text(
        f"thresholds:\n  hot: {threshold}\n  cold: 5\n", encoding="utf-8")
    (folder / "aaa_profile.yaml").write_text(
        "identity:\n  kind: personal\n", encoding="utf-8")


def test_clone_pins_the_version_and_copies_the_template(sandbox):
    _write_template(sandbox, 1, 50)
    folder = templates.clone("aaa", "bbb", "My Search")
    assert (folder / "template" / "bbb_criteria.yaml").exists()
    assert templates.pinned_version("bbb") == 1
    assert templates.update_available("bbb") is None


def test_a_newer_template_does_not_change_behaviour_until_asked(sandbox):
    """Смысл закрепления версии: git pull не двигает выдачу.

    Копия шаблона лежит внутри идентичности, поэтому обновление файлов в
    репозитории на неё не влияет, пока человек не согласится обновиться.
    """
    _write_template(sandbox, 1, 50)
    templates.clone("aaa", "bbb", "My Search")
    before = settings.resolve("criteria", "bbb")[0]["thresholds"]["hot"]

    _write_template(sandbox, 2, 99)          # «пришёл git pull»
    after = settings.resolve("criteria", "bbb")[0]["thresholds"]["hot"]
    assert after == before == 50

    update = templates.update_available("bbb")
    assert update["from"] == 1 and update["to"] == 2
    assert update["entries"], "человеку нечего показать про изменение"


def test_update_replaces_the_template_copy_and_keeps_personal_settings(sandbox):
    """Ключевое свойство всей схемы: обновление не может съесть личную правку,
    потому что личные файлы в операции вообще не участвуют."""
    _write_template(sandbox, 1, 50)
    folder = templates.clone("aaa", "bbb", "My Search")
    (folder / "bbb_criteria.yaml").write_text(
        "thresholds:\n  cold: 1\n", encoding="utf-8")

    _write_template(sandbox, 2, 99)
    result = templates.apply_update("bbb")
    assert result["updated"] and result["to"] == 2

    merged = settings.resolve("criteria", "bbb")[0]["thresholds"]
    assert merged["hot"] == 99, "не приехало обновление шаблона"
    assert merged["cold"] == 1, "обновление затёрло личную настройку"
    assert templates.pinned_version("bbb") == 2


def test_update_notes_which_personal_keys_might_be_stale(sandbox):
    _write_template(sandbox, 1, 50)
    folder = templates.clone("aaa", "bbb", "My Search")
    (folder / "bbb_criteria.yaml").write_text(
        "thresholds:\n  hot: 30\n", encoding="utf-8")
    _write_template(sandbox, 2, 99)
    result = templates.apply_update("bbb")
    assert "thresholds.hot" in result["conflicts"]


def test_clone_refuses_a_taken_prefix(sandbox):
    _write_template(sandbox, 1, 50)
    templates.clone("aaa", "bbb", "My Search")
    with pytest.raises(templates.TemplateError):
        templates.clone("aaa", "bbb", "Another Search")
