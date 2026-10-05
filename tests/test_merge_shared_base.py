"""How tools/merge_shared_base.py made one record of a vacancy two identities
had each stored (2026-10-05)."""
import merge_shared_base as merge


def test_the_later_fetch_wins_and_what_either_learned_is_kept():
    early = {"id": "x", "title": "Old title", "first_seen": "2026-08-01", "last_seen": "2026-09-01",
             "description_text": "The whole page, read once.", "tags": ["market:uk"],
             "employment_types": ["contract"], "external_signals": {"glassdoor": 4},
             "link_check": {"status": "alive", "checked_at": "2026-09-30"}}
    late = {"id": "x", "title": "New title", "first_seen": "2026-09-10", "last_seen": "2026-10-03",
            "description_text": "A snippet.", "tags": ["market:eu"],
            "employment_types": ["part-time"], "external_signals": {"salary_estimate": 1},
            "link_check": {"status": "dead", "checked_at": "2026-09-20"}}
    merged = merge.merge_facts([late, early])
    assert merged["title"] == "New title"
    assert merged["first_seen"] == "2026-08-01" and merged["last_seen"] == "2026-10-03"
    assert merged["description_text"] == "The whole page, read once."
    assert merged["tags"] == ["market:uk", "market:eu"]
    assert set(merged["employment_types"]) == {"contract", "part-time"}
    assert merged["external_signals"] == {"glassdoor": 4, "salary_estimate": 1}
    assert merged["link_check"]["checked_at"] == "2026-09-30", "the newer check"


def test_what_belongs_to_an_identity_is_not_a_fact():
    record = {"id": "x", "computed": {"score": 3}, "duplicate_of": "y", "manual": {"status": "new"},
              "_company_reputation": {}, "title": "T"}
    assert merge.facts_of(record) == {"id": "x", "title": "T"}


def test_companies_keep_what_was_gathered_by_hand():
    a = {"name": "Acme", "first_seen": "2026-09-01", "last_seen": "2026-09-05",
         "vacancy_ids": ["1"], "notes": "", "reputation": {"overall_rating": 4}}
    b = {"name": "Acme", "first_seen": "2026-08-01", "last_seen": "2026-10-01",
         "vacancy_ids": ["2"], "notes": "EOR ok", "intel": {"founded": 2001}}
    merged = merge.merge_companies([a, b])
    assert merged["reputation"] == {"overall_rating": 4} and merged["intel"] == {"founded": 2001}
    assert merged["notes"] == "EOR ok"
    assert (merged["first_seen"], merged["last_seen"]) == ("2026-08-01", "2026-10-01")
    assert merged["vacancy_ids"] == ["1", "2"]
