"""report.vacancy_view(): the row data the app and the Markdown report share —
here, the two dates every row shows."""
import pytest

import report


@pytest.mark.parametrize("value, expected", [
    (1785899946, "2026-08-05"),                          # unix seconds (4dayweek)
    (1785899946000, "2026-08-05"),                       # milliseconds
    ("1785899946", "2026-08-05"),
    ("2026-07-27T11:17:30-04:00", "2026-07-27"),         # the source's own day, not shifted
    ("2026-08-05T14:27:12.425+00:00", "2026-08-05"),
    ("2025-02-26T09:38:38.127Z", "2025-02-26"),
    ("2026-07-28T14:23:05", "2026-07-28"),
    ("2026-08-15", "2026-08-15"),
    ("Thu, 23 Jul 2026 16:56:41 +0000", "2026-07-23"),   # RSS
    (None, None), ("", None), ("sometime last week", None), (True, None),
])
def test_calendar_date_reads_every_format_the_sources_use(value, expected):
    assert report.calendar_date(value) == expected


def test_view_carries_posted_and_first_seen_dates():
    view = report.vacancy_view({
        "id": "a", "title": "t", "company": "c", "url": "u",
        "posted_at": "Thu, 23 Jul 2026 16:56:41 +0000",
        "first_seen": "2026-07-29T20:52:40.169266+00:00",
        "computed": {"score": 10, "classification": "hot_lead", "score_breakdown": {}},
    })
    assert view["posted_on"] == "2026-07-23"
    assert view["first_seen_on"] == "2026-07-29"


def test_a_vacancy_without_dates_says_so_with_none():
    view = report.vacancy_view({"id": "a", "computed": {}})
    assert view["posted_on"] is None and view["first_seen_on"] is None


def test_the_row_is_rendered_in_every_language_of_the_app():
    import i18n

    before = i18n.language()
    views = report.vacancy_views({"id": "a", "computed": {
        "score": 10, "classification": "hot_lead", "score_breakdown": {}}})
    assert set(views) == set(i18n.LANGUAGES) == {"en", "ru"}
    assert views["en"]["salary"].startswith("not stated")
    assert views["ru"]["salary"].startswith(i18n.translate("not stated", "ru"))
    assert views["ru"]["salary"] != views["en"]["salary"]
    assert i18n.language() == before, "the identity's language is back after rendering"


def test_speaking_refuses_an_unknown_language_and_always_restores():
    import i18n

    before = i18n.language()
    with pytest.raises(ValueError):
        with i18n.speaking("xx"):
            pass
    with pytest.raises(RuntimeError):
        with i18n.speaking("ru"):
            assert i18n.language() == "ru"
            raise RuntimeError("a rendering failed")
    assert i18n.language() == before
