"""
Engagement, graded pay, and axes an identity declares for itself.

Three mechanisms added together on 2026-09-13, for a second search run by the
same person: side work beside a main job — part-time, as well paid as
possible, interesting where it can be. That search scores several things the
first one scores the other way round, and one thing the first one never had to
ask at all: HOW MANY HOURS.

THE ENGAGEMENT GATE HAS THE SAME TWO HALVES AS THE REMOTE GATE
--------------------------------------------------------------
* The employer's or the board's own statement decides. "Employment type:
  Full-time" is a refusal; "Part-time" or "20 hours a week" a confirmation.
* Silence decides nothing. Full-time is the default most postings never write
  down, so an unstated engagement is the COMMON case — and treating it as a
  refusal would throw away most of the market on a guess (CLAUDE.md section 5,
  "a refusal by guesswork is not a refusal"). It goes to its own class, with
  the score untouched.

A search that has no `engagement_fit` block must not notice any of this — the
first tests below are about exactly that.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import normalize  # noqa: E402
import score  # noqa: E402

from test_score import CRITERIA, PROFILE, make_vacancy  # noqa: E402

GOOD_TEXT = ("Maintain and extend an ASP.NET Core and SQL Server platform in C#. "
             "Fully remote, we hire worldwide.")

ENGAGEMENT = {
    "confirming_types": ["part-time", "freelance"],
    "contradicting_types": ["full-time", "internship"],
    "confirming_patterns": [
        {"name": "part-time", "pattern": r"\bpart[- ]time\b"},
        {"name": "under thirty hours a week",
         "pattern": r"\b(?:[5-9]|[12]\d|30)\s*(?:(?:-|to|–)\s*\d{1,2}\s*)?(?:hours|hrs)\s*(?:per|a|/)\s*week"},
    ],
    "contradicting_patterns": [
        {"name": "a full-time position",
         "pattern": r"\bthis is a full[- ]time (?:position|role|job)\b"},
    ],
    "unconfirmed_policy": "manual_check",
}


def _criteria(**blocks):
    criteria = copy.deepcopy(CRITERIA)
    criteria.update(copy.deepcopy(blocks))
    return criteria


def _score(criteria=None, **kwargs):
    kwargs.setdefault("description_text", GOOD_TEXT)
    return score.score_vacancy(make_vacancy(**kwargs), criteria or CRITERIA, PROFILE)


CONFIDENT = ("hot_lead", "worth_a_look", "long_shot")


def test_the_baseline_vacancy_passes_every_gate():
    """Every test below compares against this, so it has to be a real
    candidate — otherwise "not rejected" would prove nothing."""
    assert _score()["classification"] in CONFIDENT


# --- normalisation: every spelling a board uses ----------------------------

def test_every_board_spelling_reaches_the_same_canonical_value():
    for given, expected in [
        ("part_time", ["part-time"]),        # Remotive
        ("Part Time", ["part-time"]),        # Himalayas
        ("PART_TIME", ["part-time"]),        # schema.org
        ("Part-time", ["part-time"]),        # LinkedIn
        ("part-time", ["part-time"]),        # Remote Rocketship
        ("Contractor", ["contract"]),
        (["FULL_TIME", "CONTRACTOR"], ["full-time", "contract"]),
        ("Full-time, Part-time", ["full-time", "part-time"]),
        ("freelance", ["freelance"]),
    ]:
        assert normalize.employment_types(given) == expected, given


def test_a_value_that_says_nothing_about_hours_is_dropped():
    """"Permanent" says how long a job lasts, not how many hours it takes: a
    UK permanent role can be part-time. Mapping it to full-time would turn a
    board's silence into a refusal."""
    for given in (None, "", [], "Permanent", "Other", "volunteer", 0):
        assert normalize.employment_types(given) == [], given


def test_the_order_is_canonical_so_equal_statements_store_equally():
    assert (normalize.employment_types(["contract", "part-time"])
            == normalize.employment_types("Part Time, Contractor")
            == ["part-time", "contract"])


# --- a search without the block does not notice it -------------------------

def test_without_the_block_nothing_changes():
    plain = _score(employment_types=["full-time"])
    assert plain["score_breakdown"]["engagement_fit"] == {}
    assert not any(d.startswith("engagement:") for d in plain["dealbreakers"])
    assert plain["classification"] in CONFIDENT


# --- the statement decides --------------------------------------------------

def test_a_board_saying_part_time_confirms():
    r = _score(_criteria(engagement_fit=ENGAGEMENT), employment_types=["part-time"])
    assert r["score_breakdown"]["engagement_fit"]["verdict"] == "confirmed"
    assert r["classification"] in CONFIDENT


