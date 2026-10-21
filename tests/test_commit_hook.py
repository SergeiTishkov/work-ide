""".githooks/commit-msg: every commit names its task, and changes it (the
owner, 2026-10-20; CLAUDE.md §12 "Tasks"). The hook is run here by git itself,
in a scratch repository, so what is tested is what refuses a real commit."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / ".githooks"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def _git(repo, *args, check=True):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", check=check)


def _write(repo, rel, text="x\n"):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _git(repo, "add", rel)


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "config", "core.autocrlf", "false")
    _write(tmp_path, "tasks/1-triage/0001-an-idea.md", "# 0001 An idea\n")
    _write(tmp_path, "tasks/2-to-do/0002-agreed-work.md", "# 0002 Agreed work\n")
    _write(tmp_path, "tools/a.py")
    _git(tmp_path, "commit", "-q", "-m", "start")
    _git(tmp_path, "config", "core.hooksPath", HOOKS.as_posix())
    return tmp_path


def _commit(repo, message):
    result = _git(repo, "commit", "-q", "-m", message, check=False)
    return result.returncode == 0, result.stderr


def test_a_commit_without_a_task_line_is_refused(repo):
    _write(repo, "tools/a.py", "y\n")
    ok, err = _commit(repo, "Fix a thing")
    assert not ok and "Task: NNNN" in err


def test_a_task_that_does_not_exist_is_refused(repo):
    _write(repo, "tools/a.py", "y\n")
    ok, err = _commit(repo, "Fix a thing\n\nTask: 0099")
    assert not ok and "Task 0099" in err


def test_the_task_file_must_change_in_the_commit(repo):
    _write(repo, "tools/a.py", "y\n")
    ok, err = _commit(repo, "Fix a thing\n\nTask: 0002")
    assert not ok and "does not change" in err


def test_a_commit_that_names_and_updates_its_task_passes(repo):
    _write(repo, "tools/a.py", "y\n")
    _write(repo, "tasks/2-to-do/0002-agreed-work.md", "# 0002 Agreed work\n- DONE - it\n")
    ok, err = _commit(repo, "Fix a thing\n\nTask: 0002\n\nCo-Authored-By: someone")
    assert ok, err


def test_moving_the_task_to_done_counts_as_changing_it(repo):
    _write(repo, "tools/a.py", "y\n")
    (repo / "tasks/3-done").mkdir()
    _git(repo, "mv", "tasks/2-to-do/0002-agreed-work.md", "tasks/3-done/0002-agreed-work.md")
    ok, err = _commit(repo, "Finish\n\nTask: 0002")
    assert ok, err


def test_a_triage_task_does_not_cover_work_outside_tasks(repo):
    _write(repo, "tools/a.py", "y\n")
    _write(repo, "tasks/1-triage/0001-an-idea.md", "# 0001 An idea, measured\n")
    ok, err = _commit(repo, "Try the idea\n\nTask: 0001")
    assert not ok and "triage" in err


def test_a_cancelled_task_does_not_cover_work_outside_tasks(repo):
    _write(repo, "tools/a.py", "y\n")
    _write(repo, "tasks/4-cancelled/0004-not-wanted.md", "# 0004 Not wanted\n")
    ok, err = _commit(repo, "Do it anyway\n\nTask: 0004")
    assert not ok and "cancelled" in err


def test_cancelling_a_task_needs_no_task_line(repo):
    (repo / "tasks/4-cancelled").mkdir()
    _git(repo, "mv", "tasks/2-to-do/0002-agreed-work.md", "tasks/4-cancelled/0002-agreed-work.md")
    ok, err = _commit(repo, "Tasks: 0002 is cancelled")
    assert ok, err


def test_a_commit_of_task_files_only_needs_no_task_line(repo):
    _write(repo, "tasks/1-triage/0003-another-idea.md", "# 0003 Another idea\n")
    _write(repo, "tasks/2-to-do/0002-agreed-work.md", "# 0002 Agreed work, planned\n")
    ok, err = _commit(repo, "Tasks: another idea, a plan")
    assert ok, err


def test_deleting_a_task_that_needed_no_commit_needs_no_task_line(repo):
    _git(repo, "rm", "-q", "tasks/2-to-do/0002-agreed-work.md")
    ok, err = _commit(repo, "Tasks: 0002 needed no commit")
    assert ok, err


def test_a_change_to_the_task_system_is_not_a_task_file(repo):
    _write(repo, "tasks/README.md", "the format\n")
    ok, err = _commit(repo, "Tasks: a new rule")
    assert not ok and "Task: NNNN" in err


def test_merges_and_reverts_are_exempt(repo):
    _write(repo, "tools/a.py", "y\n")
    ok, err = _commit(repo, 'Revert "Fix a thing"')
    assert ok, err


def test_this_repository_runs_the_hook():
    if not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    configured = _git(ROOT, "config", "--get", "core.hooksPath", check=False).stdout.strip()
    assert configured == ".githooks", "turn the commit hook on: git config core.hooksPath .githooks"
