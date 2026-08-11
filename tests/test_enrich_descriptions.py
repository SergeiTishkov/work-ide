"""
Fetching descriptions for shortlist vacancies that arrived without one.

The gap this closes was measured, not guessed: 1023 LinkedIn cards in the base
had no description and 251 of them were in the head of the shortlist, where
every gate that reads text was deciding blind. See the module docstring of
tools/enrich_descriptions.py for the vacancy that made it visible.

No network here: the fetch is replaced, as everywhere else in this suite.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import enrich_descriptions  # noqa: E402


def _facts(description, workplace_type=None, salary_raw=None, closed=False):
    """What fetch_page_facts returns — one request, four facts."""
    return {"description": description, "workplace_type": workplace_type,
            "salary_raw": salary_raw, "closed": closed}


def _vacancy(score, classification, description="", url="https://x/1", **extra):
    record = {
        "url": url,
        "description_text": description,
        "computed": {"score": score, "classification": classification},
    }
    record.update(extra)
    return record


def test_only_shortlist_vacancies_without_a_description_are_fetched():
    """The point of running after scoring: spend a request on what a person may
    actually read, not on the whole tail of the base."""
    vacancies = {
        "a": _vacancy(60, "hot_lead"),                      # wanted
        "b": _vacancy(30, "worth_a_look"),                  # wanted
        "c": _vacancy(80, "rejected"),                      # not in the shortlist
        "d": _vacancy(70, "hot_lead", description="has text"),  # already has one
        "e": _vacancy(50, "long_shot", url=None),           # nothing to fetch from
    }
    assert set(enrich_descriptions.worklist(vacancies)) == {"a", "b"}


def test_the_highest_scoring_are_fetched_first():
    """If the budget runs out it should run out on the vacancies a person is
    least likely to reach."""
    vacancies = {
        "low": _vacancy(10, "long_shot"),
        "high": _vacancy(90, "hot_lead"),
        "mid": _vacancy(50, "worth_a_look"),
    }
    assert enrich_descriptions.worklist(vacancies, limit=2) == ["high", "mid"]


def test_a_page_that_gave_nothing_is_not_refetched_every_run(monkeypatch):
    """Without this the same dead pages are requested on every single run —
    the same reasoning as link_check's cache."""
    import fetch_linkedin

    monkeypatch.setattr(fetch_linkedin, "fetch_page_facts",
                        lambda url, timeout: _facts(""))
    vacancies = {"a": _vacancy(60, "hot_lead")}

    first = enrich_descriptions.enrich(vacancies)
    assert first["considered"] == 1 and first["empty"] == 1
    assert vacancies["a"]["description_fetch"]["chars"] == 0

    second = enrich_descriptions.enrich(vacancies)
    assert second["considered"] == 0, "an attempt already recorded must not repeat"


def test_a_fetched_description_lands_on_the_record(monkeypatch):
    import fetch_linkedin

    monkeypatch.setattr(fetch_linkedin, "fetch_page_facts",
                        lambda url, timeout: _facts("Must be US Citizen. C# and ASP.NET."))
    vacancies = {"a": _vacancy(32, "worth_a_look")}

    stats = enrich_descriptions.enrich(vacancies)

    assert stats["fetched"] == 1
    assert "US Citizen" in vacancies["a"]["description_text"], (
        "this is the whole point: the citizenship gate can only fire on text "
        "the scoring actually sees"
    )


def test_one_failing_page_does_not_stop_the_rest(monkeypatch):
    """The same principle as one source failing in the pipeline."""
    import fetch_linkedin

    def flaky(url, timeout):
        if url.endswith("boom"):
            raise RuntimeError("network")
        return _facts("C# and SQL Server.")

    monkeypatch.setattr(fetch_linkedin, "fetch_page_facts", flaky)
    vacancies = {
        "bad": _vacancy(90, "hot_lead", url="https://x/boom"),
        "good": _vacancy(80, "hot_lead", url="https://x/ok"),
    }

    stats = enrich_descriptions.enrich(vacancies)

    assert stats["errors"] == 1 and stats["fetched"] == 1
    assert vacancies["good"]["description_text"]


def test_coverage_counts_what_is_still_scored_blind():
    """The number that made the gap visible in the first place, so it can be
    watched rather than rediscovered."""
    vacancies = {
        "a": _vacancy(60, "hot_lead"),
        "b": _vacancy(50, "worth_a_look", description="text"),
        "c": _vacancy(90, "rejected"),
    }
    assert enrich_descriptions.coverage(vacancies) == {
        "in_shortlist": 2, "without_description": 1,
    }


def test_a_closed_vacancy_is_marked_dead(monkeypatch):
    """"No longer accepting applications" — found by the owner 2026-08-11 on a
    vacancy leading his shortlist at 65 (SharePoint & .NET Engineer @
    Jobstronaut).

    Recorded through link_check, which the report already filters on: the same
    treatment as a 404, and for the same reason — there is nothing on the other
    end of the link. Verified on three real pages: the marker is present for
    the closed one and absent for both open ones.
    """
    import fetch_linkedin

    monkeypatch.setattr(fetch_linkedin, "fetch_page_facts",
                        lambda url, timeout: _facts("SharePoint and .NET work.",
                                                    closed=True))
    vacancies = {"a": _vacancy(65, "hot_lead")}

    stats = enrich_descriptions.enrich(vacancies)

    assert stats["closed"] == 1
    assert vacancies["a"]["link_check"]["status"] == "dead"
    assert "no longer accepting" in vacancies["a"]["link_check"]["reason"]


def test_a_declared_remote_and_a_stated_salary_are_kept(monkeypatch):
    """Both arrive in the same response as the description, and both were being
    discarded. A salary stated in the vacancy is the highest of the three
    levels of trust (CLAUDE.md §5); TELECOMMUTE is the only positive proof of
    remoteness the guest page ever gives."""
    import fetch_linkedin

    monkeypatch.setattr(fetch_linkedin, "fetch_page_facts",
                        lambda url, timeout: _facts(
                            "C# and SQL Server.", workplace_type="remote",
                            salary_raw="CAD 80000-90000 YEAR"))
    vacancies = {"a": _vacancy(60, "hot_lead")}

    stats = enrich_descriptions.enrich(vacancies)

    assert stats["declared_remote"] == 1 and stats["salary_found"] == 1
    assert vacancies["a"]["workplace_type"] == "remote"
    assert vacancies["a"]["salary_raw"] == "CAD 80000-90000 YEAR"


def test_a_salary_already_known_is_not_overwritten(monkeypatch):
    """A board that stated the salary itself knows better than our parsing of
    somebody else's markup."""
    import fetch_linkedin

    monkeypatch.setattr(fetch_linkedin, "fetch_page_facts",
                        lambda url, timeout: _facts("C#.", salary_raw="USD 1 YEAR"))
    vacancies = {"a": _vacancy(60, "hot_lead", salary_raw="$120k-$140k")}

    enrich_descriptions.enrich(vacancies)

    assert vacancies["a"]["salary_raw"] == "$120k-$140k"
