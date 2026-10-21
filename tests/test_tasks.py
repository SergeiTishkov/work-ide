"""tasks/: the list of work, one Markdown file per task, the folder its stage
(the owner, 2026-10-20; the format is tasks/README.md). A list nobody checks
drifts into three spellings of "done" within a month; this keeps it readable
by a person and by a grep."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import tasks as tasks_tool  # noqa: E402

TASKS = ROOT / "tasks"
STAGES = ("1-triage", "2-to-do", "3-done", "4-cancelled")
NAME = re.compile(r"^(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
MARK = re.compile(r"^(?:- |### )(TO DO|DONE) - \S")
# a line that means to be a mark but is spelled another way
MARK_LIKE = re.compile(r"^(?:- |### )(?:to[ -]?do|done)\b", re.IGNORECASE)


def _tickets():
    for stage in STAGES:
        if (TASKS / stage).is_dir():   # git keeps no empty folder: an emptied stage is absent in a clone
            for path in sorted((TASKS / stage).iterdir()):
                yield stage, path


def _lines(path):
    return path.read_text(encoding="utf-8").splitlines()


def test_no_folder_but_the_four_stages():
    assert set(p.name for p in TASKS.iterdir() if p.is_dir()) <= set(STAGES)


def test_a_task_is_a_numbered_markdown_file_with_a_number_of_its_own():
    seen = {}
    for stage, path in _tickets():
        match = NAME.match(path.name)
        assert match, f"{stage}/{path.name}: expected NNNN-a-few-words.md"
        number = match.group(1)
        assert number not in seen, f"{number} is both {seen[number]} and {stage}/{path.name}"
        seen[number] = f"{stage}/{path.name}"
        assert _lines(path)[0].startswith(f"# {number} "), f"{seen[number]}: the title starts with '# {number} '"


def test_the_business_comes_first():
    for stage, path in _tickets():
        headings = [line for line in _lines(path) if line.startswith("## ")]
        assert headings and headings[0] == "## Business", f"{stage}/{path.name}: first section is '## Business'"


def test_every_task_from_0052_names_its_scope():
    """The owner, 2026-10-20: every task states what it is about, from a short
    fixed list (tools/tasks.py SCOPES), so the list can be read by area."""
    for stage, path in _tickets():
        number = int(NAME.match(path.name).group(1))
        lines = _lines(path)
        scopes = [line for line in lines if line.startswith("Scope:")]
        if number < tasks_tool.FIRST_WITH_SCOPE:
            continue
        where = f"{stage}/{path.name}"
        assert len(scopes) == 1, f"{where}: one 'Scope: <scope>, <scope>' line"
        assert lines.index(scopes[0]) < lines.index("## Business"), f"{where}: Scope comes before ## Business"
        errors = tasks_tool.scope_errors(scopes[0][len("Scope:"):])
        assert not errors, f"{where}: " + "; ".join(errors)


def test_a_scope_is_one_or_more_from_the_list():
    assert tasks_tool.scope_errors(" tools, docs") == []
    assert tasks_tool.scope_errors("identity:sharp, other") == []
    assert tasks_tool.scope_errors("") and tasks_tool.scope_errors(" , ")
    assert tasks_tool.scope_errors("misc")
    assert tasks_tool.scope_errors("identity:<prefix>") and tasks_tool.scope_errors("identity:Sharp")
    assert tasks_tool.scope_errors("tools, tools")


def test_marks_are_spelled_one_way_and_agree_with_the_stage():
    for stage, path in _tickets():
        marks = []
        for number, line in enumerate(_lines(path), 1):
            if MARK_LIKE.match(line):
                match = MARK.match(line)
                assert match, f"{stage}/{path.name}:{number}: write '- TO DO - <what>' or '- DONE - <what>'"
                marks.append(match.group(1))
        assert marks, f"{stage}/{path.name}: no items"
        if stage == "4-cancelled":
            continue  # left as it stood when the owner cancelled it
        if stage == "3-done":
            assert "TO DO" not in marks, f"{path.name}: a TO DO left in a DONE task"
        else:
            assert "TO DO" in marks, f"{stage}/{path.name}: nothing left to do, so it belongs in 3-done"


def test_a_cancelled_task_says_who_cancelled_it_when_and_why():
    """The owner, 2026-10-21: work decided against keeps its file, in
    4-cancelled, with the decision on a 'Cancelled:' line under 'Source:'."""
    for path in sorted((TASKS / "4-cancelled").glob("*.md")):
        lines = _lines(path)
        cancelled = [line for line in lines if line.startswith("Cancelled: ")]
        assert len(cancelled) == 1, f"4-cancelled/{path.name}: one 'Cancelled: <who, when>: <why>' line"
        assert lines.index(cancelled[0]) < lines.index("## Business"), \
            f"4-cancelled/{path.name}: Cancelled comes before ## Business"


def test_a_new_task_takes_the_next_number_and_passes_the_format(tmp_path, monkeypatch):
    for stage in STAGES:
        (tmp_path / stage).mkdir()
    (tmp_path / "3-done" / "0007-old-work.md").write_text("# 0007 Old work\n", encoding="utf-8")
    monkeypatch.setattr(tasks_tool, "TASKS", tmp_path)
    assert tasks_tool.next_number() == "0008"
    path = tasks_tool.new("to-do", "a-fix", "A fix", "the owner", "Why.", "tools,identity:sharp")
    assert path.name == "0008-a-fix.md" and path.parent.name == "2-to-do"
    lines = _lines(path)
    assert lines[0] == "# 0008 A fix"
    assert "Scope: tools, identity:sharp" in lines
    assert [line for line in lines if line.startswith("## ")][0] == "## Business"
    assert MARK.match(lines[-1]) and MARK.match(lines[-1]).group(1) == "TO DO"
    assert tasks_tool.find(["fix"]) == [path]


def test_a_new_task_goes_into_a_stage_git_did_not_keep(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks_tool, "TASKS", tmp_path)
    path = tasks_tool.new("triage", "an-idea", "An idea", "the agent", "Why.", "tools")
    assert path.parent == tmp_path / "1-triage" and path.is_file()


def test_a_new_task_needs_a_scope_from_the_list(tmp_path, monkeypatch):
    import pytest

    for stage in STAGES:
        (tmp_path / stage).mkdir()
    monkeypatch.setattr(tasks_tool, "TASKS", tmp_path)
    with pytest.raises(SystemExit):
        tasks_tool.new("to-do", "a-fix", "A fix", "the owner", "Why.", "misc")
    assert not list((tmp_path / "2-to-do").iterdir())


def test_a_deleted_task_keeps_its_number(tmp_path, monkeypatch):
    """A task that needed no commit is deleted (tasks/README.md); git history
    still knows its number, and the next task does not take it again."""
    import subprocess

    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Test")
    for stage in STAGES:
        (tmp_path / stage).mkdir()
    (tmp_path / "3-done" / "0007-old-work.md").write_text("# 0007 Old work\n", encoding="utf-8")
    (tmp_path / "2-to-do" / "0008-no-commit-needed.md").write_text("# 0008 x\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-q", "-m", "two tasks")
    git("rm", "-q", "2-to-do/0008-no-commit-needed.md")
    git("commit", "-q", "-m", "drop the task that needed no commit")
    monkeypatch.setattr(tasks_tool, "TASKS", tmp_path)
    assert tasks_tool.next_number() == "0009"
