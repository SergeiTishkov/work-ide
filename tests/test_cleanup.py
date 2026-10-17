"""tools/cleanup.py: the app's "Clean up" button deletes vacancies for good,
by age, status and class, and never what the person still needs."""
from datetime import date

import pytest

import cleanup
import db

TODAY = date(2026, 10, 17)


def _base(rows):
    """rows: {vid: (posted_at, first_seen, {identity: (status, class, reviewed)})}"""
    with db.session() as conn:
        for ident in ("sharp", "partsharp"):
            conn.execute("INSERT OR IGNORE INTO identities (id, created_at) VALUES (?, ?)", (ident, db.now_iso()))
        conn.execute("INSERT INTO selections (identity_id, run, created_at, kind) VALUES ('sharp', 1, ?, 'run')",
                     (db.now_iso(),))
        for vid, (posted, seen, held) in rows.items():
            conn.execute("INSERT INTO vacancies (id, data) VALUES (?, ?)",
                         (vid, db.dumps({"id": vid, "posted_at": posted, "first_seen": seen})))
            for ident, (status, cls, reviewed) in held.items():
                conn.execute("INSERT INTO vacancy_identity (identity_id, vacancy_id, class, feedback_status, "
                             "feedback_reviewed_at) VALUES (?, ?, ?, ?, ?)", (ident, vid, cls, status, reviewed))
            conn.execute("INSERT INTO selection_items (selection_id, segment, vacancy_id, class, class_position, "
                         "section_limit, score, eligibility_rank) VALUES (1, 'full', ?, 'hot_lead', 0, 15, 50, 0)",
                         (vid,))


def _ids(conn, table, column="id"):
    return {r[0] for r in conn.execute(f"SELECT {column} FROM {table}")}


@pytest.mark.parametrize("posted, seen, band", [
    ("2026-10-17", None, "today"), ("2026-10-12T08:00:00Z", None, "week"),
    ("Thu, 24 Sep 2026 10:00:00 +0000", None, "month"), ("2026-09-01", "2026-10-16", "older"),
    (None, "2026-09-01T00:00:00+00:00", "older"), (None, None, "today"),
])
def test_the_age_is_the_posted_date_else_the_first_sighting(posted, seen, band):
    assert cleanup.age_band(posted, seen, TODAY) == band


def test_old_ones_go_but_the_funnel_and_unread_feedback_stay(isolated_data_dir):
    both = lambda status="new", cls="hot_lead", reviewed=None: {
        "sharp": (status, cls, reviewed), "partsharp": ("new", "rejected", None)}
    _base({
        "old": ("2026-08-01", None, both()),
        "fresh": ("2026-10-16", None, both()),
        "applied": ("2026-08-01", None, both("applied")),
        "unread": ("2026-08-01", None, both("bugged")),
        "read": ("2026-08-01", None, both("bugged", reviewed="2026-10-10")),
        "declined": ("2026-08-01", None, {"sharp": ("new", "rejected", None),
                                           "partsharp": ("declined", "hot_lead", None)}),
    })
    with db.session() as conn:
        found = cleanup.plan(conn, "sharp", ages=["older"], today=TODAY)
    assert sorted(found["delete"]) == ["old", "read"]
    assert (found["kept_funnel"], found["kept_unreviewed"]) == (2, 1)


def test_a_filter_holds_in_every_identity_that_has_the_vacancy(isolated_data_dir):
    _base({
        "both_expired": ("2026-10-10", None, {"sharp": ("expired", "hot_lead", None),
                                              "partsharp": ("expired", "long_shot", None)}),
        "only_here": ("2026-10-10", None, {"sharp": ("expired", "hot_lead", None),
                                           "partsharp": ("new", "hot_lead", None)}),
        "sharp_only": ("2026-10-10", None, {"sharp": ("expired", "hot_lead", None)}),
    })
    with db.session() as conn:
        found = cleanup.plan(conn, "sharp", statuses=["expired"], today=TODAY)
        assert sorted(found["delete"]) == ["both_expired", "sharp_only"]
        assert found["kept_other_identity"] == 1
        assert cleanup.plan(conn, "sharp", classes=["long_shot"], today=TODAY)["delete"] == []


def test_run_deletes_every_row_of_the_vacancy_and_a_dry_run_nothing(isolated_data_dir):
    _base({"a": ("2026-01-01", None, {"sharp": ("new", "rejected", None)}),
           "b": (date.today().isoformat(), None, {"sharp": ("new", "hot_lead", None)})})
    dry = cleanup.run("sharp", ages=["older"], dry_run=True)
    assert (dry["matched"], dry["deleted"]) == (1, 0)
    done = cleanup.run("sharp", ages=["older"], vacuum=False)
    assert done["deleted"] == 1
    with db.session() as conn:
        assert _ids(conn, "vacancies") == {"b"}
        assert _ids(conn, "vacancy_identity", "vacancy_id") == {"b"}
        assert _ids(conn, "selection_items", "vacancy_id") == {"b"}


def test_no_filter_or_an_unknown_one_is_refused(isolated_data_dir):
    _base({})
    with db.session() as conn:
        with pytest.raises(ValueError):
            cleanup.plan(conn, "sharp")
        with pytest.raises(ValueError):
            cleanup.plan(conn, "sharp", ages=["ancient"])
        with pytest.raises(ValueError):
            cleanup.plan(conn, "sharp", statuses=["archived"])
