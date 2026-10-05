import kb


def make_normalized(vid_suffix="1", company="Acme Corp", title="Senior .NET Developer"):
    return {
        "id": f"vac-{vid_suffix}",
        "source": "arbeitnow",
        "external_id": vid_suffix,
        "title": title,
        "company": company,
        "url": f"https://example.com/{vid_suffix}",
        "location_raw": "Remote",
        "remote": True,
        "tags": ["dotnet"],
        "description_text": "Maintain legacy systems.",
        "posted_at": None,
        "salary_raw": None,
    }


DUMMY_COMPUTED = {
    "score": 70,
    "score_breakdown": {
        "remote_location_fit": {},
        "legacy_enterprise_signal": {"hits": ["legacy"]},
    },
    "classification": "hot_lead",
    "dealbreakers": [],
    "needs_manual_review": False,
}


def test_merge_vacancy_creates_a_new_record(isolated_data_dir):
    vacancies = {}
    action = kb.merge_vacancy(vacancies, make_normalized(), DUMMY_COMPUTED)
    assert action == "new"
    v = vacancies["vac-1"]
    assert "manual" not in v, "the old status system is gone: feedback lives in its own columns"
    assert v["external_signals"] == {}
    assert v["first_seen"] == v["last_seen"]


def test_merge_vacancy_preserves_external_signals_on_rerun(isolated_data_dir):
    # Regression: merge_vacancy rebuilds a record from scratch on every update
    # — external_signals (a pay estimate found by hand) must not be lost.
    vacancies = {}
    kb.merge_vacancy(vacancies, make_normalized(), DUMMY_COMPUTED)
    vacancies["vac-1"]["external_signals"]["salary_estimate"] = {
        "low": 60000, "high": 80000, "period": "year", "source": "Glassdoor",
    }

    kb.merge_vacancy(vacancies, make_normalized(title="Senior .NET Developer (refetched)"), DUMMY_COMPUTED)

    assert vacancies["vac-1"]["external_signals"]["salary_estimate"]["source"] == "Glassdoor"


def test_merge_vacancy_updates_the_facts_and_keeps_first_seen(isolated_data_dir):
    vacancies = {}
    kb.merge_vacancy(vacancies, make_normalized(), DUMMY_COMPUTED)
    first_seen_before = vacancies["vac-1"]["first_seen"]

    # The second pipeline run sees the same vacancy again (same id)
    action = kb.merge_vacancy(vacancies, make_normalized(title="Senior .NET Developer (updated title)"), DUMMY_COMPUTED)

    assert action == "updated"
    v = vacancies["vac-1"]
    assert v["first_seen"] == first_seen_before, "first_seen must not move on re-discovery"
    assert v["title"] == "Senior .NET Developer (updated title)", "but the vacancy data itself is updated"


def test_a_refetched_card_keeps_what_was_learned_from_its_page(isolated_data_dir):
    """Until 2026-10-05 a re-fetch rebuilt the record from the source alone: a
    LinkedIn card comes without a description, so every run threw away the
    page read for it, scored the shortlist blind and read the page again."""
    card = {**make_normalized(), "description_text": "", "salary_raw": None,
            "employment_types": ["contract"]}
    vacancies = {}
    kb.merge_vacancy(vacancies, card, DUMMY_COMPUTED)
    learned = vacancies["vac-1"]
    learned["description_text"] = "The full page: C#, ASP.NET Core, remote across Europe."
    learned["salary_raw"] = "€60 – €70 per hour"
    learned["workplace_type"] = "remote"
    learned["employment_types"] = ["contract", "part-time"]
    learned["description_fetch"] = {"attempted_at": "2026-10-01T10:00:00+00:00", "chars": 52}
    learned["link_check"] = {"status": "alive", "checked_at": "2026-10-01T10:00:00+00:00"}
    learned["apply_channels"] = [{"kind": "careers_page", "url": "https://acme.test/jobs"}]

    kb.merge_vacancy(vacancies, card, DUMMY_COMPUTED)

    v = vacancies["vac-1"]
    assert v["description_text"].startswith("The full page")
    assert v["salary_raw"] == "€60 – €70 per hour"
    assert v["workplace_type"] == "remote"
    assert set(v["employment_types"]) == {"contract", "part-time"}
    for key in ("description_fetch", "link_check", "apply_channels"):
        assert v[key] == learned[key], key


def test_what_the_source_says_now_wins_over_an_older_fact(isolated_data_dir):
    vacancies = {}
    kb.merge_vacancy(vacancies, {**make_normalized(), "salary_raw": "£500/day"}, DUMMY_COMPUTED)
    kb.merge_vacancy(vacancies, {**make_normalized(), "salary_raw": "£550/day"}, DUMMY_COMPUTED)
    assert vacancies["vac-1"]["salary_raw"] == "£550/day"


