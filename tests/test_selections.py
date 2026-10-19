"""Selections in the database (tools/selections.py) and the queries the app
lists them with (schemas/queries.sql): markets, the per-class limit, the view
(several markets, statuses, freshness, boards and classes at once), freshness
across runs, and the row view shared with the report."""
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
    {"slug": "full", "name": "Everything", "everything": True, "default": True,
     "translations": {"ru": "Vsyo vmeste"}},
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
        **extra,
    }


def _store(vacancies: dict, kind="run", run=1) -> int:
    kb.save_vacancies(vacancies)
    return selections.record(vacancies, {"run_count": run}, kind=kind)


def _set_feedback(vid, status, reason=None, selection_id=None):
    """Exactly what the app runs."""
    with db.session() as conn:
        conn.execute(selections.load_queries()["set_feedback"], {
            "identity": db.identity(), "id": vid, "status": status,
            "rejected_reason": reason if status == "rejected" else None,
            "bugged_reason": reason if status == "bugged" else None,
            "at": db.now_iso(), "selection_id": selection_id,
        })


# The single filters the app had before 2026-10-07, as views: the guarantees
# below were written against them and still hold.
FILTERS = ("fresh_new", "no_feedback", "all", "fresh") + selections.FUNNEL + selections.DENIED


def _view(segment="full", filter_name="fresh_new", source=None, fit=None):
    fresh = ("fresh",) if filter_name in ("fresh_new", "fresh") else selections.FRESHNESS
    statuses = {"fresh_new": selections.NEW, "no_feedback": selections.NEW,
                "all": selections.STATUSES, "fresh": selections.STATUSES}.get(filter_name, (filter_name,))
    segments_ = [segment] if isinstance(segment, str) else segment
    return selections.view(segments_, statuses, fresh,
                           sources=[source] if source else None, fits=[fit] if fit else None)


def _listing(selection_id, segment="full", filter_name="fresh_new", **kw):
    with db.session() as conn:
        return selections.listing(conn, selection_id, _view(segment, filter_name), **kw)


def _count(conn, selection_id, chosen):
    """The view's size by the "Show" drop-down's numbers — both axes agree."""
    counts = selections.counts(conn, selection_id, chosen)
    by_status = sum(counts["statuses"][s] for s in chosen["statuses"])
    by_fresh = sum(counts["fresh"][f] for f in chosen["fresh"])
    assert by_status == by_fresh, chosen
    return by_status


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
        rows = conn.execute(selections.load_queries()["segments"], {"selection_id": sel}).fetchall()
    assert [r[0] for r in rows] == ["worldwide", "uk", "rest", "full"]
    # The market holding everything is the app's "all markets" row.
    assert [r[5] for r in rows] == [0, 0, 0, 1]
    # Each market's name in every language the configuration gives.
    assert json.loads(rows[3][2]) == {"en": "Everything", "ru": "Vsyo vmeste"}
    assert json.loads(rows[1][2]) == {"en": "United Kingdom"}


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
    assert ids("no_feedback") == {"old_new", "new"}
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
        for name in FILTERS:
            chosen = _view("full", name)
            everything = selections.listing(conn, sel, chosen, expanded=_all_classes())
            totals = selections.class_totals(conn, sel, chosen)
            assert _count(conn, sel, chosen) == len(everything) == sum(totals.values()), name
    # fresh worth_a_look: limit+4 of which 2 marked -> limit+2 new, capped on screen
    with db.session() as conn:
        shown = selections.listing(conn, sel, _view())
        totals = selections.class_totals(conn, sel, _view())
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
        for name in FILTERS:
            full = _count(conn, sel, _view("full", name))
            parts = sum(_count(conn, sel, _view(seg, name)) for seg in ("worldwide", "uk", "rest"))
            together = _count(conn, sel, _view(["worldwide", "uk", "rest"], name))
            assert parts == full == together, name


