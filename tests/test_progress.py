"""tools/progress.py: what a long run says about itself while it runs."""
import pytest

import progress


def test_stage_reports_start_end_and_its_note(capsys):
    with progress.stage("check links") as st:
        st.note = "checked 3, dead 1"
    lines = capsys.readouterr().err.splitlines()
    assert lines[0].endswith(">> check links")
    assert "ok check links - 0 s (checked 3, dead 1)" in lines[1]


def test_a_failing_stage_says_so_and_still_raises(capsys):
    with pytest.raises(ValueError):
        with progress.stage("save"):
            raise ValueError("disk full")
    assert "!! save - failed after 0 s: ValueError: disk full" in capsys.readouterr().err


def test_progress_reports_counts_and_stays_quiet_at_the_end(capsys):
    tick = progress.Progress(4, "rescore", every=0)
    for _ in range(4):
        tick()
    lines = capsys.readouterr().err.splitlines()
    assert [line.split("] ", 1)[1].split(",")[0] for line in lines] == [
        "   rescore: 1/4 (25%)", "   rescore: 2/4 (50%)", "   rescore: 3/4 (75%)"]


def test_progress_is_rate_limited(capsys):
    tick = progress.Progress(1000, "rescore", every=3600)
    for _ in range(999):
        tick()
    assert capsys.readouterr().err == ""


def test_lines_are_mirrored_into_the_log_file(tmp_path, capsys):
    path = progress.open_log(tmp_path / "runs" / "pipeline.log")
    try:
        progress.log("hello")
    finally:
        progress.close_log()
    progress.log("after close")
    text = path.read_text(encoding="utf-8")
    assert "hello" in text and "after close" not in text


@pytest.mark.parametrize("seconds, text", [(5, "5 s"), (75, "1:15"), (3725, "1:02:05")])
def test_durations_read_like_a_clock(seconds, text):
    assert progress.duration(seconds) == text