def test_build_companies_from_vacancies_preserves_notes_and_first_seen(isolated_data_dir):
    vacancies = {}
    kb.merge_vacancy(vacancies, make_normalized(), DUMMY_COMPUTED)
    companies_v1 = kb.build_companies_from_vacancies(vacancies, previous_companies={})
    slug = list(companies_v1.keys())[0]
    companies_v1[slug]["notes"] = "Known to hire contractors and to pay on time."
    first_seen_v1 = companies_v1[slug]["first_seen"]

    # add a second vacancy for the same company and rebuild
    kb.merge_vacancy(vacancies, make_normalized(vid_suffix="2", company="Acme Corp"), DUMMY_COMPUTED)
    companies_v2 = kb.build_companies_from_vacancies(vacancies, previous_companies=companies_v1)

    assert companies_v2[slug]["notes"] == "Known to hire contractors and to pay on time."
    assert companies_v2[slug]["first_seen"] == first_seen_v1
    assert len(companies_v2[slug]["vacancy_ids"]) == 2


def test_build_companies_does_not_duplicate_vacancy_ids_on_rebuild(isolated_data_dir):
    vacancies = {}
    kb.merge_vacancy(vacancies, make_normalized(), DUMMY_COMPUTED)
    companies = kb.build_companies_from_vacancies(vacancies, previous_companies={})
    # rebuild once more with the same data — it must not grow without bound
    companies2 = kb.build_companies_from_vacancies(vacancies, previous_companies=companies)
    slug = list(companies2.keys())[0]
    assert len(companies2[slug]["vacancy_ids"]) == 1


def test_mark_duplicates_collapses_exact_title_company_repost(isolated_data_dir):
    vacancies = {}
    computed_low = dict(DUMMY_COMPUTED, score=30)
    computed_high = dict(DUMMY_COMPUTED, score=55)
    kb.merge_vacancy(
        vacancies,
        make_normalized(vid_suffix="1", company="Acme Corp", title="Senior .NET Developer"),
        computed_low,
    )
    kb.merge_vacancy(
        vacancies,
        make_normalized(vid_suffix="2", company="Acme Corp", title="Senior .NET Developer"),
        computed_high,
    )
    marked = kb.mark_duplicates(vacancies)
    assert marked == 1
    # the canonical record is the one with the higher score
    assert vacancies["vac-2"].get("duplicate_of") is None
    assert vacancies["vac-1"].get("duplicate_of") == "vac-2"


def test_mark_duplicates_ignores_different_companies_or_titles(isolated_data_dir):
    vacancies = {}
    kb.merge_vacancy(vacancies, make_normalized(vid_suffix="1", company="Acme Corp", title="Senior .NET Developer"), DUMMY_COMPUTED)
    kb.merge_vacancy(vacancies, make_normalized(vid_suffix="2", company="Other Corp", title="Senior .NET Developer"), DUMMY_COMPUTED)
    kb.merge_vacancy(vacancies, make_normalized(vid_suffix="3", company="Acme Corp", title="Totally Different Role"), DUMMY_COMPUTED)
    marked = kb.mark_duplicates(vacancies)
    assert marked == 0
    assert all(v.get("duplicate_of") is None for v in vacancies.values())


def test_mark_duplicates_recomputes_fresh_each_call(isolated_data_dir):
    vacancies = {}
    kb.merge_vacancy(vacancies, make_normalized(vid_suffix="1", company="Acme Corp", title="Senior .NET Developer"), DUMMY_COMPUTED)
    kb.merge_vacancy(vacancies, make_normalized(vid_suffix="2", company="Acme Corp", title="Senior .NET Developer"), DUMMY_COMPUTED)
    kb.mark_duplicates(vacancies)
    assert sum(1 for v in vacancies.values() if v.get("duplicate_of")) == 1

    # if one of the duplicates "vanished" (deleted by hand, say), the mark must not stick forever
    del vacancies["vac-2"]
    kb.mark_duplicates(vacancies)
    assert vacancies["vac-1"].get("duplicate_of") is None


def test_cmd_set_salary_estimate_updates_score_immediately(isolated_data_dir):
    vacancies = {}
    normalized = make_normalized()
    normalized["description_text"] = "Great legacy .NET role, no salary mentioned in the posting."
    computed = dict(DUMMY_COMPUTED, score=0, score_breakdown={})
    kb.merge_vacancy(vacancies, normalized, computed)
    kb.save_vacancies(vacancies)

    class Args:
        id = "vac-1"
        low = 65000.0
        high = 85000.0
        period = "year"
        source = "Glassdoor"
        note = "Looked up on Glassdoor"

    kb.cmd_set_salary_estimate(Args())

    saved = kb.load_vacancies()
    v = saved["vac-1"]
    assert v["external_signals"]["salary_estimate"]["source"] == "Glassdoor"
    # the score must be recomputed at once, not only on the next pipeline.py
    assert v["computed"]["score_breakdown"]["compensation_signal"]["points"] > 0


def test_cmd_set_salary_estimate_missing_vacancy_exits(isolated_data_dir):
    import pytest as _pytest

    class Args:
        id = "does-not-exist"
        low = 1.0
        high = 2.0
        period = "year"
        source = "Glassdoor"
        note = None

    with _pytest.raises(SystemExit):
        kb.cmd_set_salary_estimate(Args())
