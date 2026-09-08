"""
Three defects the first UK run exposed, and none of them was visible in a test.

All three were found by reading the numbers a finished run produced, which is
the only way any of them could have been found: each one looked like an
ordinary property of the data.

  1. **normalize dropped `workplace_type`.** ContractorUK badges 52 of 142
     vacancies Remote and Outside IR35 Jobs badges all 50 of its own — and
     every stored record had None. The tags beside it survived, so the loss
     read as "those boards do not publish an arrangement". They do; it was
     being thrown away between the fetcher and the database.

  2. **Reed's exhausted pagination was reported as an error.** The board
     answers 404 past the last page. "contract-net-developer p3: HTTPError" in
     the source-health panel is not a failure, and a panel full of harmless
     noise is a panel nobody reads.

  3. **`remote_unconfirmed` was never enriched.** That class holds more
     vacancies than every confident tier put together, and it exists precisely
     because nobody said whether the work is remote — which reading the
     description is the one thing that could settle. Of Reed's 222 records,
     five had any text.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import enrich_descriptions  # noqa: E402
import fetch_reed as reed  # noqa: E402
import normalize  # noqa: E402

RAW = {
    "source": "contractoruk",
    "external_id": "contractoruk:430150",
    "title": "Senior .Net Developer",
    "company": "Undisclosed agency (ContractorUK)",
    "url": "https://www.contractoruk.com/job/430150-x",
    "location_raw": "Nationwide",
    "remote": None,
    "tags": ["market:United Kingdom", "Outside IR35", "Remote"],
    "description_text": "C# and SQL Server.",
    "salary_raw": "£500 – £550/day",
}


# --- 1. the badge must survive normalisation -------------------------------

def test_the_arrangement_a_board_states_survives_normalisation():
    """The single most valuable thing ContractorUK and Outside IR35 Jobs give:
    the board ticking a box rather than a phrase somewhere in prose. It feeds
    the gate that rejects hybrid and onsite work outright."""
    record = normalize.normalize_record(dict(RAW, workplace_type="remote"))

    assert record["workplace_type"] == "remote"


def test_every_arrangement_the_scoring_understands_survives():
    for given, expected in [("remote", "remote"), ("hybrid", "hybrid"),
                            ("on-site", "on-site"), ("onsite", "on-site"),
                            ("Remote", "remote"), ("  HYBRID ", "hybrid")]:
        record = normalize.normalize_record(dict(RAW, workplace_type=given))
        assert record["workplace_type"] == expected, given


def test_a_spelling_nothing_downstream_reads_becomes_none():
    """A value the arrangement gate cannot interpret is worse than no value:
    it looks like knowledge and behaves like silence."""
    for given in (None, "", "somewhere", "flexible", 0, []):
        record = normalize.normalize_record(dict(RAW, workplace_type=given))
        assert record["workplace_type"] is None, given


def test_the_field_is_present_even_when_no_source_sets_it():
    """Absent and None must not be different states downstream."""
    record = normalize.normalize_record(dict(RAW))

    assert "workplace_type" in record
    assert record["workplace_type"] is None


# --- 2. an exhausted pagination is not a failure ---------------------------

def test_a_404_past_the_last_page_is_not_an_error(monkeypatch):
    """Reed answers 404 for a page that does not exist. Reporting that as a
    failure fills the source-health panel with noise and teaches a person to
    ignore the one place real breakage shows up."""
    import requests

    class FakeResponse:
        status_code = 404
        text = "not found"

        def raise_for_status(self):
            raise AssertionError("a 404 must be handled before this is called")

    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse())

    assert reed._fetch_page("net-developer", "", 3, 10) == ""


def test_a_real_failure_is_still_raised(monkeypatch):
    """The reverse guard: swallowing every status would hide a board that had
    genuinely broken."""
    import requests

    class FakeResponse:
        status_code = 500
        text = ""

        def raise_for_status(self):
            raise RuntimeError("500")

    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse())

    try:
        reed._fetch_page("net-developer", "", 1, 10)
    except RuntimeError:
        return
    raise AssertionError("a server error should not be silently swallowed")


def test_an_exhausted_pagination_produces_no_note(monkeypatch):
    """End to end: three pages asked for, one page of results, and nothing
    that reads as breakage."""
    from test_fetch_reed import SNAPSHOT

    def fake_page(keyword, variant, page, timeout):
        return SNAPSHOT if page == 1 else ""

    monkeypatch.setattr(reed, "_fetch_page", fake_page)
    monkeypatch.setattr(reed.time, "sleep", lambda *_: None)

    records, note = reed.fetch(keywords=["net-developer"], max_pages=3)

    assert len(records) == 2
    assert note is None, f"an exhausted pagination reported as: {note}"


# --- 3. the unconfirmed are exactly who needs reading ----------------------

def test_vacancies_nobody_called_remote_are_enriched():
    """The class exists because nobody said whether the work is remote. The
    description is the one thing that could settle it, and until 2026-09-08 it
    was the one thing never fetched — for more vacancies than every confident
    tier put together."""
    assert "remote_unconfirmed" in enrich_descriptions.HEAD_CLASSES


def test_the_unconfirmed_actually_reach_the_worklist():
    vacancies = {
        "hot": {"source": "reed", "url": "https://x/1", "description_text": "",
                "computed": {"score": 60, "classification": "hot_lead"}},
        "unconfirmed": {"source": "reed", "url": "https://x/2", "description_text": "",
                        "computed": {"score": 55, "classification": "remote_unconfirmed"}},
        "rejected": {"source": "reed", "url": "https://x/3", "description_text": "",
                     "computed": {"score": 90, "classification": "rejected"}},
    }

    assert set(enrich_descriptions.worklist(vacancies)) == {"hot", "unconfirmed"}
