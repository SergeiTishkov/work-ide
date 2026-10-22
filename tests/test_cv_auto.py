"""
tools/cv_auto.py: which vacancies of the shortlist get a CV and a cover
letter without a click — the identity's filters, any of them; every match,
fresh or earlier, that lacks a document.
"""
from __future__ import annotations

import pytest

import cv_auto
import db
import documents
import kb
import segments
import selections

CONFIG = {"segments": [
    {"slug": "worldwide", "name": "Worldwide", "groups": ["worldwide"]},
    {"slug": "uk", "name": "United Kingdom", "groups": ["united_kingdom"]},
    {"slug": "rest", "name": "Rest of the world", "rest": True},
    {"slug": "full", "name": "Everything", "everything": True, "default": True},
]}
UK = "London, United Kingdom"
SETTINGS = {"documents": ["cv", "letter"],
            "filters": [{"markets": ["worldwide"]}, {"classes": ["hot_lead"]}]}


@pytest.fixture(autouse=True)
def _segments(monkeypatch):
    monkeypatch.setattr(segments, "load_segments",
                        lambda prefix=None: segments.parse_segments(CONFIG))


def _vacancy(vid, location="Anywhere in the World", classification="long_shot", source="remotive",
             company=None):
    return {"id": vid, "title": f"Developer {vid}", "company": company or f"Company {vid}",
            "url": f"https://example.test/{vid}", "location_raw": location, "source": source,
            "description_text": "C# and SQL Server.", "tags": [],
            "computed": {"score": 60, "classification": classification,
                         "score_breakdown": {}, "dealbreakers": []}}


def _two_runs():
    first = {"old_w": _vacancy("old_w"),
             "old_uk_hot": _vacancy("old_uk_hot", UK, "hot_lead"),
             "old_uk_other": _vacancy("old_uk_other", UK, "national_market")}
    kb.save_vacancies(first)
    selections.record(first, {"run_count": 1}, kind="run")
    second = {**first, "new_w": _vacancy("new_w"), "new_uk_other": _vacancy("new_uk_other", UK, "national_market")}
    kb.save_vacancies(second)
    selections.record(second, {"run_count": 2}, kind="run")


def _pick(tmp_path, settings=SETTINGS):
    with db.session() as conn:
        return cv_auto.pick(conn, settings, "ftf", tmp_path / "docs")


def _ids(items):
    return sorted(i["vacancy_id"] for i in items)


def test_every_match_of_the_latest_selection_fresh_or_earlier(isolated_data_dir, tmp_path):
    # the owner, 2026-10-21: a vacancy that rose into a class after its first
    # run (old_uk_hot, old_w) gets its documents as a fresh one does
    _two_runs()
    assert _ids(_pick(tmp_path)) == ["new_w", "old_uk_hot", "old_w"]
    assert _ids(_pick(tmp_path)) == ["new_w", "old_uk_hot", "old_w"]   # asking again changes nothing
    item = next(i for i in _pick(tmp_path) if i["vacancy_id"] == "new_w")
    assert item["documents"] == ["cv", "letter"] and item["title"] == "Developer new_w"


def test_company_kinds_leave_out_a_freelance_marketplace(isolated_data_dir, tmp_path):
    vacancies = {"hot": _vacancy("hot", UK, "hot_lead"),
                 "team": _vacancy("team", classification="hot_lead", company="A.Team"),
                 "lemon": _vacancy("lemon", UK, "worth_a_look", company="Lemon.io"),
                 "agency": _vacancy("agency", UK, "long_shot", company="Kforce Inc."),
                 "unread": _vacancy("unread", UK, "remote_unconfirmed")}
    kb.save_vacancies(vacancies)
    selections.record(vacancies, {"run_count": 1}, kind="run")
    shortlist = {"documents": ["cv", "letter"], "filters": [{
        "classes": ["hot_lead", "worth_a_look", "long_shot"], "company_kinds": ["agency", "reposter", "other"]}]}
    assert _ids(_pick(tmp_path, shortlist)) == ["agency", "hot"]
    every_kind = {"documents": ["cv"], "filters": [{"classes": ["hot_lead", "worth_a_look", "long_shot"]}]}
    assert _ids(_pick(tmp_path, every_kind)) == ["agency", "hot", "lemon", "team"]
    nothing = {"documents": ["cv"], "filters": [{"company_kinds": []}]}
    assert _pick(tmp_path, nothing) == []


def test_everything_named_in_one_filter_must_match(isolated_data_dir, tmp_path):
    _two_runs()
    settings = {"documents": ["cv"], "filters": [{"markets": ["uk"], "classes": ["hot_lead"]}]}
    assert _ids(_pick(tmp_path, settings)) == ["old_uk_hot"]
    by_site = {"documents": ["cv"], "filters": [{"sources": ["remotive.com"], "markets": ["worldwide"]}]}
    assert _ids(_pick(tmp_path, by_site)) == ["new_w", "old_w"]
    other_board = {"documents": ["cv"], "filters": [{"sources": ["reed"]}]}
    assert _pick(tmp_path, other_board) == []


