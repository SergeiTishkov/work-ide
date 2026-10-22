"""
tools/documents.py: the folder of generated CVs and cover letters, its
versions and its log.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

import documents


def _new(tmp_path, name, text):
    path = tmp_path / "build" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(text)
    return path


def test_an_existing_folder_gets_its_own_folder_inside_a_new_one_is_used_as_it_is(tmp_path, monkeypatch):
    monkeypatch.setattr(documents.common, "IDENTITIES_DIR", tmp_path / "ids")
    monkeypatch.delenv("WORK_IDE_DOCUMENTS_DIR", raising=False)
    (tmp_path / "Downloads").mkdir()
    assert documents.set_root(str(tmp_path / "Downloads")) == (tmp_path / "Downloads" / documents.FOLDER_NAME)
    assert documents.root() == (tmp_path / "Downloads" / documents.FOLDER_NAME)
    fresh = tmp_path / "Job search" / "docs"
    assert documents.set_root(str(fresh)) == fresh.resolve() and fresh.is_dir()
    assert documents.root() == fresh.resolve()
    # naming the folder itself does not nest another one in it
    named = tmp_path / "Downloads" / documents.FOLDER_NAME
    assert documents.set_root(str(named)) == named
    assert "documents:" in documents.settings_path().read_text(encoding="utf-8")


def test_unset_it_is_in_downloads_and_the_environment_wins(tmp_path, monkeypatch):
    monkeypatch.setattr(documents.common, "IDENTITIES_DIR", tmp_path / "ids")
    monkeypatch.delenv("WORK_IDE_DOCUMENTS_DIR", raising=False)
    assert documents.root() == Path.home() / "Downloads" / documents.FOLDER_NAME
    monkeypatch.setenv("WORK_IDE_DOCUMENTS_DIR", str(tmp_path / "env"))
    assert documents.root() == tmp_path / "env"


def test_identity_then_vacancy_and_a_bad_id_is_refused(tmp_path):
    assert documents.vacancy_dir("sharp", "a2b7", tmp_path) == tmp_path / "sharp" / "a2b7"
    for bad in ("../x", "", "a/b"):
        with pytest.raises(documents.DocumentsError):
            documents.vacancy_dir("sharp", bad, tmp_path)


def test_versions_move_into_old_versions_and_the_log_records_each(tmp_path):
    folder = tmp_path / "sharp" / "v1"
    doc = documents.Document(folder, "cv", "CV Alex")
    at = datetime(2026, 10, 13, 14, 2)
    first = doc.publish([_new(tmp_path, "x.docx", "one"), _new(tmp_path, "x.pdf", "one")],
                        message=None, previous_failed=False, failed_reason=None, now=at)
    assert first["version"] == 1 and not (folder / "Old versions").exists()
    doc.publish([_new(tmp_path, "x.docx", "two"), _new(tmp_path, "x.pdf", "two")],
                message="Fix the summary.\n\nAnd the dates.", previous_failed=False, failed_reason=None, now=at)
    doc.publish([_new(tmp_path, "x.docx", "three")],
                message="Start over.", previous_failed=True, failed_reason="asked to start over", now=at)
    assert (folder / "CV Alex.docx").read_text() == "three"
    assert not (folder / "CV Alex.pdf").exists()   # no new PDF: the old one is not left as current
    old = folder / "Old versions"
    assert sorted(p.name for p in old.iterdir()) == [
        "CV Alex V1.docx", "CV Alex V1.pdf", "CV Alex V2 failed.docx", "CV Alex V2 failed.pdf"]
    entries = documents.read_log(folder / "CV log.md")
    assert [(e["version"], e["failed"]) for e in entries] == [(1, False), (2, True), (3, False)]
    assert entries[0]["message"] is None and entries[0]["at"] == "2026-10-13 14:02"
    assert entries[1]["message"] == "Fix the summary.\n\nAnd the dates."
    assert entries[1]["failed_reason"] == "asked to start over"
    assert doc.next_version() == 4
    text = (folder / "CV log.md").read_text(encoding="utf-8")
    assert "## V2 · 2026-10-13 14:02 · failed" in text and "Without a message." in text


def test_a_cv_and_a_letter_share_the_vacancys_folder_with_logs_of_their_own(tmp_path):
    folder = tmp_path / "sharp" / "v1"
    documents.Document(folder, "cv", "CV Alex").publish(
        [_new(tmp_path, "x.pdf", "cv")], message=None, previous_failed=False, failed_reason=None)
    documents.Document(folder, "letter", "Cover Letter Alex").publish(
        [_new(tmp_path, "y.pdf", "cl")], message="Mention Azure.", previous_failed=False, failed_reason=None)
    assert sorted(p.name for p in folder.iterdir()) == [
        "CV Alex.pdf", "CV log.md", "Cover Letter Alex.pdf", "Cover Letter log.md"]
    state = documents.state("sharp", ["v1", "v2"], tmp_path)
    assert state == {"v1": {"dir": str(folder), "cv": 1, "letter": 1, "errors": {}, "by_person": True}}


def test_files_without_a_log_count_as_the_first_version(tmp_path):
    folder = tmp_path / "sharp" / "v1"
    folder.mkdir(parents=True)
    (folder / "CV Alex.pdf").write_text("by hand")
    doc = documents.Document(folder, "cv", "CV Alex")
    assert doc.next_version() == 2
    result = doc.publish([_new(tmp_path, "x.pdf", "new")], message=None, previous_failed=False,
                         failed_reason=None)
    assert result["version"] == 2
    assert (folder / "Old versions" / "CV Alex V1.pdf").read_text() == "by hand"


def test_a_vacancy_found_gone_leaves_an_error_and_no_version(tmp_path):
    folder = tmp_path / "sharp" / "v1"
    doc = documents.Document(folder, "cv", "CV Alex")
    doc.record_error("Vacancy not found, possibly outdated: the link is dead.", now=datetime(2026, 10, 13, 14, 25))
    assert sorted(p.name for p in folder.iterdir()) == ["CV log.md"]
    text = (folder / "CV log.md").read_text(encoding="utf-8")
    assert text.startswith("# CV log") and "## Error · 2026-10-13 14:25" in text
    assert documents.read_log(folder / "CV log.md") == [] and doc.next_version() == 1
    assert documents.state("sharp", ["v1"], tmp_path)["v1"]["errors"] == {
        "cv": "Vacancy not found, possibly outdated: the link is dead."}
    # a version made later ends the log, and the error is gone with it
    doc.publish([_new(tmp_path, "x.pdf", "cv")], message=None, previous_failed=False, failed_reason=None)
    assert documents.state("sharp", ["v1"], tmp_path)["v1"] == {"dir": str(folder), "cv": 1, "letter": 0,
                                                                "errors": {}, "by_person": True}


def test_an_error_after_a_version_keeps_the_version(tmp_path):
    folder = tmp_path / "sharp" / "v1"
    doc = documents.Document(folder, "cv", "CV Alex")
    doc.publish([_new(tmp_path, "x.pdf", "cv")], message="Shorter.", previous_failed=False, failed_reason=None)
    doc.record_error("Vacancy not found, possibly outdated: the link is dead.")
    entries = documents.read_log(folder / "CV log.md")
    assert [(e["version"], e["message"]) for e in entries] == [(1, "Shorter.")]
    assert documents.last_error(folder / "CV log.md").startswith("Vacancy not found")


def test_a_version_the_batch_made_is_marked_and_the_rest_are_the_persons(tmp_path):
    # task 0087: the batch leaves alone a vacancy with a document of the person's
    folder = tmp_path / "sharp" / "v1"
    doc = documents.Document(folder, "cv", "CV Alex")
    doc.publish([_new(tmp_path, "x.pdf", "one")], message=None, previous_failed=False,
                failed_reason=None, auto=True)
    assert "Without a message.\nMade automatically.\n" in (folder / "CV log.md").read_text(encoding="utf-8")
    assert documents.state("sharp", ["v1"], tmp_path)["v1"]["by_person"] is False
    doc.publish([_new(tmp_path, "x.pdf", "two")], message="Shorter.", previous_failed=False, failed_reason=None)
    assert [e["auto"] for e in documents.read_log(folder / "CV log.md")] == [True, False]
    assert documents.state("sharp", ["v1"], tmp_path)["v1"]["by_person"] is True
