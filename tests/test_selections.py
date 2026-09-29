"""Selections in the database (tools/selections.py) and the queries the app
lists them with (schemas/queries.sql): markets, the per-class limit, the six
filters, freshness across runs, and the row view shared with the report."""
import json

import pytest

import db
import kb
import report
import segments
import selections

CONFIG = {"segments": [
    {"slug": "worldwide", "name": "Worldwide", "groups": ["worldwide"]},
    {"slug": "uk", "name": "United Kingdom", "groups": ["united_kingdom"]},
    {"slug": "rest", "name": "Rest of the world", "rest": True},
    {"slug": "full", "name": "Everything", "everything": True, "default": True},
]}


@pytest.fixture(autouse=True)
def _segments(monkeypatch):
    monkeypatch.setattr(segments, "load_segments",
                        lambda prefix=None: segments.parse_segments(CONFIG))


def _vacancy(vid, country=None, score=60, classification="hot_lead", **extra):
    return {
        "id": vid,
        "title": f"Senior .NET Developer {vid}",
        "company": f"Company {vid}",
        "url": f"https://example.test/{vid}",
        "location_raw": country or "Anywhere in the World",
        "description_text": "C# and SQL Server.",
        "tags": [],
        "computed": {"score": score, "classification": classification,
                     "score_breakdown": {}, "dealbreakers": []},
        "manual": {"status": "new"},
        **extra,
    }


def _store(vacancies: dict, kind="run", run=1) -> int:
    kb.save_vacancies(vacancies)
    return selections.record(vacancies, {"run_count": run}, kind=kind)


def _set_feedback(vid, status, reason=None, selection_id=None):
    """Exactly what the app runs."""
    with db.session() as conn:
        conn.execute(selections.load_queries()["set_feedback"], {
            "id": vid, "status": status,
            "rejected_reason": reason if status == "rejected" else None,
            "bugged_reason": reason if status == "bugged" else None,
            "at": db.now_iso(), "selection_id": selection_id,
        })


def _listing(selection_id, segment="full", filter_name="fresh_new"):
    with db.session() as conn:
        return selections.listing(conn, selection_id, segment, filter_name)


def _ids(rows):
    return [r["vacancy_id"] for r in rows]


def test_vacancy_lands_in_every_market_that_holds_it(isolated_data_dir):
    sel = _store({
        "w": _vacancy("w"),
        "uk": _vacancy("uk", "London, United Kingdom"),
        "ca": _vacancy("ca", "Toronto, Ontario, Canada"),
    })
    assert set(_ids(_listing(sel, "full"))) == {"w", "uk", "ca"}
    assert _ids(_listing(sel, "uk")) == ["uk"]
    assert _ids(_listing(sel, "worldwide")) == ["w"]
    assert _ids(_listing(sel, "rest")) == ["ca"]
    with db.session() as conn:
        names = [r[0] for r in conn.execute(selections.load_queries()["segments"],
                                            {"selection_id": sel})]
    assert names == ["worldwide", "uk", "rest", "full"]


def test_only_what_the_report_would_list_is_recorded(isolated_data_dir):
    sel = _store({
        "ok": _vacancy("ok"),
        "rej": _vacancy("rej", classification="rejected"),
        "dup": _vacancy("dup", duplicate_of="ok"),
        "dead": _vacancy("dead", link_check={"status": "dead"}),
    })
    assert _ids(_listing(sel, filter_name="all")) == ["ok"]


def test_a_new_selection_leaves_the_old_one_untouched(isolated_data_dir):
    first = _store({"a": _vacancy("a", score=50)})
    second = _store({"a": _vacancy("a", score=80), "b": _vacancy("b")}, run=2)
    assert second > first
    assert [(r["vacancy_id"], r["score"]) for r in _listing(first, filter_name="all")] == [("a", 50)]
    assert {r["vacancy_id"]: r["score"] for r in _listing(second, filter_name="all")} == {"a": 80, "b": 60}


def test_classes_in_report_order_then_by_score(isolated_data_dir):
    sel = _store({
        "ls": _vacancy("ls", score=90, classification="long_shot"),
        "h1": _vacancy("h1", score=40),
        "h2": _vacancy("h2", score=70),
        "w": _vacancy("w", score=99, classification="worth_a_look"),
    })
    assert _ids(_listing(sel, filter_name="all")) == ["h2", "h1", "w", "ls"]


def test_marked_vacancy_leaves_the_top_and_the_next_one_moves_up(isolated_data_dir):
    vacancies = {f"v{i:02}": _vacancy(f"v{i:02}", score=100 - i) for i in range(20)}
    sel = _store(vacancies)
    top = _ids(_listing(sel))
    assert top == [f"v{i:02}" for i in range(report.TOP_N_PER_SECTION)]

    _set_feedback("v00", "rejected", "too much travel", selection_id=sel)

    top = _ids(_listing(sel))
    assert "v00" not in top
    assert len(top) == report.TOP_N_PER_SECTION
    assert top[-1] == f"v{report.TOP_N_PER_SECTION:02}"
    rejected = _listing(sel, filter_name="rejected")
    assert _ids(rejected) == ["v00"]
    assert rejected[0]["rejected_reason"] == "too much travel"