def test_several_markets_list_a_vacancy_once(isolated_data_dir):
    """Markets chosen together (the owner, 2026-10-07): a vacancy in two of
    them is one row."""
    sel = _store({
        "w": _vacancy("w"),
        "uk": _vacancy("uk", "London, United Kingdom"),
        "ca": _vacancy("ca", "Toronto, Ontario, Canada"),
    })
    assert set(_ids(_listing(sel, ["uk", "worldwide"]))) == {"uk", "w"}
    assert sorted(_ids(_listing(sel, ["uk", "full"]))) == ["ca", "uk", "w"]
    assert _listing(sel, []) == []


def test_an_expanded_class_shows_every_row(isolated_data_dir):
    limit = report.TOP_N_PER_SECTION
    sel = _store({f"v{i:02}": _vacancy(f"v{i:02}", score=100 - i) for i in range(limit + 5)})
    assert len(_listing(sel, filter_name="all")) == limit
    assert len(_listing(sel, filter_name="all", expanded=("hot_lead",))) == limit + 5
    assert len(_listing(sel, filter_name="all", expanded=("long_shot",))) == limit


def test_shown_raises_the_limit_of_one_class(isolated_data_dir):
    """"Show more" and the scroll ask ten more rows of a class at a time
    (the owner, 2026-10-04)."""
    limit = report.TOP_N_PER_SECTION
    vacancies = {f"v{i:02}": _vacancy(f"v{i:02}", score=100 - i) for i in range(limit + 20)}
    vacancies.update({f"w{i}": _vacancy(f"w{i}", score=40 - i, classification="worth_a_look")
                      for i in range(limit + 5)})
    sel = _store(vacancies)
    _set_feedback("v00", "applied", selection_id=sel)
    def count(cls, **kw):
        return sum(r["class"] == cls for r in _listing(sel, filter_name="all", **kw))
    assert count("hot_lead", shown={"hot_lead": limit + 10}) == 1 + limit + 10, "feedback rows uncapped"
    assert count("worth_a_look", shown={"hot_lead": limit + 10}) == limit
    assert count("hot_lead", shown={"hot_lead": 1000}) == limit + 20
    rows = _listing(sel, filter_name="all", shown={"hot_lead": limit + 1})
    # The vacancies without an answer by score, the application after them.
    assert _ids(rows)[:3] == ["v01", "v02", "v03"] and "v00" in _ids(rows), "the order stays"


def test_fit_narrows_the_listing_counts_and_sources_to_one_class(isolated_data_dir):
    """The third drop-down: one class, together with the status and the source."""
    sel = _store(_by_source())
    _set_feedback("l0", "applied", selection_id=sel)
    _set_feedback("d0", "rejected", selection_id=sel)
    with db.session() as conn:
        for fit in ("hot_lead", "worth_a_look"):
            totals = selections.class_totals(conn, sel, _view("full", "all", fit=fit))
            for name in FILTERS:
                chosen = _view("full", name, fit=fit)
                rows = selections.listing(conn, sel, chosen, expanded=_all_classes())
                assert {r["class"] for r in rows} <= {fit}, (fit, name)
                assert _count(conn, sel, chosen) == len(rows), (fit, name)
            assert _count(conn, sel, _view("full", "all", fit=fit)) == totals[fit]
        assert selections.sources(conn, sel, _view("full", "all", fit="worth_a_look")) == {"devitjobs": 3}
        assert selections.sources(conn, sel, _view("full", "applied", fit="worth_a_look")) == {}
        assert selections.sources(conn, sel, _view("full", "applied", fit="hot_lead")) == {"linkedin": 1}
        assert _ids(selections.listing(conn, sel, _view("full", "rejected", source="devitjobs",
                                                        fit="worth_a_look"))) == ["d0"]
        assert selections.listing(conn, sel, _view("full", "rejected", source="linkedin",
                                                   fit="worth_a_look")) == []


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
        (name,) = conn.execute(selections.load_queries()["display_name"],
                               {"identity": db.identity()}).fetchone()
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
    for name in FILTERS:
        assert "old" not in _ids(_listing(second, filter_name=name)), name
    with db.session() as conn:
        assert _count(conn, second, _view("full", "rejected")) == 0

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
            chosen = _view(segment, "applied")
            assert _ids(selections.listing(conn, second, chosen)) == ["a"], segment
            assert _count(conn, second, chosen) == 1
            assert selections.class_totals(conn, second, chosen) == {"hot_lead": 1}


