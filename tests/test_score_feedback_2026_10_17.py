"""Two settings from the owner's feedback of 2026-10-17 (sharp): silence about
remote after the text was read, and title rules that reject."""
import copy

import score

CRITERIA = score.load_criteria()
PROFILE = score.load_profile()

OFFICE_TEXT = ("We are a trading platform founded in London. You will build and maintain C# and .NET "
               "services for our trading desks, work with SQL Server and Azure, and review code with a "
               "team of eight engineers. ") * 4


def _vacancy(**fields):
    base = {"id": "x", "source": "linkedin", "title": "Senior Software Engineer (C#/.NET)",
            "company": "Acme", "url": "https://example.com/x",
            "location_raw": "Belfast, Northern Ireland, United Kingdom", "description_text": OFFICE_TEXT,
            "tags": []}
    return {**base, **fields}


def _criteria(rl=None, title_rules=None):
    c = copy.deepcopy(CRITERIA)
    c["remote_location_fit"].update(rl or {})
    if title_rules is not None:
        c["title_role_penalty"] = {"rules": title_rules}
    return c


def test_silence_about_remote_parks_by_default():
    computed = score.score_vacancy(_vacancy(), _criteria(), PROFILE)
    assert computed["classification"] == "remote_unconfirmed"


def test_silence_after_the_text_was_read_rejects_where_the_identity_says_so():
    criteria = _criteria({"unstated_remote_after_reading": "reject"})
    computed = score.score_vacancy(_vacancy(), criteria, PROFILE)
    assert computed["classification"] == "rejected"
    assert score.REMOTE_UNSTATED_IN_TEXT in computed["dealbreakers"]
    # a card with no text read yet stays parked: the page may still say remote
    card = score.score_vacancy(_vacancy(description_text="C# developer, Belfast."), criteria, PROFILE)
    assert card["classification"] == "remote_unconfirmed"


def test_a_title_rule_with_reject_is_a_dealbreaker_and_has_no_points():
    rules = [{"pattern": r"\b(junior|graduate)\b", "label": "junior or graduate", "reject": True},
             {"pattern": "front[ -]?end", "label": "front-end", "reject": True, "unless": ["full[ -]?stack"]}]
    criteria = _criteria({"unstated_remote_after_reading": "park"}, rules)
    remote = "Fully remote, we hire worldwide as contractors. " + OFFICE_TEXT
    junior = score.score_vacancy(_vacancy(title="Junior C# Developer", description_text=remote), criteria, PROFILE)
    assert junior["classification"] == "rejected"
    assert "title: junior or graduate" in junior["dealbreakers"]
    full_stack = score.score_vacancy(
        _vacancy(title="Full Stack Engineer (Front End and C#)", description_text=remote), criteria, PROFILE)
    assert not any(d.startswith("title: ") for d in full_stack["dealbreakers"])
    title_part = [p for p in full_stack["score_parts"] if p["key"] == "title"]
    assert not title_part or (title_part[0]["min"], title_part[0]["max"]) == (0, 0)