def test_a_document_already_made_or_found_gone_is_not_made_again(isolated_data_dir, tmp_path):
    _two_runs()
    folder = documents.vacancy_dir("ftf", "new_w", tmp_path / "docs")
    built = tmp_path / "x.pdf"
    built.write_text("cv")
    documents.Document(folder, "cv", "CV Alex").publish(   # the batch's CV
        [built], message=None, previous_failed=False, failed_reason=None, auto=True)
    documents.Document(documents.vacancy_dir("ftf", "old_w", tmp_path / "docs"), "cv", "CV Alex").record_error(
        "Vacancy not found, possibly outdated: the link is dead.")
    documents.Document(documents.vacancy_dir("ftf", "old_w", tmp_path / "docs"), "letter",
                       "Cover Letter Alex").record_error("Vacancy not found, possibly outdated: the link is dead.")
    kinds = {i["vacancy_id"]: i["documents"] for i in _pick(tmp_path)}
    assert kinds == {"new_w": ["letter"], "old_uk_hot": ["cv", "letter"]}


def test_the_settings_are_checked():
    assert cv_auto.auto_settings({}) is None
    assert cv_auto.auto_settings({"cv": {"auto": {"filters": [{"markets": ["worldwide"]}]}}}) == {
        "documents": ["cv", "letter"], "filters": [{"markets": ["worldwide"]}]}
    for bad in ({"filters": []}, {"filters": [{"market": ["uk"]}]}, {"filters": [{"classes": "hot_lead"}]},
                {"documents": ["resume"], "filters": [{}]}, ["worldwide"],
                {"filters": [{"company_kinds": ["marketplaces"]}]}, {"filters": [{"company_kinds": "other"}]}):
        with pytest.raises(cv_auto.AutoError):
            cv_auto.auto_settings({"cv": {"auto": bad}})


def test_an_unknown_market_is_named(isolated_data_dir, tmp_path):
    _two_runs()
    with pytest.raises(cv_auto.AutoError, match="europe"):
        _pick(tmp_path, {"documents": ["cv"], "filters": [{"markets": ["europe"]}]})


# The person's vacancies are left alone (the owner, 2026-10-22, task 0087):
# feedback, a document of the person's or a queued CV or letter task, and
# neither document is made.

def _publish(tmp_path, vacancy_id, kind, auto):
    built = tmp_path / f"{vacancy_id}-{kind}.pdf"
    built.write_text(kind)
    stem = "CV Alex" if kind == "cv" else "Cover Letter Alex"
    documents.Document(documents.vacancy_dir("ftf", vacancy_id, tmp_path / "docs"), kind, stem).publish(
        [built], message=None, previous_failed=False, failed_reason=None, auto=auto)


def test_a_cv_of_the_persons_means_no_letter_either(isolated_data_dir, tmp_path):
    _two_runs()
    _publish(tmp_path, "new_w", "cv", auto=False)       # the person's CV
    _publish(tmp_path, "old_w", "cv", auto=True)        # the batch's CV
    kinds = {i["vacancy_id"]: i["documents"] for i in _pick(tmp_path)}
    assert kinds == {"old_w": ["letter"], "old_uk_hot": ["cv", "letter"]}
    with db.session() as conn:
        assert cv_auto.left_alone(conn, "ftf", ["new_w", "old_w"], tmp_path / "docs") == {
            "new_w": "the person made a document for it"}


def test_a_queued_document_task_of_the_persons_leaves_the_vacancy_alone(isolated_data_dir, tmp_path):
    import taskq
    _two_runs()
    with taskq.session() as tasks:
        taskq.add(tasks, "letter", "ftf", vacancy_id="new_w", origin="app")
        done = taskq.add(tasks, "cv", "ftf", vacancy_id="old_w", origin="app")["task"]
        tasks.execute("UPDATE tasks SET state = 'failed' WHERE id = ?", (done["id"],))   # ended, made nothing
        taskq.add(tasks, "cv", "other", vacancy_id="old_uk_hot", origin="app")   # another identity
    assert _ids(_pick(tmp_path)) == ["old_uk_hot", "old_w"]
    with db.session() as conn:
        assert cv_auto.left_alone(conn, "ftf", ["new_w"], tmp_path / "docs") == {
            "new_w": "the person generates a document for it"}


def test_any_feedback_leaves_the_vacancy_alone(isolated_data_dir, tmp_path):
    _two_runs()
    with db.session() as conn:
        conn.execute("UPDATE vacancy_identity SET feedback_status = 'applied' WHERE vacancy_id = 'new_w'")
        conn.execute("UPDATE vacancy_identity SET feedback_status = 'rejected' WHERE vacancy_id = 'old_w'")
        conn.commit()
        assert cv_auto.left_alone(conn, "ftf", ["new_w", "old_w", "old_uk_hot"], tmp_path / "docs") == {
            "new_w": "the person gave feedback", "old_w": "the person gave feedback"}
    assert _ids(_pick(tmp_path)) == ["old_uk_hot"]