def test_freshness_is_measured_against_the_last_run(isolated_data_dir):
    first = _store({"a": _vacancy("a"), "b": _vacancy("b")})
    assert set(_ids(_listing(first))) == {"a", "b"}, "no earlier run: everything is fresh"

    second = _store({"a": _vacancy("a"), "b": _vacancy("b"), "c": _vacancy("c")}, run=2)
    assert _ids(_listing(second)) == ["c"]

    # A rebuild (a filter fix, no fetching) must not make the unread look old.
    rebuilt = _store({"a": _vacancy("a"), "b": _vacancy("b"), "c": _vacancy("c"),
                      "d": _vacancy("d")}, kind="rebuild", run=2)
    assert set(_ids(_listing(rebuilt))) == {"c", "d"}


def test_every_filter_returns_exactly_its_own_set(isolated_data_dir):
    _store({"old_new": _vacancy("old_new"), "old_applied": _vacancy("old_applied")})
    sel = _store({
        "old_new": _vacancy("old_new"), "old_applied": _vacancy("old_applied"),
        "new": _vacancy("new"), "applied": _vacancy("applied"),
        "rejected": _vacancy("rejected"), "bugged": _vacancy("bugged"),
    }, run=2)
    for vid, status in (("old_applied", "applied"), ("applied", "applied"),
                        ("rejected", "rejected"), ("bugged", "bugged")):
        _set_feedback(vid, status, selection_id=sel)

    def ids(name):
        return set(_ids(_listing(sel, filter_name=name)))

    assert ids("fresh_new") == {"new"}
    assert ids("all") == {"old_new", "old_applied", "new", "applied", "rejected", "bugged"}
    assert ids("fresh") == {"new", "applied", "rejected", "bugged"}
    assert ids("applied") == {"old_applied", "applied"}
    assert ids("rejected") == {"rejected"}
    assert ids("bugged") == {"bugged"}


def test_limit_applies_after_the_filter_and_never_to_marked(isolated_data_dir):
    limit = report.TOP_N_PER_SECTION
    old = {f"o{i:02}": _vacancy(f"o{i:02}", score=90) for i in range(limit + 5)}
    _store(old)
    fresh = {f"f{i}": _vacancy(f"f{i}", score=10) for i in range(3)}
    sel = _store({**old, **fresh}, run=2)

    # The fresh ones score far below the old top, and still fill "fresh".
    assert set(_ids(_listing(sel))) == set(fresh)
    assert len(_listing(sel, filter_name="all")) == limit

    for vid in list(old)[:limit + 2]:
        _set_feedback(vid, "applied", selection_id=sel)
    assert len(_listing(sel, filter_name="applied")) == limit + 2, "marked ones are never capped"


def test_counts_match_the_listing_for_every_filter(isolated_data_dir):
    limit = report.TOP_N_PER_SECTION
    _store({f"o{i:02}": _vacancy(f"o{i:02}") for i in range(limit + 3)})
    vacancies = {f"o{i:02}": _vacancy(f"o{i:02}") for i in range(limit + 3)}
    vacancies.update({f"f{i:02}": _vacancy(f"f{i:02}", classification="worth_a_look")
                      for i in range(limit + 4)})
    sel = _store(vacancies, run=2)
    _set_feedback("o00", "bugged", "a Java role", selection_id=sel)
    _set_feedback("f00", "rejected", selection_id=sel)
    _set_feedback("f01", "applied", selection_id=sel)

    for segment in ("full", "worldwide", "uk"):
        with db.session() as conn:
            counts = selections.listing_counts(conn, sel, segment)
        for name in selections.FILTERS:
            assert counts[name] == len(_listing(sel, segment, name)), (segment, name)


def test_row_view_is_the_one_the_report_renders(isolated_data_dir):
    v = _vacancy("a", "London, United Kingdom")
    sel = _store({"a": v})
    view = json.loads(_listing(sel)[0]["view"])
    assert view == json.loads(db.dumps(report.vacancy_view(v)))
    for key in ("id", "title", "company", "url", "score", "classification", "highlights",
                "salary", "to_confirm", "eligibility", "apply_channels", "technologies",
                "reputation", "hiring_country", "needs_manual_review"):
        assert key in view, key
    line = report._fmt_vacancy_line(v)
    assert view["salary"] in line and view["hiring_country"] in line


def test_display_name_is_recorded_for_the_app(isolated_data_dir):
    _store({"a": _vacancy("a")})
    with db.session() as conn:
        (name,) = conn.execute(selections.load_queries()["display_name"]).fetchone()
    assert name


def test_record_refuses_an_unknown_kind(isolated_data_dir):
    with pytest.raises(ValueError):
        selections.record({}, {}, kind="whatever")
