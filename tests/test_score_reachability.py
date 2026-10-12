"""
Reachability from abroad weighs in the score (SHARP template V20).

The owner, 2026-10-05: the top of the list is full of vacancies that cannot be
taken from abroad. Measured on SHARP's 373 unanswered vacancies in view: the
location axis gave 0-8 points against ~37 for the stack, 50 hot leads offered
a 401(k) or RRSP, and "hybrid remote", "anywhere within the United States" or
"Must live in Houston" passed every existing pattern.

The rules are read from the SHARP template itself and laid over the frozen
fixture's criteria, so these tests check the template a person actually uses.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import score  # noqa: E402

from test_score import CRITERIA, PROFILE, make_vacancy  # noqa: E402

SHARP = yaml.safe_load(
    (Path(__file__).resolve().parent.parent / "identity-templates"
     / "sharp-senior-dotnet-remote-engineering" / "sharp_criteria.yaml").read_text(encoding="utf-8"))
SHARP_RL = SHARP["remote_location_fit"]

NEW_HARD = {"hybrid remote", "work mode field says hybrid", "hybrid as a separate item",
            "work in a hybrid environment", "remote within one country, said at length",
            "based in one country", "must live in a named place",
            # found by the checklist, 2026-10-12
            "anywhere in one country", "open to applicants in one country",
            "remote role based in one country", "some US states only",
            "candidates from one country", "office now and then",
            # found by PARTSHARP's checklist, 2026-10-12
            "attend the office", "office at least some days", "work from home some days",
            # the second checklist round, 2026-10-12
            "remote within a named country", "remote, then one country", "partner based in one country",
            "workplace model says hybrid", "days a week in a named office", "a named office, days a week",
            "remote on US western hours", "office stated plainly",
            # the third checklist round, 2026-10-12
            "remote in one place only", "location: a country (remote)", "one country's applicants only",
            "only candidates who reside"}
PAYROLL = "US or Canadian payroll benefits (401(k), RRSP)"

STACK = (" Maintain a legacy ASP.NET and SQL Server platform in C#, with .NET Core"
         " services and Entity Framework.")


def _criteria(points=None):
    rl = dict(CRITERIA["remote_location_fit"])
    wa = dict(rl["work_authorization"])
    wa["rules"] = list(wa["rules"]) + [r for r in SHARP_RL["work_authorization"]["rules"]
                                      if r["name"] == PAYROLL]
    wa["international_hiring_patterns"] = SHARP_RL["work_authorization"]["international_hiring_patterns"]
    rl["work_authorization"] = wa
    hard = dict(rl["hard_dealbreakers"])
    hard["patterns"] = list(hard.get("patterns") or []) + [
        p for p in SHARP_RL["hard_dealbreakers"]["patterns"] if p["name"] in NEW_HARD]
    rl["hard_dealbreakers"] = hard
    rl["residency_eligibility"] = {
        **(rl.get("residency_eligibility") or {}),
        "points": SHARP_RL["residency_eligibility"]["points"] if points is None else points}
    return {**CRITERIA, "remote_location_fit": rl}


def _score(description, criteria=None, **fields):
    fields = {"location_raw": "", **fields}
    return score.score_vacancy(make_vacancy(description_text=description + STACK, **fields),
                               criteria or _criteria(), PROFILE)


def test_the_template_carries_every_rule_these_tests_lay_over():
    names = {p["name"] for p in SHARP_RL["hard_dealbreakers"]["patterns"]}
    assert NEW_HARD <= names
    assert PAYROLL in {r["name"] for r in SHARP_RL["work_authorization"]["rules"]}


@pytest.mark.parametrize("benefits", [
    "Benefits include a 401(k) with company match, dental and vision.",
    "We offer medical, dental, HSA, FSA, 401K and life insurance.",
    "Employer RRSP contribution (3%) and comprehensive health benefits.",
])
def test_a_us_or_canadian_retirement_plan_rejects(benefits):
    result = _score("Fully remote role. " + benefits)
    assert result["classification"] == "rejected"
    assert f"location: {PAYROLL}" in result["dealbreakers"]


@pytest.mark.parametrize("text", [
    "Fully remote role. We hire contractors from any country. US employees get a 401(k).",
    "Fully remote role. A 401(k) plan for our US employees; elsewhere a local equivalent.",
])
def test_the_plan_does_not_reject_an_employer_that_engages_people_abroad(text):
    assert f"location: {PAYROLL}" not in _score(text)["dealbreakers"]


@pytest.mark.parametrize("text", [
    "This is a hybrid remote role based in Verdun, QC.",
    "Mode of work: Hybrid.",
    "C#, WPF, .NET Developer - Hybrid - Outside IR35 - 12 month contract.",
    "Work in a hybrid environment with opportunities for remote collaboration.",
    "Fully remote opportunity with the option to work anywhere within the United States.",
    "Location: Remote (UK-based). You MUST be UK based to be considered.",
    "Must live in Houston, TX (required).",
    "Remote. Must reside within the United States.",
    # the checklist of 2026-10-12: fresh vacancies that passed every pattern
    "As a remote-first company, we offer the flexibility to work from anywhere in the U.S.",
    "This position can be performed remotely from within Ireland.",
    "We offer fully remote work in Canada and the United States across Pacific to Eastern time zones.",
    "This full-time position is fully remote in the U.S., with Eastern Time working hours.",
    "Please note: this is a remote position open to qualified applicants in Canada.",
    "Remote. This role is open to applicants in the US and Canada.",
    "This remote role is based in USA/Canada.",
    "Remote. Currently reside in one of these states: CO, GA, FL, MA, MN, NC; relocation is not available.",
    "This is a remote position. Candidates must be CURRENT WI residents. No relocation is allowed.",
    "Candidate must live and work in PDT or MDT time zones!",
    "Location: Birmingham - flexible remote working options available - Candidates UK wide can be considered.",
    "Remote. We recruit across the UK and offer remote working opportunities.",
    "We offer a remote role, with occasional office work.",
    "As a remote employee, you may be required to be present at a CohnReznick office with scheduled notice.",
    "Remote working possibilities with a minimum of 1-2 days per month in the Frankfurt headquarters.",
    "Remote. 20 business days remote working, or use the time to cover mandatory office days.",
    # PARTSHARP's checklist of 2026-10-12
    "Remote. The candidate is required to attend the office a minimum of 3 days per week.",
    "Remote. We are based in Chesterfield and require office attendance at least 2 days per week.",
    "Remote. Flexibility to work from home typically two days per week in a five-day working week.",
    # the second checklist round of 2026-10-12
    "Location: Remote (US Region). Duration: Long-Term Contract.",
    "LOCATION & WORK HOURS Location: Remote – Canada. Work Arrangement: Remote.",
    "Part-Time AI Training Work - Remote (United States).",
    "Contract 6-12 months Remote UK £550 - £600 per day.",
    "Location: We are open to fully remote candidates within New Zealand.",
    "Remote. Our partner is looking for a Senior Full-Stack Engineer based in Switzerland.",
    "Remote. Employment type: Permanent Workplace model: Hybrid.",
    "Remote. Office collaboration: you welcome working 3 days per week in the Espoo office.",
    "Remote. We encourage our team members to join us at our Coleshill office 2 days per week.",
    "Student Information System (SIS) Remote (MST) 4-month contract.",
    "Remote. The position is primarily based in Fredrikstad. We work mainly from the office.",
    "Remote. Please note that a fully remote work policy is not offered for this role.",
    # the third checklist round of 2026-10-12
    "SALARY: $102,050.00 - $115,000.00 Annually LOCATION: Remote in CA only General Description.",
    "Location: Canada (remote) The salary range for this role is $120,000.",
    "Remote. US applicants only, we are an Equal Opportunity Employer.",
    "Remote. At this time, we are only able to consider candidates who reside and work in British Columbia.",
])
def test_a_stated_place_or_hybrid_arrangement_rejects(text):
    result = _score(text)
    assert result["classification"] == "rejected"
    assert any(d[len("location: "):] in NEW_HARD for d in result["dealbreakers"]
               if d.startswith("location: ")), result["dealbreakers"]


@pytest.mark.parametrize("text", [
    "Remote. CSC offers hybrid or remote work schedules in alignment with local regulation.",
    "Remote. Hybrid / remote-friendly work environment.",
    "Remote. Experience with on-prem, hybrid, cloud deployments.",
    "Remote. Location: Hybrid, Remote.",
    # nothing ties these to one country
    "Work from anywhere in the world; we connect you with startups in the US and Europe.",
    "Remote (Work from Anywhere). Contract.",
    "We are open to candidates from any country.",
    "Our remote team spans the US, Europe and Asia.",
    "The office is open to employees in London who want it; this role is fully remote worldwide.",
    "Fully remote: work from home 5 days per week, from any country.",
    "Remote (US or Europe).",
    "Remote, US time zones overlap of four hours.",
    "Remote within Europe or worldwide; the office in Lisbon is optional.",
    "Remote in any country, but only during EU hours.",
    "Location: Canada (remote) or anywhere in Europe.",
    "We consider candidates who reside anywhere in the world.",
])
def test_hybrid_offered_beside_remote_or_as_technology_does_not(text):
    assert not any(d[len("location: "):] in NEW_HARD for d in _score(text)["dealbreakers"]
                   if d.startswith("location: "))


def test_a_board_saying_anywhere_makes_it_likely_and_adds_the_bonus():
    fields = dict(location_raw="Anywhere in the World", source="weworkremotely")
    with_bonus = _score("Fully remote.", **fields)
    without = _score("Fully remote.", criteria=_criteria(points={}), **fields)
    assert with_bonus["residency_eligibility"] == score.ELIGIBILITY_LIKELY
    bonus = SHARP_RL["residency_eligibility"]["points"]["likely"]
    assert bonus > 0
    assert with_bonus["score_breakdown"]["reachability_bonus"] == {
        "points": bonus, "eligibility": score.ELIGIBILITY_LIKELY}
    assert with_bonus["score"] == min(100, without["score"] + bonus)


def test_no_bonus_when_nothing_says_where_from():
    result = _score("Fully remote.", location_raw="Toronto, Ontario, Canada")
    assert result["residency_eligibility"] == score.ELIGIBILITY_UNKNOWN
    assert result["score_breakdown"]["reachability_bonus"]["points"] == 0


def test_a_contract_with_the_persons_own_business_counts_as_engaging_abroad():
    result = _score("Fully remote contract. You need to have an IE (individual entrepreneur), "
                    "or LLC registered to cooperate with us.")
    assert result["residency_eligibility"] == score.ELIGIBILITY_LIKELY


def test_a_board_saying_place_only_is_rejected():
    fields = dict(location_raw="United States only", source="himalayas")
    result = _score("Fully remote.", **fields)
    assert result["classification"] == "rejected"
    assert any(d.startswith("location: source restricts hiring to")
               for d in result["dealbreakers"])


# A posting written wholly in a language the person does not read (the
# checklist of 2026-10-12). The detection is read from the SHARP template.
LANGUAGE = SHARP["language_requirement_signal"]


@pytest.mark.parametrize("text, language", [
    ("CHI SIAMO Adentis Italia è un gruppo europeo di consulenza ingegneristica e IT. "
     "Siamo una realtà in continua evoluzione. Modalità: Full remote sede: Italia. "
     "Stiamo cercando un .NET Core Developer con circa 4 anni di esperienza nello sviluppo "
     "di applicazioni backend, da inserire all'interno di un team tecnico.", "italian"),
    ("Arbejdssted: Billund (Hybrid / Remote efter aftale). Vi søger en erfaren Senior Backend "
     "Engineer, som vil være med til at designe og udvikle backend-arkitekturen bag vores "
     "platform. Dine arbejdsopgaver: Backend-udvikling (.NET / C#) og integrationer til "
     "eksterne systemer.", "scandinavian"),
])
def test_a_posting_written_in_another_language_is_detected(text, language):
    criteria = {**CRITERIA, "language_requirement_signal": {
        **CRITERIA["language_requirement_signal"],
        "foreign_language_posting_indicators": LANGUAGE["foreign_language_posting_indicators"]}}
    result = _score(text, criteria=criteria)
    hits = result["score_breakdown"]["language_requirement_signal"]["foreign_language_posting_hits"]
    assert language in hits
    assert result["classification"] == "rejected"


def test_an_english_posting_is_not_taken_for_italian_or_scandinavian():
    criteria = {**CRITERIA, "language_requirement_signal": {
        **CRITERIA["language_requirement_signal"],
        "foreign_language_posting_indicators": LANGUAGE["foreign_language_posting_indicators"]}}
    result = _score("Fully remote. We are looking for a developer with experience in the "
                    "development of backend services; the team works on the platform and "
                    "integrations to external systems, and the role is open worldwide.",
                    criteria=criteria)
    hits = result["score_breakdown"]["language_requirement_signal"]["foreign_language_posting_hits"]
    assert not ({"italian", "scandinavian"} & set(hits))


@pytest.mark.parametrize("text", [
    "Required Skills & Experience (MUST): C#, .NET. Language : Japanese.",
    "Remote. Native Mandarin fluency.",
    "Remote. Japanese required for client meetings.",
    "Remote. Excellent English and Korean verbal and written communication skills.",
    "Remote. Strong communication skills in both Norwegian and English.",
])
def test_an_asian_language_demanded_rejects(text):
    criteria = {**CRITERIA, "language_requirement_signal": {
        **CRITERIA["language_requirement_signal"],
        "explicit_requirement_patterns": LANGUAGE["explicit_requirement_patterns"]}}
    assert _score("Fully remote, worldwide. " + text, criteria=criteria)["classification"] == "rejected"


def test_japanese_as_a_market_does_not_reject():
    criteria = {**CRITERIA, "language_requirement_signal": {
        **CRITERIA["language_requirement_signal"],
        "explicit_requirement_patterns": LANGUAGE["explicit_requirement_patterns"]}}
    result = _score("Fully remote, worldwide. Our customers include Japanese and Korean banks. "
                    "The app supports English and Chinese to accommodate diverse user needs.",
                    criteria=criteria)
    assert result["classification"] != "rejected", result["dealbreakers"]


def _sharp_authorization(text):
    hits, _ = score._check_work_authorization(text.lower(), SHARP, PROFILE, False)
    return hits


@pytest.mark.parametrize("text, rule", [
    ("8570 Baseline IAT Level I Minimum Clearance Secret Physical Requirements.", "security clearance required"),
    ("US Citizen Eligible for a government-issued Secret-level clearance.", "security clearance required"),
    ("Clearance: Top Secret.", "security clearance required"),
    ("Duration: 9 Months Contract (Potential Extension) Contract: W2 We are seeking an engineer.",
     "US payroll only (W-2)"),
])
def test_clearance_and_w2_fields_the_third_round_found_refuse(text, rule):
    assert rule in _sharp_authorization(text)


@pytest.mark.parametrize("text", [
    "No security clearance is required for this role.",
    "Employment Type: W2/1099/FTE.",
])
def test_clearance_and_w2_fields_do_not_refuse_what_is_not_demanded(text):
    assert not {"security clearance required", "US payroll only (W-2)"} & set(_sharp_authorization(text))
