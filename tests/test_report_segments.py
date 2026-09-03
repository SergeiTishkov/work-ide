"""
Writing several shortlists instead of one.

The unit-level guarantees are in test_segments.py; this file checks what a
person actually ends up with on disk:

  * one file per configured segment, named predictably;
  * `<prefix>_latest.md` still there and still meaning the whole shortlist,
    because RUNBOOK.md, the archive and habit all point at it;
  * each file saying which shortlist it is and where the others are — without
    that, splitting the report would quietly HIDE work from somebody who only
    ever opens the UK one;
  * a broken segmentation costing a person the report rather than the whole
    run, which by that point has already done all the work.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import common  # noqa: E402
import report  # noqa: E402
import segments  # noqa: E402


def _vacancy(vid, country, score=60, classification="hot_lead", title=None):
    return {
        "id": vid,
        "title": title or f"Senior .NET Developer {vid}",
        "company": f"Company {vid}",
        "url": f"https://example.test/{vid}",
        "location_raw": country or "Anywhere in the World",
        "description_text": "C# and SQL Server.",
        "tags": [],
        "computed": {
            "score": score,
            "classification": classification,
            "score_breakdown": {},
            "dealbreakers": [],
        },
        "manual": {"status": "new"},
    }


CONFIG = {"segments": [
    {"slug": "worldwide", "name": "Worldwide", "groups": ["worldwide"]},
    {"slug": "uk", "name": "United Kingdom", "groups": ["united_kingdom"]},
    {"slug": "rest", "name": "Rest of the world", "rest": True},
    {"slug": "full", "name": "Everything", "everything": True, "default": True},
]}


def _vacancies():
    return {
        "w": _vacancy("w", None),
        "uk": _vacancy("uk", "London, United Kingdom"),
        "ca": _vacancy("ca", "Toronto, Ontario, Canada"),
    }


def test_one_file_per_segment_plus_the_historical_name(monkeypatch, tmp_path):
    monkeypatch.setattr(segments, "load_segments",
                        lambda prefix=None: segments.parse_segments(CONFIG))
    monkeypatch.setattr(common, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(common, "REPORTS_ARCHIVE_DIR", tmp_path / "reports" / "archive")

    written = report.write_segmented_reports(_vacancies(), {}, {}, criteria={})

    names = sorted(p.name for p in written.values())
    prefix = common.FILE_PREFIX or ""
    assert names == sorted([
        f"{prefix}worldwide_latest.md",
        f"{prefix}uk_latest.md",
        f"{prefix}rest_latest.md",
        f"{prefix}full_latest.md",
        f"{prefix}latest.md",
    ])
    for path in written.values():
        assert path.exists() and path.read_text(encoding="utf-8").strip()


def test_a_vacancy_appears_in_its_own_market_file_and_not_in_another(
        monkeypatch, tmp_path):
    monkeypatch.setattr(segments, "load_segments",
                        lambda prefix=None: segments.parse_segments(CONFIG))
    monkeypatch.setattr(common, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(common, "REPORTS_ARCHIVE_DIR", tmp_path / "reports" / "archive")

    written = report.write_segmented_reports(_vacancies(), {}, {}, criteria={})
    text = {slug: path.read_text(encoding="utf-8") for slug, path in written.items()}

    assert "Company uk" in text["uk"]
    assert "Company ca" not in text["uk"]
    assert "Company ca" in text["rest"]
    assert "Company w" in text["worldwide"]
    # And everything is in the undivided file, which is the point of keeping it.
    for company in ("Company w", "Company uk", "Company ca"):
        assert company in text[""]


def test_each_file_points_at_the_others(monkeypatch, tmp_path):
    """Otherwise splitting the report hides work: somebody who opens the UK
    shortlist has no way of learning that a worldwide one exists."""
    monkeypatch.setattr(segments, "load_segments",
                        lambda prefix=None: segments.parse_segments(CONFIG))
    monkeypatch.setattr(common, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(common, "REPORTS_ARCHIVE_DIR", tmp_path / "reports" / "archive")

    written = report.write_segmented_reports(_vacancies(), {}, {}, criteria={})
    uk = written["uk"].read_text(encoding="utf-8")
    prefix = common.FILE_PREFIX or ""

    assert f"{prefix}worldwide_latest.md" in uk
    assert f"{prefix}rest_latest.md" in uk
    assert f"{prefix}uk_latest.md" not in uk, "a file need not link to itself"


def test_the_archive_keeps_the_days_shortlists_apart(monkeypatch, tmp_path):
    """Without the slug, eight files written on one day would overwrite one
    another and the archive would hold whichever ran last."""
    monkeypatch.setattr(segments, "load_segments",
                        lambda prefix=None: segments.parse_segments(CONFIG))
    monkeypatch.setattr(common, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(common, "REPORTS_ARCHIVE_DIR", tmp_path / "archive")

    report.write_segmented_reports(_vacancies(), {}, {}, criteria={},
                                   run_date="2026-08-12")

    archived = sorted(p.name for p in (tmp_path / "archive").iterdir())
    assert archived == ["2026-08-12.md", "2026-08-12_full.md", "2026-08-12_rest.md",
                        "2026-08-12_uk.md", "2026-08-12_worldwide.md"]


def test_an_identity_with_no_segmentation_gets_the_one_report_it_always_got(
        monkeypatch, tmp_path):
    monkeypatch.setattr(segments, "load_segments", lambda prefix=None: [])
    monkeypatch.setattr(common, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(common, "REPORTS_ARCHIVE_DIR", tmp_path / "reports" / "archive")

    written = report.write_segmented_reports(_vacancies(), {}, {}, criteria={})

    assert list(written) == [""]
    assert written[""].name == f"{common.FILE_PREFIX or ''}latest.md"
    assert "Company ca" in written[""].read_text(encoding="utf-8")


def test_a_broken_segmentation_still_produces_a_report(monkeypatch, tmp_path):
    """The report is the last step of a cycle that has already collected,
    scored and enriched. A typo in a config file must not be what a person
    walks away with instead of their shortlist."""
    def explode(prefix=None):
        raise ValueError("segment 'uk' names unknown market group ['untied_kingdom']")

    monkeypatch.setattr(segments, "load_segments", explode)
    monkeypatch.setattr(common, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(common, "REPORTS_ARCHIVE_DIR", tmp_path / "reports" / "archive")

    written = report.write_segmented_reports(_vacancies(), {}, {}, criteria={})

    assert list(written) == [""]
    assert "Company uk" in written[""].read_text(encoding="utf-8")


def test_the_filename_of_a_segment_is_predictable():
    assert report.segment_filename("uk", prefix="kisel_") == "kisel_uk_latest.md"
    assert report.segment_filename("", prefix="kisel_") == "kisel_latest.md"
