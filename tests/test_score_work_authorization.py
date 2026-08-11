"""
Work-authorization requirements, and why they are matched by regex.

Found 2026-08-11 by the manual checklist on the rebuilt head of the shortlist.
The substring list already held "must be a us citizen" — and missed both real
spellings that were sitting in the shortlist at the time:

    "the person(s) hired must be a U.S. Citizen or Green Card holder"   the dots
    "Must be US Citizen."                                              no article

Five vacancies with a hard citizenship or work-authorization requirement were
in the head of the shortlist, one of them second overall at 69. The fix is not
more literal variants — that is how the list got here — but patterns, using the
mechanism `_matches_patterns` already provides for exactly this class of miss
(see docs/TECH_MATCHING.md).

Punctuation cannot be stripped before matching: it is what makes "c#" and
"asp.net" matchable at all (`common.normalize_for_matching`).

Each test is named after the vacancy that exposed the gap, so that when one
goes red the failure says which real posting the rule was protecting against.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import score  # noqa: E402

from test_score import CRITERIA, PROFILE, make_vacancy  # noqa: E402


def _score(**kwargs):
    return score.score_vacancy(make_vacancy(**kwargs), CRITERIA, PROFILE)


# --- the two spellings that leaked ----------------------------------------

def test_tcs_corpus_christi_us_citizen_with_dots():
    """Stood second in the shortlist at 69. Its own text: "in accordance with
    laws and regulations pertaining to this position, the person(s) hired must
    be a U.S. Citizen or Green Card holder." The dots were the whole gap."""
    r = _score(
        title="Dotnet Senior Engineer",
        location_raw="Corpus Christi, TX",
        remote=True,
        description_text=(
            "Proficiency in C#, .NET Framework, .NET Core, ASP.NET MVC, Web API "
            "and Entity Framework. In accordance with laws and regulations "
            "pertaining to this position, the person(s) hired must be a U.S. "
            "Citizen or Green Card holder."
        ),
    )
    assert r["classification"] == "rejected", r["score"]


def test_sunrise_systems_must_be_us_citizen_without_the_article():
    """The vacancy that made the blind-description gap visible in the first
    place (see tools/enrich_descriptions.py). Its description was fetched, the
    words arrived — and it still scored 53 in hot_lead, because the list held
    "must be a us citizen" and the text says "Must be US Citizen".

    Two gaps in one vacancy, closed a day apart.
    """
    r = _score(
        title="Software Developer (Angular, .NET (C#), SQL Server stack) PART-TIME/Remote",
        location_raw="Anywhere in the World",
        remote=True,
        description_text=(
            "Maintain an existing Angular, .NET (C#) and SQL Server application. "
            "Must be US Citizen. Must be eligible to work on U.S. government "
            "contracts."
        ),
    )
    assert r["classification"] == "rejected", r["score"]


# --- the neighbouring forms, measured in the same pass ---------------------

def test_a_refusal_to_sponsor_a_visa_is_a_refusal():
    """43 vacancies in the base. An employer who will not sponsor is not going
    to engage somebody who needs it, whatever the remote field says."""
    r = _score(
        title="Senior .NET Developer",
        location_raw="Austin, TX",
        remote=True,
        description_text=(
            "Work on a legacy ASP.NET and SQL Server platform in C#. We are "
            "unable to provide visa sponsorship for this position."
        ),
    )
    assert r["classification"] == "rejected"


def test_existing_work_authorization_is_a_requirement_not_a_preference():
    """31 vacancies. "Must be authorized to work in the United States" is the
    employer's own words about who they can engage."""
    r = _score(
        title="Back End (C# .NET) Software Engineer",
        location_raw="Remote, United States",
        remote=True,
        description_text=(
            "Build backend services in C# and .NET with SQL Server. Candidates "
            "must be authorized to work in the United States."
        ),
    )
    assert r["classification"] == "rejected"


def test_security_clearance_phrased_as_a_requirement():
    """44 in the base. The substring "security clearance" was already listed;
    this guards the pattern that replaces guessing at its phrasings."""
    r = _score(
        title=".NET Developer",
        location_raw="Anywhere in the World",
        remote=True,
        description_text=(
            "C# and SQL Server maintenance work. The successful candidate must "
            "be able to obtain an active security clearance."
        ),
    )
    assert r["classification"] == "rejected"


# --- the reverse guards ---------------------------------------------------

def test_an_equal_opportunity_footer_does_not_disqualify():
    """The reason every pattern demands a requiring context. Mentioning
    citizenship in a non-discrimination footer is the opposite of refusing
    somebody, and a bare "citizen" substring would throw the vacancy away."""
    r = _score(
        title="Senior .NET Developer",
        location_raw="Anywhere in the World",
        remote=True,
        description_text=(
            "Fully remote worldwide. Maintain a legacy ASP.NET and SQL Server "
            "platform in C#. We are an equal opportunity employer and do not "
            "discriminate on the basis of citizenship status, race or age."
        ),
    )
    assert r["classification"] != "rejected", r["dealbreakers"]


def test_a_company_that_does_sponsor_visas_is_not_rejected_for_saying_so():
    """The pattern matches a REFUSAL to sponsor. An offer to sponsor uses many
    of the same words and is a plus, not a dealbreaker."""
    r = _score(
        title="Senior .NET Developer",
        location_raw="Anywhere in the World",
        remote=True,
        description_text=(
            "Worldwide remote. Legacy C#, ASP.NET and SQL Server. We are happy "
            "to provide visa sponsorship and relocation support if you ever "
            "want to join us in person."
        ),
    )
    assert r["classification"] != "rejected", r["dealbreakers"]


def test_mentioning_a_green_card_in_passing_is_not_a_requirement():
    """"Green card holders welcome" alongside everybody else restricts nobody."""
    r = _score(
        title="Senior .NET Developer",
        location_raw="Anywhere in the World",
        remote=True,
        description_text=(
            "Remote from anywhere. C# and SQL Server on a legacy platform. "
            "Contractors, green card holders and citizens of any country are "
            "all welcome to apply."
        ),
    )
    assert r["classification"] != "rejected", r["dealbreakers"]
