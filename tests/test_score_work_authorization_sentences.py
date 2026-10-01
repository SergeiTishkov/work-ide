"""
Work authorization, read one sentence at a time (remote_location_fit.
work_authorization, score._check_work_authorization).

Every case below is a sentence from a real posting in the owner's bases,
found on 2026-10-01 by reading every vacancy that mentions citizenship, a
green card, work authorization, a clearance, sponsorship or W-2. The first
group were missed — several sat in hot_lead. The second group were refusals
that refused nobody: a negation, a preference, a company-wide caveat, an
offer of help, a product for citizens, a tax form.

Each case asserts WHICH rule refuses, not only that something did: a refusal
for the wrong reason passes a classification test and hides the miss.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import score  # noqa: E402

from test_score import CRITERIA, PROFILE, make_vacancy  # noqa: E402

RULES = {rule["name"] for rule in
         CRITERIA["remote_location_fit"]["work_authorization"]["rules"]}


def _refusals(text, title="Senior .NET Developer"):
    """The work-authorization rules that refuse a worldwide-remote posting
    whose only peculiarity is `text`."""
    r = score.score_vacancy(make_vacancy(
        title=title, location_raw="Anywhere in the World", remote=True,
        description_text="Fully remote. Legacy C#, ASP.NET and SQL Server.\n" + text,
    ), CRITERIA, PROFILE)
    return {d[len("location: "):] for d in r["dealbreakers"]
            if d.startswith("location: ") and d[len("location: "):] in RULES}


REFUSED = [
    # citizenship, in the forms that slipped through
    ("We require U.S. citizenship or permanent resident/Green Card status.", "citizenship required"),
    ("Requirements\nSingapore Citizen (mandatory)", "citizenship required"),
    ("This opportunity is currently open to candidates who are Singapore Citizens "
     "or Singapore Permanent Residents.", "citizenship required"),
    ("You are a US citizen or hold a valid Green Card.", "citizenship required"),
    ("Requirements:\n- U.S. citizenship\n- Bachelor's degree", "citizenship required"),
    ("Singapore citizens or PR only.", "citizenship required"),
    # a preference later in the line belongs to its own term
    ("security clearance requirements must be an australian citizen must be able to "
     "obtain a negative vetting level 1 (nv1) clearance an active nv1 clearance is "
     "preferred", "citizenship required"),
    # green card, US work statuses
    ("NO C2C ONLY W2 CANDIDATES USC OR GC ONLY $80/HOUR",
     "green card or permanent residency required"),
    ("Rate: $80-$90/hr on C2C Visa: H1B, GC, USC", "US work status listed"),
    ("Must meet Export Control requirements as a U.S. Person under 22 C.F.R.",
     "US person (export control) required"),
    # the right to work somewhere else
    ("Located in Canada & legally entitled to work in Canada",
     "work authorization in another country required"),
    ("- Eligibility to work in the UK.", "work authorization in another country required"),
    ("EU work authorisation or existing right to work in Luxembourg",
     "work authorization in another country required"),
    ("Candidates must be eligible to work full time and long term in the location "
     "specified or currently hold a valid appropriate long term work Visa to apply.",
     "work authorization in another country required"),
    ("Requires a valid Danish work permit.", "work authorization in another country required"),
    # an equal-opportunity list in the same run-on line does not cancel it
    ("without regard to citizenship, or any other factor protected by "
     "anti-discrimination laws applicants must be authorized to work in the u.s.",
     "work authorization in another country required"),
    # sponsorship
    ("Please note - we do not offer visa sponsorship for this position.", "visa sponsorship refused"),
    ("- No visa sponsorship is needed.", "visa sponsorship refused"),
    ("us citizens/gc holders encouraged to apply we do not offer sponsorship for this role",
     "visa sponsorship refused"),
    # clearance
    ("Hays are now looking for an SC cleared senior full stack developer.",
     "security clearance required"),
    ("£620 p/d inside IR35, remote, 6 month+ contract, BPSS", "security clearance required"),
    ("An active TS/SCI clearance with polygraph is required.", "security clearance required"),
    ("Candidates must hold an active NV1 security clearance prior to commencement.",
     "security clearance required"),
    # residency
    ("This role requires residency in Colorado, Utah, or Florida.", "residency required"),
    # W-2: US payroll
    ("Compensation is $100–$120 per hour on W-2.", "US payroll only (W-2)"),
    ("The pay range is $75–$80 per hour on a W-2 basis.", "US payroll only (W-2)"),
    ("Pay: $60-65/hr W2", "US payroll only (W-2)"),
    ("For W2 consultants, we provide a benefits package that includes medical.",
     "US payroll only (W-2)"),
    ("Employment Type: Full-time, direct W2 (no C2C, no 1099, no third-party)",
     "US payroll only (W-2)"),
    # found by reading what was still listed after the first rewrite
    ("No visa sponsorship available with this position", "visa sponsorship refused"),
    ("You are a US citizen or hold a valid Green Card (no visa sponsorship available)",
     "visa sponsorship refused"),
    ("UK working rights required; no sponsorship is offered for this role",
     "work authorization in another country required"),
    ("UK working rights required; no sponsorship is offered for this role",
     "visa sponsorship refused"),
    ("The role is hybrid and requires UK right to work.",
     "work authorization in another country required"),
    ("Pre-requisites: you must be in possession of a work permit valid for Swiss territory.",
     "work authorization in another country required"),
    ("We are not able to consider candidates who currently or in the future will require "
     "visa sponsorship.", "visa sponsorship refused"),
    ("We are only considering candidates who do not require visa sponsorship.",
     "visa sponsorship refused"),
    ("While we love all parts of the world, we can only hire permanent US residents at this time.",
     "residency required"),
    ("Fully REMOTE (Poland or Romanian residents only)", "residency required"),
]


@pytest.mark.parametrize("text, rule", REFUSED, ids=[r[1] + ": " + r[0][:40] for r in REFUSED])
def test_a_requirement_found_in_its_sentence_refuses(text, rule):
    assert rule in _refusals(text)


NOT_REFUSED = [
    # an equal-opportunity list
    "We consider all applicants without regard to race, color, religion, national origin, "
    "citizenship, or any other protected status.",
    # a negation of the requirement (it threw out nine vacancies)
    "Nor will Machine Learning Technologies require in a posting or otherwise U.S. citizenship "
    "or lawful permanent residency in the U.S. as a condition of employment.",
    # a preference
    "Active public trust or security clearance is preferred.",
    "Singapore Citizens and PRs preferred.",
    # a company-wide caveat
    "Some positions require the ability to obtain a security clearance, which may be granted "
    "only to U.S. citizens.",
    "We also participate in E-Verify and note that many of our roles may require the ability "
    "to obtain a security clearance.",
    # an offer of help
    "We assist eligible candidates requiring STEM extension support, as well as H-1B and "
    "green card filing assistance.",
    "We are happy to provide visa sponsorship if you ever want to join us in person.",
    # documents, products, programmes
    "Copy of Candidate Identification (i.e., Driver's License/Green Card/Visa and Passport).",
    "You will build citizen-facing digital products for government agencies.",
    "The E-Verify program is operated by the U.S. Citizenship and Immigration Services.",
    "Underwriting a loan means pulling numbers out of paystubs, W-2s and bank statements.",
    "Own payroll reconciliations and reporting (W-2, amendments, 401(k) testing).",
    # W-2 as one option among others
    "Employment Type: W-2, 1099, C2C",
    "We can engage consultants on W-2 or corp-to-corp terms. The posted W-2 rate is $85.",
    # a refusal that cannot apply to somebody who never needs a visa
    "We do not provide visa assistance. We work with developers from 75+ countries across "
    "Europe, Latin America and Asia.",
    "We are unable to sponsor visas for roles outside of engineering; sponsorship for "
    "engineering roles is not guaranteed.",
    # the person's own country
    "Must be legally authorized to work in the country where you reside.",
    "Must be authorized to work in Georgia (we are based in Tbilisi).",
    # ordinary English
    "Able to work in a fast-paced environment with distributed teams.",
    "You will have the right to work from home whenever you like.",
    # found by reading what was still listed after the first rewrite
    "The base salary range for this role is currently for residents of the United States only.",
    "TikTok will be prioritizing applicants who have a current right to work in Singapore, "
    "and do not require TikTok sponsorship of a visa.",
    "Flexible hybrid and local work options, with the option for visa sponsorship.",
    "We can help you relocate to the UK. We can sponsor visas.",
    "Deep experience with JVM performance analysis, heap dumps and GC tuning.",
]


@pytest.mark.parametrize("text", NOT_REFUSED, ids=[t[:50] for t in NOT_REFUSED])
def test_a_sentence_that_refuses_nobody_is_not_a_refusal(text):
    assert _refusals(text) == set()


def test_georgia_the_us_state_is_not_this_person_s_country():
    """The owner lives in Georgia, the country. "Atlanta, Georgia" is the US
    state, and a requirement to work there still refuses."""
    assert "work authorization in another country required" in _refusals(
        "Must be authorized to work in Atlanta, Georgia.")


def test_a_citizenship_the_profile_records_is_the_person_s_own():
    """owner.citizenships, when the profile has it, counts like the country
    of residence."""
    profile = {**PROFILE, "owner": {**PROFILE["owner"], "citizenships": ["Belarus"]}}
    r = score.score_vacancy(make_vacancy(
        location_raw="Anywhere in the World", remote=True,
        description_text="Legacy C# and SQL Server. Must be a citizen of Belarus.",
    ), CRITERIA, profile)
    assert not any(d == "location: citizenship required" for d in r["dealbreakers"])


def test_a_refusal_shows_the_sentence_it_read():
    r = score.score_vacancy(make_vacancy(
        location_raw="Anywhere in the World", remote=True,
        description_text="Legacy C#. Compensation is $100 per hour on W-2. Great team.",
    ), CRITERIA, PROFILE)
    detail = r["score_breakdown"]["remote_location_fit"]["work_authorization"]
    assert detail == [{"rule": "US payroll only (W-2)",
                       "sentence": "compensation is $100 per hour on w-2"}]


@pytest.mark.parametrize("text, expected", [
    ("Remote freelance contractor engagement, invoiced monthly.", score.ELIGIBILITY_UNKNOWN),
    ("We work with international contractors, invoiced monthly.", score.ELIGIBILITY_LIKELY),
    ("We work with developers from 75+ countries.", score.ELIGIBILITY_LIKELY),
])
def test_only_an_international_arrangement_makes_eligibility_likely(text, expected):
    r = score.score_vacancy(make_vacancy(
        location_raw="Remote", remote=True,
        description_text="Legacy C#, ASP.NET and SQL Server. " + text,
    ), CRITERIA, PROFILE)
    assert r["residency_eligibility"] == expected, r["residency_eligibility_reason"]


def test_sentences_keep_abbreviations_whole():
    assert score._sentences("must be a u.s. citizen, e.g. a native. next one; last\nline") == [
        "must be a u.s. citizen, e.g. a native", "next one", "last", "line"]


def test_the_adjective_national_is_not_a_nationality():
    """"A national police check might be required" — found in the before/after
    read of 2026-10-01, where "nationals?" matched the adjective."""
    assert _refusals("Please note that a national police check might be required.") == set()
