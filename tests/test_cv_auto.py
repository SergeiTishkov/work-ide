"""
tools/cv_auto.py: which vacancies of the latest collection get a CV and a
cover letter without a click — the identity's filters, any of them; fresh
vacancies for a filter already applied, the earlier ones too for a new one.
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


def _vacancy(vid, location="Anywhere in the World", classification="long_shot", source="remotive"):
    return {"id": vid, "title": f"Developer {vid}", "company": f"Company {vid}",
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


def _pick(tmp_path, settings=SETTINGS, applied=None):
    with db.session() as conn:
        return cv_auto.pick(conn, settings, "ftf", tmp_path / "docs", applied=applied)


def _ids(items):
    return sorted(i["vacancy_id"] for i in items)


def _applied(settings=SETTINGS):
    return [cv_auto.filter_key(one, settings["documents"]) for one in settings["filters"]]


def test_a_new_filter_takes_the_earlier_vacancies_too_an_applied_one_the_fresh_only(isolated_data_dir, tmp_path):
    _two_runs()
    assert _ids(_pick(tmp_path)) == ["new_w", "old_uk_hot", "old_w"]
    assert _ids(_pick(tmp_path, applied=_applied())) == ["new_w"]
    # the worldwide filter applied, the hot leads one added since
    worldwide_only = {"documents": ["cv", "letter"], "filters": [{"markets": ["worldwide"]}]}
    assert _ids(_pick(tmp_path, applied=_applied(worldwide_only))) == ["new_w", "old_uk_hot"]
    item = next(i for i in _pick(tmp_path) if i["vacancy_id"] == "new_w")
    assert item["documents"] == ["cv", "letter"] and item["title"] == "Developer new_w"


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
    documents.Document(folder, "cv", "CV Alex").publish(
        [built], message=None, previous_failed=False, failed_reason=None)
    documents.Document(documents.vacancy_dir("ftf", "old_w", tmp_path / "docs"), "cv", "CV Alex").record_error(
        "Vacancy not found, possibly outdated: the link is dead.")
    documents.Document(documents.vacancy_dir("ftf", "old_w", tmp_path / "docs"), "letter",
                       "Cover Letter Alex").record_error("Vacancy not found, possibly outdated: the link is dead.")
    kinds = {i["vacancy_id"]: i["documents"] for i in _pick(tmp_path)}
    assert kinds == {"new_w": ["letter"], "old_uk_hot": ["cv", "letter"]}


def test_remember_makes_every_filter_fresh_only_and_no_filters_forget(isolated_data_dir):
    assert cv_auto.applied_filters() == []
    cv_auto.remember(SETTINGS)
    assert cv_auto.applied_filters() == _applied()
    # the order inside a filter does not make it new
    reordered = {"documents": ["letter", "cv"], "filters": [{"classes": ["hot_lead"]}, {"markets": ["worldwide"]}]}
    assert sorted(_applied(reordered)) == sorted(cv_auto.applied_filters())
    # more documents: every filter is new again
    assert _applied({"documents": ["cv"], "filters": SETTINGS["filters"]})[0] not in cv_auto.applied_filters()
    cv_auto.remember(None)
    assert cv_auto.applied_filters() == []


def test_the_settings_are_checked():
    assert cv_auto.auto_settings({}) is None
    assert cv_auto.auto_settings({"cv": {"auto": {"filters": [{"markets": ["worldwide"]}]}}}) == {
        "documents": ["cv", "letter"], "filters": [{"markets": ["worldwide"]}]}
    for bad in ({"filters": []}, {"filters": [{"market": ["uk"]}]}, {"filters": [{"classes": "hot_lead"}]},
                {"documents": ["resume"], "filters": [{}]}, ["worldwide"]):
        with pytest.raises(cv_auto.AutoError):
            cv_auto.auto_settings({"cv": {"auto": bad}})


def test_an_unknown_market_is_named(isolated_data_dir, tmp_path):
    _two_runs()
    with pytest.raises(cv_auto.AutoError, match="europe"):
        _pick(tmp_path, {"documents": ["cv"], "filters": [{"markets": ["europe"]}]})
