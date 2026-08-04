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
        # По умолчанию тестовая вакансия - подтверждённо remote (флаг от
        # источника), чтобы тесты про другие оси (сложность роли, релевантность
        # роли, стек и т.п.) не спотыкались об гейт "не подтверждено как
        # remote". Тесты про сам location/remote гейт переопределяют явно.
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
    # Подтверждено владельцем явно (2026-07-30): жёсткое "US only" без
    # worldwide/EOR-сигнала - dealbreaker, а не просто ниже приоритет,
    # ровно как и любой другой региональный restrictive-сигнал.
    assert r_us["classification"] == "rejected"


def test_restrictive_region_latam_is_rejected():
    # Реальный найденный баг (2026-07-30): HN-вакансия "remote LATAM"
    # получила приличный score, хотя физически недоступна человеку из
    # Грузии.
    v = make_vacancy(
        title="Full-stack Developer",
        description_text="C# .NET SQL Server. This is a remote LATAM position, Latin America only.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any("latam" in d.lower() or "latin america" in d.lower() for d in r["dealbreakers"])


def test_restrictive_region_overridden_by_worldwide_signal():
    # Если ЕСТЬ явный worldwide/EOR сигнал - одиночное упоминание
    # региональной фразы не должно рубить вакансию (возможно, это просто
    # один из нескольких req'ов у гибкой компании).
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
    # Исправленная ошибка первой версии (2026-07-30): "EU Remote"/"remote
    # Europe" в реальной вакансии означает требование резидентства В ЕС -
    # это dealbreaker (как "US Remote"), а не плюс, как ошибочно считалось
    # раньше.
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
    """{'georgia': 'ambiguous'|'meaning_a'|'meaning_b'} из score_breakdown."""
    hits = result["score_breakdown"]["remote_location_fit"].get("ambiguous_place_hits") or []
    return {h["name"]: h["verdict"] for h in hits}


def test_ambiguous_place_flags_manual_review():
    """Ни один контекст не сработал — непонятно, о каком месте речь."""
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
    """Механизм должен быть data-driven, а не заточен под одну ловушку.

    Cambridge (Англия vs Массачусетс) — та же проблема для другого человека.
    Правило описано в конфиге фикстуры, кода под него нет.
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
    """Строка отказа по стеку раньше содержала захардкоженный '.NET/JS'."""
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
    # Много совпадений не должно давать бесконечно растущий балл
    all_keywords = " ".join(score.load_profile()["tech_stack"]["strong"])
    v = make_vacancy(description_text=all_keywords)
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    cap = CRITERIA["stack_fit"]["cap"]
    assert r["score_breakdown"]["stack_fit"]["points"] <= cap


def test_stack_fit_core_technology_weighs_more_than_familiar():
    # Подтверждено владельцем явно (2026-07-30): технологии, с которыми
    # реально работал чаще (core, встречаются в 6-8 из 8 ролей за 7 лет),
    # должны давать больше очков, чем те, с которыми пересекался мало
    # (familiar, 1-2 роли).
    v_core = make_vacancy(description_text="C# ASP.NET SQL Server")  # 3 core-слова
    v_familiar = make_vacancy(description_text="MongoDB SOAP XSLT")  # 3 familiar-слова
    r_core = score.score_vacancy(v_core, CRITERIA, PROFILE)
    r_familiar = score.score_vacancy(v_familiar, CRITERIA, PROFILE)
    assert (
        r_core["score_breakdown"]["stack_fit"]["points"]
        > r_familiar["score_breakdown"]["stack_fit"]["points"]
    )
    assert len(r_core["score_breakdown"]["stack_fit"]["core_hits"]) == 3


def test_webforms_not_claimed_as_personal_skill():
    # WebForms/VB.NET убраны из tech_stack (нет подтверждения в CV) -
    # упоминание одного только WebForms не должно засчитываться в stack_fit,
    # хотя остаётся сигналом легаси в legacy_enterprise_signal.
    v = make_vacancy(title="Application Support", description_text="Maintaining a legacy WebForms VB.NET application.")
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["score_breakdown"]["stack_fit"]["points"] == 0
    assert len(r["score_breakdown"]["legacy_enterprise_signal"]["hits"]) > 0


def test_role_complexity_gate_triggers_on_title_principal_scientist():
    # Реальный найденный случай (2026-07-30): "Principal Machine Learning
    # Scientist" - явно не простая роль, даже если в описании легаси-слова.
    v = make_vacancy(
        title="Principal Machine Learning Scientist (Experiences)",
        description_text="Enterprise banking insurance client, legacy systems, SQL Server, C#.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "low_priority"
    assert r["score_breakdown"]["role_complexity_signal"]["gate_triggered"] is True
    assert r["score_breakdown"]["role_complexity_signal"]["title_hits"]


def test_role_complexity_gate_triggers_on_title_agentic():
    # Реальный найденный случай: "Staff Software Engineer, Agentic Platform"
    # в банке - легаси/enterprise слова в описании компании не делают
    # AI-платформенную роль простой.
    v = make_vacancy(
        title="Staff Software Engineer, Agentic Platform",
        description_text="We serve banking and insurance clients. C# .NET SQL Server Azure.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "low_priority"
    assert r["score_breakdown"]["role_complexity_signal"]["gate_triggered"] is True


def test_role_complexity_gate_triggers_on_title_llm_engineer():
    # Реальный найденный случай (2026-07-30): "LLM Engineer Freelancer" -
    # явно AI-роль ("design, build, and integrate practical AI features"),
    # не поймана первой версией гейта (только "agentic"/"Principal
    # Scientist"-паттерны).
    v = make_vacancy(
        title="LLM Engineer Freelancer",
        description_text="Design, build, and integrate practical AI features. C# .NET JavaScript.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "low_priority"
    assert r["score_breakdown"]["role_complexity_signal"]["gate_triggered"] is True


def test_role_complexity_gate_needs_multiple_description_hits_not_just_one():
    # Одно случайное модное словечко в бойлерплейте не должно гейтить
    # нормальную легаси-роль - нужен порог (threshold_hits) для description.
    v = make_vacancy(
        title="Senior .NET Developer",
        description_text=(
            "Maintain legacy enterprise banking system, C# ASP.NET SQL Server. "
            "We use cutting-edge monitoring tools for uptime."  # только 1 red-flag слово
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
    # Явная ЗП в тексте вакансии всегда выигрывает у внешней оценки.
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
    # Регрессия: "$6,000/month" не должен трактоваться как годовая ставка
    # (что дало бы огромный штраф "below annual target").
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
    # Явно подтверждённый владельцем приоритет (2026-07-30): гарантированно
    # низкая нагрузка важнее более высокой оплаты. Защита от случайного
    # "выравнивания" весов в будущем.
    assert CRITERIA["weights"]["low_intensity_signal"] >= 2 * CRITERIA["weights"]["compensation_signal"]
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


def test_structured_location_country_name_is_rejected():
    # Реальный найденный баг (2026-07-30): источники отдают гео-ограничение
    # СТРУКТУРНЫМ полем (Jobicy jobGeo="USA", Himalayas
    # locationRestrictions=["Canada"], Remotive
    # candidate_required_location="Brazil"), а проверялся только текст
    # описания. ~20 из 32 кандидатов оказались недоступны по гео.
    for loc in ["USA", "Canada only", "Brazil", "Costa Rica", "Texas", "Virginia"]:
        v = make_vacancy(
            location_raw=loc,
            description_text="C# ASP.NET SQL Server developer role.",
        )
        r = score.score_vacancy(v, CRITERIA, PROFILE)
        assert r["classification"] == "rejected", f"{loc} должна отклоняться"
        assert any("source restricts hiring" in d for d in r["dealbreakers"]), loc


def test_structured_location_worldwide_markers_pass():
    for loc in ["Anywhere in the World", "Anywhere", "100% Remote (Global)", "Worldwide"]:
        v = make_vacancy(
            location_raw=loc,
            description_text="C# ASP.NET SQL Server developer role.",
        )
        r = score.score_vacancy(v, CRITERIA, PROFILE)
        assert r["classification"] != "rejected", f"{loc} НЕ должна отклоняться"


def test_structured_location_remote_without_country_is_not_a_restriction():
    # Реальный найденный баг (2026-07-31, после подключения ATS):
    # Greenhouse/Ashby пишут "Remote job", GitLab — "Distributed"; это
    # указание формата работы, а не страны, и резать по нему нельзя.
    for loc in ["Remote job", "Distributed", "Remote", "Work from home", "N/A"]:
        v = make_vacancy(
            location_raw=loc,
            description_text="C# ASP.NET SQL Server developer role.",
        )
        r = score.score_vacancy(v, CRITERIA, PROFILE)
        assert not any("source restricts hiring" in d for d in r["dealbreakers"]), loc


def test_structured_location_continent_list_treated_as_worldwide():
    # Remotive отдаёт "Americas, Europe, Asia, Africa, Oceania" — слова
    # "worldwide" нет, но по смыслу это весь мир.
    v = make_vacancy(
        location_raw="Americas, Europe, Asia, Africa, Oceania",
        description_text="C# ASP.NET SQL Server developer role.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] != "rejected"
    assert r["score_breakdown"]["remote_location_fit"]["structured_location"]["verdict"] == "worldwide_by_continents"


def test_structured_location_not_overridden_by_marketing_worldwide_phrase():
    # Реальный найденный баг (2026-07-30): Prima (страховая, London)
    # публиковала 5 вакансий с location="London", а в описании бенефитов
    # была фраза "work from anywhere" (типичное "работай откуда хочешь N
    # недель в году") — это снимало гео-ограничение. Структурное поле
    # площадки авторитетнее маркетинговой фразы в тексте.
    v = make_vacancy(
        location_raw="London",
        description_text=(
            "C# TypeScript React developer role at our insurance company. "
            "Benefits include the ability to work from anywhere for a few weeks a year."
        ),
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any("source restricts hiring" in d for d in r["dealbreakers"])


def test_ml_engineer_titles_are_gated_as_complex():
    for title in ["Senior Machine Learning Engineer", "ML Engineer", "Data Scientist"]:
        v = make_vacancy(
            title=title,
            location_raw="Anywhere in the World",
            description_text="C# TypeScript React SQL Server enterprise legacy.",
        )
        r = score.score_vacancy(v, CRITERIA, PROFILE)
        assert r["classification"] == "low_priority", f"{title} должна гейтиться как сложная"
        assert r["score_breakdown"]["role_complexity_signal"]["gate_triggered"] is True


def test_structured_location_not_overridden_by_eor_mention():
    # Реальный найденный баг (2026-07-30): LawnStarter публикует вакансии с
    # location="Brazil" и упоминает Multiplier (EOR) — раньше упоминание EOR
    # снимало гео-ограничение и 11 латиноамериканских вакансий попадали в
    # кандидаты. EOR говорит КАК оформляют, а не ГДЕ нанимают.
    v = make_vacancy(
        location_raw="Brazil",
        description_text="C# TypeScript React role. We hire via Multiplier as a contractor.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any("source restricts hiring" in d for d in r["dealbreakers"])


def test_remote_only_source_is_trusted_without_remote_word():
    # Реальный найденный баг (2026-07-30): вакансии с remote-only площадок
    # (WWR/RemoteOK/Remotive/Jobicy/Himalayas) отклонялись как "не
    # подтверждено как remote" только потому, что в тексте не встретилось
    # слово "remote" — чистый ложноотрицательный результат.
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
    # Реальная находка (2026-07-30): вакансии Canonical (embedded/Linux
    # systems) проходили гейт только по слову "Docker". Общие
    # инфраструктурные слова не доказывают, что роль подходит .NET/JS
    # разработчику - нужен настоящий язык/фреймворк.
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
    # Реальные находки (2026-07-30): "GTM Operations Process Architect" @
    # Stripe, "Partner Solutions Architect" @ Nebius, "Senior Manager,
    # DevOps", "Senior Developer Advocate" @ Datadog - все содержат
    # architect/engineer/developer в заголовке, из-за чего обычный
    # developer-override снимал гейт.
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
        assert r["classification"] == "rejected", f"{title} должна отклоняться"
        assert any(d.startswith("role:") for d in r["dealbreakers"]), title


def test_devops_and_infrastructure_roles_are_rejected():
    # Подтверждено владельцем явно (2026-07-30): "выкинь девопсов, это не
    # моя вакансия". Владелец - прикладной .NET/JS разработчик, а не
    # инженер эксплуатации. Слово "engineer" в заголовке не должно
    # снимать этот гейт.
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
        assert r["classification"] == "rejected", f"{title} должна отклоняться"
        assert any(d.startswith("role:") for d in r["dealbreakers"]), title


def test_normal_developer_titles_still_pass():
    # Защита от перекоса в другую сторону: обычные инженерные заголовки
    # НЕ должны попадать под hard_wrong_profession.
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
        assert r["classification"] != "rejected", f"{title} НЕ должна отклоняться"


def test_thresholds_let_plain_passing_vacancy_into_report():
    # Ключевое изменение 2026-07-30: обычная нормальная remote-вакансия,
    # прошедшая ВСЕ жёсткие гейты, но без слов "legacy"/"part-time"/вилки
    # набирает всего ~15 баллов. При старом пороге long_shot=25 она вообще
    # не показывалась владельцу - из 966 вакансий показывалась 1.
    v = make_vacancy(
        title="Senior Software Engineer",
        location_raw="Anywhere in the World",
        description_text="We are looking for a TypeScript and React developer to join our team.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] in ("long_shot", "worth_a_look", "hot_lead"), (
        "вакансия, прошедшая все гейты, обязана попадать в отчёт, "
        f"а не в low_priority (score={r['score']})"
    )


def test_company_reputation_no_data_is_neutral():
    v = make_vacancy(location_raw="Anywhere in the World",
                     description_text="C# TypeScript React developer role.")
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    bd = r["score_breakdown"]["company_reputation_signal"]
    assert bd["has_data"] is False
    # Как и с зарплатой: "нет данных" != "плохо".
    baseline = r["score"]

    v2 = dict(v, _company_reputation={"overall_rating": 4.2, "work_life_balance": 4.4,
                                      "source": "Glassdoor"})
    r2 = score.score_vacancy(v2, CRITERIA, PROFILE)
    assert r2["score"] > baseline


def test_good_work_life_balance_outweighs_mediocre_overall_rating():
    # Для этого проекта WLB важнее общего рейтинга: компания может быть
    # "хорошей" за счёт зарплат и карьеры, но выжимать людей.
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
    # Реальный найденный баг (2026-07-30, найдено ручным чек-листом): голое
    # "eor" ложно совпадало как подстрока внутри "theoretical"/"theory" и
    # обходило гейт "не подтверждено как remote" для вакансии constellr
    # (Hybrid, Munich, remote=False, ни слова "remote" в тексте).
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
    # Реальный найденный случай (2026-07-30, найдено ручным чек-листом):
    # "Staff Software Engineer (AI CICD)" @ Chainguard упоминал "agentic AI
    # foundation" один раз в описании - недостаточно для порога threshold_hits
    # (нужно 2 расплывчатых слова), но "agentic" само по себе однозначно и
    # должно гейтить с одного упоминания, даже если оно не в заголовке.
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
    # Подтверждено владельцем явно (2026-07-30): "мне нужны ТОЛЬКО РЕМОУТ
    # позиции" - реальный найденный случай, вакансия Rangeview (явно
    # ONSITE, город "El Segundo, CA") не содержала слова "remote" вообще
    # нигде и раньше получала мягкий needs_manual_review вместо отказа.
    # Без ЛЮБОГО remote-сигнала (ни флага источника, ни слова в тексте) -
    # dealbreaker, а не "неизвестно, но пусть будет".
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
    # Стек-релевантная, легаси-энтерпрайзная вакансия, которая ГДЕ-ТО
    # упоминает "remote" (так что это не dealbreaker "не подтверждено как
    # remote"), но без явного worldwide/US-only/EOR/region сигнала - это
    # ровно тот случай, где стоит попросить агента перепроверить руками.
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
    # Полностью нерелевантная вакансия без единого технического слова - неважно,
    # что локация тоже неясна, никто не должен тратить время на её перепроверку.
    v = make_vacancy(
        title="Groundman II",
        remote=None,
        location_raw="",
        description_text="Manual labor, utility line maintenance. Benefits include health insurance.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    # Подтверждено владельцем явно (2026-07-30): "0% шанс попасть в выдачу"
    # для того, что не связано с реальными навыками - это dealbreaker
    # (rejected), не просто низкий приоритет.
    assert r["classification"] == "rejected"
    assert any(d.startswith("stack:") for d in r["dealbreakers"])
    assert r["needs_manual_review"] is False


def test_stack_gate_rejects_irrelevant_boilerplate_job():
    # Реальный кейс, найденный на живых данных: вакансия без единого совпадения
    # по стеку (score_breakdown.stack_fit.points == 0), но с кучей generic
    # enterprise/legacy-слов из бойлерплейта ("we serve banking, insurance,
    # government and healthcare clients") набирала high-ish score и
    # проваливалась в long_shot/needs_review, хотя не имеет отношения к .NET.
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
    # Реальный найденный случай (2026-07-30, найдено ручным чек-листом):
    # "Web Publisher Half time US Timezone" - работа с CMS/Figma/контентом,
    # не программирование, но прошла фильтр только за упоминание HTML/CSS
    # (слишком общий сигнал стека сам по себе для web-adjacent ролей).
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
    # Реальный найденный баг (2026-07-30): "LESS" (CSS-препроцессор,
    # familiar-уровень) ложно совпадал с обычным английским словом "less" в
    # финансовой вакансии ("CFO Controller"), и одного familiar-совпадения
    # хватало, чтобы пройти гейт. Теперь familiar-хита одного недостаточно -
    # нужен core или strong.
    v = make_vacancy(
        title="CFO Controller",
        description_text="Support ownership with financial modeling, no less than 5 years experience required.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["score_breakdown"]["stack_fit"]["familiar_hits"] == []  # "LESS" убран из списка
    assert r["classification"] == "rejected"


def test_tech_agnostic_override_bypasses_stack_gate():
    v = make_vacancy(
        title="Engineer",
        description_text="We are a tech agnostic team - any programming language welcome. Fully remote worldwide.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] != "rejected"


def test_role_relevance_gate_rejects_cfo_controller():
    # Реальный найденный баг (2026-07-30): "CFO Controller" @ FractionalFinders
    # получила score 60 и попала в worth_a_look.
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
    # "Developer"/"Engineer" в заголовке снимает МЯГКИЙ гейт профессии
    # (в отличие от жёсткого списка - менеджмент/продажи/devops, см.
    # test_devops_and_infrastructure_roles_are_rejected). Здесь: слово
    # "Support" само по себе подозрительно, но "Engineer" рядом означает
    # инженера поддержки продукта, а не саппорт-консультанта.
    v = make_vacancy(
        title="Application Support Engineer",
        description_text="C# .NET Core ASP.NET SQL Server, maintaining legacy enterprise systems.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] != "rejected"
    assert r["score_breakdown"]["role_relevance_signal"]["developer_override_hits"]


def test_language_requirement_german_explicit_is_dealbreaker():
    # Реальный найденный баг (2026-07-30): "Web-Administration / Webmaster
    # TYPO3" требовал "sehr gute Deutschkenntnisse" - владелец знает только
    # русский и английский.
    v = make_vacancy(
        title="Web Developer",
        description_text="C# .NET ASP.NET role. Requires sehr gute Deutschkenntnisse for client calls.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any(d.startswith("language:") for d in r["dealbreakers"])


def test_language_requirement_german_market_heuristic_rejects_german_language_posting():
    # Вакансия целиком на немецком, без явной англоязычной фразы про язык -
    # эвристика по частым немецким словам/"m/w/d" должна поймать это тоже.
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
    # Подтверждено владельцем явно (2026-07-30): "Я ДОТНЕТЧИК, МЕНЯ НА ДЖАВА
    # ПОЗИЦИЮ НЕ ВОЗЬМУТ" - чистая Java web-роль без .NET/JS не должна
    # проходить гейт релевантности стека, даже с настоящим developer-заголовком.
    v = make_vacancy(
        title="Java Developer",
        description_text="Backend Java development, Spring Boot, REST APIs, enterprise banking client.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any(d.startswith("stack:") for d in r["dealbreakers"])


def test_java_scala_for_data_pipelines_is_accepted():
    # Подтверждено владельцем явно (2026-07-30): "Scala для дата пайплайнов -
    # оставь... Джава дата пайплайны тоже норм" - Java/Scala + контекст
    # дата-инженерии (Spark/Databricks/ETL) - желанный вариант, в отличие от
    # чистой Java web-роли.
    v = make_vacancy(
        title="Data Engineer",
        description_text="Build ETL pipelines with Scala and Apache Spark on Databricks. Legacy data warehouse migration.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] != "rejected"
    assert r["score_breakdown"]["stack_fit"]["data_pipeline_exception_applied"] is True


@pytest.mark.parametrize("classification_key", ["hot_lead", "worth_a_look", "long_shot", "low_priority", "rejected"])
def test_all_classification_buckets_are_reachable(classification_key):
    # Просто проверяем, что константа известна скорингу (защита от опечаток в criteria.yaml)
    thresholds = CRITERIA["classification_thresholds"]
    valid_keys = set(thresholds.keys()) | {"low_priority", "rejected"}
    assert classification_key in valid_keys


# ============================================================================
# Баги, найденные ручным чек-листом 2026-07-31 на реальной выдаче.
# Каждый тест назван по своему реальному источнику: если фильтр когда-нибудь
# сломают обратно, из падения будет видно, какой именно случай он защищал.
# ============================================================================


def test_millions_paid_out_are_not_read_as_an_hourly_rate():
    # Lemon.io: "We've already paid out over $11M to our engineers". Отчёт
    # показывал владельцу "ЗП: $11/час" — дезинформация в поле, по которому
    # принимается решение откликаться.
    v = make_vacancy(
        description_text="We've already paid out over $11M to our engineers. Great C# projects.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    comp = r["score_breakdown"]["compensation_signal"]
    assert comp["explicit"] is False, "сумма выплат площадки — не зарплата вакансии"
    assert not comp.get("hourly_amounts_found")


def test_real_hourly_rate_is_still_recognised():
    # Обратная сторона фикса выше: настоящая ставка обязана распознаваться.
    v = make_vacancy(description_text="C# contract role, up to $60 per hour.")
    comp = score.score_vacancy(v, CRITERIA, PROFILE)["score_breakdown"]["compensation_signal"]
    assert comp["explicit"] is True
    assert 60.0 in comp["hourly_amounts_found"]


def test_employer_header_us_remote_beats_boards_worldwide_field():
    # Stripe: region от WWR = "Anywhere in the World", а первая строка
    # описания — "Headquarters: US Remote". Вакансия была в hot_lead.
    v = make_vacancy(
        title="Software Engineer",
        location_raw="Anywhere in the World",
        description_text="Headquarters: US Remote\nWe build payments infrastructure with TypeScript.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] == "rejected"
    assert any("header" in d for d in r["dealbreakers"])


def test_employer_header_with_plain_country_is_not_a_restriction():
    # Mindrift: "Headquarters: Saudi Arabia" — это адрес компании, а не
    # заявление о том, где она нанимает. Отсекать по нему нельзя.
    v = make_vacancy(
        location_raw="Anywhere in the World",
        description_text="Headquarters: Saudi Arabia\nURL: http://example.ai\nFreelance C# work, worldwide.",
    )
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["classification"] != "rejected"


def test_kubernetes_platform_role_with_neutral_title_is_rejected():
    # Airtable "Software Engineer, Compute (8+ YOE)": заголовок нейтральный,
    # тело — Kubernetes-платформа. Владелец исключил DevOps явно.
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
    # Порог обязан пропускать обычную прикладную вакансию: пара
    # инфраструктурных слов есть почти в каждой.
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
    # Lemon.io "Senior Graphic Designer" получал core_hits ["C#", "Angular"]
    # из рекламного абзаца, перечисляющего ~60 технологий.
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
    # Дизайн — не программирование, даже если стек в тексте настоящий.
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
    # Владелец в UTC+4, CET(UTC+1)+3 = UTC+4 — попадает.
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
    # То же правило с другим поясом: PST +/- 2 = UTC-10..-6, владелец в UTC+4.
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
    # Скрыть настоящую вакансию хуже, чем показать сомнительную.
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
    # Work and Study Travel: объявление целиком на испанском, оплата
    # 16 000 MXN/мес. Прошло фильтр, потому что эвристика "объявление на
    # чужом языке" существовала только для немецкого.
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
    # Обратная страховка: маркеры не должны срабатывать на английском тексте.
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
    # of Pacific timezone" — единственная C#/.NET вакансия в выдаче и
    # физически недостижимая: Pacific ±3 = UTC-11..-5, владелец в UTC+4.
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
    # Отчёт показывал вилку "$20,000-$250,000/год".
    v = make_vacancy(
        description_text="Salary: $150,000-$250,000 USD. $20,000 signing bonus. C# and TypeScript.",
    )
    comp = score.score_vacancy(v, CRITERIA, PROFILE)["score_breakdown"]["compensation_signal"]
    assert 20000.0 not in comp["annual_amounts_found"]
    assert 150000.0 in comp["annual_amounts_found"]