def test_a_board_saying_full_time_refuses():
    r = _score(_criteria(engagement_fit=ENGAGEMENT), employment_types=["full-time"])
    assert r["classification"] == "rejected"
    assert "engagement: the board lists it as full-time" in r["dealbreakers"]


def test_full_time_beside_contract_is_still_full_time():
    """An ATS "Full-time, Contract" is a full-time contract. Requiring EVERY
    stated type to be refused would have let it through."""
    r = _score(_criteria(engagement_fit=ENGAGEMENT),
               employment_types=["full-time", "contract"])
    assert r["classification"] == "rejected"


def test_the_employer_writing_full_time_refuses():
    r = _score(_criteria(engagement_fit=ENGAGEMENT),
               description_text=GOOD_TEXT + " This is a full-time position.")
    assert r["classification"] == "rejected"
    assert any("a full-time position" in d for d in r["dealbreakers"])


def test_contract_alone_is_not_a_statement_about_hours():
    """A UK day-rate contract is five days a week. "Contract" answers who
    invoices whom, not how many hours."""
    r = _score(_criteria(engagement_fit=ENGAGEMENT), employment_types=["contract"])
    assert r["classification"] == "engagement_unconfirmed"


# --- a confirmation anywhere beats a refusal anywhere -----------------------

def test_the_employer_stating_hours_beats_the_boards_default():
    r = _score(_criteria(engagement_fit=ENGAGEMENT), employment_types=["full-time"],
               description_text=GOOD_TEXT + " Around 15-20 hours per week, flexible.")
    assert r["score_breakdown"]["engagement_fit"]["verdict"] == "confirmed"
    assert r["classification"] in CONFIDENT


def test_full_time_or_part_time_is_an_offer_of_part_time():
    r = _score(_criteria(engagement_fit=ENGAGEMENT),
               description_text=GOOD_TEXT + " This is a full-time role; part-time is possible too.")
    assert r["score_breakdown"]["engagement_fit"]["verdict"] == "confirmed"


def test_forty_hours_a_week_is_not_mistaken_for_a_part_time_figure():
    r = _score(_criteria(engagement_fit=ENGAGEMENT),
               description_text=GOOD_TEXT + " Expect 40 hours per week.")
    assert r["score_breakdown"]["engagement_fit"]["verdict"] == "unconfirmed"


# --- silence: its own class, its score untouched ----------------------------

def test_silence_goes_to_a_person_with_the_score_unchanged():
    """The owner's rule for the remote gate, carried over: "in hot_lead we can
    have a 70, and in 'check by hand' a 70 as well"."""
    gated = _score(_criteria(engagement_fit=ENGAGEMENT))
    plain = _score()
    assert gated["classification"] == "engagement_unconfirmed"
    assert gated["score"] == plain["score"]
    assert score.ENGAGEMENT_UNCONFIRMED in gated["dealbreakers"]


def test_the_policy_can_refuse_silence_or_ignore_it():
    refuse = dict(ENGAGEMENT, unconfirmed_policy="reject")
    ignore = dict(ENGAGEMENT, unconfirmed_policy="accept")
    assert _score(_criteria(engagement_fit=refuse))["classification"] == "rejected"
    assert _score(_criteria(engagement_fit=ignore))["classification"] in CONFIDENT


def test_a_real_refusal_beside_silence_is_still_a_refusal():
    r = _score(_criteria(engagement_fit=ENGAGEMENT),
               description_text=GOOD_TEXT + " Security clearance required.")
    assert r["classification"] == "rejected"


def test_when_both_remote_and_hours_are_unknown_both_are_kept():
    """The remote question takes the class — a vacancy that turns out to be
    onsite is out whatever its hours — but the report has to be able to say
    that the hours are unknown too."""
    r = _score(_criteria(engagement_fit=ENGAGEMENT), remote=None,
               description_text="Maintain an ASP.NET Core and SQL Server platform in C#.")
    assert r["classification"] == "remote_unconfirmed"
    assert score.REMOTE_UNCONFIRMED in r["dealbreakers"]
    assert score.ENGAGEMENT_UNCONFIRMED in r["dealbreakers"]


def test_a_role_ruled_out_is_not_parked_for_a_person_when_the_identity_says_so():
    """PJOICE's first run: a Principal Data Engineer at 55 in "hours not
    confirmed". Confirming its hours could not have made it a candidate."""
    criteria = _criteria(engagement_fit=ENGAGEMENT)
    criteria["role_complexity_signal"] = dict(criteria["role_complexity_signal"],
                                              title_red_flag_patterns=["data engineer"],
                                              applies_to_unconfirmed=True)
    r = _score(criteria, title="Principal Data Engineer")
    assert r["score_breakdown"]["role_complexity_signal"]["gate_triggered"]
    assert r["classification"] == "low_priority"


