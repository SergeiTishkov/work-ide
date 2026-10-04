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


def _all_classes():
    return tuple(report.LISTED_CLASSES)


def test_counts_are_whole_numbers_and_the_list_says_how_many_more(isolated_data_dir):
    limit = report.TOP_N_PER_SECTION
    _store({f"o{i:02}": _vacancy(f"o{i:02}") for i in range(limit + 3)})
    vacancies = {f"o{i:02}": _vacancy(f"o{i:02}") for i in range(limit + 3)}
    vacancies.update({f"f{i:02}": _vacancy(f"f{i:02}", classification="worth_a_look")
                      for i in range(limit + 4)})
    sel = _store(vacancies, run=2)
    _set_feedback("o00", "bugged", "a Java role", selection_id=sel)
    _set_feedback("f00", "rejected", selection_id=sel)
    _set_feedback("f01", "applied", selection_id=sel)

    with db.session() as conn:
        counts = selections.listing_counts(conn, sel, "full")
        for name in selections.FILTERS:
            everything = selections.listing(conn, sel, "full", name, expanded=_all_classes())
            totals = selections.class_totals(conn, sel, "full", name)
            assert counts[name] == len(everything) == sum(totals.values()), name
    # fresh worth_a_look: limit+4 of which 2 marked -> limit+2 new, capped on screen
    with db.session() as conn:
        shown = selections.listing(conn, sel, "full", "fresh_new")
        totals = selections.class_totals(conn, sel, "full", "fresh_new")
    assert totals == {"worth_a_look": limit + 2}
    assert len(shown) == limit, "the list stays capped; the count does not"


def test_markets_add_up_to_everything(isolated_data_dir):
    """The owner, 2026-09-30: UK 40 + ANZ 15 was more than "everything" 54,
    because each count was capped separately."""
    countries = [None, "London, United Kingdom", "Toronto, Ontario, Canada"]
    vacancies = {}
    for i in range(60):
        vid = f"v{i:02}"
        vacancies[vid] = _vacancy(vid, countries[i % 3], score=100 - i,
                                  classification=("hot_lead", "long_shot")[i % 2])
    sel = _store(vacancies)
    _set_feedback("v00", "rejected", selection_id=sel)
    with db.session() as conn:
        for name in selections.FILTERS:
            full = selections.listing_counts(conn, sel, "full")[name]
            parts = sum(selections.listing_counts(conn, sel, seg)[name]
                        for seg in ("worldwide", "uk", "rest"))
            assert parts == full, name


def test_an_expanded_class_shows_every_row(isolated_data_dir):
    limit = report.TOP_N_PER_SECTION
    sel = _store({f"v{i:02}": _vacancy(f"v{i:02}", score=100 - i) for i in range(limit + 5)})
    with db.session() as conn:
        assert len(selections.listing(conn, sel, "full", "all")) == limit
        assert len(selections.listing(conn, sel, "full", "all", expanded=("hot_lead",))) == limit + 5
        assert len(selections.listing(conn, sel, "full", "all", expanded=("long_shot",))) == limit


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


def test_decisions_from_earlier_collections_are_settled_and_hidden(isolated_data_dir):
    """The owner, 2026-09-30: "rejected" listed vacancies turned down a month
    ago. A selection shows the feedback of its own collection only."""
    first = _store({"old": _vacancy("old"), "kept": _vacancy("kept")})
    _set_feedback("old", "rejected", "a month ago", selection_id=first)
    assert _ids(_listing(first, filter_name="rejected")) == ["old"]

    second = _store({"old": _vacancy("old"), "kept": _vacancy("kept"),
                     "new": _vacancy("new")}, run=2)
    for name in selections.FILTERS:
        assert "old" not in _ids(_listing(second, filter_name=name)), name
    with db.session() as conn:
        assert selections.listing_counts(conn, second, "full")["rejected"] == 0

    # Decided now, then re-selected without fetching: same collection, still shown.
    _set_feedback("new", "rejected", "not for me", selection_id=second)
    rebuilt = _store({"old": _vacancy("old"), "kept": _vacancy("kept"),
                      "new": _vacancy("new")}, kind="rebuild", run=2)
    assert _ids(_listing(rebuilt, filter_name="rejected")) == ["new"]


