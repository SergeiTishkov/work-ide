"""
Where the work actually happens, and what to do when nobody says.

Found 2026-08-11 by the owner, opening the top three vacancies in his own
shortlist and reading the badges LinkedIn shows a logged-in person:

    Dotnet Developer @ Capgemini, Toronto          [80]  Hybrid
    Senior Software Engineer (.NET) @ Emdad, Riyadh [71]  On-site
    SharePoint & .NET Engineer @ Jobstronaut       [65]  On-site, and closed

All three were in the base as `remote: True`. That flag was not a weak signal
— it was hardcoded, on the reasoning that the search query carries LinkedIn's
f_WT=2 ("Remote") filter.

THE MEASUREMENT THAT SETTLED IT
-------------------------------
The guest search ignores f_WT entirely. The same job id comes back under
f_WT=1 (on-site), f_WT=2 (remote) and f_WT=3 (hybrid), and the result sets for
"remote" and "on-site" were byte-identical. So every LinkedIn vacancy in the
base — 100% of them — was clearing the remote gate on a fabrication.

The badge itself is not readable: checked three ways, it is absent from the
search results, from the guest jobPosting fragment and from the page HTML. It
renders only for a logged-in session, and going there would cross the line in
CLAUDE.md §5. What the page DOES give is schema.org `jobLocationType`, which
says TELECOMMUTE for a declared-remote posting and nothing at all otherwise.

SO THE RULE HAS TWO HALVES, AND THE SPLIT IS THE POINT
------------------------------------------------------
* The employer's own word — "hybrid", "on-site", the board's location field —
  disqualifies. That is not a guess.
* Silence disqualifies nothing. It goes to a class of its own, with the score
  UNCHANGED, and the person decides. The owner was explicit about the score:
  "in hot_lead we can have a 70, and in 'check by hand' a 70 as well".

Measured before the change, because the owner's binding constraint was that no
mass of real vacancies may quietly vanish: of the 131 affected, 22 say
"hybrid" in their own text, 109 have a full description that never mentions
the arrangement at all, and exactly 1 has no description.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import score  # noqa: E402

from test_score import CRITERIA, PROFILE, make_vacancy  # noqa: E402


def _score(**kwargs):
    kwargs.setdefault("remote", None)
    return score.score_vacancy(make_vacancy(**kwargs), CRITERIA, PROFILE)


# --- the employer's own word: rejected -------------------------------------

def test_the_board_location_field_saying_hybrid_is_a_refusal():
    """210 vacancies in the base have exactly "Hybrid" in the location field.

    A separate rule from the description patterns, because this field is short
    and functional: "hybrid" in it can only mean commuting.
    """
    r = _score(
        title="Senior .NET Developer",
        location_raw="Hybrid",
        description_text="Maintain a legacy ASP.NET and SQL Server platform in C#.",
    )
    assert r["classification"] == "rejected"
    assert any("location field" in d for d in r["dealbreakers"]), r["dealbreakers"]


def test_a_location_field_offering_remote_as_well_is_not_a_refusal():
    """The reverse guard, and the reason `unless_also` exists. Three real values
    in the base offer both: "Hybrid or Remote", "Dallas, TX (Remote US or
    Hybrid)", "Distributed; Hybrid". Rejecting those would be the exact false
    negative the owner warned against."""
    r = _score(
        title="Senior .NET Developer",
        location_raw="Dallas, TX (Remote US or Hybrid)",
        description_text="Legacy ASP.NET, C# and SQL Server maintenance.",
    )
    assert r["classification"] != "rejected", r["dealbreakers"]


def test_hybrid_stated_as_an_arrangement_in_the_description():
    """"Senior C#/.NET Engineer  Location: London (Hybrid)" — quoted from a
    real posting in the shortlist."""
    r = _score(
        title="Senior C#/.NET Engineer",
        location_raw="London, England",
        description_text=(
            "Senior C#/.NET Engineer Location: London (Hybrid) Contract: "
            "12-Month. Legacy .NET and SQL Server platform work."
        ),
    )
    assert r["classification"] == "rejected", r["score"]


def test_days_per_week_in_the_office_is_an_arrangement():
    """"we've adopted a hybrid approach, with teams in the office around four
    days a week" — the phrasing that survives every "hybrid X" pattern."""
    r = _score(
        title=".NET Developer",
        location_raw="Anywhere in the World",
        description_text=(
            "C# and SQL Server on a legacy platform. We've adopted a hybrid "
            "approach, with teams in the office around four days a week."
        ),
    )
    assert r["classification"] == "rejected"


# --- the same word about technology: untouched -----------------------------

def test_hybrid_cloud_is_not_a_commute():
    """58 vacancies in the base say "hybrid cloud", "hybrid architecture" or
    "hybrid deployment". A bare "hybrid" keyword would have thrown away every
    one of them, and this is the third time this project has been bitten by a
    short token matched without context — see docs/TECH_MATCHING.md."""
    r = _score(
        title="Senior .NET Developer",
        location_raw="Anywhere in the World",
        remote=True,
        description_text=(
            "Fully remote worldwide. Deep understanding of hybrid cloud "
            "environments (AWS/GCP), on-premise infrastructure and hybrid "
            "architecture. C#, ASP.NET and SQL Server."
        ),
    )
    assert r["classification"] != "rejected", r["dealbreakers"]


