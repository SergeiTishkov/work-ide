"""
Hygiene of identities and of the template.

Checks the rules that are easy to break by hand and hard to spot by eye: one
prefix throughout a folder, no references to other identities, template
integrity, and config structure kept in step with it.
"""
import os

import pytest

import common
import identity


ALL_IDENTITIES = identity.list_identities(include_fixtures=True)


def test_repo_has_at_least_one_identity():
    assert ALL_IDENTITIES, "there should be at least one identity present"


@pytest.mark.parametrize("prefix", ALL_IDENTITIES)
def test_identity_passes_validation(prefix):
    problems = identity.validate(prefix)
    assert not problems, f"{prefix}: " + "; ".join(problems)


@pytest.mark.parametrize("prefix", ALL_IDENTITIES)
def test_identity_prefix_matches_format(prefix):
    assert identity.PREFIX_RE.match(prefix), identity.PREFIX_RULE_TEXT


@pytest.mark.parametrize("prefix", ALL_IDENTITIES)
def test_every_file_carries_its_own_prefix(prefix):
    """The system's central rule: confusing kisel_notes.md with jvst_notes.md is
    practically impossible, whereas two files called notes.md is a matter of time."""
    d = identity.identity_dir(prefix)
    offenders = [
        p.name for p in d.iterdir()
        if p.is_file()
        and p.name not in identity.KNOWN_FILES
        and not p.name.startswith(f"{prefix}_")
    ]
    assert not offenders, f"files without the prefix '{prefix}_': {offenders}"

    # The same rule applies inside template/: the template copy is renamed to the
    # identity's prefix at clone time, and if foreign names are left there, then
    # cloning did the wrong thing.
    copy_dir = d / "template"
    if copy_dir.is_dir():
        stray = [
            p.name for p in copy_dir.iterdir()
            if p.is_file()
            and p.name not in identity.KNOWN_FILES
            and not p.name.startswith(f"{prefix}_")
        ]
        assert not stray, f"files in the template copy without '{prefix}_': {stray}"


@pytest.mark.parametrize("prefix", ALL_IDENTITIES)
def test_no_references_to_other_identities(prefix):
    """Catches copy-paste from a neighbouring folder with paths half corrected."""
    problems = identity._check_foreign_prefix_leaks(prefix)
    assert not problems, "; ".join(problems)


@pytest.mark.parametrize("prefix", ALL_IDENTITIES)
def test_profile_declares_kind(prefix):
    import settings

    profile, _ = settings.resolve("profile", prefix)
    kind = (profile.get("identity") or {}).get("kind")
    assert kind in ("personal", "shared_example", "fixture"), (
        f"{prefix}: identity.kind should be personal | shared_example | fixture, not {kind!r}"
    )


# --- Template --------------------------------------------------------------

def test_template_dir_exists_and_is_complete():
    """The template is a new user's entry point; an incomplete one means
    onboarding runs into a missing file."""
    template_dir = common.TEMPLATES_DIR / identity.TEMPLATE_DIR_NAME
    assert template_dir.is_dir(), "no blank template in identity-templates/"

    for name in identity.REQUIRED_FILES:
        path = template_dir / f"{identity.TEMPLATE_PREFIX}_{name}"
        assert path.exists(), f"the template has no {path.name}"


def test_template_files_all_prefixed():
    template_dir = common.TEMPLATES_DIR / identity.TEMPLATE_DIR_NAME
    offenders = [
        p.name for p in template_dir.iterdir()
        if p.is_file()
        and p.name not in {"template.yaml", "CHANGELOG.md"}
        and not p.name.startswith(f"{identity.TEMPLATE_PREFIX}_")
    ]
    assert not offenders, f"template files without a prefix: {offenders}"


def test_template_is_not_listed_as_identity():
    """Otherwise the agent will one day try to search for work using the template."""
    assert identity.TEMPLATE_DIR_NAME not in ALL_IDENTITIES


@pytest.mark.parametrize("prefix", ALL_IDENTITIES)
def test_identity_is_not_behind_its_template(prefix):
    """A local identity must not fall silently behind its template.

    This test used to compare key structure: identities were full copies, and an
    "improvement that never arrived" looked like a missing key. The structure now
    comes from the template copy automatically, and falling behind is expressed
    as a VERSION NUMBER — a comparison rather than an analysis.
    """
    import templates

    update = templates.update_available(prefix)
    assert update is None, (
        f"{prefix}: template '{update['template']}' moved from v{update['from']} "
        f"to v{update['to']}. Update it: python tools/templates.py update "
        f"--identity {prefix}"
    )


# --- Derivation tables -----------------------------------------------------

def test_derivation_tables_present_and_wellformed():
    """The derivation tables are what a new identity's geography and language
    rules are assembled from. Without them onboarding is impossible."""
    for name, top_key in (
        ("regions.yaml", "regions"),
        ("languages.yaml", "languages"),
        ("ambiguous_places.yaml", "places"),
    ):
        path = common.shared_config("derivation") / name
        assert path.exists(), f"no config/derivation/{name}"
        data = common.load_yaml(path) or {}
        assert data.get(top_key), f"{name}: key '{top_key}' is empty or missing"


def test_regions_table_separates_residency_from_company_location():
    """The key distinction of all the geography logic: 'the company is in X' and
    'residency in X is required' are different things. The project has already
    got 'EU Remote' wrong once."""
    data = common.load_yaml(common.shared_config("derivation") / "regions.yaml")
    for name, region in data["regions"].items():
        assert "residency_required_phrases" in region, f"{name}: no residency_required_phrases"
        assert "company_located_phrases" in region, f"{name}: no company_located_phrases"
        overlap = set(region["residency_required_phrases"]) & set(region["company_located_phrases"])
        assert not overlap, (
            f"{name}: the phrases {overlap} landed in both residency and company "
            "location — those are different things and must not be mixed"
        )


def test_missing_dependency_gives_a_human_message_not_a_traceback(tmp_path):
    """The first thing a person sees on a fresh clone if they forgot to install
    the dependencies. It used to be a bare `ModuleNotFoundError: yaml`."""
    import subprocess
    import sys as _sys

    tools_dir = str(common.ROOT / "tools")
    # A stub that makes `import yaml` fail exactly as it would with nothing installed.
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
