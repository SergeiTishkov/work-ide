"""tasks/: the list of work, one Markdown file per task, the folder its stage
(the owner, 2026-10-20; the format is tasks/README.md). A list nobody checks
drifts into three spellings of "done" within a month; this keeps it readable
by a person and by a grep."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS = ROOT / "tasks"
STAGES = ("1-triage", "2-to-do", "3-done")
NAME = re.compile(r"^(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
MARK = re.compile(r"^(?:- |### )(TO DO|DONE) - \S")
# a line that means to be a mark but is spelled another way
MARK_LIKE = re.compile(r"^(?:- |### )(?:to[ -]?do|done)\b", re.IGNORECASE)


def _tickets():
    for stage in STAGES:
        for path in sorted((TASKS / stage).iterdir()):
            yield stage, path


def _lines(path):
    return path.read_text(encoding="utf-8").splitlines()


def test_three_stages_in_order_and_nothing_else():
    assert sorted(p.name for p in TASKS.iterdir() if p.is_dir()) == list(STAGES)


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


def test_marks_are_spelled_one_way_and_agree_with_the_stage():
    for stage, path in _tickets():
        marks = []
        for number, line in enumerate(_lines(path), 1):
            if MARK_LIKE.match(line):
                match = MARK.match(line)
                assert match, f"{stage}/{path.name}:{number}: write '- TO DO - <what>' or '- DONE - <what>'"
                marks.append(match.group(1))
        assert marks, f"{stage}/{path.name}: no items"
        if stage == "3-done":
            assert "TO DO" not in marks, f"{path.name}: a TO DO left in a DONE task"
        else:
            assert "TO DO" in marks, f"{stage}/{path.name}: nothing left to do, so it belongs in 3-done"


def test_a_new_task_takes_the_next_number_and_passes_the_format(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, str(ROOT / "tools"))
    import tasks as tasks_tool

    for stage in STAGES:
        (tmp_path / stage).mkdir()
    (tmp_path / "3-done" / "0007-old-work.md").write_text("# 0007 Old work\n", encoding="utf-8")
    monkeypatch.setattr(tasks_tool, "TASKS", tmp_path)
    assert tasks_tool.next_number() == "0008"
    path = tasks_tool.new("to-do", "a-fix", "A fix", "the owner", "Why.")
    assert path.name == "0008-a-fix.md" and path.parent.name == "2-to-do"
    lines = _lines(path)
    assert lines[0] == "# 0008 A fix"
    assert [line for line in lines if line.startswith("## ")][0] == "## Business"
    assert MARK.match(lines[-1]) and MARK.match(lines[-1]).group(1) == "TO DO"
    assert tasks_tool.find(["fix"]) == [path]
