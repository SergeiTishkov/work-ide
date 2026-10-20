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
    yield tmp_path
    # Return the process to the state the other tests expect
    monkeypatch.undo()
    common.activate_identity(TEST_IDENTITY, allow_fixture=True)


def test_a_vacancy_is_shared_and_the_verdict_on_it_is_not(two_identities):
    """Since 2026-10-05 the identities share one base: what a vacancy IS (its
    title, its page, its company) is fetched once for all of them. What one
    identity made of it — the score, the class, the person's answer — stays
    with that identity."""
    common.activate_identity("aaaa", allow_fixture=True)
    common.ensure_dirs()
    kb.save_vacancies({"vac-1": {"id": "vac-1", "title": "A .NET role",
                                 "computed": {"score": 77, "classification": "hot_lead"}}})

    common.activate_identity("bbbb", allow_fixture=True)
    common.ensure_dirs()
    assert kb.load_vacancies() == {"vac-1": {"id": "vac-1", "title": "A .NET role"}}, (
        "B sees the vacancy, not A's verdict on it")


def _identity_paths() -> dict:
    return {
        "data": common.DATA_DIR,
        "state": common.STATE_PATH,
        "insights": common.INSIGHTS_PATH,
    }


def test_paths_of_two_identities_share_no_components(two_identities):
    common.activate_identity("aaaa", allow_fixture=True)
    a_paths = _identity_paths()
    a_shared = (common.DB_PATH, common.RAW_DIR)

    common.activate_identity("bbbb", allow_fixture=True)
    b_paths = _identity_paths()

    for key in a_paths:
        assert a_paths[key] != b_paths[key], f"path '{key}' matched for two identities"
        assert "aaaa" not in str(b_paths[key]), f"A's prefix leaked into B's path '{key}'"
    assert (common.DB_PATH, common.RAW_DIR) == a_shared, "the base and raw/ are shared"


def test_a_remote_only_board_is_the_same_fact_for_every_identity(two_identities):
    """Whether a board publishes only remote roles is a fact about the board.
    It used to be read from the active identity's ENABLED sources, so a
    vacancy from We Work Remotely lost its proof of remoteness when scored for
    an identity that does not fetch from that board — in a shared base, every
    vacancy is scored for every identity."""
    common.activate_identity("aaaa", allow_fixture=True)
    a_sources = score._remote_only_sources()
    common.activate_identity("bbbb", allow_fixture=True)
    b_sources = score._remote_only_sources()
    assert "weworkremotely" in a_sources
    assert a_sources == b_sources
    assert "arbeitnow" not in b_sources


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
