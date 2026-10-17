"""One vacancy's employer reputation on request (tools/reputation_lookup.py),
the app's "Collect reputation" button. No model is called: each test passes
a `call` of its own (conftest refuses the real one)."""
import json

import db
import kb
import report
import reputation_lookup


def _base():
    vacancy = {"id": "v1", "title": "Senior .NET Engineer", "company": "Acme Ltd",
               "source": "arbeitnow", "url": "https://example.com/v1",
               "location_raw": "Remote", "description_text": "C# and .NET, fully remote, worldwide."}
    vacancy["computed"] = {"classification": "hot_lead", "score": 50}
    vacancies = {"v1": vacancy}
    kb.save_vacancies(vacancies)
    kb.save_companies(kb.build_companies_from_vacancies(vacancies))
    # the app shows rows that have a view
    with db.session() as conn:
        conn.execute("UPDATE vacancy_identity SET view = '{}' WHERE vacancy_id = 'v1'")


def _view():
    with db.session() as conn:
        row = conn.execute("SELECT view FROM vacancy_identity WHERE vacancy_id = 'v1'").fetchone()
    return json.loads(row[0])


def _company():
    return kb.load_companies()[next(iter(kb.load_companies()))]


def test_found_ratings_are_recorded_and_the_card_says_so(isolated_data_dir):
    _base()
    asked = []

    def call(text):
        asked.append(text)
        return {"found": True, "overall_rating": 4.1, "work_life_balance": 3.9,
                "source": "Glassdoor", "retrieval": "web_search", "review_count": 120,
                "red_flags": [], "notes": "Calm pace, slow promotions.",
                "searched": "Glassdoor, Indeed"}, 0.12

    outcome = reputation_lookup.lookup("v1", call=call)
    assert "Company: Acme Ltd" in asked[0] and "fully remote" in asked[0]
    assert outcome["result"].startswith("found: 4.1") and outcome["cost_usd"] == 0.12
    rep = _company()["reputation"]
    assert rep["overall_rating"] == 4.1 and rep["source"] == "Glassdoor" and rep["checked_at"]
    view = _view()
    assert view["reputation_collected"] is True, "the button goes"
    assert "4.1" in view["reputation"]


def test_nothing_found_is_a_result_too(isolated_data_dir):
    _base()
    call = lambda text: ({"found": False, "overall_rating": None, "work_life_balance": None,  # noqa: E731
                          "source": "", "retrieval": "web_search", "review_count": None,
                          "red_flags": [], "notes": "", "searched": "Glassdoor, Trustpilot"}, 0.05)
    assert reputation_lookup.lookup("v1", call=call)["result"] == "too few sources"
    rep = _company()["reputation"]
    assert rep["verdict"] == "insufficient_sources" and rep["searched"] == "Glassdoor, Trustpilot"
    assert _view()["reputation_collected"] is True


def test_a_company_with_a_result_is_not_looked_up_again(isolated_data_dir):
    _base()
    first = lambda text: ({"found": False, "overall_rating": None, "work_life_balance": None,  # noqa: E731
                           "source": "", "retrieval": "web_search", "review_count": None,
                           "red_flags": [], "notes": "", "searched": "x"}, 0.05)
    reputation_lookup.lookup("v1", call=first)

    def refuse(text):
        raise AssertionError("no second lookup")

    outcome = reputation_lookup.lookup("v1", call=refuse)
    assert outcome["result"] == "already collected" and outcome["rescored"] == 1


def test_a_pipeline_saving_old_companies_keeps_a_newer_reputation(isolated_data_dir):
    """A pipeline loads the companies at its start and saves them whole at
    its end; a lookup recorded in between must survive."""
    _base()
    loaded_by_the_pipeline = kb.load_companies()
    reputation_lookup.lookup("v1", call=lambda text: (
        {"found": True, "overall_rating": 4.0, "work_life_balance": 4.0, "source": "Indeed",
         "retrieval": "web_search", "review_count": 10, "red_flags": [], "notes": "",
         "searched": ""}, 0.1))
    kb.save_companies(loaded_by_the_pipeline)
    assert _company()["reputation"]["source"] == "Indeed"


def test_the_message_names_the_company_and_where_it_is():
    text = reputation_lookup.message({"company": "Acme Ltd", "company_url": "https://acme.example",
                                      "location_raw": "London", "title": "Engineer"})
    assert "Company: Acme Ltd" in text and "https://acme.example" in text and "London" in text