def test_a_remote_vacancy_that_merely_offers_offices_is_not_rejected():
    """Quoted from a real posting: "100% remote opportunity (we have 4 office
    locations for hybrid/onsite work preference in NY, SF, LA and Chicago)".
    Offering an office is the opposite of requiring one."""
    r = _score(
        title="Senior .NET Developer",
        location_raw="Remote, United States",
        remote=True,
        description_text=(
            "This is a 100% remote opportunity. C#, ASP.NET and SQL Server on "
            "a legacy platform. We work remotely across the company."
        ),
    )
    assert r["classification"] != "rejected", r["dealbreakers"]


# --- silence: its own class, score intact ----------------------------------

def test_silence_about_the_arrangement_is_not_a_rejection():
    """109 vacancies had a full description that never mentions the
    arrangement. Before 2026-08-11 every one of them was rejected outright."""
    r = _score(
        title="Senior .NET Developer",
        location_raw="Toronto, Ontario, Canada",
        description_text=(
            "6+ years of IT industry experience. Design, develop and deploy "
            "enterprise applications using .NET Framework and .NET Core. "
            "Build and maintain RESTful APIs. SQL Server."
        ),
    )
    assert r["classification"] == "remote_unconfirmed"
    assert r["dealbreakers"] == [score.REMOTE_UNCONFIRMED]


def test_the_score_is_not_reduced_for_uncertainty():
    """The owner, explicitly: "in hot_lead we can have a vacancy scoring 70,
    and in 'check by hand' a vacancy scoring 70 as well". Only the certainty
    differs, and the class is what carries it."""
    common = dict(
        title="Senior .NET Developer",
        location_raw="Toronto, Ontario, Canada",
        description_text=(
            "Design and maintain enterprise applications using .NET Core, "
            "ASP.NET MVC, C# and SQL Server. Legacy platform support."
        ),
    )
    silent = _score(**common)
    stated = score.score_vacancy(
        make_vacancy(remote=None, workplace_type="remote", **common),
        CRITERIA, PROFILE)

    assert silent["classification"] == "remote_unconfirmed"
    assert stated["classification"] != "remote_unconfirmed"
    assert silent["score"] == stated["score"], (
        "uncertainty must not cost points — it is a statement about what we "
        "know, not about the vacancy"
    )


def test_the_employers_declaration_of_remote_is_believed():
    """schema.org jobLocationType=TELECOMMUTE, the one positive signal the
    guest page actually gives. Of 28 vacancies at the top of the shortlist,
    exactly one carried it."""
    r = _score(
        title="C# Developer",
        location_raw="Calgary, Alberta, Canada",
        workplace_type="remote",
        description_text="Maintain legacy C# services against SQL Server.",
    )
    assert r["classification"] != "remote_unconfirmed"
    assert score.REMOTE_UNCONFIRMED not in r["dealbreakers"]


def test_the_policy_is_a_per_identity_choice():
    """Another identity may not mind commuting at all. Asked for by the owner
    in the same conversation: "make it customisable — for another identity
    on-site and hybrid may be fine"."""
    import copy

    vacancy = make_vacancy(
        remote=None,
        title="Senior .NET Developer",
        location_raw="Toronto, Ontario, Canada",
        description_text="Enterprise .NET Core, C# and SQL Server work.",
    )

    accepting = copy.deepcopy(CRITERIA)
    accepting["remote_location_fit"]["unconfirmed_remote_policy"] = "accept"
    assert score.score_vacancy(vacancy, accepting, PROFILE)["dealbreakers"] == []

    strict = copy.deepcopy(CRITERIA)
    strict["remote_location_fit"]["unconfirmed_remote_policy"] = "reject"
    assert score.score_vacancy(vacancy, strict, PROFILE)["classification"] == "rejected"


def test_squad_hybrid_named_in_the_title_alongside_the_salary():
    """"Backend Developer (C# - SSIS) - (hybrid, 36-40k)" — a real title that
    survived the first version of these rules and sat in hot_lead at 38.

    The narrow "(hybrid)" pattern wanted the brackets to hold nothing else.
    Real postings put the salary, the contract type or the office share in
    there with it.
    """
    r = _score(
        title="Backend Developer (C# - SSIS) - (hybrid, 36-40k)",
        location_raw="Madrid, Community of Madrid, Spain",
        description_text=(
            "We are working with one of our clients to onboard a Backend "
            "Developer. C#, .NET Core, SQL Server and Angular."
        ),
    )
    assert r["classification"] == "rejected", r["score"]


def test_brackets_offering_remote_are_spared():
    """A real posting says "(hybrid and options for remote work)". That offers
    remote rather than refusing it, and it is why the bracket rule carries a
    negative guard for "remote" as well as for the technology words."""
    r = _score(
        title="Senior .NET Developer (hybrid and options for remote work)",
        location_raw="Anywhere in the World",
        remote=True,
        description_text="Legacy C#, ASP.NET and SQL Server. Remote friendly.",
    )
    assert r["classification"] != "rejected", r["dealbreakers"]


def test_an_arrangement_entered_by_hand_outranks_everything():
    """The badge a logged-in person sees cannot be fetched — so when the owner
    reads it himself and enters it, that has to count.

    All three vacancies at the top of the shortlist on 2026-08-11 were like
    this: the page said Hybrid or On-site, the anonymous fetch could not see
    it, and the description never mentioned the arrangement either. Without
    this, what a person reads with their own eyes cannot reach the scoring.
    """
    r = _score(
        title="Dotnet Developer",
        location_raw="Toronto, Ontario, Canada",
        workplace_type="hybrid",
        description_text=(
            "6+ years of IT industry experience. Design and deploy enterprise "
            "applications using .NET Framework and .NET Core. SQL Server."
        ),
    )
    assert r["classification"] == "rejected"
    assert any("entered by hand" in d for d in r["dealbreakers"]), r["dealbreakers"]
