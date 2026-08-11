"""
Gaps found by the manual candidate checklist on 2026-08-11.

Each test is named after the vacancy that exposed it. That naming is the point:
when one of these goes red in a year, the failure says which real posting the
rule was protecting against, and the rule can be judged rather than deleted.

Every gap here was measured across the whole base before it was closed — the
counts are in the comments of the criteria entries.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import score  # noqa: E402

from test_score import CRITERIA, PROFILE, make_vacancy  # noqa: E402


def _score(**kwargs):
    return score.score_vacancy(make_vacancy(**kwargs), CRITERIA, PROFILE)


# --- Onsite in the employer's own words ------------------------------------

def test_master_works_job_location_client_site_is_onsite():
    """Arrived through LinkedIn's remote filter, scored 62 and led the shortlist.

    Its own text ended "Job Location: Client Site." The board said remote, the
    employer said otherwise, and the employer wins — the same principle already
    applied to the Headquarters heading.
    """
    r = _score(
        title="GIS Full Stack .Net Developer",
        location_raw="Riyadh, Saudi Arabia",
        remote=True,
        description_text=(
            "Design and maintain enterprise web applications using .NET Core, "
            "ASP.NET MVC, C#, WCF (SOAP) services and SQL Server. "
            "Job Location: Client Site."
        ),
    )
    assert r["classification"] == "rejected", r["score"]


def test_altkamul_driving_licence_means_commuting():
    """"UAE Experience is a must with driving license" — a licence is only ever
    required of somebody who travels to a place of work."""
    r = _score(
        title="Backend Developer",
        location_raw="Sharjah, United Arab Emirates",
        remote=True,
        description_text=(
            "Design, code and test applications in C#, ASP.NET and MS SQL "
            "Server. UAE Experience is a must with driving license."
        ),
    )
    assert r["classification"] == "rejected"


def test_natsoft_in_person_interview_requires_presence():
    """Opened with "Client interview: In person in Wilmington, DE" and scored 41.

    An interview that must happen in person requires being in that country,
    whatever the posting says about the work itself being remote.
    """
    r = _score(
        title="Dotnet Developer",
        location_raw="Wilmington, DE",
        remote=True,
        description_text=(
            "Client interview: In person in Wilmington, DE. Develop backend "
            "services using .NET Core / ASP.NET and Angular."
        ),
    )
    assert r["classification"] == "rejected"


def test_an_ordinary_remote_vacancy_survives_the_onsite_phrases():
    """The reverse guard. These phrases are specific for a reason: "client" and
    "license" on their own appear in perfectly ordinary remote vacancies."""
    r = _score(
        title="Senior .NET Developer",
        location_raw="Anywhere in the World",
        remote=True,
        description_text=(
            "Fully remote. You will work with our client teams on a legacy "
            "ASP.NET and SQL Server platform. MIT license, open source "
            "friendly. C# and Entity Framework."
        ),
    )
    assert r["classification"] != "rejected", r["dealbreakers"]


# --- An advertisement with no vacancy behind it ----------------------------

def test_mariner_talent_pipeline_is_not_an_opening():
    """Scored 50 and led the shortlist: stack, remote and legacy enterprise all
    matched, because the posting was written to match. There was nothing to
    apply to — it collects CVs against roles that may open later."""
    r = _score(
        title="Senior .NET Developer",
        location_raw="Halifax, Nova Scotia, Canada",
        remote=True,
        description_text=(
            "We are always looking to connect with talented Senior .NET "
            "Developers interested in future opportunities. By joining our "
            "talent pipeline you will be considered for upcoming roles as new "
            "opportunities arise. Strong expertise in C#, .NET Core, ASP.NET "
            "Core and SQL Server. Support for remote work."
        ),
    )
    assert r["classification"] == "rejected"
    assert any("talent-pipeline" in d for d in r["dealbreakers"]), r["dealbreakers"]


def test_a_real_vacancy_mentioning_a_data_pipeline_is_untouched():
    """The reverse guard, and the reason the phrases are two words long: an
    ordinary vacancy says "pipeline" about data and CI all the time."""
    r = _score(
        title="Senior .NET Developer",
        location_raw="Anywhere in the World",
        remote=True,
        description_text=(
            "Worldwide remote. Maintain our data pipeline and CI/CD pipeline "
            "on a legacy ASP.NET platform. C#, SQL Server, Entity Framework."
        ),
    )
    assert r["classification"] != "rejected", r["dealbreakers"]


# --- Languages that were missing from the derivation table -----------------

def test_talents_sea_arabic_requirement_disqualifies():
    """"Good communication in Arabic & English" sat in worth_a_look at 36.

    Not because the gate misjudged it, but because Arabic was absent from
    config/derivation/languages.yaml altogether — so the requirement produced
    no rule for anybody, in any identity.
    """
    r = _score(
        title=".NET Developer / Team Lead",
        location_raw="Riyadh, Saudi Arabia",
        remote=True,
        description_text=(
            "Develop and maintain applications using ASP.NET Core and .NET 6+, "
            "C#, Entity Framework Core and SQL Server. Good communication in "
            "Arabic & English."
        ),
    )
    assert r["classification"] == "rejected"


def test_skapa_swedish_requirement_disqualifies():
    """Found by measuring the same gap across the base: a hot_lead at 51 asking
    for Swedish. Swedish was missing from the table too."""
    r = _score(
        title="C# .NET System Developer",
        location_raw="Anywhere in the World",
        remote=True,
        description_text=(
            "Maintain our legacy C# and .NET systems with SQL Server. "
            "Fluent Swedish required."
        ),
    )
    assert r["classification"] == "rejected"


def test_a_company_named_in_arabic_does_not_disqualify_by_itself():
    """The reverse guard: naming the company in another script, or mentioning a
    language in passing, is not a requirement to speak it."""
    r = _score(
        title="Senior .NET Developer",
        location_raw="Anywhere in the World",
        remote=True,
        description_text=(
            "Worldwide remote role maintaining a legacy ASP.NET and SQL Server "
            "platform in C#. Our documentation is available in English and "
            "Arabic. English is the working language."
        ),
    )
    assert r["classification"] != "rejected", r["dealbreakers"]