def test_without_the_option_a_ruled_out_role_still_waits_for_a_person():
    """KISEL's order, kept on purpose: there a single "agentic" in boilerplate
    gates an ordinary .NET Developer, and 51 such vacancies would vanish."""
    criteria = _criteria(engagement_fit=ENGAGEMENT)
    criteria["role_complexity_signal"] = dict(criteria["role_complexity_signal"],
                                              title_red_flag_patterns=["data engineer"])
    criteria["role_complexity_signal"].pop("applies_to_unconfirmed", None)
    r = _score(criteria, title="Principal Data Engineer")
    assert r["classification"] == "engagement_unconfirmed"


# --- axes an identity declares ----------------------------------------------

SIGNALS = [{
    "name": "interesting_domain",
    "label": "interesting",
    "points_per_keyword": 3,
    "cap": 5,
    "keywords": ["microservices", "blockchain", "llm"],
    "negative_keywords": ["on-call rotation"],
    "negative_points_per_keyword": -4,
    "floor": -4,
}]


def test_a_declared_signal_adds_points_up_to_its_cap():
    text = GOOD_TEXT + " Microservices for a blockchain wallet, with an LLM assistant."
    with_signal = _score(_criteria(extra_signals=SIGNALS), description_text=text)
    without = _score(description_text=text)
    detail = with_signal["score_breakdown"]["extra_signals"]["interesting_domain"]
    assert detail["hits"] == ["microservices", "blockchain", "llm"]
    assert detail["points"] == 5
    assert with_signal["score"] == without["score"] + 5


def test_a_declared_signal_can_subtract_down_to_its_floor():
    text = GOOD_TEXT + " Weekly on-call rotation."
    detail = _score(_criteria(extra_signals=SIGNALS), description_text=text)[
        "score_breakdown"]["extra_signals"]["interesting_domain"]
    assert detail["negative_hits"] == ["on-call rotation"]
    assert detail["points"] == -4


def test_a_malformed_signal_is_skipped_rather_than_fatal():
    points, detail = score._score_extra_signals("anything", {"extra_signals": [{}, None, {"keywords": ["x"]}]})
    assert (points, detail) == (0, {})


# --- graded pay --------------------------------------------------------------

def test_the_hourly_equivalent_takes_the_middle_of_each_range_and_the_best_unit():
    assert score._hourly_equivalent([], [90, 150], []) == 120
    assert score._hourly_equivalent([208_000], [], []) == 100
    assert round(score._hourly_equivalent([], [], [17_333]), 1) == 100.0
    assert score._hourly_equivalent([104_000], [120], []) == 120


def test_an_implausible_amount_is_not_a_rate():
    """"$2,000,000 raised" with no "million" beside it, "$3 per seat"."""
    assert score._hourly_equivalent([2_000_000], [3], [50]) is None


TIERS = {
    "hourly_equivalent_tiers": [
        {"at_least": 100, "points": 20},
        {"at_least": 60, "points": 10},
        {"at_least": 0, "points": -5},
    ],
}


def _pay_criteria():
    criteria = copy.deepcopy(CRITERIA)
    criteria["compensation_signal"].update(copy.deepcopy(TIERS))
    return criteria


def test_pay_is_graded_by_tier():
    criteria = _pay_criteria()
    base = criteria["compensation_signal"]["has_explicit_range_points"]
    for salary, expected in (("$120 - $150 per hour", 20),
                             ("$70 per hour", 10),
                             ("$25 per hour", -5)):
        comp = _score(criteria, salary_raw=salary)["score_breakdown"]["compensation_signal"]
        assert comp["rate_tier_points"] == expected, salary
        assert comp["points"] == base + expected, salary


def test_the_boards_salary_field_outranks_amounts_in_the_prose():
    """Descriptions hold prices and perks the extractor cannot always tell
    from a rate; the board's own field is a rate by definition."""
    comp = _score(_pay_criteria(), salary_raw="$150,000 - $170,000",
                  description_text=GOOD_TEXT + " Includes a $40 per month gym stipend.")[
        "score_breakdown"]["compensation_signal"]
    assert comp["hourly_equivalent_usd"] == round(160_000 / 2080, 1)
    assert comp["rate_tier_points"] == 10


def test_no_salary_stays_neutral_even_with_tiers():
    """CLAUDE.md section 5: no data is not bad pay."""
    criteria = _pay_criteria()
    comp = _score(criteria)["score_breakdown"]["compensation_signal"]
    assert comp["points"] == criteria["compensation_signal"]["no_range_points"]
    assert "rate_tier_points" not in comp


def test_a_salary_the_extractor_cannot_read_gets_no_tier():
    comp = _score(_pay_criteria(), salary_raw="EUR 60,000-70,000/year")[
        "score_breakdown"]["compensation_signal"]
    assert comp["hourly_equivalent_usd"] is None
    assert comp["rate_tier_points"] is None
