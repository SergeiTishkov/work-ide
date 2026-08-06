"""pytest configuration.

It does two things:

1. Puts tools/ on sys.path so modules import flat (`import common`), exactly as
   they do when the scripts are run standalone.

2. **Activates the test identity `ftf` at module level**, not as a fixture.
   That is essential: `tests/test_score.py` reads config at module level
   (`CRITERIA = score.load_criteria()`), that is, during test COLLECTION —
   earlier than any fixture could run. Without activation here, collection
   NoActiveIdentityError.

   `ftf` is a frozen fixture (see its ftf_identity.md): the tests must not
   depend on which identity a developer happens to keep active, and must not
   go red when somebody tunes their own personal criteria.
"""
import os
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import common  # noqa: E402

TEST_IDENTITY = "ftf"

# For subprocesses, and for tools that resolve the identity themselves.
os.environ.setdefault("WORK_IDE_IDENTITY", TEST_IDENTITY)

# allow_fixture=True is the one place in the project where activating a fixture
# is permitted. In normal work common.activate_identity() rejects it.
common.activate_identity(TEST_IDENTITY, allow_fixture=True)


@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    """Redirects every data/* path into a temporary directory, so that pipeline
    and KB tests never touch the real knowledge base.

    File names here are prefixed exactly as they are in production: a test that
    accidentally hard-codes "vacancies.json" should fail, not quietly work.
    """
    data_dir = tmp_path / "data"
    knowledge_dir = data_dir / "knowledge"
    prefix = f"{TEST_IDENTITY}_"

    monkeypatch.setattr(common, "FILE_PREFIX", prefix)
    monkeypatch.setattr(common, "DATA_DIR", data_dir)
    monkeypatch.setattr(common, "KNOWLEDGE_DIR", knowledge_dir)
    monkeypatch.setattr(common, "RAW_DIR", data_dir / "raw")
    # Reports live apart from data: a shared reports/ folder, with the archive
    # inside it split per identity (see common.activate_identity).
    reports_dir = tmp_path / "reports"
    monkeypatch.setattr(common, "REPORTS_DIR", reports_dir)
    monkeypatch.setattr(common, "REPORTS_ARCHIVE_DIR", reports_dir / "archive" / TEST_IDENTITY)
    monkeypatch.setattr(common, "STATE_PATH", data_dir / f"{prefix}state.json")
    monkeypatch.setattr(common, "VACANCIES_PATH", knowledge_dir / f"{prefix}vacancies.json")
    monkeypatch.setattr(common, "COMPANIES_PATH", knowledge_dir / f"{prefix}companies.json")
    monkeypatch.setattr(common, "RECRUITERS_PATH", knowledge_dir / f"{prefix}recruiters.json")
    monkeypatch.setattr(common, "INSIGHTS_PATH", knowledge_dir / f"{prefix}insights.md")
    common.ensure_dirs()
    return data_dir


@pytest.fixture(autouse=True, scope="session")
def _no_test_writes_into_real_folders():
    """A safety net against tests writing into the REAL data and report folders.

    It catches a whole class of mistakes rather than one case: a test isolates
    its data and forgets to isolate reports (or the other way round), and litter
    appears exactly where a person looks. That is how the empty `aaaa` and `bbbb`
    folders from the isolation tests turned up in reports/archive/ (2026-08-04).

    The folder contents are compared before and after the run; an ordinary pytest
    run is known not to touch them at all.
    """
    def snapshot():
        result = {}
        for root in (common.REPORTS_ROOT, common.DATA_ROOT):
            result[root] = sorted(p.name for p in root.iterdir()) if root.exists() else None
            archive = root / "archive"
            if archive.exists():
                result[archive] = sorted(p.name for p in archive.iterdir())
        return result

    before = snapshot()
    yield
    after = snapshot()

    appeared_all = []
    for path, names_before in before.items():
        names_after = after.get(path)
        if names_before is None and names_after is None:
            continue
        for name in sorted(set(names_after or []) - set(names_before or [])):
            appeared_all.append((path, name))

    # Clear the fixture's traces FIRST, then complain.
    #
    # Detection turned out not to be enough. On 2026-08-04 this net honestly
    # failed the run, I fixed the cause — and ftf_latest.md itself simply stayed
    # in the reports folder, where a person found it a day later. Litter in the
    # one place a person actually looks is unacceptable, warning or no warning.
    cleaned = []
    try:
        import clean_fixture_artifacts
        cleaned = clean_fixture_artifacts.clean()
    except Exception as exc:  # noqa: BLE001 — cleanup must not hide the cause
        cleaned = [f"(cleanup failed: {type(exc).__name__})"]

    # Complain regardless: writing into the real folders is a defect in the test,
    # and it must be visible even once the consequences have been tidied away.
    assert not appeared_all, (
        "the tests created, in the real folders: "
        + ", ".join(f"{name} in {path}" for path, name in appeared_all)
        + (f". Cleared automatically: {cleaned}." if cleaned else ".")
        + " Isolate both DATA_ROOT and REPORTS_ROOT — see tests/test_identity_isolation.py"
    )
