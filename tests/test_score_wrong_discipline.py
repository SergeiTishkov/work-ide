"""
A different branch of engineering is not a different stack.

Found by the owner on 2026-08-12, reading his own UK shortlist and reaching
line 39:

    **[15] Senior Security Engineer, Security Incident Response Team (SIRT)**
    "ЭТО НЕ МОЯ ВАКАНСИЯ. Профильтруй базируясь на моем резюме"

His CV is a .NET one end to end — C#, ASP.NET, Entity Framework, Azure,
MS SQL, with Angular and React on the front. Security incident response is
somebody else's profession.

WHY THE TWO EXISTING TIERS BOTH FAILED IT
-----------------------------------------
`wrong_profession_title_patterns` is cancelled by any developer word in the
title, and the override list contains a bare "engineer" — which "Security
Engineer" satisfies. So the soft tier was disarmed by the very word that names
the wrong profession.

`hard_wrong_profession_title_patterns` fires whatever the stack says, which is
right for a manager or a designer and wrong here. Measured before writing this:
a blanket rule over these titles would have removed fifteen vacancies and taken
five real ones with it —

    ".NET AppSec Engineer" @ Kforce                        core: .NET
    "Senior Software Engineer (WPF, Firmware & Systems)"   core: C#, .NET
    "Software Engineer- Senior Embedded Engineer" @ Realtek core: C#, .NET

A .NET job with an unusual title is still a .NET job.

SO THERE IS A THIRD TIER
------------------------
`wrong_discipline_title_patterns` fires UNLESS the vacancy names the core
stack. The employer's own word outranks the title's discipline — the same
principle the rest of this file runs on.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import score  # noqa: E402

from test_score import CRITERIA, PROFILE, make_vacancy  # noqa: E402

# Enough .NET to keep a vacancy out of every other gate's way, so that what
# these tests measure is the discipline rule and nothing else.
DOTNET = ("Maintain a legacy ASP.NET and SQL Server platform in C#, with "
          ".NET Core services and Entity Framework.")
NO_DOTNET = ("Work with Python, Go and Kubernetes across our production "
             "estate. Strong communication skills required.")


def _score(title, description, **kwargs):
    kwargs.setdefault("remote", True)
    kwargs.setdefault("location_raw", "Anywhere in the World")
    return score.score_vacancy(
        make_vacancy(title=title, description_text=description, **kwargs),
        CRITERIA, PROFILE)


def _rejected_for_role(result):
    bd = result["score_breakdown"]["role_relevance_signal"]
    return bd["gate_triggered"] and bd["wrong_discipline_gate"]


# --- the vacancy that started it -------------------------------------------

def test_gitlab_security_incident_response_is_not_this_persons_job():
    """The one the owner pointed at. Scored 15 and reached the UK shortlist."""
    r = _score(
        "Senior Security Engineer, Security Incident Response Team (SIRT) - EMEA",
        "You will respond to security incidents, run investigations and "
        "improve detection. Familiarity with React is a plus.",
    )
    assert _rejected_for_role(r), r["score_breakdown"]["role_relevance_signal"]
    assert r["classification"] not in ("hot_lead", "worth_a_look", "long_shot")


# --- the disciplines, each with a real title from the base ------------------

def test_other_engineering_disciplines_are_filtered():
    titles = [
        "Senior Security Engineer",                      # helsing
        "Senior Data Engineer (Python)",                 # Proxify
        "Senior Analytics Engineer",                     # Numan
        "Staff Machine Learning Engineer",               # SailPoint
        "Senior AI Engineer",                            # wongdoody
        "Senior Embedded Software Engineer",             # TALENTSIS
        "Sr. Forward Deployed Engineer - FDE (Fullstack)",  # databricks
        "Technical Support Engineer (EMEA)",             # Stripe
        "Business Intelligence Analyst",                 # React Health
        "Data Analyst",                                  # Stripe
    ]
    for title in titles:
        r = _score(title, NO_DOTNET)
        # What matters is that it does not reach a list the owner reads. Which
        # gate stopped it is not the point, and asserting the mechanism would
        # make this test fail the day a better one catches it first — "Senior
        # Data Engineer (Python)" is now stopped by the title-stack gate,
        # because Python is outside the core and strong tiers.
        assert r["classification"] not in ("hot_lead", "worth_a_look", "long_shot"), (
            title, r["classification"], r["dealbreakers"])


def test_titles_that_are_not_engineering_at_all_are_filtered():
    """These belong in the HARD tier — no stack could make them right. Both
    reached long_shot at 22 before this."""
    for title in ("Vice President, Data & Insights", "Sales Enablement | SDR"):
        r = _score(title, NO_DOTNET)
        bd = r["score_breakdown"]["role_relevance_signal"]
        assert bd["hard_wrong_profession_hits"], title


# --- the false negatives the measurement caught in advance -----------------

def test_a_dotnet_appsec_role_survives():
    """".NET AppSec Engineer" @ Kforce. The employer named the stack in the
    title itself; a blanket security rule would have thrown it away."""
    r = _score(".NET AppSec Engineer", DOTNET)
    assert not _rejected_for_role(r), r["score_breakdown"]["role_relevance_signal"]
    assert r["classification"] != "rejected", r["dealbreakers"]


def test_a_wpf_firmware_role_naming_c_sharp_survives():
    """"Senior Software Engineer (WPF, Firmware & Systems)" — WPF is .NET
    desktop work, and the description carries C# and .NET."""
    r = _score("Senior Software Engineer (WPF, Firmware & Systems)", DOTNET)
    assert not _rejected_for_role(r)


