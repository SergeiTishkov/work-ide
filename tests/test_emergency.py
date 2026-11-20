"""
tools/emergency.py: the emergency file (task 0135). conftest points
emergency.PATH at a scratch file, so no test writes the repository's one.
"""
from __future__ import annotations

from datetime import datetime

import emergency


def test_entries_are_appended_after_a_line_of_underscores_and_read_back():
    assert emergency.entries() == []
    emergency.report("LinkedIn fetch kept", "17240 records in linkedin_fetched.json\n\nMerge them.",
                     now=datetime(2026, 11, 20, 22, 59))
    emergency.report("CV batch stopped", "Word did not answer.", now=datetime(2026, 11, 21, 3, 0))
    text = emergency.PATH.read_text(encoding="utf-8")
    assert text.startswith(emergency.SEPARATOR + "\n")
    assert text.count(emergency.SEPARATOR) == 2
    assert emergency.entries() == [
        "## 2026-11-20 22:59 LinkedIn fetch kept\n\n17240 records in linkedin_fetched.json\n\nMerge them.",
        "## 2026-11-21 03:00 CV batch stopped\n\nWord did not answer.",
    ]


def test_a_hand_written_separator_and_an_emptied_file_read_right(tmp_path):
    path = tmp_path / "emergency.md"
    path.write_text("___\nfirst\n\n_______________\nsecond\n", encoding="utf-8")
    assert emergency.entries(path) == ["first", "second"]
    path.write_text("\n", encoding="utf-8")
    assert emergency.entries(path) == []


def test_a_report_that_cannot_be_written_does_not_raise(tmp_path, capsys):
    assert emergency.report("x", "y", path=tmp_path / "missing" / "emergency.md") is None
    assert "could not write" in capsys.readouterr().err


def test_the_command_line_adds_and_lists(capsys):
    assert emergency.main(["add", "Base locked", "The rest run waited 2 hours."]) == 0
    emergency.main([])
    out = capsys.readouterr().out
    assert emergency.SEPARATOR in out and "Base locked" in out and "waited 2 hours" in out
