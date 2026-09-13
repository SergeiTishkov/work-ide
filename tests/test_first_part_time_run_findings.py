"""
What the first run of a part-time search found wrong in the SHARED machinery.

The run was for a new identity, but two of its findings were about code every
identity uses, and both were measured over the older identity's base before
being fixed:

  1. **"freelance", "contractor" and "1099" exempted a vacancy from confirming
     it is remote.** They were in the same list as named employer-of-record
     platforms, and that list skipped the remote check outright. Eight
     vacancies in the confident tiers stood on those words alone — freelance
     missions in Brussels, Lille, Stevenage, and a Stripe posting where "1099"
     is the tax form its product files. Not one was remote work.

  2. **A language requirement a word list cannot hold.** "Fluent in Dutch or
     French" is a refusal; "Dutch or French is desirable" is not; "LANGUAGES –
     MUST Dutch OR French: fluent" puts the demand after the languages. A
     substring would have got two of six real postings wrong.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import score  # noqa: E402

from test_score import CRITERIA, PROFILE, make_vacancy  # noqa: E402

STACK = "Maintain and extend an ASP.NET Core and SQL Server platform in C#."


def _score(criteria=None, **kwargs):
    return score.score_vacancy(make_vacancy(**kwargs), criteria or CRITERIA, PROFILE)


# --- 1. a contractor word is not a location -------------------------------------

def test_freelance_alone_does_not_confirm_remote_work():
    """"Freelance Fullstack .NET Developer – Brussels, long-term assignment"."""
    r = _score(remote=None, location_raw="Brussels, Belgium",
               description_text=STACK + " A freelance assignment with a client in Brussels.")
    assert score.REMOTE_UNCONFIRMED in r["dealbreakers"]
    assert r["classification"] != "hot_lead"


def test_1099_as_a_tax_form_does_not_confirm_remote_work():
    r = _score(remote=None, location_raw="Seattle, WA",
               description_text=STACK + " Build 1099 tax reporting for platform users.")
    assert score.REMOTE_UNCONFIRMED in r["dealbreakers"]


def test_the_contractor_words_still_earn_their_points():
    """The tightening is about proof of location, not about the signal's value."""
    with_word = _score(remote=None, description_text=STACK + " Freelance contract.")
    without = _score(remote=None, description_text=STACK)
    assert with_word["score"] >= without["score"]
    assert with_word["score_breakdown"]["remote_location_fit"].get("eor_or_contractor_hits")


def test_a_named_platform_still_exempts():
    """"Paid through Deel" is evidence a company engages people across borders."""
    platform = PROFILE["eor_platforms_signal"][0]
    r = _score(remote=None, description_text=STACK + f" Contractors are paid through {platform}.")
    assert score.REMOTE_UNCONFIRMED not in r["dealbreakers"]


def test_saying_remote_still_confirms_it():
    r = _score(remote=None, description_text=STACK + " Freelance, fully remote.")
    assert score.REMOTE_UNCONFIRMED not in r["dealbreakers"]


# --- 2. a language demand read in context ------------------------------------------

LANGUAGE_PATTERNS = [
    {"name": "fluent in a language this person does not speak",
     "pattern": r"\b(?:fluen\w*|command of|proficien\w*|communicate fluently)\b[^.;]{0,20}"
                r"\b(?:dutch|french|german|flemish)\b(?![^.;]{0,40}\b(?:desirable|optional\w*|a plus|plus"
                r"|nice to have|advantage|asset|bonus|preferred|beneficial)\b)"},
    {"name": "a language, then the demand",
     "pattern": r"\b(?:dutch|french|german|flemish)\b[^.;]{0,20}:\s*(?:fluent|native|required|mandatory|must)"},
]


def _language_criteria():
    criteria = copy.deepcopy(CRITERIA)
    criteria["language_requirement_signal"]["explicit_requirement_patterns"] = copy.deepcopy(LANGUAGE_PATTERNS)
    return criteria


def _rejected_for_language(sentence):
    r = _score(_language_criteria(), description_text=STACK + " " + sentence)
    return any(d.startswith("language:") for d in r["dealbreakers"])


def test_real_demands_are_refusals():
    for sentence in (
        "You are fluent in Dutch or French with a very good level of English.",
        "Language skills: you have a good command of both Dutch and English.",
        "You communicate fluently in Dutch and English.",
        "LANGUAGES – MUST Dutch OR French: fluent. English: comprehension.",
        "Fluency in English and French is required; Dutch is a strong plus.",
    ):
        assert _rejected_for_language(sentence), sentence


def test_a_wish_is_not_a_demand():
    for sentence in (
        "Proficiency in English is a must and Dutch or French is desirable.",
        "Proficiency in English, and optionally in either Dutch or French.",
        "Fluent English; German is a plus.",
        "Fluent in English (French would be an advantage).",
        "We are a French company with an English-speaking team.",
    ):
        assert not _rejected_for_language(sentence), sentence


def test_without_patterns_the_gate_is_unchanged():
    r = _score(description_text=STACK + " You are fluent in Dutch or French.")
    assert r["score_breakdown"]["language_requirement_signal"]["explicit_requirement_hits"] == []