def test_the_exemption_is_recorded_rather_than_silent():
    """When a discipline title is let through because the stack is named, the
    breakdown says so — otherwise the next person to read a report has no way
    of telling this rule from a hole in it."""
    r = _score("Senior Data Engineer", DOTNET)
    bd = r["score_breakdown"]["role_relevance_signal"]
    assert bd["wrong_discipline_hits"], "the title really does name a discipline"
    assert bd["wrong_discipline_exempted"] is True
    assert bd["wrong_discipline_gate"] is False


# --- ordinary vacancies must be untouched ----------------------------------

def test_an_ordinary_dotnet_vacancy_is_not_affected():
    for title in ("Senior .NET Developer",
                  "ASP.NET MVC C# /.NET Developer",
                  "Senior Full Stack Developer (React/.Net)",
                  "Dotnet Developer"):
        r = _score(title, DOTNET)
        bd = r["score_breakdown"]["role_relevance_signal"]
        assert not bd["wrong_discipline_hits"], title
        assert r["classification"] != "rejected", (title, r["dealbreakers"])


def test_a_javascript_role_is_not_a_wrong_discipline():
    """The gate is about a different PROFESSION, not a different stack. Whether
    a pure front-end role is wanted is a question of score, and the owner's CV
    has React and TypeScript on it."""
    r = _score(
        "Senior Frontend Developer (React.js / Next.js)",
        "Build and maintain our React and TypeScript front end. HTML, CSS.",
    )
    bd = r["score_breakdown"]["role_relevance_signal"]
    assert not bd["wrong_discipline_hits"]


# --- the exemptions must be earned -----------------------------------------

def test_one_stray_data_word_does_not_exempt_a_discipline_title():
    """The loophole this rule opened when first written, and closed the same
    day. Measured: 64 vacancies in the shortlist carry exactly one
    data-pipeline context word against 45 carrying two or more — a single
    "ETL" in a sales posting is not evidence of data engineering."""
    r = _score(
        "Senior Security Engineer",
        "Respond to incidents across our estate. You will occasionally review "
        "an ETL job. Python and Go.",
    )
    assert _rejected_for_role(r), r["score_breakdown"]["stack_fit"]


def test_real_data_engineering_is_still_wanted():
    """The owner confirmed on 2026-07-30 that data pipelines over Spark and
    Databricks are his work, and his CV carries both. A rule added later must
    not quietly overturn a decision made earlier."""
    r = _score(
        "Analytics Engineer",
        "Build ETL pipelines with Apache Spark on Databricks. Worldwide remote.",
    )
    assert not _rejected_for_role(r), r["score_breakdown"]["role_relevance_signal"]


def test_a_sales_consultant_is_not_an_engineer_but_a_technical_one_may_be():
    """"Solutions Consultant, Enterprise" @ Ramp reached long_shot at 21.
    ".Net Technical Consultant" @ alfanar is a real .NET role — the measurement
    found it before the pattern was written, which is why the pattern names
    "solutions" and "sales" and stops there."""
    sales = _score("Solutions Consultant, Enterprise", NO_DOTNET)
    assert sales["score_breakdown"]["role_relevance_signal"]["hard_wrong_profession_hits"]

    technical = _score(".Net Technical Consultant", DOTNET)
    assert not technical["score_breakdown"]["role_relevance_signal"]["hard_wrong_profession_hits"]
    assert technical["classification"] != "rejected", technical["dealbreakers"]
