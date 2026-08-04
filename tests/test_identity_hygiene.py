"""
Гигиена идентичностей и шаблона.

Проверяет правила, которые легко нарушить вручную и трудно заметить глазами:
единый префикс внутри папки, отсутствие ссылок на чужие идентичности,
целостность шаблона и синхронизацию структуры конфигов с ним.
"""
import os

import pytest

import common
import identity


ALL_IDENTITIES = identity.list_identities(include_fixtures=True)


def test_repo_has_at_least_one_identity():
    assert ALL_IDENTITIES, "в репозитории должна быть хотя бы одна идентичность"


@pytest.mark.parametrize("prefix", ALL_IDENTITIES)
def test_identity_passes_validation(prefix):
    problems = identity.validate(prefix)
    assert not problems, f"{prefix}: " + "; ".join(problems)


@pytest.mark.parametrize("prefix", ALL_IDENTITIES)
def test_identity_prefix_matches_format(prefix):
    assert identity.PREFIX_RE.match(prefix), identity.PREFIX_RULE_TEXT


@pytest.mark.parametrize("prefix", ALL_IDENTITIES)
def test_every_file_carries_its_own_prefix(prefix):
    """Главное правило системы: перепутать kisel_notes.md и jvst_notes.md
    практически невозможно, а два файла notes.md — вопрос времени."""
    d = identity.identity_dir(prefix)
    offenders = [p.name for p in d.iterdir() if p.is_file() and not p.name.startswith(f"{prefix}_")]
    assert not offenders, f"файлы без префикса '{prefix}_': {offenders}"


@pytest.mark.parametrize("prefix", ALL_IDENTITIES)
def test_no_references_to_other_identities(prefix):
    """Ловит копипасту из соседней папки с недоправленными путями."""
    problems = identity._check_foreign_prefix_leaks(prefix)
    assert not problems, "; ".join(problems)


@pytest.mark.parametrize("prefix", ALL_IDENTITIES)
def test_profile_declares_kind(prefix):
    profile = common.load_yaml(identity.identity_file(prefix, "profile.yaml")) or {}
    kind = (profile.get("identity") or {}).get("kind")
    assert kind in ("personal", "shared_example", "fixture"), (
        f"{prefix}: identity.kind должен быть personal | shared_example | fixture, а не {kind!r}"
    )


# --- Шаблон ---------------------------------------------------------------

def test_template_dir_exists_and_is_complete():
    """Шаблон — точка входа для нового пользователя; неполный шаблон означает,
    что онбординг упрётся в отсутствующий файл."""
    template_dir = common.IDENTITIES_DIR / identity.TEMPLATE_DIR_NAME
    assert template_dir.is_dir(), "нет identities/_template/"

    for name in identity.REQUIRED_FILES:
        path = template_dir / f"{identity.TEMPLATE_PREFIX}_{name}"
        assert path.exists(), f"в шаблоне нет {path.name}"


def test_template_files_all_prefixed():
    template_dir = common.IDENTITIES_DIR / identity.TEMPLATE_DIR_NAME
    offenders = [
        p.name for p in template_dir.iterdir()
        if p.is_file() and not p.name.startswith(f"{identity.TEMPLATE_PREFIX}_")
    ]
    assert not offenders, f"файлы шаблона без префикса: {offenders}"


def test_template_is_not_listed_as_identity():
    """Иначе агент однажды попробует искать работу по шаблону."""
    assert identity.TEMPLATE_DIR_NAME not in ALL_IDENTITIES


@pytest.mark.parametrize("prefix", ALL_IDENTITIES)
def test_identity_criteria_structure_matches_template(prefix):
    """Отсутствующий у идентичности ключ означает, что до неё не доехало
    улучшение машинерии. Это отчётный тест: он именно ловит рассинхрон, ради
    которого выбран подход 'полные копии вместо наследования'."""
    result = identity.diff_template(prefix, "criteria.yaml")
    assert not result["missing"], (
        f"{prefix}: нет ключей, которые есть в шаблоне: {result['missing']}. "
        f"Перенести вручную: python tools/identity.py diff-template --identity {prefix}"
    )


# --- Derivation-таблицы ---------------------------------------------------

def test_derivation_tables_present_and_wellformed():
    """Таблицы вывода — то, из чего собираются гео- и языковые правила новой
    идентичности. Без них онбординг невозможен."""
    for name, top_key in (
        ("regions.yaml", "regions"),
        ("languages.yaml", "languages"),
        ("ambiguous_places.yaml", "places"),
    ):
        path = common.shared_config("derivation") / name
        assert path.exists(), f"нет config/derivation/{name}"
        data = common.load_yaml(path) or {}
        assert data.get(top_key), f"{name}: пустой или отсутствует ключ '{top_key}'"


def test_regions_table_separates_residency_from_company_location():
    """Ключевое различие всей гео-логики: 'компания находится в X' и 'нужно
    резидентство в X' — разные вещи. Проект уже ошибался на 'EU Remote'."""
    data = common.load_yaml(common.shared_config("derivation") / "regions.yaml")
    for name, region in data["regions"].items():
        assert "residency_required_phrases" in region, f"{name}: нет residency_required_phrases"
        assert "company_located_phrases" in region, f"{name}: нет company_located_phrases"
        overlap = set(region["residency_required_phrases"]) & set(region["company_located_phrases"])
        assert not overlap, (
            f"{name}: фразы {overlap} попали и в резидентство, и в местоположение компании — "
            "это разные вещи, смешивать нельзя"
        )


def test_missing_dependency_gives_a_human_message_not_a_traceback(tmp_path):
    """Первое, что видит человек на свежем клоне, если забыл поставить
    зависимости. Раньше здесь был голый `ModuleNotFoundError: yaml`."""
    import subprocess
    import sys as _sys

    tools_dir = str(common.ROOT / "tools")
    # Заглушка, из-за которой `import yaml` падает так же, как без установки.
    (tmp_path / "yaml.py").write_text("raise ImportError('no yaml')", encoding="utf-8")

    result = subprocess.run(
        [_sys.executable, "-c", "import common"],
        cwd=str(tmp_path),
        env={**os.environ, "PYTHONPATH": f"{tmp_path}{os.pathsep}{tools_dir}"},
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert "requirements.txt" in result.stderr
    assert "pip install" in result.stderr
