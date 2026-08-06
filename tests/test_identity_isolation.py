"""
The no-leak test — the central guarantee of the multi-user architecture.

It checks that after switching from identity A to B, nothing of A is left: no
paths, no data, no caches. This is the failure impossible to spot by eye — the
report looks fine, it is simply wrong — so it has to be caught automatically.


Both identities used here are fixtures in temporary directories, so the test
does not depend on which identities actually live in the repository.
"""
import shutil

import pytest

import common
import identity
import kb
import score


TEST_IDENTITY = "ftf"


@pytest.fixture
def two_identities(tmp_path, monkeypatch):
    """Creates two complete identities (aaaa and bbbb) in a temporary folder.

    aaaa: the remote-only source weworkremotely is enabled
    bbbb: the NOT remote-only source arbeitnow is enabled
    The different sets are what catches a leak of the _remote_only_sources() cache.
    """
    identities_dir = tmp_path / "identities"
    src = identity.identity_dir(TEST_IDENTITY)

    for prefix, sources_yaml in (
        ("aaaa", "sources:\n  - name: weworkremotely\n    enabled: true\n    remote_only: true\n"),
        ("bbbb", "sources:\n  - name: arbeitnow\n    enabled: true\n    remote_only: false\n"),
    ):
        # The folder name carries an expansion (the naming rule); the files inside
        # carry the short prefix.
        d = identities_dir / f"{prefix}-isolation-test-identity"
        d.mkdir(parents=True)
        # Profile and criteria are copied from the fixture — the contents do not
        # matter here, the structure and the isolation do.
        for name in ("profile.yaml", "criteria.yaml"):
            shutil.copy(src / f"{TEST_IDENTITY}_{name}", d / f"{prefix}_{name}")
        (d / f"{prefix}_sources.yaml").write_text(sources_yaml, encoding="utf-8")
        (d / f"{prefix}_identity.md").write_text(f"# {prefix}\n", encoding="utf-8")
        (d / f"{prefix}_questionnaire.yaml").write_text(
            f"schema_version: 1\nidentity_prefix: {prefix}\nanswers: []\n", encoding="utf-8"
        )

    monkeypatch.setattr(common, "IDENTITIES_DIR", identities_dir)
    # Fixtures are found by the identity scan too; for the duration of this test
    # they have to go, or ftf would end up in the sandbox as well.
    monkeypatch.setattr(common, "FIXTURES_DIR", tmp_path / "no-fixtures")
    monkeypatch.setattr(common, "DATA_ROOT", tmp_path / "data")
    # And REPORTS_ROOT too. A real case, 2026-08-04: only DATA_ROOT was replaced,
    # and the test created reports/archive/aaaa and .../bbbb right inside the
    # person's actual reports folder. Empty folders, but they sat there for
    # months in the one place a person really looks.
    monkeypatch.setattr(common, "REPORTS_ROOT", tmp_path / "reports")
    yield tmp_path
    # Return the process to the state the other tests expect
    monkeypatch.undo()
    common.activate_identity(TEST_IDENTITY, allow_fixture=True)


def test_data_written_under_a_is_invisible_under_b(two_identities):
    common.activate_identity("aaaa", allow_fixture=True)
    common.ensure_dirs()
    kb.save_vacancies({"vac-1": {"id": "vac-1", "title": "Identity A secret"}})
    assert len(kb.load_vacancies()) == 1

    common.activate_identity("bbbb", allow_fixture=True)
    common.ensure_dirs()
    assert kb.load_vacancies() == {}, "B's database must be empty — A's data is not its business"


def _identity_paths() -> dict:
    return {
        "vacancies": common.VACANCIES_PATH,
        "companies": common.COMPANIES_PATH,
        "state": common.STATE_PATH,
        "reports_archive": common.REPORTS_ARCHIVE_DIR,
        "raw": common.RAW_DIR,
    }


def test_paths_of_two_identities_share_no_components(two_identities):
    common.activate_identity("aaaa", allow_fixture=True)
    a_paths = _identity_paths()

    common.activate_identity("bbbb", allow_fixture=True)
    b_paths = _identity_paths()

    for key in a_paths:
        assert a_paths[key] != b_paths[key], f"path '{key}' matched for two identities"
        assert "aaaa" not in str(b_paths[key]), f"A's prefix leaked into B's path '{key}'"


def test_reports_folder_is_shared_but_files_are_not(two_identities):
    """The one deliberate exception to path isolation.

    The `reports/` folder is shared: a person opens it by hand and wants the
    latest shortlists of all their identities side by side. There is no overlap
    even so — the files differ by prefix, and the archive is split into subfolders.
    """
    common.activate_identity("aaaa", allow_fixture=True)
    a_dir, a_latest, a_archive = (
        common.REPORTS_DIR,
        common.REPORTS_DIR / f"{common.FILE_PREFIX}latest.md",
        common.REPORTS_ARCHIVE_DIR,
    )

    common.activate_identity("bbbb", allow_fixture=True)
    b_dir, b_latest, b_archive = (
        common.REPORTS_DIR,
        common.REPORTS_DIR / f"{common.FILE_PREFIX}latest.md",
        common.REPORTS_ARCHIVE_DIR,
    )

    assert a_dir == b_dir, "the reports folder is shared deliberately"
    assert a_latest != b_latest, "but the files themselves must differ by prefix"
    assert a_archive != b_archive, "archives are split per identity"
    assert a_archive.name == "aaaa" and b_archive.name == "bbbb"


def test_remote_only_cache_does_not_leak_between_identities(two_identities):
    """A regression test for one specific bug: before the refactor
    _REMOTE_ONLY_SOURCES_CACHE was a single global set, filled on first call. A's
    set of sources would then drive B's remote gate — and that gate decides
    between 'disqualify the vacancy' and 'add 4 points'."""
    common.activate_identity("aaaa", allow_fixture=True)
    a_sources = score._remote_only_sources()
    assert a_sources == {"weworkremotely"}

    common.activate_identity("bbbb", allow_fixture=True)
    b_sources = score._remote_only_sources()
    assert b_sources == set(), "B has no remote-only sources — A's cache leaked"
    assert "weworkremotely" not in b_sources


def test_criteria_and_profile_read_from_active_identity(two_identities):
    common.activate_identity("aaaa", allow_fixture=True)
    assert common.identity_config("criteria.yaml").name == "aaaa_criteria.yaml"

    common.activate_identity("bbbb", allow_fixture=True)
    assert common.identity_config("criteria.yaml").name == "bbbb_criteria.yaml"


def test_identity_hook_fires_on_every_activation(two_identities):
    """Modules with caches rely on this hook. If it ever stops being called, the
    leaks come back silently."""
    calls = []
    common.register_identity_hook(lambda: calls.append(common.ACTIVE_IDENTITY))
    try:
        common.activate_identity("aaaa", allow_fixture=True)
        common.activate_identity("bbbb", allow_fixture=True)
        # Is the hook called BEFORE ACTIVE_IDENTITY is assigned? No — after the
        # paths are bound, so the list already holds the new values
        assert len(calls) >= 2
    finally:
        common._IDENTITY_HOOKS.pop()