def test_applying_dates_the_funnel_and_going_back_forgets_it(isolated_data_dir):
    sel = _store({"a": _vacancy("a")})
    _set_feedback("a", "applied", selection_id=sel)
    with db.session() as conn:
        conn.execute(selections.load_queries()["write_progress"], {
            "identity": db.identity(), "id": "a", "status": "interview", "at": "2026-10-02T10:00:00+00:00",
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
        row = conn.execute(selections.load_queries()["vacancy_progress"],
                           {"identity": db.identity(), "id": "a"}).fetchone()
    assert row["feedback_status"] == "interview"
    assert row["contact_comment"] == "" and row["interview_comments"] == '["went well"]'
    assert _ids(_listing(sel, filter_name="interview")) == ["a"]

    _set_feedback("a", "new", selection_id=None)
    with db.session() as conn:
        conn.row_factory = selections._dict_row
        row = conn.execute(selections.load_queries()["vacancy_progress"],
                           {"identity": db.identity(), "id": "a"}).fetchone()
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
        conn.execute("UPDATE vacancy_identity SET views = NULL")
    renamed = {"a": {**_vacancy("a"), "title": "Renamed"}, "b": _vacancy("b")}
    assert selections.refresh_views(renamed) == 1
    row = _listing(sel)[0]
    assert {v["title"] for v in json.loads(row["views"]).values()} == {"Renamed"}
    assert json.loads(row["view"])["title"] == "Renamed"
    with db.session() as conn:
        assert conn.execute("SELECT COUNT(*) FROM selections").fetchone()[0] == 1
        assert conn.execute("SELECT view FROM vacancy_identity WHERE vacancy_id = 'b'"
                            ).fetchone()[0] is None


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
            return set(_ids(selections.listing(conn, sel, _view("full", name, source=source))))
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
            for name in FILTERS:
                chosen = _view("full", name, source=source)
                rows = selections.listing(conn, sel, chosen, expanded=_all_classes())
                totals = selections.class_totals(conn, sel, chosen)
                assert _count(conn, sel, chosen) == len(rows) == sum(totals.values()), (source, name)
        assert _count(conn, sel, _view("full", "applied", source="devitjobs")) == 0
        assert _count(conn, sel, _view("full", "applied", source="linkedin")) == 1


def test_the_source_list_counts_under_the_status_filter(isolated_data_dir):
    sel = _store(_by_source())
    _set_feedback("d0", "rejected", selection_id=sel)
    _set_feedback("l0", "applied", selection_id=sel)
    with db.session() as conn:
        def boards(name, **kw):
            return selections.sources(conn, sel, _view("full", name, **kw))
        assert boards("all") == {"linkedin": 6, "devitjobs": 3}
        assert list(boards("all")) == ["linkedin", "devitjobs"]
        assert boards("fresh_new") == {"linkedin": 5, "devitjobs": 2}
        assert boards("rejected") == {"devitjobs": 1}
        assert boards("applied") == {"linkedin": 1}
        assert boards("all", source="linkedin") == boards("all"), "the chosen board aside"


def test_a_view_written_before_it_carried_the_source_is_still_filtered(isolated_data_dir):
    """Views recorded before 2026-10-04 have no "source": the record's is read."""
    sel = _store(_by_source())
    with db.session() as conn:
        conn.execute("UPDATE vacancy_identity SET view = json_remove(view, '$.source')")
    with db.session() as conn:
        assert set(_ids(selections.listing(conn, sel, _view("full", "all", source="devitjobs")))) \
            == {"d0", "d1", "d2"}
        assert selections.sources(conn, sel, _view("full", "all")) == {"linkedin": 6, "devitjobs": 3}


def test_a_selection_carries_the_websites_of_the_sources(isolated_data_dir):
    """The app shows "linkedin.com", not "linkedin" (the owner, 2026-10-04);
    it reads the database only, so the catalogue's sites travel in meta."""
    _store(_by_source())
    with db.session() as conn:
        (value,) = conn.execute(selections.load_queries()["source_sites"]).fetchone()
    sites = json.loads(value)
    assert sites["linkedin"] == "linkedin.com"
    assert sites["mycareersfuture"] == "mycareersfuture.gov.sg"


def test_every_automatic_source_in_the_catalogue_names_its_website():
    import common

    catalog = common.load_yaml(common.shared_config("sources.catalog.yaml"))
    missing = [s["name"] for s in catalog["sources"]
               if s.get("kind") != "manual_ingest" and not s.get("site")]
    assert missing == []


# --- the view: several rows of each drop-down at once -------------------------
# The owner, 2026-10-07: checkboxes in all four drop-downs; "Show" is two axes,
# freshness and status, applied together.

def _two_runs():
    def v(vid, source="linkedin", **kw):
        return _vacancy(vid, source=source, **kw)
    _store({"old_new": v("old_new"), "old_applied": v("old_applied"), "old_rejected": v("old_rejected")})
    sel = _store({
        "old_new": v("old_new"), "old_applied": v("old_applied"), "old_rejected": v("old_rejected"),
        "new": v("new"), "applied": v("applied"),
        "rejected": v("rejected", source="devitjobs"),
        "bugged": v("bugged", classification="worth_a_look"),
    }, run=2)
    for vid, status in (("old_applied", "applied"), ("applied", "applied"),
                        ("old_rejected", "rejected"), ("rejected", "rejected"),
                        ("bugged", "bugged")):
        _set_feedback(vid, status, selection_id=sel)
    return sel


def test_freshness_and_status_are_applied_together(isolated_data_dir):
    sel = _two_runs()
    with db.session() as conn:
        def ids(statuses, fresh=selections.FRESHNESS, **kw):
            chosen = selections.view(["full"], statuses, fresh, **kw)
            return set(_ids(selections.listing(conn, sel, chosen, expanded=_all_classes())))
        assert ids(selections.NEW, ("fresh",)) == {"new"}, "the default"
        assert ids(selections.NEW, ("earlier",)) == {"old_new"}
        assert ids(selections.FUNNEL, ("fresh",)) == {"applied"}
        assert ids(selections.FUNNEL) == {"applied", "old_applied"}
        assert ids(selections.NEW + selections.DENIED, ("fresh",)) == {"new", "rejected", "bugged"}
        assert ids(("rejected", "bugged")) == {"old_rejected", "rejected", "bugged"}
        assert ids(selections.STATUSES, ()) == set(), "no freshness chosen: nothing"
        assert ids((), selections.FRESHNESS) == set(), "no status chosen: nothing"


def test_several_boards_and_classes_and_none_of_them(isolated_data_dir):
    sel = _two_runs()
    with db.session() as conn:
        def ids(**kw):
            chosen = selections.view(["full"], selections.STATUSES, **kw)
            return set(_ids(selections.listing(conn, sel, chosen, expanded=_all_classes())))
        everything = ids()
        assert ids(sources=["devitjobs"]) == {"rejected"}
        assert ids(sources=["devitjobs", "linkedin"]) == ids(sources=None) == everything
        assert ids(sources=[]) == set()
        assert ids(fits=["worth_a_look"]) == {"bugged"}
        assert ids(fits=["worth_a_look", "hot_lead"]) == everything
        assert ids(fits=[]) == set()


def test_each_axis_of_show_is_counted_under_the_other(isolated_data_dir):
    sel = _two_runs()
    with db.session() as conn:
        counts = selections.counts(conn, sel, selections.view(["full"], selections.NEW, ("fresh",)))
    # statuses under "fresh"; freshness under "not applied or denied"
    assert counts["statuses"]["new"] == 1 and counts["statuses"]["applied"] == 1
    assert counts["statuses"]["rejected"] == 1 and counts["statuses"]["bugged"] == 1
    assert counts["fresh"] == {"fresh": 1, "earlier": 1}


def test_class_totals_leave_the_chosen_classes_aside(isolated_data_dir):
    sel = _two_runs()
    with db.session() as conn:
        chosen = selections.view(["full"], selections.STATUSES, fits=["worth_a_look"])
        assert selections.class_totals(conn, sel, chosen) == {"hot_lead": 6, "worth_a_look": 1}


def test_an_unknown_status_or_freshness_is_refused(isolated_data_dir):
    sel = _store({"a": _vacancy("a")})
    with db.session() as conn, pytest.raises(ValueError):
        selections.listing(conn, sel, selections.view(["full"], ("archived",)))
    with db.session() as conn, pytest.raises(ValueError):
        selections.listing(conn, sel, selections.view(["full"], fresh=("stale",)))



def test_the_age_comes_from_the_posted_date_else_the_first_sighting(isolated_data_dir):
    from datetime import date, timedelta
    day = lambda n: (date.today() - timedelta(days=n)).isoformat()
    sel = _store({
        "t": _vacancy("t", posted_at=day(0)),
        "w": _vacancy("w", posted_at=day(6)),
        "m": _vacancy("m", posted_at=day(25)),
        "o": _vacancy("o", posted_at=day(45), first_seen=day(1)),
        "f": _vacancy("f", first_seen=day(40)),
    })
    every = selections.view(["full"], selections.STATUSES, selections.FRESHNESS)
    with db.session() as conn:
        assert selections.ages(conn, sel, {**every, "ages": ["today"]}) ==             {"today": 1, "week": 1, "month": 1, "older": 2}
        def ids(ages):
            return set(_ids(selections.listing(conn, sel, {**every, "ages": ages})))
        assert ids(["today", "week"]) == {"t", "w"}
        assert ids(["older"]) == {"o", "f"}
        assert ids([]) == set()
        assert _count(conn, sel, {**every, "ages": ["month"]}) == 1
        with pytest.raises(ValueError):
            selections.listing(conn, sel, {**every, "ages": ["ancient"]})

def test_the_words_typed_narrow_the_list_and_every_count(isolated_data_dir):
    sel = _store({
        "a": _vacancy("a", title="Backend Engineer (Go)", company="Zürich Labs"),
        "b": _vacancy("b"),
        "c": _vacancy("c", title="Разработчик Ёлка"),
    })
    every = selections.view(["full"], selections.STATUSES, selections.FRESHNESS)
    with db.session() as conn:
        def ids(text):
            return set(_ids(selections.listing(conn, sel, {**every, "text": text})))
        assert ids("backend") == {"a"}
        assert ids("ENGINEER zürich") == {"a"}
        assert ids("zurich") == {"a"}
        assert ids("ZÜRICH") == {"a"}
        assert ids("engineer acme") == set()
        assert ids("example.test/b") == {"b"}
        assert ids("разработчик") == {"c"}
        assert ids("ЕЛКА") == {"c"}
        assert ids("  ") == {"a", "b", "c"}
        assert _count(conn, sel, {**every, "text": "backend"}) == 1
        assert selections.class_totals(conn, sel, {**every, "text": "backend"}) == {"hot_lead": 1}


# --- the company: freelance marketplaces, agencies, reposters, the rest --------
# The owner, 2026-10-14: a fifth drop-down, the intermediaries by kind and by
# name, every other company one row (tools/company_kinds.py).

def _by_company():
    companies = {"p0": "Proxify", "p1": "Proxify AB", "t0": "Toptal", "h0": "Hays Technology",
                 "j0": "Jobgether", "s0": "Stripe", "s1": "Ramp", "s2": "Notion"}
    return {vid: _vacancy(vid, score=90 - i, company=company,
                          source="devitjobs" if vid == "s2" else "linkedin",
                          classification="worth_a_look" if vid == "h0" else "hot_lead")
            for i, (vid, company) in enumerate(companies.items())}


def _companies(kinds=selections.COMPANY_KINDS, hidden=()):
    return {"kinds": list(kinds), "hidden": list(hidden)}


def test_a_selection_carries_the_kind_of_each_intermediary(isolated_data_dir):
    _store(_by_company())
    with db.session() as conn:
        (value,) = conn.execute("SELECT value FROM meta WHERE key = 'company_kinds'").fetchone()
    assert json.loads(value) == {
        "Proxify": {"kind": "marketplace", "name": "Proxify"},
        "Proxify AB": {"kind": "marketplace", "name": "Proxify"},
        "Toptal": {"kind": "marketplace", "name": "Toptal"},
        "Hays Technology": {"kind": "agency", "name": "Hays"},
        "Jobgether": {"kind": "reposter", "name": "Jobgether"},
    }


def test_the_company_narrows_the_listing_by_kind_and_by_name(isolated_data_dir):
    sel = _store(_by_company())
    with db.session() as conn:
        def ids(companies):
            chosen = selections.view(["full"], selections.STATUSES, companies=companies)
            return set(_ids(selections.listing(conn, sel, chosen, expanded=_all_classes())))
        everything = set(_by_company())
        assert ids(None) == ids(_companies()) == everything
        assert ids(_companies(["marketplace"])) == {"p0", "p1", "t0"}
        assert ids(_companies(["other"])) == {"s0", "s1", "s2"}
        assert ids(_companies(hidden=["Proxify"])) == everything - {"p0", "p1"}, "both spellings"
        assert ids(_companies(["agency", "reposter"], hidden=["Hays"])) == {"j0"}
        assert ids(_companies([])) == set()
        # a name is hidden whatever its kind says; "other" has no names
        assert ids(_companies(["other"], hidden=["Stripe"])) == {"s0", "s1", "s2"}


def test_counts_totals_and_sources_follow_the_company(isolated_data_dir):
    sel = _store(_by_company())
    no_marketplaces = _companies(["agency", "reposter", "other"])
    with db.session() as conn:
        chosen = selections.view(["full"], selections.STATUSES, companies=no_marketplaces)
        rows = selections.listing(conn, sel, chosen, expanded=_all_classes())
        assert _count(conn, sel, chosen) == len(rows) == 5
        assert selections.class_totals(conn, sel, chosen) == {"hot_lead": 4, "worth_a_look": 1}
        assert selections.sources(conn, sel, chosen) == {"linkedin": 4, "devitjobs": 1}


def test_the_company_list_counts_under_the_other_drop_downs_not_itself(isolated_data_dir):
    sel = _store(_by_company())
    _set_feedback("s0", "rejected", selection_id=sel)
    with db.session() as conn:
        def listed(**kw):
            return selections.companies(conn, sel, selections.view(["full"], **kw))
        assert listed(statuses=selections.STATUSES) == [
            ("other", None, 3), ("marketplace", "Proxify", 2), ("agency", "Hays", 1),
            ("marketplace", "Toptal", 1), ("reposter", "Jobgether", 1)]
        assert ("other", None, 2) in listed(), "the denied one aside"
        assert listed(statuses=selections.STATUSES, sources=["devitjobs"]) == [("other", None, 1)]
        assert listed(statuses=selections.STATUSES, fits=["worth_a_look"]) == [("agency", "Hays", 1)]
        assert listed(statuses=selections.STATUSES, companies=_companies(["other"])) \
            == listed(statuses=selections.STATUSES), "the chosen companies aside"


def test_a_base_without_company_kinds_has_only_other_companies(isolated_data_dir):
    """A base last written before 2026-10-14: every company is "other" until
    the next run or rebuild, and the filter still works."""
    sel = _store(_by_company())
    with db.session() as conn:
        conn.execute("DELETE FROM meta WHERE key = 'company_kinds'")
    with db.session() as conn:
        assert selections.companies(conn, sel, selections.view(["full"], selections.STATUSES)) \
            == [("other", None, 8)]
        chosen = selections.view(["full"], selections.STATUSES, companies=_companies(["marketplace"]))
        assert selections.listing(conn, sel, chosen) == []


def test_refreshing_the_views_writes_the_company_kinds_again(isolated_data_dir):
    vacancies = _by_company()
    _store(vacancies)
    with db.session() as conn:
        conn.execute("DELETE FROM meta WHERE key = 'company_kinds'")
    selections.refresh_views(vacancies)
    with db.session() as conn:
        (value,) = conn.execute("SELECT value FROM meta WHERE key = 'company_kinds'").fetchone()
    assert json.loads(value)["Proxify AB"] == {"kind": "marketplace", "name": "Proxify"}


def test_an_unknown_company_kind_is_refused(isolated_data_dir):
    sel = _store({"a": _vacancy("a")})
    with db.session() as conn, pytest.raises(ValueError):
        selections.listing(conn, sel, selections.view(["full"], companies={"kinds": ["employer"]}))
