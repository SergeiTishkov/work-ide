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


def test_progress_says_what_the_loop_has_found(capsys):
    """A walk of hours reports its haul, not only its count: pages, vacancies,
    rate limits — what a person watching the log wants to know."""
    tick = progress.Progress(3, "linkedin pairs", every=0)
    tick.note = "4 pages, 37 vacancies"
    tick()
    assert capsys.readouterr().err.rstrip().endswith("left - 4 pages, 37 vacancies")


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


def test_the_estimate_follows_the_recent_pace(monkeypatch, capsys):
    """Fast at first, slow now: the time left is judged by now."""
    clock = [0.0]
    monkeypatch.setattr(progress.time, "monotonic", lambda: clock[0])
    tick = progress.Progress(1000, "link check", every=10)
    clock[0] = 10.0
    tick(500)                    # 50 per second at first
    clock[0] = 20.0
    tick(10)                     # 1 per second now: 490 left -> ~8 minutes
    lines = capsys.readouterr().err.splitlines()
    assert lines[-1].endswith("~8:10 left")
