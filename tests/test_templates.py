# -*- coding: utf-8 -*-
"""Templates: versions, changelog, cloning, updating.

The main thing checked here: a template update DOES NOT TOUCH personal
settings. That property is exactly why the template copy sits in its own folder
rather than being merged with the personal files — merging texts would be the
place where an agent one day quietly loses somebody's edit.
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
    """The rule «bump the version, describe the change» is checked, not remembered.

    Rules in this project that rested on the agent's memory have broken before:
    «clear the fixture's traces» had to be moved out of documentation into code.
    """
    version = templates.template_version(name)
    entries = templates.changelog_entries(name, after=version - 1)
    assert entries, (
        f"template '{name}' declares v{version}, but CHANGELOG.md has no "
        f"'## V{version}' section. A version with no entry is useless: there is no "
        "way to tell whether the update affects local settings."
    )


@pytest.mark.parametrize("name", sorted(templates.template_folders()))
def test_template_has_no_leftover_local_sentinels(name):
    """The `local` sentinel belonged to an architecture retired on 2026-08-06,
    when identities moved outside git and there was nobody left to hide personal
    fields from. Left in a template, it reaches scoring as the string 'local'
    instead of a value, so this guards against reintroducing the pattern."""
    folder = templates.template_dir(name)
    offenders = []
    for path in folder.glob("*.yaml"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip().endswith(": local"):
                offenders.append(f"{path.name}:{number}")
    assert not offenders, f"local sentinels left behind: {offenders}"


# Ordinary words that hide a short technology token. Each one is either a real
# false match this project has shipped or the same trap one letter away — see
# docs/TECH_MATCHING.md for the class of mistake.
_WORDS_THAT_HIDE_TOKENS = [
    "defining", "definitely", "deficit", "enrollment", "philanthropic",
    "theoretical", "theory", "no less than", "express", "export", "exposure",
    "storage", "leverage", "average", "interpret", "trust", "said", "method",
    "solution", "good", "diagram", "category", "strategic", "enterprise",
    "nonetheless", "harnly.net",
]


@pytest.mark.parametrize("name", sorted(templates.template_folders()))
def test_declared_signal_keywords_do_not_hide_inside_ordinary_words(name):
    """`extra_signals` match by substring, like every keyword list in scoring.

    Found 2026-09-13 in a rendered report: "interesting work: defi" on a
    posting that said "defining engineering standards". "llm" and "anthropic"
    had the same flaw ("enrollment", "philanthropic"). A keyword may still
    EQUAL an ordinary word — that is a choice — but it must not sit inside one.
    """
    import score

    path = templates.template_dir(name) / f"{name}_criteria.yaml"
    if not path.exists():
        return
    criteria = common.load_yaml(path) or {}
    offenders = []
    for signal in criteria.get("extra_signals") or []:
        for keyword in (signal.get("keywords") or []) + (signal.get("negative_keywords") or []):
            # The needle scoring actually looks for, edge spaces included.
            needle = score.keyword_needle(keyword)
            for word in _WORDS_THAT_HIDE_TOKENS:
                if needle and needle != word and needle in f" {word} ":
                    offenders.append(f"{signal.get('name')}: '{keyword}' inside '{word}'")
    assert not offenders, offenders


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Its own set of templates and its own local-identities folder."""
    templates_root = tmp_path / "identity-templates"
    (templates_root / "aaa-test-template").mkdir(parents=True)
    monkeypatch.setattr(common, "TEMPLATES_DIR", templates_root)
    monkeypatch.setattr(common, "IDENTITIES_DIR", tmp_path / "local-identities")
    monkeypatch.setattr(common, "FIXTURES_DIR", tmp_path / "no-fixtures")
    return templates_root / "aaa-test-template"


def _write_template(folder, version, threshold):
    (folder / "template.yaml").write_text(
        f"name: aaa\nversion: {version}\nsummary: test template\n", encoding="utf-8")
    (folder / "CHANGELOG.md").write_text(
        "".join(f"## V{v} — change {v}\n\ntext\n\n" for v in range(version, 0, -1)),
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
    """The point of pinning a version: git pull does not move the shortlist.

    The template copy sits inside the identity, so updating the files in the
    repository does not affect it until the person agrees to update.
    """
    _write_template(sandbox, 1, 50)
    templates.clone("aaa", "bbb", "My Search")
    before = settings.resolve("criteria", "bbb")[0]["thresholds"]["hot"]

    _write_template(sandbox, 2, 99)          # «a git pull arrived»
    after = settings.resolve("criteria", "bbb")[0]["thresholds"]["hot"]
    assert after == before == 50

    update = templates.update_available("bbb")
    assert update["from"] == 1 and update["to"] == 2
    assert update["entries"], "there is nothing to show the person about the change"


def test_update_replaces_the_template_copy_and_keeps_personal_settings(sandbox):
    """The key property of the whole scheme: an update cannot eat a personal edit,
    because personal files take no part in the operation at all."""
    _write_template(sandbox, 1, 50)
    folder = templates.clone("aaa", "bbb", "My Search")
    (folder / "bbb_criteria.yaml").write_text(
        "thresholds:\n  cold: 1\n", encoding="utf-8")

    _write_template(sandbox, 2, 99)
    result = templates.apply_update("bbb")
    assert result["updated"] and result["to"] == 2

    merged = settings.resolve("criteria", "bbb")[0]["thresholds"]
    assert merged["hot"] == 99, "the template update did not arrive"
    assert merged["cold"] == 1, "the update overwrote a personal setting"
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
