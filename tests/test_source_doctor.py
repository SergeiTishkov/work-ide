"""
The publishing half of /source-doctor. What is pinned here is the owner's rule:
a repair is committed and pushed ONLY when a maintainer runs it. For anybody
else the fix stays in their working copy, and that is a normal outcome — an
agent must not stall on a push that was always going to fail.
"""
import pytest

import source_doctor


def test_scope_is_the_source_and_nothing_shared():
    scope = source_doctor.scope("linkedin")
    assert "tools/fetch_linkedin.py" in scope
    assert "docs/sources/linkedin.md" in scope
    assert source_doctor.in_scope("tests/test_fetch_linkedin.py", scope)
    assert source_doctor.in_scope("tests/fixtures/sources/linkedin/search.html", scope)
    assert not source_doctor.in_scope("tools/normalize.py", scope)
    assert not source_doctor.in_scope("tools/fetch_reed.py", scope)
    assert not source_doctor.in_scope("tests/fixtures/sources/reed/page.html", scope)


def test_unknown_source_has_no_scope():
    with pytest.raises(KeyError):
        source_doctor.scope("no-such-board")


@pytest.fixture
def repo(monkeypatch):
    """A fake repository: changed files, who runs it, and every git call."""
    state = {"changed": ["tools/fetch_linkedin.py", "tests/test_fetch_linkedin.py",
                         "tools/score.py"],
             "email": "tishkovsergei92@gmail.com", "branch": "app-v1",
             "upstream": "origin/app-v1", "push_fails": False, "calls": []}

    def fake_git(*args):
        state["calls"].append(args)
        if args[:2] == ("config", "user.email"):
            return 0, state["email"]
        if args[0] == "symbolic-ref":
            return (0, state["branch"]) if state["branch"] else (1, "")
        if args[0] == "rev-parse":
            return (0, state["upstream"]) if state["upstream"] else (128, "no upstream")
        if args[0] == "push":
            return (1, "rejected") if state["push_fails"] else (0, "")
        return 0, ""

    monkeypatch.setattr(source_doctor, "git", fake_git)
    monkeypatch.setattr(source_doctor, "changed_paths", lambda: list(state["changed"]))
    return state


def _publish(contract="ok", green=True):
    return source_doctor.publish(
        "linkedin", "LinkedIn pages are ten cards long",
        check_contract=lambda source: {"status": contract, "detail": "x"},
        run_tests=lambda: (green, "1 failed"))


def _committed(repo):
    return [c for c in repo["calls"] if c[0] == "commit"]


def test_a_maintainer_publishes_only_the_sources_files(repo):
    result = _publish()
    assert result["outcome"] == "published"
    commit = _committed(repo)[0]
    assert "tools/fetch_linkedin.py" in commit and "tests/test_fetch_linkedin.py" in commit
    assert "tools/score.py" not in commit, "somebody's other work is left alone"
    assert result["left_untouched"] == ["tools/score.py"]
    assert ("push",) in repo["calls"]


def test_anybody_else_keeps_the_fix_and_nothing_fails(repo):
    repo["email"] = "someone.else@example.org"
    result = _publish()
    assert result["outcome"] == "kept-local"
    assert source_doctor.EXIT_CODES["kept-local"] == 0
    assert not _committed(repo) and ("push",) not in repo["calls"]


def test_no_git_identity_is_not_a_maintainer(repo):
    repo["email"] = ""
    assert _publish()["outcome"] == "kept-local"


def test_no_upstream_keeps_the_fix_local(repo):
    repo["upstream"] = None
    assert _publish()["outcome"] == "kept-local"
    assert not _committed(repo)


def test_a_detached_head_keeps_the_fix_local(repo):
    repo["branch"] = None
    assert _publish()["outcome"] == "kept-local"


def test_a_contract_still_failing_is_refused(repo):
    result = _publish(contract="broken")
    assert result["outcome"] == "refused" and not _committed(repo)


def test_red_tests_are_refused(repo):
    result = _publish(green=False)
    assert result["outcome"] == "refused" and not _committed(repo)


def test_a_rejected_push_is_reported_never_forced(repo):
    repo["push_fails"] = True
    result = _publish()
    assert result["outcome"] == "push-failed"
    assert not any("--force" in c or "-f" in c for c in repo["calls"])


def test_nothing_in_scope_publishes_nothing(repo):
    repo["changed"] = ["tools/score.py"]
    assert _publish()["outcome"] == "nothing-to-publish"
    assert not _committed(repo)


def test_the_maintainers_file_names_the_owner():
    assert "tishkovsergei92@gmail.com" in source_doctor.maintainer_emails()