def test_feedback_carried_over_from_before_selections_is_settled(isolated_data_dir):
    """Migrated 'not_relevant' marks have no selection: decided before any."""
    sel = _store({"a": _vacancy("a"), "b": _vacancy("b")})
    _set_feedback("a", "rejected", "migrated", selection_id=None)
    assert _ids(_listing(sel, filter_name="rejected")) == []
    assert _ids(_listing(sel, filter_name="all")) == ["b"]


def test_applications_stay_listed_across_collections_and_markets(isolated_data_dir):
    """An application lives for weeks; a later run must not make it vanish."""
    first = _store({"a": _vacancy("a", "London, United Kingdom"), "b": _vacancy("b")})
    _set_feedback("a", "applied", selection_id=first)
    second = _store({"b": _vacancy("b"), "c": _vacancy("c")}, run=2)   # "a" gone from the list
    for segment in ("full", "uk", "worldwide"):
        with db.session() as conn:
            assert _ids(selections.listing(conn, second, segment, "applied")) == ["a"], segment
            assert selections.listing_counts(conn, second, segment)["applied"] == 1
            assert selections.class_totals(conn, second, segment, "applied") == {"hot_lead": 1}


def test_applying_dates_the_funnel_and_going_back_forgets_it(isolated_data_dir):
    sel = _store({"a": _vacancy("a")})
    _set_feedback("a", "applied", selection_id=sel)
    with db.session() as conn:
        conn.execute(selections.load_queries()["write_progress"], {
            "id": "a", "status": "interview", "at": "2026-10-02T10:00:00+00:00",
            "rejected_reason": None, "bugged_reason": None,
            "applied_at": "2026-10-01T10:00:00+00:00",
            "contact_comment": "", "contact_at": "2026-10-01T12:00:00+00:00",
            "interview_comments": '["went well"]', "interview_at": '["2026-10-02T10:00:00+00:00"]',
            "final_comment": None, "final_at": None,
            "awaiting_offer_comment": None, "awaiting_offer_at": None,
            "declined_comment": "budget frozen", "declined_at": "2026-10-02T11:00:00+00:00",
            "offered_comment": None, "offered_at": None,
            "started_comment": None, "started_at": None,
        })
        conn.row_factory = selections._dict_row
        row = conn.execute(selections.load_queries()["vacancy_progress"], {"id": "a"}).fetchone()
    assert row["feedback_status"] == "interview"
    assert row["contact_comment"] == "" and row["interview_comments"] == '["went well"]'
    assert _ids(_listing(sel, filter_name="interview")) == ["a"]

    _set_feedback("a", "new", selection_id=None)
    with db.session() as conn:
        conn.row_factory = selections._dict_row
        row = conn.execute(selections.load_queries()["vacancy_progress"], {"id": "a"}).fetchone()
    assert row["applied_at"] is None and row["contact_at"] is None
    assert row["interview_comments"] is None and row["final_comment"] is None
    assert row["declined_comment"] is None and row["declined_at"] is None


def test_every_language_of_the_app_gets_its_row_and_view_keeps_the_identitys(isolated_data_dir):
    import i18n

    sel = _store({"a": _vacancy("a")})
    row = _listing(sel)[0]
    views = json.loads(row["views"])
    assert set(views) == set(i18n.LANGUAGES)
    assert json.loads(row["view"]) == views[i18n.language()]
    assert views["ru"]["salary"] != views["en"]["salary"]


