import json
import pytest
import score

CRITERIA = score.load_criteria()
PROFILE = score.load_profile()


def make_vacancy(**overrides):
    base = {
        "id": "abc",
        "title": "Senior C# Developer",
        "company": "Acme Corp",
        "location_raw": "",
        # By default the test vacancy is confirmed remote (a flag from the
        # source), so that tests about other axes (role difficulty, role
        # relevance, stack and so on) do not trip over the "not confirmed as
        # remote" gate. Tests about the location/remote gate itself say so.
        "remote": True,
        "tags": [],
        "description_text": "",
        "salary_raw": None,
    }
    base.update(overrides)
    return base


def test_worldwide_remote_scores_higher_than_restrictive_us_only():
    v_world = make_vacancy(
        location_raw="Remote - Anywhere",
        description_text="We hire remote worldwide, no location restriction.",
    )
    v_us = make_vacancy(
        location_raw="Remote (US)",
        description_text="Must be located in the United States.",
    )
    r_world = score.score_vacancy(v_world, CRITERIA, PROFILE)
    r_us = score.score_vacancy(v_us, CRITERIA, PROFILE)
    assert r_world["score"] > r_us["score"]
    assert r_world["classification"] != "rejected"
    # Confirmed explicitly by the owner (2026-07-30): a hard "US only" with no
    # worldwide or EOR signal is a dealbreaker rather than merely lower
    # priority, exactly like any other restrictive regional signal.
    assert r_us["classification"] == "rejected"


