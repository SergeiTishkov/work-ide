"""The /feedback review writes tickets, never code (the owner, 2026-10-22,
task 0079). The rule lives in .claude/commands/feedback.md; these tests keep
it from drifting back to "fix the cause in tools/score.py"."""
import re
from pathlib import Path

import tasks

COMMAND = Path(__file__).resolve().parent.parent / ".claude" / "commands" / "feedback.md"


def _text() -> str:
    return COMMAND.read_text(encoding="utf-8")


def test_the_review_names_what_it_may_not_touch():
    text = _text()
    for place in ("`tools/`", "`tests/`", "`app/`", "`config/`", "`identity-templates/`",
                  "`local-identities/`"):
        assert place in text, f"{place} is not named among what the review may not edit"
    assert re.search(r"No git command that\s+changes anything", text)


def test_the_review_does_not_tell_the_agent_to_edit_code():
    text = _text()
    for instruction in ("fix the cause in", "add a test built on", "Run `pytest`", "fix the pattern"):
        assert instruction not in text, f"the command still says {instruction!r}"


def test_a_ticket_is_a_triage_task_with_the_review_prefix(tmp_path, monkeypatch):
    text = _text()
    assert "tasks/1-triage/" in text and "<NNNN>-review-feedback-<slug>.md" in text
    assert "python tools/tasks.py new triage review-feedback-<slug>" in text
    # The command it gives makes such a file.
    monkeypatch.setattr(tasks, "TASKS", tmp_path)
    path = tasks.new("triage", "review-feedback-hybrid-in-the-title", "Hybrid in the title",
                     "feedback review, 2026-10-22: sharp, vacancies a1", "What the person needs and why.",
                     "config")
    assert path.parent.name == "1-triage"
    assert re.fullmatch(r"\d{4}-review-feedback-hybrid-in-the-title\.md", path.name)