def test_refresh_views_renders_shown_rows_again_without_a_selection(isolated_data_dir):
    sel = _store({"a": _vacancy("a")})
    kb.save_vacancies({"b": _vacancy("b")})          # never shown: stays without a row
    with db.session() as conn:
        conn.execute("UPDATE vacancies SET views = NULL")
    renamed = {"a": {**_vacancy("a"), "title": "Renamed"}, "b": _vacancy("b")}
    assert selections.refresh_views(renamed) == 1
    row = _listing(sel)[0]
    assert {v["title"] for v in json.loads(row["views"]).values()} == {"Renamed"}
    assert json.loads(row["view"])["title"] == "Renamed"
    with db.session() as conn:
        assert conn.execute("SELECT COUNT(*) FROM selections").fetchone()[0] == 1
        assert conn.execute("SELECT view FROM vacancies WHERE id = 'b'").fetchone()[0] is None


# --- the source filter -------------------------------------------------------
# The owner, 2026-10-04: a "Source" drop-down next to "Show", the two applied
# together.

def _by_source():
    vacancies = {}
    for i in range(6):
        vacancies[f"l{i}"] = _vacancy(f"l{i}", score=90 - i, source="linkedin")
    for i in range(3):
        vacancies[f"d{i}"] = _vacancy(f"d{i}", score=50 - i, source="devitjobs",
                                      classification="worth_a_look")
    return vacancies


def test_the_source_narrows_the_listing_and_works_with_the_status_filter(isolated_data_dir):
    sel = _store(_by_source())
    _set_feedback("l0", "rejected", selection_id=sel)
    _set_feedback("d0", "rejected", selection_id=sel)
    with db.session() as conn:
        def ids(name, source):
            return set(_ids(selections.listing(conn, sel, "full", name, source=source)))
        assert ids("fresh_new", "devitjobs") == {"d1", "d2"}
        assert ids("rejected", "linkedin") == {"l0"}
        assert ids("rejected", "devitjobs") == {"d0"}
        assert ids("all", "") == set(_by_source())
        assert ids("all", "nowhere") == set()


def test_counts_and_totals_follow_the_source(isolated_data_dir):
    sel = _store(_by_source())
    _set_feedback("l0", "applied", selection_id=sel)
    with db.session() as conn:
        for source in ("", "linkedin", "devitjobs"):
            counts = selections.listing_counts(conn, sel, "full", source)
            for name in selections.FILTERS:
                rows = selections.listing(conn, sel, "full", name,
                                          expanded=_all_classes(), source=source)
                totals = selections.class_totals(conn, sel, "full", name, source)
                assert counts[name] == len(rows) == sum(totals.values()), (source, name)
        assert selections.listing_counts(conn, sel, "full", "devitjobs")["applied"] == 0
        assert selections.listing_counts(conn, sel, "full", "linkedin")["applied"] == 1


def test_the_source_list_counts_under_the_status_filter(isolated_data_dir):
    sel = _store(_by_source())
    _set_feedback("d0", "rejected", selection_id=sel)
    _set_feedback("l0", "applied", selection_id=sel)
    with db.session() as conn:
        assert selections.listing_sources(conn, sel, "full", "all") == {"linkedin": 6, "devitjobs": 3}
        assert list(selections.listing_sources(conn, sel, "full", "all")) == ["linkedin", "devitjobs"]
        assert selections.listing_sources(conn, sel, "full", "fresh_new") == {"linkedin": 5, "devitjobs": 2}
        assert selections.listing_sources(conn, sel, "full", "rejected") == {"devitjobs": 1}
        assert selections.listing_sources(conn, sel, "full", "applied") == {"linkedin": 1}


def test_a_view_written_before_it_carried_the_source_is_still_filtered(isolated_data_dir):
    """Views recorded before 2026-10-04 have no "source": the record's is read."""
    sel = _store(_by_source())
    with db.session() as conn:
        conn.execute("UPDATE vacancies SET view = json_remove(view, '$.source')")
    with db.session() as conn:
        assert set(_ids(selections.listing(conn, sel, "full", "all", source="devitjobs"))) == {"d0", "d1", "d2"}
        assert selections.listing_sources(conn, sel, "full", "all") == {"linkedin": 6, "devitjobs": 3}