def test_restrictive_region_latam_is_rejected():
    # A real bug found (2026-07-30): an HN vacancy saying "remote LATAM" got a
    # decent score although it is physically unavailable to a person in
    # Georgia.
    v = make_vacancy(
        title="Full-stack Developer",
        description_text="C# .NET SQL Server. This is a remote LATAM position, Latin America only.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any("latam" in d.lower() or "latin america" in d.lower() for d in r["dealbreakers"])


def test_restrictive_region_overridden_by_worldwide_signal():
    # If an explicit worldwide/EOR signal IS present, a single mention of a
    # regional phrase must not kill the vacancy (it may be just one of several
    # requirements at a flexible company).
    v = make_vacancy(
        description_text="We hire remote worldwide via Deel. One of our teams is UK only, but most roles are open globally.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] != "rejected"


def test_acceptable_region_israel_scores_better_than_unknown_location():
    v_israel = make_vacancy(
        location_raw="Tel Aviv, Israel",
        description_text="C# .NET SQL Server role, based in Israel, hiring internationally.",
    )
    v_unknown = make_vacancy(description_text="C# .NET SQL Server role.")
    r_israel = score.score_vacancy(v_israel, CRITERIA, PROFILE)
    r_unknown = score.score_vacancy(v_unknown, CRITERIA, PROFILE)
    assert r_israel["score"] > r_unknown["score"]
    assert "israel" in r_israel["score_breakdown"]["remote_location_fit"]["acceptable_region_hits"]


def test_acceptable_region_uae_recognized():
    v_uae = make_vacancy(description_text="C# .NET role, our office is in Dubai, UAE, open to remote hires.")
    r_uae = score.score_vacancy(v_uae, CRITERIA, PROFILE)
    assert r_uae["score_breakdown"]["remote_location_fit"]["points"] > 0


def test_remote_europe_is_restrictive_not_acceptable():
    # A mistake in the first version, fixed 2026-07-30: "EU Remote"/"remote
    # Europe" in a real vacancy means residency IN the EU is required — that is
    # a dealbreaker (like "US Remote") rather than a plus, as was wrongly
    # assumed before.
    v_eu = make_vacancy(description_text="C# .NET role, remote Europe, async-first team.")
    r_eu = score.score_vacancy(v_eu, CRITERIA, PROFILE)
    assert r_eu["classification"] == "rejected"
    assert any("europe" in d.lower() for d in r_eu["dealbreakers"])


def test_hard_location_dealbreaker_forces_rejected():
    v = make_vacancy(description_text="This role requires active security clearance and on-site presence.")
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any("security clearance" in d for d in r["dealbreakers"])


def test_exclusive_employment_clause_is_a_dealbreaker():
    v = make_vacancy(
        description_text=(
            "Remote worldwide, contractor friendly via Deel. "
            "Employee agrees to exclusive employment and no other employment is permitted."
        )
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any("employment" in d for d in r["dealbreakers"])


def test_legacy_enterprise_keywords_increase_score():
    v_legacy = make_vacancy(
        description_text=(
            "Maintain a legacy enterprise banking system. On-premise SQL Server, "
            "WebForms, VB.NET. Stable and mature codebase."
        )
    )
    v_plain = make_vacancy(description_text="We build modern products.")
    r_legacy = score.score_vacancy(v_legacy, CRITERIA, PROFILE)
    r_plain = score.score_vacancy(v_plain, CRITERIA, PROFILE)
    assert r_legacy["score"] > r_plain["score"]
    assert len(r_legacy["score_breakdown"]["legacy_enterprise_signal"]["hits"]) > 0


def test_startup_fast_paced_keywords_decrease_score():
    v = make_vacancy(
        description_text="Fast-paced startup, move fast, wear many hats, on-call rotation 24/7 on-call."
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["score_breakdown"]["low_intensity_signal"]["points"] < 0


def _place_verdicts(result: dict) -> dict:
    """{'georgia': 'ambiguous'|'meaning_a'|'meaning_b'} from score_breakdown."""
    hits = result["score_breakdown"]["remote_location_fit"].get("ambiguous_place_hits") or []
    return {h["name"]: h["verdict"] for h in hits}


def test_ambiguous_place_flags_manual_review():
    """No context fired — which place is meant is unclear."""
    v = make_vacancy(location_raw="Georgia", description_text="Remote position based in Georgia.")
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["needs_manual_review"] is True
    assert _place_verdicts(r)["georgia"] == "ambiguous"


def test_ambiguous_place_resolved_by_first_meaning_context():
    v = make_vacancy(
        location_raw="Tbilisi, Georgia",
        description_text="Remote worldwide, candidate is based in Tbilisi, Georgia (country).",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert _place_verdicts(r)["georgia"] == "meaning_a"


def test_ambiguous_place_resolved_by_second_meaning_context():
    v = make_vacancy(
        location_raw="Atlanta, Georgia, USA",
        description_text="Remote (US) role, HQ in Atlanta, Georgia, USA.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert _place_verdicts(r)["georgia"] == "meaning_b"


def test_ambiguous_place_mechanism_is_not_georgia_shaped():
    """The mechanism must be data-driven rather than tailored to one trap.

    Cambridge (England vs Massachusetts) is the same problem for a different
    person. The rule is described in the fixture's config; there is no code for it.
    """
    v_uk = make_vacancy(
        location_raw="Cambridge",
        description_text="C# role in Cambridge, Cambridgeshire, United Kingdom.",
    )
    v_ma = make_vacancy(
        location_raw="Cambridge",
        description_text="C# role in Cambridge, Massachusetts, near Harvard.",
    )
    v_unclear = make_vacancy(
        location_raw="Cambridge",
        description_text="C# developer role based in Cambridge.",
    )

    assert _place_verdicts(score.score_vacancy(v_uk, CRITERIA, PROFILE))["cambridge"] == "meaning_a"
    assert _place_verdicts(score.score_vacancy(v_ma, CRITERIA, PROFILE))["cambridge"] == "meaning_b"
    assert _place_verdicts(score.score_vacancy(v_unclear, CRITERIA, PROFILE))["cambridge"] == "ambiguous"


def test_stack_label_comes_from_criteria_not_hardcoded():
    """The stack refusal line used to contain a hard-coded '.NET/JS'."""
    v = make_vacancy(
        title="Ruby Developer",
        location_raw="Anywhere in the World",
        description_text="Ruby on Rails and Elixir only.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    stack_dealbreakers = [d for d in r["dealbreakers"] if d.startswith("stack:")]
    assert stack_dealbreakers
    assert CRITERIA["stack_fit"]["stack_label"] in stack_dealbreakers[0]


def test_stack_fit_rewards_known_technologies():
    v_match = make_vacancy(description_text="C# ASP.NET Entity Framework SQL Server Angular Azure")
    v_nomatch = make_vacancy(description_text="Ruby on Rails and Elixir")
    r_match = score.score_vacancy(v_match, CRITERIA, PROFILE)
    r_nomatch = score.score_vacancy(v_nomatch, CRITERIA, PROFILE)
    assert r_match["score_breakdown"]["stack_fit"]["points"] > r_nomatch["score_breakdown"]["stack_fit"]["points"]


def test_stack_fit_is_capped():
    # Many matches must not give an endlessly growing score
    all_keywords = " ".join(score.load_profile()["tech_stack"]["strong"])
    v = make_vacancy(description_text=all_keywords)
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    cap = CRITERIA["stack_fit"]["cap"]
    assert r["score_breakdown"]["stack_fit"]["points"] <= cap


def test_stack_fit_core_technology_weighs_more_than_familiar():
    # Confirmed explicitly by the owner (2026-07-30): technologies actually
    # worked with more often (core, appearing in 6-8 of 8 roles over 7 years)
    # should score more than ones only brushed against (familiar, 1-2 roles).
    # (familiar, 1-2 roles).
    v_core = make_vacancy(description_text="C# ASP.NET SQL Server")  # 3 core words
    v_familiar = make_vacancy(description_text="MongoDB SOAP XSLT")  # 3 familiar words
    r_core = score.score_vacancy(v_core, CRITERIA, PROFILE)
    r_familiar = score.score_vacancy(v_familiar, CRITERIA, PROFILE)
    assert (
        r_core["score_breakdown"]["stack_fit"]["points"]
        > r_familiar["score_breakdown"]["stack_fit"]["points"]
    )
    assert len(r_core["score_breakdown"]["stack_fit"]["core_hits"]) == 3


def test_webforms_not_claimed_as_personal_skill():
    # WebForms/VB.NET were removed from tech_stack (no confirmation in the CV):
    # a mention of WebForms alone must not count towards stack_fit, though it
    # remains a legacy signal in legacy_enterprise_signal.
    # Revised 2026-08-05. The first version demanded EXACTLY 0 for the stack on
    # such a vacancy. That was too much: the person genuinely does not know
    # WebForms, but VB.NET is .NET — the same runtime and the same ecosystem —
    # and .NET has been in their core for seven years. Supporting legacy VB.NET
    # is in fact a model vacancy for this search: dull, stable, few rivals.
    #
    # So what is checked is what was actually wanted: WebForms on its own does
    # NOT count as a skill, while the .NET platform counts modestly.
    v = make_vacancy(title="Application Support", description_text="Maintaining a legacy WebForms VB.NET application.")
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    stack = r["score_breakdown"]["stack_fit"]
    assert "WebForms" not in stack["core_hits"] + stack["strong_hits"]
    assert stack["core_hits"] == [".NET"], stack["core_hits"]

    only_webforms = make_vacancy(
        title="Application Support",
        description_text="Maintaining a legacy WebForms application.")
    assert score.score_vacancy(only_webforms, CRITERIA, PROFILE)[
        "score_breakdown"]["stack_fit"]["points"] == 0
    assert len(r["score_breakdown"]["legacy_enterprise_signal"]["hits"]) > 0


def test_role_complexity_gate_triggers_on_title_principal_scientist():
    # A real case found (2026-07-30): "Principal Machine Learning Scientist" is
    # clearly not a simple role, even with legacy words in the description.
    v = make_vacancy(
        title="Principal Machine Learning Scientist (Experiences)",
        description_text="Enterprise banking insurance client, legacy systems, SQL Server, C#.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "low_priority"
    assert r["score_breakdown"]["role_complexity_signal"]["gate_triggered"] is True
    assert r["score_breakdown"]["role_complexity_signal"]["title_hits"]


def test_role_complexity_gate_triggers_on_title_agentic():
    # A real case found: "Staff Software Engineer, Agentic Platform" at a bank —
    # legacy and enterprise words in the company description do not make an
    # AI-platform role simple.
    v = make_vacancy(
        title="Staff Software Engineer, Agentic Platform",
        description_text="We serve banking and insurance clients. C# .NET SQL Server Azure.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "low_priority"
    assert r["score_breakdown"]["role_complexity_signal"]["gate_triggered"] is True


def test_role_complexity_gate_triggers_on_title_llm_engineer():
    # A real case found (2026-07-30): "LLM Engineer Freelancer" — plainly an AI
    # role ("design, build, and integrate practical AI features"), not caught by
    # the first version of the gate (which only had "agentic"/"Principal
    # Scientist" patterns).
    v = make_vacancy(
        title="LLM Engineer Freelancer",
        description_text="Design, build, and integrate practical AI features. C# .NET JavaScript.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "low_priority"
    assert r["score_breakdown"]["role_complexity_signal"]["gate_triggered"] is True


def test_role_complexity_gate_needs_multiple_description_hits_not_just_one():
    # One stray buzzword in boilerplate must not gate a perfectly normal legacy
    # role — hence a threshold (threshold_hits) for the description.
    v = make_vacancy(
        title="Senior .NET Developer",
        description_text=(
            "Maintain legacy enterprise banking system, C# ASP.NET SQL Server. "
            "We use cutting-edge monitoring tools for uptime."  # only 1 red-flag word
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["score_breakdown"]["role_complexity_signal"]["gate_triggered"] is False


def test_role_complexity_gate_triggers_on_multiple_description_red_flags():
    v = make_vacancy(
        title="Senior Software Engineer",
        description_text=(
            "Build a greenfield platform from scratch, own the entire architecture, "
            "using cutting-edge, state-of-the-art techniques. C# .NET SQL Server."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "low_priority"
    assert r["score_breakdown"]["role_complexity_signal"]["gate_triggered"] is True
    assert len(r["score_breakdown"]["role_complexity_signal"]["description_hits"]) >= 2


def test_external_salary_estimate_gives_small_bonus_when_no_explicit_salary():
    v = make_vacancy(
        description_text="Great legacy .NET role, no salary mentioned in the posting.",
        external_signals={
            "salary_estimate": {"low": 65000, "high": 85000, "period": "year", "source": "Glassdoor"}
        },
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    bd = r["score_breakdown"]["compensation_signal"]
    assert bd["explicit"] is False
    assert 0 < bd["points"] < CRITERIA["compensation_signal"]["has_explicit_range_points"]


def test_external_salary_estimate_ignored_when_explicit_salary_present():
    # An explicit salary in the vacancy text always beats an external estimate.
    v = make_vacancy(
        salary_raw="$70/hour",
        external_signals={
            "salary_estimate": {"low": 1000, "high": 2000, "period": "year", "source": "Glassdoor"}
        },
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    bd = r["score_breakdown"]["compensation_signal"]
    assert bd["explicit"] is True


def test_external_salary_estimate_below_target_is_penalized():
    v = make_vacancy(
        description_text="No salary mentioned in the posting.",
        external_signals={
            "salary_estimate": {"low": 10000, "high": 15000, "period": "year", "source": "Glassdoor"}
        },
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    bd = r["score_breakdown"]["compensation_signal"]
    assert bd["points"] < CRITERIA["compensation_signal"]["external_estimate_points"]


def test_compensation_no_salary_is_neutral_not_penalized():
    v = make_vacancy(description_text="Great legacy .NET role, no salary mentioned.")
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["score_breakdown"]["compensation_signal"]["explicit"] is False
    assert r["score_breakdown"]["compensation_signal"]["points"] == 0


def test_compensation_hourly_rate_within_target_scores_well():
    v = make_vacancy(salary_raw="$60/hour contractor rate")
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["score_breakdown"]["compensation_signal"]["explicit"] is True
    assert r["score_breakdown"]["compensation_signal"]["points"] > 0


def test_compensation_below_target_is_penalized():
    v = make_vacancy(salary_raw="$10/hour")
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    bd = r["score_breakdown"]["compensation_signal"]
    assert bd["points"] < CRITERIA["compensation_signal"]["has_explicit_range_points"]


def test_compensation_monthly_rate_within_target_not_misread_as_annual():
    # Regression: "$6,000/month" must not be read as an annual rate (which would
    # give an enormous "below annual target" penalty).
    v = make_vacancy(description_text="Part-time contractor role, $6,000/month.")
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    bd = r["score_breakdown"]["compensation_signal"]
    assert bd["monthly_amounts_found"] == [6000.0]
    assert bd["annual_amounts_found"] == []
    assert bd["points"] >= CRITERIA["compensation_signal"]["has_explicit_range_points"]


def test_compensation_monthly_rate_below_target_is_penalized():
    v = make_vacancy(description_text="Part-time role, $1,500 per month.")
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    bd = r["score_breakdown"]["compensation_signal"]
    assert bd["monthly_amounts_found"] == [1500.0]
    assert bd["points"] < CRITERIA["compensation_signal"]["has_explicit_range_points"]


def test_low_intensity_weight_intentionally_dominates_compensation_weight():
    # A priority confirmed explicitly by the owner (2026-07-30): guaranteed low
    # intensity matters more than higher pay. This guards against the weights
    # being accidentally "levelled out" in future.
    # Revised 2026-08-05: the `weights` block was deleted — no line of code read
    # it, and it was a declaration reality had drifted away from.
    # A component's real weight is its CAP, so that is what gets compared.
    intensity_swing = CRITERIA["low_intensity_signal"]["cap"] - CRITERIA["low_intensity_signal"]["floor"]
    comp_swing = CRITERIA["compensation_signal"]["has_explicit_range_points"] + max(
        CRITERIA["compensation_signal"]["above_target_bonus"],
        abs(CRITERIA["compensation_signal"]["below_target_penalty"]),
    )
    assert intensity_swing > comp_swing


def test_score_is_always_clamped_between_0_and_100():
    v_best = make_vacancy(
        location_raw="Remote worldwide",
        description_text=(
            "Remote worldwide, contractor via Deel, 1099, part-time flexible hours async, "
            "legacy enterprise banking insurance government on-premise mainframe cobol vb.net "
            "webforms winforms soap monolith C# ASP.NET Entity Framework SQL Server Azure "
            "no on-call low stress work-life balance"
        ),
        salary_raw="$90/hour",
    )
    r = score.score_vacancy(v_best, CRITERIA, PROFILE)
    assert 0 <= r["score"] <= 100


def test_a_named_country_is_not_an_objection_by_itself():
    """Revised 2026-08-05 on the owner's direct instruction: «the target region
    — who cares, what does a region give me? What matters is not geography but

    The history: at first any country in the location field meant total
    rejection — of 3281 European vacancies, one reached the shortlist. Then a
    tier of "target markets" appeared, and the world split into countries with a
    plus and countries with a refusal. Both editions decided for the person
    """
    for loc in ["USA", "Brazil", "Costa Rica", "Texas", "Virginia", "Dublin, Ireland"]:
        v = make_vacancy(
            location_raw=loc,
            description_text="C# ASP.NET SQL Server developer role.",
        )
        r = score.score_vacancy(v, CRITERIA, PROFILE)
        assert not any(d.startswith("location:") for d in r["dealbreakers"]), \
            f"{loc}: {r['dealbreakers']}"


def test_a_net_exporter_country_costs_points_but_is_not_excluded():
    """«There is such a thing as a NON-target region — India, Pakistan, the
    Philippines, minus for them. Even in India you could find something, it is
    just that most vacancies there will not be my style» (owner, 2026-08-05).

    Hence a penalty rather than rejection: a vacancy from there has to be better
    """
    neutral = make_vacancy(location_raw="Portugal",
                           description_text="C# ASP.NET SQL Server developer role.")
    exporter = make_vacancy(location_raw="Bengaluru, India",
                            description_text="C# ASP.NET SQL Server developer role.")
    r_neutral = score.score_vacancy(neutral, CRITERIA, PROFILE)
    r_exporter = score.score_vacancy(exporter, CRITERIA, PROFILE)

    assert r_exporter["score"] < r_neutral["score"]
    assert r_exporter["classification"] != "rejected"
    assert r_exporter["score_breakdown"]["net_exporter_penalty"]["country"] == "India"


def test_structured_location_worldwide_markers_pass():
    for loc in ["Anywhere in the World", "Anywhere", "100% Remote (Global)", "Worldwide"]:
        v = make_vacancy(
            location_raw=loc,
            description_text="C# ASP.NET SQL Server developer role.",
        )
        r = score.score_vacancy(v, CRITERIA, PROFILE)
        assert r["classification"] != "rejected", f"{loc} must NOT be rejected"


def test_structured_location_remote_without_country_is_not_a_restriction():
    # A real bug found (2026-07-31, after the ATS sources were connected):
    # Greenhouse/Ashby write "Remote job", GitLab writes "Distributed"; that
    # states the working arrangement, not a country, and must not cut anything.
    for loc in ["Remote job", "Distributed", "Remote", "Work from home", "N/A"]:
        v = make_vacancy(
            location_raw=loc,
            description_text="C# ASP.NET SQL Server developer role.",
        )
        r = score.score_vacancy(v, CRITERIA, PROFILE)
        assert not any("source restricts hiring" in d for d in r["dealbreakers"]), loc


def test_structured_location_continent_list_treated_as_worldwide():
    # Remotive returns "Americas, Europe, Asia, Africa, Oceania" — the word
    # "worldwide" is absent, but in meaning that is the whole world.
    v = make_vacancy(
        location_raw="Americas, Europe, Asia, Africa, Oceania",
        description_text="C# ASP.NET SQL Server developer role.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] != "rejected"
    assert r["score_breakdown"]["remote_location_fit"]["structured_location"]["verdict"] == "worldwide_by_continents"


def test_structured_location_not_overridden_by_marketing_worldwide_phrase():
    # A real bug found (2026-07-30): Prima (an insurer, London) published 5
    # vacancies with location="London", while the benefits section said "work
    # from anywhere" (the usual "work where you like for N weeks a year") — and
    # that lifted the geography restriction. The board's structured field
    # carries more authority than a marketing phrase in the text.
    v = make_vacancy(
        location_raw="London",
        description_text=(
            "C# TypeScript React developer role at our insurance company. "
            "Benefits include the ability to work from anywhere for a few weeks a year."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    # Revised 2026-08-05: a country by itself is no longer an objection, so
    # there is nothing left to check here except one thing — that the marketing
    # phrase in the text did not turn into a PLUS for worldwide remote work.
    # That was exactly its danger: "work from anywhere for a few weeks a year"
    # in a benefits block read as willingness to hire from anywhere.
    assert not r["score_breakdown"]["remote_location_fit"].get("worldwide_remote_hits")


def test_ml_engineer_titles_are_gated_as_complex():
    for title in ["Senior Machine Learning Engineer", "ML Engineer", "Data Scientist"]:
        v = make_vacancy(
            title=title,
            location_raw="Anywhere in the World",
            description_text="C# TypeScript React SQL Server enterprise legacy.",
        )
        r = score.score_vacancy(v, CRITERIA, PROFILE)
        assert r["classification"] == "low_priority", f"{title} should be gated as complex"
        assert r["score_breakdown"]["role_complexity_signal"]["gate_triggered"] is True


def test_structured_location_not_overridden_by_eor_mention():
    # A real bug found (2026-07-30): LawnStarter publishes vacancies with
    # location="Brazil" and mentions Multiplier (an EOR) — a mention of EOR used
    # to lift the geography restriction, and 11 Latin American vacancies became
    # candidates. An EOR says HOW people are engaged, not WHERE they are hired.
    v = make_vacancy(
        location_raw="Brazil",
        description_text="C# TypeScript React role. We hire via Multiplier as a contractor.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    # Revised 2026-08-05: a country by itself is no longer an objection, so
    # there is nothing left to check here except one thing — that the marketing
    # phrase in the text did not turn into a PLUS for worldwide remote work.
    # That was exactly its danger: "work from anywhere for a few weeks a year"
    # in a benefits block read as willingness to hire from anywhere.
    assert not r["score_breakdown"]["remote_location_fit"].get("worldwide_remote_hits")


def test_remote_only_source_is_trusted_without_remote_word():
    # A real bug found (2026-07-30): vacancies from remote-only boards
    # (WWR/RemoteOK/Remotive/Jobicy/Himalayas) were rejected as "not confirmed
    # as remote" purely because the word "remote" did not appear in the text —
    # a pure false negative.
    v = make_vacancy(
        source="weworkremotely",
        remote=None,
        location_raw="",
        description_text="C# ASP.NET SQL Server developer role, legacy maintenance.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] != "rejected"
    assert not any("not confirmed as a remote position" in d for d in r["dealbreakers"])


def test_non_remote_only_source_still_needs_remote_signal():
    v = make_vacancy(
        source="arbeitnow",
        remote=None,
        location_raw="",
        description_text="C# ASP.NET SQL Server developer role.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any("not confirmed as a remote position" in d for d in r["dealbreakers"])


def test_infrastructure_only_stack_is_not_enough():
    # A real finding (2026-07-30): Canonical vacancies (embedded/Linux systems)
    # passed the gate on the word "Docker" alone. Generic infrastructure words
    # do not prove a role suits a .NET/JS developer — a real language or
    # framework is needed.
    v = make_vacancy(
        title="Embedded Linux Systems Engineer",
        description_text="Embedded Linux, C, kernel optimisation, Docker containers, Azure cloud.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any(d.startswith("stack:") for d in r["dealbreakers"])


def test_primary_language_match_passes_stack_gate():
    v = make_vacancy(description_text="TypeScript React frontend role with Docker deployment.")
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] != "rejected"
    assert r["score_breakdown"]["stack_fit"]["primary_language_hits"]


def test_hard_wrong_profession_not_lifted_by_engineer_in_title():
    # Real findings (2026-07-30): "GTM Operations Process Architect" at
    # Stripe, "Partner Solutions Architect" @ Nebius, "Senior Manager,
    # DevOps", "Senior Developer Advocate" at Datadog — all contain
    # architect/engineer/developer in the title, which made the ordinary
    # developer override lift the gate.
    for title in [
        "GTM Operations Process Architect",
        "Partner Solutions Architect",
        "Senior Manager, DevOps",
        "Senior Developer Advocate - Data Observability",
        "Senior Sales Engineer - Majors (East)",
    ]:
        v = make_vacancy(
            title=title,
            location_raw="Anywhere in the World",
            description_text="C# TypeScript React SQL Server enterprise legacy systems.",
        )
        r = score.score_vacancy(v, CRITERIA, PROFILE)
        assert r["classification"] == "rejected", f"{title} should be rejected"
        assert any(d.startswith("role:") for d in r["dealbreakers"]), title


def test_devops_and_infrastructure_roles_are_rejected():
    # Confirmed explicitly by the owner (2026-07-30): "throw out the devops, it
    # is not my kind of vacancy". The owner is an applied .NET/JS developer, not
    # an operations engineer. The word "engineer" in a title must not lift this
    # gate.
    for title in [
        "DevOps Engineer",
        "Senior DevOps Engineer",
        "Site Reliability Engineer",
        "SRE",
        "Cloud Infrastructure Engineer",
        "Platform Engineer",
        "Systems Administrator",
        "Full Stack Developer - DevOps & Cloud Systems",
    ]:
        v = make_vacancy(
            title=title,
            location_raw="Anywhere in the World",
            description_text="C# ASP.NET TypeScript React SQL Server legacy enterprise maintenance.",
        )
        r = score.score_vacancy(v, CRITERIA, PROFILE)
        assert r["classification"] == "rejected", f"{title} should be rejected"
        assert any(d.startswith("role:") for d in r["dealbreakers"]), title


def test_normal_developer_titles_still_pass():
    # Guarding against the opposite skew: ordinary engineering titles must NOT
    # fall under hard_wrong_profession.
    for title in [
        "Senior Software Engineer",
        "Full Stack Developer",
        "Senior .NET Developer",
        "Backend Engineer",
        "Frontend Developer",
    ]:
        v = make_vacancy(
            title=title,
            location_raw="Anywhere in the World",
            description_text="C# ASP.NET TypeScript React SQL Server legacy enterprise maintenance.",
        )
        r = score.score_vacancy(v, CRITERIA, PROFILE)
        assert r["classification"] != "rejected", f"{title} should NOT be rejected"


def test_thresholds_let_plain_passing_vacancy_into_report():
    # The key change of 2026-07-30: an ordinary, perfectly normal remote vacancy
    # that passed ALL the hard gates but says nothing about "legacy" or
    # "part-time" and quotes no range scores only about 15 points. Under the old
    # long_shot=25 threshold it was never shown to the owner — 1 of 966 was.
    v = make_vacancy(
        title="Senior Software Engineer",
        location_raw="Anywhere in the World",
        description_text="We are looking for a TypeScript and React developer to join our team.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] in ("long_shot", "worth_a_look", "hot_lead"), (
        "a vacancy that passed every gate must reach the report rather than "
        f"low_priority (score={r['score']})"
    )


def test_company_reputation_no_data_is_neutral():
    v = make_vacancy(location_raw="Anywhere in the World",
                     description_text="C# TypeScript React developer role.")
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    bd = r["score_breakdown"]["company_reputation_signal"]
    assert bd["has_data"] is False
    # As with pay: "no data" != "bad".
    baseline = r["score"]

    v2 = dict(v, _company_reputation={"overall_rating": 4.2, "work_life_balance": 4.4,
                                      "source": "Glassdoor"})
    r2 = score.score_vacancy(v2, CRITERIA, PROFILE)
    assert r2["score"] > baseline


def test_good_work_life_balance_outweighs_mediocre_overall_rating():
    # For this project work-life balance matters more than the overall rating: a
    # company can be "good" on pay and career while squeezing its people dry.
    good_wlb = make_vacancy(
        location_raw="Anywhere in the World",
        description_text="C# TypeScript React developer role.",
        _company_reputation={"overall_rating": 3.6, "work_life_balance": 4.5, "source": "Glassdoor"},
    )
    bad_wlb = make_vacancy(
        location_raw="Anywhere in the World",
        description_text="C# TypeScript React developer role.",
        _company_reputation={"overall_rating": 4.2, "work_life_balance": 2.5, "source": "Glassdoor"},
    )
    r_good = score.score_vacancy(good_wlb, CRITERIA, PROFILE)
    r_bad = score.score_vacancy(bad_wlb, CRITERIA, PROFILE)
    assert r_good["score"] > r_bad["score"]


def test_alarming_rating_and_red_flags_force_manual_review():
    v = make_vacancy(
        location_raw="Anywhere in the World",
        description_text="C# TypeScript React developer role.",
        _company_reputation={"overall_rating": 2.1, "work_life_balance": 2.0,
                             "source": "Glassdoor", "red_flags": ["late payments", "toxic"]},
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["needs_manual_review"] is True
    bd = r["score_breakdown"]["company_reputation_signal"]
    assert bd["alarming_rating"] is True
    assert bd["red_flags"] == ["late payments", "toxic"]
    assert bd["points"] < 0


def test_eor_bare_keyword_does_not_false_match_inside_common_words():
    # A real bug found (2026-07-30, via the manual checklist): a bare
    # "eor" matched as a substring inside "theoretical"/"theory" and bypassed the
    # "not confirmed as remote" gate for the constellr vacancy
    # (Hybrid, Munich, remote=False, not one "remote" in the text).
    v = make_vacancy(
        remote=False,
        location_raw="Hybrid, Munich",
        description_text="Theoretical and applied background in AI planning systems. C# ASP.NET SQL Server.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert "eor_or_contractor_hits" not in r["score_breakdown"]["remote_location_fit"]
    assert r["classification"] == "rejected"
    assert any("not confirmed as a remote position" in d for d in r["dealbreakers"])


def test_role_complexity_gate_triggers_on_single_agentic_mention_in_description():
    # A real case found (2026-07-30, via the manual checklist):
    # "Staff Software Engineer (AI CICD)" at Chainguard mentioned "agentic AI
    # foundation" once in the description — not enough for the threshold_hits
    # bar (two vague words needed) — but "agentic" is unambiguous on its own and
    # must gate on a single mention, even outside the title.
    v = make_vacancy(
        title="Staff Software Engineer (AI CICD)",
        description_text=(
            "We're building the next generation of security products. "
            "Extend our agentic AI foundation into customer-facing product experiences. "
            "C# .NET SQL Server Azure."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "low_priority"
    assert r["score_breakdown"]["role_complexity_signal"]["gate_triggered"] is True
    assert r["score_breakdown"]["role_complexity_signal"]["strong_single_hit_matches"]


def test_vacancy_with_zero_remote_signal_is_rejected_not_just_flagged():
    # Confirmed explicitly by the owner (2026-07-30): "I need ONLY REMOTE
    # positions". A real case found: the Rangeview vacancy (plainly ONSITE, city
    # "El Segundo, CA") contained the word "remote" nowhere at all and used to
    # get a soft needs_manual_review rather than a refusal. With no remote signal
    # of ANY kind — neither a source flag nor a word in the text — that is a
    # dealbreaker, not "unknown, but let it through".
    v = make_vacancy(
        remote=None,
        location_raw="El Segundo, CA",
        description_text=(
            "C# ASP.NET SQL Server legacy enterprise banking maintenance webforms monolith. ONSITE."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any("not confirmed as a remote position" in d or "onsite" in d.lower() for d in r["dealbreakers"])


def test_needs_manual_review_when_promising_vacancy_mentions_remote_but_unclear_region():
    # A stack-relevant, legacy-enterprise vacancy that mentions "remote"
    # SOMEWHERE (so it is not a "not confirmed as remote" dealbreaker) but has no
    # explicit worldwide/US-only/EOR/region signal is exactly the case worth
    # asking the agent to re-check by hand.
    v = make_vacancy(
        remote=None,
        location_raw="",
        description_text=(
            "Remote C# ASP.NET SQL Server legacy enterprise banking maintenance webforms monolith"
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] in ("hot_lead", "worth_a_look", "long_shot")
    assert r["needs_manual_review"] is True


def test_irrelevant_vacancy_with_no_stack_match_not_flagged_for_review():
    # A completely irrelevant vacancy without a single technical word — never
    # mind that the location is unclear too, nobody should spend time re-checking it.
    v = make_vacancy(
        title="Groundman II",
        remote=None,
        location_raw="",
        description_text="Manual labor, utility line maintenance. Benefits include health insurance.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    # Confirmed explicitly by the owner (2026-07-30): "0% chance of reaching the
    # shortlist" for anything unrelated to real skills means a dealbreaker
    # (rejected), not merely low priority.
    assert r["classification"] == "rejected"
    assert any(d.startswith("stack:") for d in r["dealbreakers"])
    assert r["needs_manual_review"] is False


def test_stack_gate_rejects_irrelevant_boilerplate_job():
    # A real case found on live data: a vacancy with not one stack match
    # (score_breakdown.stack_fit.points == 0) but plenty of generic
    # enterprise/legacy boilerplate words ("we serve banking, insurance,
    # government and healthcare clients") scored high-ish and fell into
    # long_shot/needs_review despite having nothing to do with .NET.
    v = make_vacancy(
        title="Transportation Analyst",
        description_text=(
            "We serve clients across banking, insurance, government, healthcare, "
            "logistics and manufacturing. Legacy processes, mature and well-established "
            "back office operations, low stress, work-life balance, part-time hours."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["score_breakdown"]["stack_fit"]["points"] == 0
    assert r["classification"] == "rejected"
    assert any(d.startswith("stack:") for d in r["dealbreakers"])


def test_role_relevance_gate_rejects_web_publisher():
    # A real case found (2026-07-30, via the manual checklist):
    # "Web Publisher Half time US Timezone" — CMS/Figma/content work rather than
    # programming, but it passed the filter purely for mentioning HTML/CSS
    # (too generic a stack signal on its own for web-adjacent roles).
    v = make_vacancy(
        title="Web Publisher Half time US Timezone",
        description_text=(
            "Build pages in a Content Management System. HTML & CSS basic knowledge. "
            "Experience with Figma designs. Drupal knowledge is a plus."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any(d.startswith("role:") for d in r["dealbreakers"])


def test_stack_gate_rejects_a_single_familiar_only_match():
    # A real bug found (2026-07-30): "LESS" (the CSS preprocessor, at familiar
    # level) falsely matched the ordinary English word "less" in a finance
    # vacancy ("CFO Controller"), and one familiar match was enough to pass the
    # gate. One familiar hit is no longer enough — a core or strong one is needed.
    # a core or strong one is needed.
    v = make_vacancy(
        title="CFO Controller",
        description_text="Support ownership with financial modeling, no less than 5 years experience required.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["score_breakdown"]["stack_fit"]["familiar_hits"] == []  # "LESS" removed from the list
    assert r["classification"] == "rejected"


def test_tech_agnostic_override_bypasses_stack_gate():
    v = make_vacancy(
        title="Engineer",
        description_text="We are a tech agnostic team - any programming language welcome. Fully remote worldwide.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] != "rejected"


def test_role_relevance_gate_rejects_cfo_controller():
    # A real bug found (2026-07-30): "CFO Controller" at FractionalFinders scored
    # 60 and reached worth_a_look.
    v = make_vacancy(
        title="CFO Controller",
        description_text="Support ownership as the primary financial partner. Contractor, part-time, 1099.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any(d.startswith("role:") for d in r["dealbreakers"])


def test_role_relevance_gate_rejects_product_manager():
    v = make_vacancy(
        title="Product Manager, Mapping and Weather Visualization",
        description_text="Own the roadmap for our mapping product. C# ASP.NET SQL Server backend team collaboration.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any(d.startswith("role:") for d in r["dealbreakers"])


def test_developer_override_lifts_soft_wrong_profession_hit():
    # "Developer"/"Engineer" in a title lifts the SOFT profession gate (unlike
    # the hard list — management, sales, devops; see
    # test_devops_and_infrastructure_roles_are_rejected). Here: the word
    # "Support" is suspicious on its own, but "Engineer" beside it means a
    # product support engineer rather than a support consultant.
    v = make_vacancy(
        title="Application Support Engineer",
        description_text="C# .NET Core ASP.NET SQL Server, maintaining legacy enterprise systems.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] != "rejected"
    assert r["score_breakdown"]["role_relevance_signal"]["developer_override_hits"]


def test_language_requirement_german_explicit_is_dealbreaker():
    # A real bug found (2026-07-30): "Web-Administration / Webmaster TYPO3"
    # required "sehr gute Deutschkenntnisse" — the owner speaks only Russian and
    # English.
    v = make_vacancy(
        title="Web Developer",
        description_text="C# .NET ASP.NET role. Requires sehr gute Deutschkenntnisse for client calls.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any(d.startswith("language:") for d in r["dealbreakers"])


def test_language_requirement_german_market_heuristic_rejects_german_language_posting():
    # A vacancy entirely in German, with no explicit English phrase about
    # language — the heuristic over frequent German words and "m/w/d" must catch
    v = make_vacancy(
        title="Java Entwicklung (m/w/d)",
        description_text=(
            "Wir suchen einen erfahrenen Entwickler. Ihre Aufgaben: Softwareentwicklung. "
            "Ihr Profil: gute Kenntnisse. Bewerbung an unser Unternehmen. Vollzeit, Homeoffice moeglich."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any(d.startswith("language:") for d in r["dealbreakers"])


def test_language_requirement_english_posting_not_flagged():
    v = make_vacancy(description_text="C# .NET ASP.NET SQL Server, fully remote, English-speaking team.")
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["score_breakdown"]["language_requirement_signal"]["gate_triggered"] is False


def test_java_web_developer_role_is_rejected_not_a_fit():
    # Confirmed explicitly by the owner (2026-07-30): "I AM A .NET DEVELOPER,
    # THEY WILL NOT TAKE ME FOR A JAVA POSITION" — a pure Java web role with no
    # .NET/JS must not pass the stack relevance gate, even with a real
    v = make_vacancy(
        title="Java Developer",
        description_text="Backend Java development, Spring Boot, REST APIs, enterprise banking client.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any(d.startswith("stack:") for d in r["dealbreakers"])


def test_java_scala_for_data_pipelines_is_accepted():
    # Confirmed explicitly by the owner (2026-07-30): "Scala for data pipelines —
    # keep it... Java data pipelines are fine too". Java/Scala plus a data
    # engineering context (Spark/Databricks/ETL) is a wanted variant, unlike a
    # pure Java web role.
    v = make_vacancy(
        title="Data Engineer",
        description_text="Build ETL pipelines with Scala and Apache Spark on Databricks. Legacy data warehouse migration.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] != "rejected"
    assert r["score_breakdown"]["stack_fit"]["data_pipeline_exception_applied"] is True


@pytest.mark.parametrize("classification_key", ["hot_lead", "worth_a_look", "long_shot", "low_priority", "rejected"])
def test_all_classification_buckets_are_reachable(classification_key):
    # Simply checks the constant is known to scoring (guards against typos in criteria.yaml)
    thresholds = CRITERIA["classification_thresholds"]
    valid_keys = set(thresholds.keys()) | {"low_priority", "rejected"}
    assert classification_key in valid_keys


# ============================================================================
# Bugs found by the manual checklist, 2026-07-31, on a real shortlist.
# Each test is named after its real source: if a filter is ever broken back
# again, the failure shows which case it was protecting.
# ============================================================================


def test_millions_paid_out_are_not_read_as_an_hourly_rate():
    # Lemon.io: "We've already paid out over $11M to our engineers". The report
    # showed the owner "Pay: $11/hour" — misinformation in the field a decision
    # to apply is made on.
    v = make_vacancy(
        description_text="We've already paid out over $11M to our engineers. Great C# projects.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    comp = r["score_breakdown"]["compensation_signal"]
    assert comp["explicit"] is False, "a board's total payout is not a vacancy's salary"
    assert not comp.get("hourly_amounts_found")


def test_real_hourly_rate_is_still_recognised():
    # The flip side of the fix above: a real rate must still be recognised.
    v = make_vacancy(description_text="C# contract role, up to $60 per hour.")
    comp = score.score_vacancy(v, CRITERIA, PROFILE)["score_breakdown"]["compensation_signal"]
    assert comp["explicit"] is True
    assert 60.0 in comp["hourly_amounts_found"]


def test_employer_header_us_remote_beats_boards_worldwide_field():
    # Stripe: region from WWR = "Anywhere in the World", while the first line of
    # the description said "Headquarters: US Remote". The vacancy was in hot_lead.
    v = make_vacancy(
        title="Software Engineer",
        location_raw="Anywhere in the World",
        description_text="Headquarters: US Remote\nWe build payments infrastructure with TypeScript.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any("header" in d for d in r["dealbreakers"])


def test_employer_header_with_plain_country_is_not_a_restriction():
    # Mindrift: "Headquarters: Saudi Arabia" is the company's address, not a
    # statement about where it hires. It must not be used to cut anything.
    v = make_vacancy(
        location_raw="Anywhere in the World",
        description_text="Headquarters: Saudi Arabia\nURL: http://example.ai\nFreelance C# work, worldwide.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] != "rejected"


def test_kubernetes_platform_role_with_neutral_title_is_rejected():
    # Airtable "Software Engineer, Compute (8+ YOE)": a neutral title, with a
    # Kubernetes platform in the body. The owner excluded DevOps explicitly.
    v = make_vacancy(
        title="Software Engineer, Compute (8+ YOE)",
        description_text=(
            "Design and scale core Kubernetes platform capabilities across ~70 clusters. "
            "Migrate to a new CNI plugin. Adopt Kubernetes operator patterns. "
            "Knowledge of infrastructure as code such as Terraform or Pulumi. "
            "Experience with ArgoCD. Define good SLO and uphold them. TypeScript to Golang rewrite."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any("infrastructure/platform" in d for d in r["dealbreakers"])


def test_app_developer_mentioning_docker_and_kubernetes_is_not_rejected():
    # The threshold has to let an ordinary applied vacancy through: a couple of
    # infrastructure words are in almost every one.
    v = make_vacancy(
        title="Senior .NET Developer",
        description_text=(
            "Maintain our ASP.NET Core services. Deployments run on Kubernetes, "
            "CI/CD via GitHub Actions. Legacy insurance platform."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] != "rejected"


def test_keyword_stuffing_block_does_not_create_stack_hits():
    # Lemon.io "Senior Graphic Designer" got core_hits ["C#", "Angular"] out of a
    # marketing paragraph listing some 60 technologies.
    v = make_vacancy(
        title="Senior Graphic Designer",
        description_text=(
            "5+ years of experience in Graphic Design and Adobe Illustrator.\n"
            "NOT YOUR TECH STACK?\n"
            "We have a variety of projects, so if you have experience in Angular, "
            ".NET & C#, React, Scala, Golang, we would be happy to connect with you "
            "and match you with a project that fits your experience."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert r["score_breakdown"]["stack_fit"]["core_hits"] == []
    assert r["score_breakdown"]["stack_fit"]["noise_sections_ignored"]


def test_designer_title_is_a_hard_dealbreaker():
    # Design is not programming, even when the stack in the text is real.
    v = make_vacancy(
        title="Senior Graphic Designer",
        description_text="Work alongside our C# and Angular engineers on a legacy enterprise product.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any(d.startswith("role:") for d in r["dealbreakers"])


def test_timezone_window_that_includes_the_candidate_is_accepted():
    # Proxify: "Located in CET timezone (+/- 3 hours), we are unable to
    # consider applications from candidates in other time zones".
    # The owner is at UTC+4; CET(UTC+1)+3 = UTC+4 — within range.
    v = make_vacancy(
        title="Senior Frontend Developer",
        description_text=(
            "Proficiency in JavaScript and TypeScript. Located in CET timezone (+/- 3 hours), "
            "we are unable to consider applications from candidates in other time zones."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    tz = r["score_breakdown"]["remote_location_fit"]["timezone_requirement"]
    assert tz["verdict"] == "fits"
    assert r["classification"] != "rejected"


def test_timezone_window_that_excludes_the_candidate_is_rejected():
    # The same rule with another zone: PST +/- 2 = UTC-10..-6, owner at UTC+4.
    v = make_vacancy(
        title="Senior Frontend Developer",
        description_text=(
            "Strong TypeScript skills. Must be located in PST (+/- 2 hours); "
            "we are unable to consider applications from candidates in other time zones."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any(d.startswith("timezone:") for d in r["dealbreakers"])


def test_unparsed_timezone_requirement_flags_for_review_instead_of_rejecting():
    # Hiding a real vacancy is worse than showing a doubtful one.
    v = make_vacancy(
        title="Senior C# Developer",
        description_text=(
            "You must be located in a timezone with significant overlap with our team. "
            "Legacy ASP.NET maintenance."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] != "rejected"
    assert r["needs_manual_review"] is True


def test_posting_written_in_spanish_is_rejected():
    # Work and Study Travel: the posting was entirely in Spanish, paying
    # 16,000 MXN/month. It passed the filter because the "posting in a foreign
    # language" heuristic existed for German only.
    v = make_vacancy(
        title="Website Builder / WordPress Specialist",
        description_text=(
            "En Work and Study Travel buscamos una persona encargada de construir sitios web. "
            "Responsabilidades: crear y mantener paginas web. "
            "Conocimientos principales: WordPress avanzado, HTML, CSS y JavaScript."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any(d.startswith("language:") for d in r["dealbreakers"])


def test_posting_written_in_polish_is_rejected():
    v = make_vacancy(
        title="Full-Stack Developer (React + AWS)",
        description_text=(
            "Obecnie szukamy Full-Stack Developera. Twoje zadania: tworzenie aplikacji "
            "webowych w React i TypeScript. Wymagania: doswiadczenie z AWS."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"


def test_english_posting_is_not_flagged_as_foreign_language():
    # The reverse guard: the markers must not fire on English text.
    v = make_vacancy(
        description_text=(
            "We are looking for a C# developer with experience in legacy enterprise systems. "
            "Requirements: strong ASP.NET background. Remote worldwide."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] != "rejected"


def test_timezone_stated_in_words_is_understood():
    # RedLine Solutions (HN): "We need a developer located within three hours
    # of Pacific timezone" — the only C#/.NET vacancy in the shortlist, and
    # physically unreachable: Pacific ±3 = UTC-11..-5, owner at UTC+4.
    v = make_vacancy(
        title="C#/.NET developer",
        description_text=(
            "RedLine Solutions is hiring a fully remote mid-level C#/.NET developer. "
            "We need a developer located within three hours of Pacific timezone."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any(d.startswith("timezone:") for d in r["dealbreakers"])


def test_signing_bonus_is_not_treated_as_the_bottom_of_the_salary_range():
    # Sticker Mule: "Salary: $150,000-$250,000 USD" + "$20,000 signing bonus".
    # The report showed a range of "$20,000-$250,000/year".
    v = make_vacancy(
        description_text="Salary: $150,000-$250,000 USD. $20,000 signing bonus. C# and TypeScript.",
    )
    comp = score.score_vacancy(v, CRITERIA, PROFILE)["score_breakdown"]["compensation_signal"]
    assert 20000.0 not in comp["annual_amounts_found"]
    assert 150000.0 in comp["annual_amounts_found"]


# ============================================================================
# Bugs found by the manual checklist, 2026-08-04.
# ============================================================================


def test_management_role_is_caught_when_the_title_is_garbage():
    """A record from Hacker News arrived with the title "YC 19" and the company
    "Ashby": the thread parser split the line on delimiters and took the wrong
    piece. The profession gate looks at the title — and "YC 19" has no
    profession in it, so a management vacancy passed as an ordinary one."""
    v = make_vacancy(
        title="YC 19",
        company="Ashby",
        description_text=(
            "Ashby | YC 19 | REMOTE | Hiring Engineering Leaders | $200k-$275k. "
            "We are looking to scale our engineering leadership team. "
            "Stack: TypeScript frontend and backend."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any(d.startswith("role:") for d in r["dealbreakers"])


def test_informative_title_does_not_pull_words_from_the_description():
    """The reverse guard: a normal vacancy has an informative title, and the word
    'manager' in corporate blurb must not throw it away."""
    v = make_vacancy(
        title="Senior C# Developer",
        description_text=(
            "Our hiring manager will contact you. Legacy ASP.NET maintenance, "
            "insurance domain, worldwide remote."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] != "rejected"


def test_crypto_company_is_a_dealbreaker_not_a_penalty():
    """Parity (Polkadot/Kusama) scored 20 and reached the shortlist although the
    profile avoids crypto/web3 outright: the words gave only -8 in
    low_intensity_signal, and the minus drowned in pluses for remote and stack."""
    v = make_vacancy(
        title="Senior Experience Engineer",
        description_text=(
            "Parity builds the core infrastructure behind blockchain. We develop "
            "Polkadot and Kusama, key parts of the Web3 tech stack. TypeScript, React."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any(d.startswith("industry:") for d in r["dealbreakers"])


def test_single_crypto_mention_is_not_enough_to_reject():
    """An ordinary company may mention crypto among its clients — the two-match
    threshold exists precisely for that."""
    v = make_vacancy(
        title="Senior C# Developer",
        description_text=(
            "Legacy insurance platform on ASP.NET. Among our clients there is one "
            "crypto exchange. Worldwide remote."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] != "rejected"


def test_timezone_stated_as_an_explicit_range():
    """SuperPlane: 'We currently work across GMT+2 to GMT-3 and welcome
    candidates in that range' — neither '±N hours' nor 'within N hours of X'."""
    v = make_vacancy(
        title="Product Engineer",
        description_text=(
            "This is a remote role. We currently work across GMT+2 to GMT-3 and "
            "welcome candidates in that range. TypeScript and React."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any(d.startswith("timezone:") for d in r["dealbreakers"])


def test_timezone_range_that_includes_the_candidate_is_accepted():
    v = make_vacancy(
        title="Senior C# Developer",
        description_text=(
            "Legacy ASP.NET maintenance. We work across UTC+2 to UTC+6 and welcome "
            "candidates in that range."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    tz = r["score_breakdown"]["remote_location_fit"]["timezone_requirement"]
    assert tz["verdict"] == "fits"
    assert r["classification"] != "rejected"


def test_keyword_stuffing_block_does_not_trigger_the_industry_gate():
    """The industry gate cut every Lemon.io vacancy: their marketing paragraph
    "NOT YOUR TECH STACK?" lists Blockchain, Ethereum and Solana. The company has
    nothing to do with crypto — that is a list of stacks they match projects to.
    A false refusal hides live vacancies."""
    v = make_vacancy(
        title="Senior C# Developer",
        description_text=(
            "Legacy insurance platform on ASP.NET, worldwide remote.\n"
            "NOT YOUR TECH STACK?\n"
            "We have a variety of projects, so if you have experience in "
            "Blockchain (Ethereum/Solana), React, .NET & C#, we would be happy "
            "to connect with you and match you with a project."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert not any(d.startswith("industry:") for d in r["dealbreakers"])


def test_title_naming_a_foreign_technology_is_rejected():
    """A leak a person spotted in the shortlist itself, 2026-08-04: the gate
    looked for a familiar language across the whole text, and a Rails vacancy
    lists HTML/CSS/JavaScript among adjacent skills."""
    for title in ("Senior Ruby on Rails Developer",
                  "Senior Fullstack Developer (Python)",
                  "Senior Vue Developer"):
        v = make_vacancy(
            title=title,
            description_text=(
                "Worldwide remote. Proficiency in HTML, CSS, JavaScript and modern "
                "frontend tooling. Strong knowledge of Git."
            ),
        )
        r = score.score_vacancy(v, CRITERIA, PROFILE)
        assert r["classification"] == "rejected", title
        assert any(d.startswith("stack: title names") for d in r["dealbreakers"]), title


def test_title_naming_a_known_technology_still_passes():
    """The reverse guard: the gate must not cut vacancies on the person's own stack."""
    for title in ("Senior C# Developer",
                  "Senior Fullstack Developer (React.js / Node.js)",
                  "Software engineer"):
        v = make_vacancy(
            title=title,
            description_text="Legacy enterprise platform, worldwide remote. C# and TypeScript.",
        )
        r = score.score_vacancy(v, CRITERIA, PROFILE)
        assert r["classification"] != "rejected", title


def test_data_pipeline_exception_survives_the_title_gate():
    """Scala/Java in the title with a Spark/Databricks context is a documented
    exception, and it must not die under the new gate."""
    v = make_vacancy(
        title="Scala Data Engineer",
        description_text=(
            "Build ETL pipelines with Scala and Apache Spark on Databricks. "
            "Legacy data warehouse migration. Worldwide remote."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] != "rejected"


# --- Personal market bonus and role penalty (2026-08-05) ---------------------

def test_personal_market_bonus_comes_from_the_local_identity(monkeypatch):
    """The bonus exists because of one person's circumstances (tax, pension,
    family) rather than the market or the search profile. So its values live
    outside git, and the mechanism must work without them: another person has none."""
    profile = dict(PROFILE)
    profile["personal_market_bonus"] = {"Belarus": {"points": 12, "remote_only": True}}

    v = make_vacancy(title="Senior C# Developer", location_raw="Minsk, Belarus",
                     description_text="Legacy ASP.NET, worldwide remote.")
    with_bonus = score.score_vacancy(v, CRITERIA, profile)

    without = dict(PROFILE)
    without.pop("personal_market_bonus", None)
    baseline = score.score_vacancy(v, CRITERIA, without)

    assert with_bonus["score"] > baseline["score"]
    assert with_bonus["score_breakdown"]["personal_market_bonus"]["hits"] == {"Belarus": 12}
    assert baseline["score_breakdown"]["personal_market_bonus"] == {}


def test_market_bonus_marked_remote_only_ignores_onsite_vacancies():
    """The point of the bonus is working from anywhere while staying a tax
    resident. For an office vacancy that point is lost."""
    profile = dict(PROFILE)
    profile["personal_market_bonus"] = {"Belarus": {"points": 12, "remote_only": True}}
    v = make_vacancy(title="Senior C# Developer", location_raw="Minsk, Belarus",
                     remote=False, description_text="Legacy ASP.NET in our office.")
    assert score.score_vacancy(v, CRITERIA, profile)["score_breakdown"]["personal_market_bonus"] == {}


def test_market_bonus_does_not_rescue_a_disqualified_vacancy():
    """The bonus is soft: it moves a vacancy up but does not make an unpassable
    one passable. The gates must fire earlier and independently."""
    profile = dict(PROFILE)
    profile["personal_market_bonus"] = {"Belarus": {"points": 99}}
    v = make_vacancy(title="Senior Ruby on Rails Developer", location_raw="Minsk, Belarus",
                     description_text="Ruby on Rails, HTML, CSS, JavaScript.")
    assert score.score_vacancy(v, CRITERIA, profile)["classification"] == "rejected"


def test_pure_frontend_role_is_penalised_but_not_rejected():
    """Confirmed by the owner (2026-08-05): «a pure Frontend Developer role I
    could do, but my experience is mostly full-stack, and there they are unlikely
    to hire me». Throwing it away would be wrong — it is downgraded instead."""
    front = make_vacancy(title="Frontend Developer",
                         description_text="React and TypeScript, worldwide remote.")
    full = make_vacancy(title="Fullstack Developer",
                        description_text="React and TypeScript, worldwide remote.")
    r_front = score.score_vacancy(front, CRITERIA, PROFILE)
    r_full = score.score_vacancy(full, CRITERIA, PROFILE)

    assert r_front["classification"] != "rejected", "the person can do this job"
    assert r_front["score"] < r_full["score"]
    assert r_front["score_breakdown"]["title_role_penalty"]["points"] < 0


def test_fullstack_title_mentioning_frontend_is_not_penalised():
    """«Fullstack (Frontend focus)» is full-stack, not pure frontend."""
    v = make_vacancy(title="Fullstack Developer (Frontend focus)",
                     description_text="React, C#, worldwide remote.")
    assert score.score_vacancy(v, CRITERIA, PROFILE)["score_breakdown"]["title_role_penalty"] == {}


def test_eor_platform_names_do_not_match_ordinary_words():
    """Measured 2026-08-05 over a base of 9527 vacancies: 345 false EOR signals.
    «Multiplier» was caught inside «productivity multiplier» and «Talent
    Multiplier» (266 times); «G-P» inside the German «Mentoring-Programm» (79
    times). EOR is the rubric's largest plus (+18), so a false positive here
    costs more than any other."""
    for text in (
        "We embrace AI as a core productivity multiplier across the team.",
        "Talent Multiplier: mentor and coach mid-level engineers.",
        "Einarbeitung inkl. Mentoring-Programm und Chancengleichheit.",
    ):
        v = make_vacancy(title="Senior C# Developer", description_text=text)
        hits = (score.score_vacancy(v, CRITERIA, PROFILE)["score_breakdown"]
                ["remote_location_fit"].get("eor_or_contractor_hits") or [])
        assert hits == [], f"false EOR match on: {text[:40]}"


def test_real_eor_mentions_are_still_detected():
    """The reverse guard to the fix above: real mentions must still be caught."""
    for text in (
        "Payments are issued in partnership with Remote.com for contractors.",
        "We hire internationally through an Employer of Record.",
        "Contract of service through the professional Deel platform.",
    ):
        v = make_vacancy(title="Senior C# Developer", description_text=text)
        hits = (score.score_vacancy(v, CRITERIA, PROFILE)["score_breakdown"]
                ["remote_location_fit"].get("eor_or_contractor_hits") or [])
        assert hits, f"a real EOR signal was missed: {text[:40]}"


def test_worldwide_vocabulary_covers_common_phrasings():
    """Measured 2026-08-05: the old list caught 75 vacancies of 9527 — not
    because there are few such vacancies but because there are many wordings and
    the list held ten. After extending it: 389."""
    for text in (
        "We are hiring anywhere in the world.",
        "Our globally distributed team works across time zones.",
        "This is a remote-first company; work from any location.",
        "We hire regardless of location.",
    ):
        v = make_vacancy(title="Senior C# Developer", description_text=text)
        hits = (score.score_vacancy(v, CRITERIA, PROFILE)["score_breakdown"]
                ["remote_location_fit"].get("worldwide_remote_hits") or [])
        assert hits, f"wording not recognised: {text}"


def test_marketing_global_does_not_count_as_worldwide_hiring():
    """«Global leader» and «global team» are marketing rather than willingness to
    hire from anywhere. Hence every phrase in the list is at least two words."""
    v = make_vacancy(
        title="Senior C# Developer",
        description_text="We are a global leader in payments with a global team of experts.",
    )
    hits = (score.score_vacancy(v, CRITERIA, PROFILE)["score_breakdown"]
            ["remote_location_fit"].get("worldwide_remote_hits") or [])
    assert hits == []


def test_java_title_is_rejected_again():
    """A regression I introduced myself: java, golang and c++ dropped out of the
    title gate while working round YAML escaping, and «Java Engineer» started
    passing again. Caught by the manual checklist 2026-08-05 on an Azumo vacancy."""
    v = make_vacancy(title="Java Engineer - Latin America",
                     description_text="Backend infrastructure, JavaScript on the frontend.")
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any(d.startswith("stack: title names") for d in r["dealbreakers"])


def test_project_manager_is_not_a_developer_role():
    """«Product / Technical Project Manager (100% Remote, Worldwide)» passed: the
    profession list held only «product manager»."""
    v = make_vacancy(title="Product / Technical Project Manager (100% Remote, Worldwide)",
                     description_text="We are redefining the internet architecture. C# and TypeScript.")
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any(d.startswith("role:") for d in r["dealbreakers"])


def test_residency_stated_without_the_word_only():
    """A residency requirement is worded in many ways. Real text:
    «The position is fully remote based in Latin America. We will only be
    considering candidates based in Latin America» — not one phrase from the old
    list appears in it."""
    v = make_vacancy(
        title="Senior C# Developer",
        location_raw="Anywhere in the World",
        description_text=(
            "The position is fully remote based in Latin America. We will only be "
            "considering candidates based in Latin America, as most of our engineers "
            "are there. C# and TypeScript."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any(d.startswith("location:") for d in r["dealbreakers"])


def test_short_legacy_acronyms_do_not_match_ordinary_words():
    """Measured 2026-08-05: «ssis» produced 1057 false matches — it is a substring
    of «ai-assisted» and «assistance» — and pushed a vacancy with no SSIS in it to
    the top of the shortlist. «ssas» was caught inside the Portuguese «nossas».

    Exactly the class of mistake as «LESS» inside «no less than» and «Multiplier»
    inside «productivity multiplier». A short acronym is written out in full."""
    for text in (
        "We use AI as an assisted tooling layer for the team.",
        "Providing assistance to customers and internal teams.",
        "Nossas lojas físicas estão em todo o país.",
    ):
        v = make_vacancy(title="Senior C# Developer", description_text=text)
        hits = (score.score_vacancy(v, CRITERIA, PROFILE)["score_breakdown"]
                ["legacy_enterprise_signal"].get("hits") or [])
        assert "ssis" not in hits and "ssas" not in hits, f"false legacy signal on: {text[:40]}"


def test_real_legacy_stack_is_detected():
    """The reverse guard: nobody writes «we have legacy», but an old stack in the
    requirements is visible — and says more about the work than words about culture."""
    v = make_vacancy(
        title="Senior C# Developer",
        description_text=(
            "Maintaining applications built with WCF services, Web Forms and MVC. "
            "Reporting via Crystal Reports and SSRS. Source control in TFS."
        ),
    )
    hits = (score.score_vacancy(v, CRITERIA, PROFILE)["score_breakdown"]
            ["legacy_enterprise_signal"].get("hits") or [])
    assert len(hits) >= 3, f"the old stack was not recognised: {hits}"


def test_engineering_support_role_counts_as_legacy_signal():
    """Support is a plus for this search: maintaining a working system is exactly
    the character of work being looked for. Customer support meanwhile stays in
    the profession disqualifiers."""
    v = make_vacancy(
        title="Application Support Engineer",
        description_text="Production support for our C# platform, incident resolution, bug fixing.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] != "rejected"
    assert (r["score_breakdown"]["legacy_enterprise_signal"].get("hits") or [])


# --- Personal technology weights and the report's technology list (2026-08-05) --

def test_personal_tech_bonus_prefers_one_known_stack_over_another():
    """stack_fit answers «can the person do this at all» and is the same for
    everyone using the identity. How much more one familiar stack is preferred
    over another is personal experience, so the weights live in the local identity."""
    profile = dict(PROFILE)
    profile["personal_tech_bonus"] = {
        "dotnet": {"points": 12, "keywords": ["c#", "asp.net"]},
        "js_backend": {"points": -10, "keywords": ["node.js", "nestjs"],
                       "unless": ["c#", "asp.net"]},
    }
    dotnet = make_vacancy(title="Senior C# Developer",
                          description_text="Legacy ASP.NET Core maintenance, worldwide remote.")
    node = make_vacancy(title="Senior Backend Engineer",
                        description_text="Node.js and NestJS backend, TypeScript, worldwide remote.")

    r_dotnet = score.score_vacancy(dotnet, CRITERIA, profile)
    r_node = score.score_vacancy(node, CRITERIA, profile)

    assert r_dotnet["score"] > r_node["score"]
    assert r_dotnet["score_breakdown"]["personal_tech_bonus"]["points"] == 12
    assert r_node["score_breakdown"]["personal_tech_bonus"]["points"] == -10
    assert r_node["classification"] != "rejected", "this is a penalty, not a disqualification"


def test_node_mentioned_next_to_dotnet_is_not_penalised():
    """«ASP.NET Core with React and Node in the tooling» is a .NET vacancy with an
    adjacent stack, not a JS backend."""
    profile = dict(PROFILE)
    profile["personal_tech_bonus"] = {
        "js_backend": {"points": -10, "keywords": ["node.js"], "unless": ["asp.net"]},
    }
    v = make_vacancy(title="Fullstack Developer",
                     description_text="ASP.NET Core backend with React and Node.js tooling.")
    assert score.score_vacancy(v, CRITERIA, profile)["score_breakdown"]["personal_tech_bonus"] == {}


def test_tech_group_is_counted_once_regardless_of_spellings():
    """A vacancy listing five ways of writing Node must not collect a fivefold
    penalty."""
    profile = dict(PROFILE)
    profile["personal_tech_bonus"] = {
        "js_backend": {"points": -10, "keywords": ["node.js", "nodejs", "node js", "nestjs"]},
    }
    v = make_vacancy(title="Backend Engineer",
                     description_text="We use Node.js, NodeJS, node js and NestJS across services.")
    assert score.score_vacancy(v, CRITERIA, profile)["score_breakdown"]["personal_tech_bonus"]["points"] == -10


def test_report_lists_expected_technologies_including_unknown_ones():
    """A global requirement, for every identity: seeing an unfamiliar technology
    in the report is no less useful than a familiar one — it tells you at once
    whether the vacancy fits, without opening the link."""
    import report

    v = make_vacancy(
        title="Senior Engineer",
        description_text=(
            "You will work with C#, ASP.NET Core and SQL Server, plus Kafka, "
            "Terraform and a legacy Delphi module."
        ),
    )
    techs = report.expected_technologies(v)
    assert "C#" in techs and "SQL Server" in techs
    assert "Delphi" in techs, "an unfamiliar technology should reach the list too"
    assert "Kafka" in techs and "Terraform" in techs


def test_tech_vocabulary_avoids_short_ambiguous_forms():
    """A rule bought with experience: short generic words are banned from the
    vocabulary — the project has been burned on them five times («LESS» in «no
    less than», «ssis» in «ai-assisted», «java» in «javascript»)."""
    import report

    v = make_vacancy(title="Support Agent",
                     description_text="We assist customers and handle assistance requests daily.")
    techs = report.expected_technologies(v)
    assert techs == [], f"false technologies from ordinary words: {techs}"


def test_keyword_stuffing_block_does_not_grant_a_personal_tech_bonus():
    """An outstaffing company whose «NOT YOUR TECH STACK?» paragraph lists .NET &
    C# in every vacancy was getting the .NET bonus even on pure React. The same
    cut as already stands on stack scoring and on the industry gate."""
    profile = dict(PROFILE)
    profile["personal_tech_bonus"] = {"dotnet": {"points": 12, "keywords": ["c#", ".net"]}}
    v = make_vacancy(
        title="Senior React Developer",
        description_text=(
            "React and TypeScript for our clients.\n"
            "NOT YOUR TECH STACK?\n"
            "We have a variety of projects, so if you have experience in .NET & C#, "
            "Golang, Ruby, we would be happy to connect with you."
        ),
    )
    assert score.score_vacancy(v, CRITERIA, profile)["score_breakdown"]["personal_tech_bonus"] == {}


def test_non_developer_professions_are_rejected_on_merit_not_by_accident():
    """A complaint from the owner, 2026-08-05: the report held Sales Manager,
    Business Partner Analyst, Patient Outreach Specialist, Data Entry. Checking
    showed all of them rejected — but on location (office, geography). Make such
    a vacancy remote and it would pass: the gate never saw what the role was."""
    for title in ("Business Partner Analyst", "Senior Compliance Analyst",
                  "Client Onboarding Manager", "Patient Outreach Specialist",
                  "Video Data Entry Specialist", "Data-Video Generalist"):
        v = make_vacancy(
            title=title,
            location_raw="Anywhere in the World",
            description_text="Worldwide remote role. We work with C# and TypeScript teams.",
        )
        r = score.score_vacancy(v, CRITERIA, PROFILE)
        assert r["classification"] == "rejected", f"passed: {title}"
        assert any(d.startswith("role:") for d in r["dealbreakers"]), (
            f"'{title}' was rejected by accident rather than for its profession: {r['dealbreakers']}"
        )


def test_analytics_engineer_is_not_caught_by_the_analyst_patterns():
    """«Analytics Engineer» is data engineering, which the person can do (Spark
    and Databricks in the CV). The wordings in the profession list are precise
    exactly for that reason: a generic «analyst» would throw away a suitable role."""
    v = make_vacancy(
        title="Analytics Engineer",
        description_text="Build ETL pipelines with Apache Spark on Databricks. Worldwide remote.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert not any(d.startswith("role:") for d in r["dealbreakers"])


def test_ai_training_crowdwork_is_rejected_however_engineering_the_title_looks():
    """Measured 2026-08-05: four of the top nine positions in the shortlist were
    platforms hiring developers to produce training data rather than to build
    software. Their titles are ordinary — «Senior Software Engineer», «Frontend
    Software Engineer». They won for good reason: they list every language at
    once, write «no set schedules» (which reads as low intensity) and quote an
    hourly rate."""
    cases = [
        ("Senior Software Engineer",
         "Open-ended contract with no minimum time or task commitments. "
         "Help advance AI research. We work with C# and TypeScript."),
        ("Frontend Software Engineer",
         "This is not a traditional software engineering role. Instead of building "
         "production applications you will help train and improve next-generation "
         "AI systems. TypeScript and CSS required."),
        ("Open Source Contributor",
         "You will create Reinforcement Learning Environments which test an AI "
         "model's ability to solve software workflows using C# and Python."),
    ]
    for title, description in cases:
        v = make_vacancy(title=title, location_raw="Anywhere in the World",
                         description_text=description + " Worldwide remote.")
        r = score.score_vacancy(v, CRITERIA, PROFILE)
        assert r["classification"] == "rejected", f"passed: {title}"
        assert any("crowdwork" in d for d in r["dealbreakers"]), r["dealbreakers"]


def test_ordinary_company_building_an_ai_product_is_not_caught_as_crowdwork():
    """The crowdwork markers are long precisely because half the market today
    does something with AI, and a short word would throw away normal vacancies."""
    v = make_vacancy(
        title="Senior .NET Developer",
        description_text="We build an AI-powered analytics product in C# and ASP.NET. "
                         "Worldwide remote, permanent position.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert not any("crowdwork" in d for d in r["dealbreakers"]), r["dealbreakers"]


def test_qa_and_mobile_titles_survive_the_engineer_override():
    """A complaint from the owner, 2026-08-05: «Senior QA Engineer — rubbish». The
    word "engineer" in the title lifted the soft profession gate, so testing and
    mobile development sit in the HARD list, which no override lifts — the same
    place devops has been since 2026-07-30."""
    for title in ("Senior QA Engineer", "QA Automation Engineer",
                  "Software Development Engineer in Test",
                  "Senior Mobile Engineer (React Native)",
                  "iOS Developer", "Android Engineer"):
        v = make_vacancy(title=title, location_raw="Anywhere in the World",
                         description_text="Worldwide remote. We use C# and TypeScript.")
        r = score.score_vacancy(v, CRITERIA, PROFILE)
        assert r["classification"] == "rejected", f"passed: {title}"
        assert any(d.startswith("role:") for d in r["dealbreakers"]), r["dealbreakers"]


def test_mobile_product_behind_a_neutral_title_is_rejected():
    """A real finding, 2026-08-05: «Lead Full-stack Developer» at Khibraty — by
    its description an existing React Native application, with all the work
    inside it. The same class as DevOps behind a neutral title."""
    v = make_vacancy(
        title="Lead Full-stack Developer",
        location_raw="Anywhere in the World",
        description_text="Take ownership of an existing mobile app codebase built with "
                         "React Native, shipping to the App Store. Worldwide remote.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any("mobile" in d for d in r["dealbreakers"]), r["dealbreakers"]


def test_a_web_role_mentioning_a_mobile_app_once_is_not_rejected():
    """The gate needs a threshold: a company may have a mobile app among its
    products while the vacancy is about the web."""
    v = make_vacancy(
        title="Senior .NET Developer",
        description_text="Our platform serves web and a companion mobile app. "
                         "You will work on the C# and ASP.NET backend. Worldwide remote.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert not any("mobile" in d for d in r["dealbreakers"]), r["dealbreakers"]


def test_matching_the_core_stack_beats_listing_many_familiar_technologies():
    """Measured 2026-08-05: a vacancy in pure C#/ASP.NET scored 7 for its stack,
    while a list of TypeScript/JavaScript/React/HTML/CSS scored 14. A point per
    match rewards the length of the list rather than the fit to the stack."""
    core = score._score_stack_fit(
        score.common.normalize_for_matching("Senior developer. C# and ASP.NET Core, Entity Framework."),
        CRITERIA, PROFILE)[0]
    breadth = score._score_stack_fit(
        score.common.normalize_for_matching(
            "TypeScript, JavaScript, React, HTML, CSS, Redux, GraphQL, Docker."),
        CRITERIA, PROFILE)[0]
    assert core > breadth, f"the core {core} did not beat the list {breadth}"


def test_reputation_red_flags_cost_points_not_only_a_review_flag():
    """A real case, 2026-08-05: a platform whose reviews say «late payments» and
    «unpredictable work availability» collected +14 for a 3.5 rating and 4.0
    work-life balance and came FIRST in the shortlist. For a contractor, late
    payment is not a nuance but the substance of the deal."""
    clean = make_vacancy(title="Senior .NET Developer")
    clean["_company_reputation"] = {"overall_rating": 3.5, "work_life_balance": 4.0}
    flagged = make_vacancy(title="Senior .NET Developer")
    flagged["_company_reputation"] = {
        "overall_rating": 3.5, "work_life_balance": 4.0,
        "red_flags": ["late payments", "unpredictable work availability"],
    }
    clean_pts = score._score_company_reputation(clean, CRITERIA)[0]
    flagged_pts = score._score_company_reputation(flagged, CRITERIA)[0]
    assert flagged_pts < clean_pts, f"{flagged_pts} is not less than {clean_pts}"


def test_dotnet_in_the_title_is_recognised_as_the_core_stack():
    """Measured 2026-08-05: 754 vacancies with .NET in the title, ALL rejected,
    325 of them with the wording «not a .NET/JS role». The cause: a bare ".NET"
    was in no list at all — every key was longer (".NET Core", "ASP.NET", "C#") —
    and the title «Senior .NET Backend Developer» matched none of them."""
    for title in ("Senior .NET Backend Developer", ".Net Backend Engineer",
                  "Dotnet Developer", "Senior .NET Engineer"):
        v = make_vacancy(title=title, location_raw="Anywhere in the World",
                         description_text="Worldwide remote contract position.")
        r = score.score_vacancy(v, CRITERIA, PROFILE)
        assert not any(d.startswith("stack:") for d in r["dealbreakers"]), \
            f"'{title}' rejected as not-dotnet: {r['dealbreakers']}"
        assert r["score_breakdown"]["stack_fit"]["core_hits"], title


def test_a_dot_net_email_domain_is_not_a_dotnet_vacancy():
    """Why a regex rather than a substring: ".net" is in every mail domain.
    A real record from Hacker News that arrived as a vacancy title:
    "Please email me ... (firstname)@harnly.net"."""
    v = make_vacancy(
        title="Please email me so I know which role (firstname)@harnly.net",
        description_text="Reach out about roles at our company.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert not r["score_breakdown"]["stack_fit"]["core_hits"], \
        "a mail domain was counted as .NET"


def test_explicit_only_wording_is_still_a_hard_rejection():
    """A distinction worth keeping explicit (2026-08-05).

    A location field of "Canada" is the board's guess: the vacancy may well be
    open to a contractor outside it. The wording "Canada only" is the employer's
    own words, and it is unambiguous. The first lands in national_market and
    stays in view; the second is rejected outright."""
    guess = make_vacancy(location_raw="Canada",
                         description_text="C# ASP.NET SQL Server developer role.")
    stated = make_vacancy(location_raw="Canada only",
                          description_text="C# ASP.NET SQL Server developer role.")
    # Revised 2026-08-05: the board's guess («Canada») no longer means anything,
    # while the employer's word («Canada only») still means refusal. The
    # difference between a guess and a statement is all that matters here.
    assert score.score_vacancy(guess, CRITERIA, PROFILE)["classification"] != "rejected"
    assert score.score_vacancy(stated, CRITERIA, PROFILE)["classification"] == "rejected"


def test_email_and_url_are_removed_before_technology_search():
    """A real record from Hacker News that arrived as a vacancy title:
    "Please email me ... (firstname)@harnly.net". Its ".net" used to count as a
    mention of the technology. It is removed by stripping contacts rather than by
    banning ".net" — otherwise "asp.net" would go along with the mail."""
    v = make_vacancy(
        title="Please email me so I know which role (firstname)@harnly.net",
        description_text="Reach out at jobs@example.net or https://careers.example.net",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert not r["score_breakdown"]["stack_fit"]["core_hits"]

    real = make_vacancy(title="Senior ASP.NET Developer",
                        description_text="ASP.NET and .NET Core work. Contact jobs@example.net")
    hits = score.score_vacancy(real, CRITERIA, PROFILE)["score_breakdown"]["stack_fit"]["core_hits"]
    assert "ASP.NET" in hits and ".NET Core" in hits


def test_dotnet_pattern_lives_in_the_global_vocabulary_not_in_identities():
    """How a technology is written is shared knowledge (CLAUDE.md §13). The
    identity names ".NET" by its canonical name; config/ holds the regex."""
    import glob
    patterns = score.tech_matching_patterns()
    assert ".NET" in patterns and patterns[".NET"].get("substring_unsafe")
    for path in glob.glob("identities/*/*.yaml"):
        text = open(path, encoding="utf-8").read()
        assert "core_patterns" not in text, path
        assert "primary_language_patterns" not in text, path


def test_red_flag_weight_comes_from_the_shared_catalogue():
    """A free-text flag from reviews belongs to a category in the shared
    catalogue, and its weight comes from there rather than one weight for all."""
    assert score.classify_red_flag("late payments") == "late_payment"
    assert score.classify_red_flag("unpredictable work availability") == "unstable_workload"
    assert score.classify_red_flag("somethingorother") is None

    points, detail = score._score_red_flags(["late payments"], {})
    assert points < 0 and detail[0]["source"] == "catalogue"


def test_local_override_can_soften_a_red_flag_and_even_flip_its_sign():
    """The owner's question, 2026-08-05: «globally this is a red flag, but locally
    we override it as normal or even as a priority — will that work?»

    It will, and a change of sign is a legitimate case rather than a typo:
    «unpredictable workload» is, for one person, the risk of being left without
    money, and for another exactly what is wanted, because they will not be loaded."""
    flags = ["late payments", "unpredictable work availability"]
    plain = score._score_red_flags(flags, {})[0]
    softened = score._score_red_flags(
        flags, {"company_red_flag_severity": {"late_payment": -4,
                                              "unstable_workload": 6}})[0]
    assert plain < 0
    assert softened > plain
    per_flag = {d["category"]: d for d in score._score_red_flags(
        flags, {"company_red_flag_severity": {"unstable_workload": 6}})[1]}
    assert per_flag["unstable_workload"]["points"] == 6
    assert per_flag["unstable_workload"]["source"] == "override"
    # A category that was not overridden keeps the catalogue's weight.
    assert per_flag["late_payment"]["source"] == "catalogue"


def test_a_string_where_a_weights_dict_is_expected_does_not_break_scoring():
    """Configuration can hold a string where scoring expects a dict — a typo, or
    a leftover from the retired `local` sentinel. Falling over on it is not
    allowed: one bad key must not take down a run over 11000 vacancies."""
    points, _ = score._score_red_flags(["late payments"],
                                       {"company_red_flag_severity": "local"})
    assert points < 0


def test_an_override_cannot_rescue_a_vacancy_killed_by_a_gate():
    """A boundary of the mechanism worth keeping explicit: overrides change the
    SCORE, while gates work independently of the score. No personal bonus makes
    an unpassable vacancy passable — otherwise personal settings would start
    returning to the shortlist what was filtered out on the merits."""
    v = make_vacancy(title="Senior QA Engineer", location_raw="Anywhere in the World",
                     description_text="Worldwide remote. C# and TypeScript.")
    v["_company_reputation"] = {"overall_rating": 4.8, "work_life_balance": 5.0}
    generous = dict(PROFILE)
    generous["personal_market_bonus"] = {"Anywhere": {"points": 100}}
    r = score.score_vacancy(v, CRITERIA, generous)
    assert r["classification"] == "rejected"


def test_an_unfamiliar_compensation_shape_does_not_crash_the_run():
    """Found by emulating onboarding in a fresh clone, 2026-08-05.

    Scoring demanded the key annual_parttime_usd and died with a KeyError
    mid-run if the profile described pay differently. An agent writing down a
    person's answer «5-8 thousand a month» naturally writes monthly_min/
    monthly_target — and the whole run collapses, with the cause visible only
    in a traceback.
    """
    profile = json.loads(json.dumps(PROFILE))
    profile["goal"]["target_compensation"] = {"currency": "USD",
                                              "monthly_min": 5000,
                                              "monthly_target": 8000}
    v = make_vacancy(title="Senior .NET Developer",
                     description_text="C# and ASP.NET role. $120,000 - $150,000 per year.")
    result = score.score_vacancy(v, CRITERIA, profile)
    assert isinstance(result["score"], int)


def test_a_filled_compensation_range_still_penalises_a_low_offer():
    """Tolerating the shape must not mean the comparison stopped working."""
    profile = json.loads(json.dumps(PROFILE))
    profile["goal"]["target_compensation"] = {"annual_parttime_usd": [60000, 96000]}
    low = make_vacancy(title="Senior .NET Developer",
                       description_text="C# and ASP.NET. Salary $20,000 - $25,000 per year.")
    fit = make_vacancy(title="Senior .NET Developer",
                       description_text="C# and ASP.NET. Salary $70,000 - $90,000 per year.")
    low_points = score.score_vacancy(low, CRITERIA, profile)["score_breakdown"]["compensation_signal"]["points"]
    fit_points = score.score_vacancy(fit, CRITERIA, profile)["score_breakdown"]["compensation_signal"]["points"]
    assert low_points < fit_points


def test_a_posting_in_an_unreadable_script_is_rejected():
    """Found by reading the shortlist, 2026-08-05: a vacancy in Hebrew stood 13th.
    The frequent-word lists existed for five European languages and could not
    catch another script in principle — whereas an alphabet is visible at once."""
    v = make_vacancy(
        title="מפתח/ת C#/.NET",
        location_raw="Anywhere in the World",
        description_text=(
            "אנחנו מחפשים מפתח תוכנה לצוות הפיתוח שלנו לפיתוח תחזוקה ושדרוג "
            "מערכות תוכנה מתקדמות הפועלות מול חומרה בתפקיד תעבוד בשיתוף פעולה "
            "הדוק עם צוותי הנדסה ופיתוח C# .NET"
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert any("language" in d for d in r["dealbreakers"]), r["dealbreakers"]


def test_a_few_foreign_words_do_not_disqualify_an_english_posting():
    """The threshold is proportional: an Israeli company may name itself in Hebrew
    inside an English posting, and that is no reason to throw the posting away."""
    v = make_vacancy(
        title="Senior .NET Developer",
        description_text=(
            "We are סנטריקל, a company based in Tel Aviv. We build enterprise "
            "software in C# and ASP.NET Core with SQL Server. The team works "
            "remotely and asynchronously across several time zones, and we are "
            "looking for an experienced backend engineer to join us."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert not any("language" in d for d in r["dealbreakers"]), r["dealbreakers"]


def test_hybrid_and_office_wording_is_a_dealbreaker():
    """Found 2026-08-05: eight vacancies saying «Hybrid Position», «hybrid working
    model» and «(WFO)» stood in the shortlist. The list contained «hybrid
    required» — which almost nobody writes."""
    for wording in ("Category: Full time, Hybrid Position",
                    "We follow a hybrid working model",
                    "Location - Dubai (WFO)",
                    "This is an office-based role"):
        v = make_vacancy(
            title="Senior .NET Developer",
            location_raw="Anywhere in the World",
            description_text=f"C# and ASP.NET Core role. {wording}.",
        )
        r = score.score_vacancy(v, CRITERIA, PROFILE)
        assert r["classification"] == "rejected", f"passed: {wording}"


def test_the_crowdwork_gate_catches_a_reworded_version_of_the_same_platform():
    """The same platform came back under a different name and with rewritten text.
    A gate that catches one edition catches an edition, not a genre."""
    v = make_vacancy(
        title="Freelance Agent Evaluation Engineer",
        location_raw="Anywhere in the World",
        description_text=(
            "Mindrift connects specialists with project-based AI opportunities "
            "for leading tech companies, focused on testing, evaluating, and "
            "improving AI systems. You will work with C# and Python."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert any("crowdwork" in d for d in r["dealbreakers"]), r["dealbreakers"]
