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


def test_merge_vacancy_creates_new_with_default_manual_block(isolated_data_dir):
    vacancies = {}
    action = kb.merge_vacancy(vacancies, make_normalized(), DUMMY_COMPUTED)
    assert action == "new"
    v = vacancies["vac-1"]
    assert v["manual"] == {"status": "new", "notes": ""}
    assert v["external_signals"] == {}
    assert v["first_seen"] == v["last_seen"]


def test_merge_vacancy_preserves_external_signals_on_rerun(isolated_data_dir):
    # Регрессия: merge_vacancy пересобирает запись с нуля на каждом обновлении
    # - external_signals (вручную найденная ЗП-оценка) не должна теряться,
    # так же как и manual.
    vacancies = {}
    kb.merge_vacancy(vacancies, make_normalized(), DUMMY_COMPUTED)
    vacancies["vac-1"]["external_signals"]["salary_estimate"] = {
        "low": 60000, "high": 80000, "period": "year", "source": "Glassdoor",
    }

    kb.merge_vacancy(vacancies, make_normalized(title="Senior .NET Developer (refetched)"), DUMMY_COMPUTED)

    assert vacancies["vac-1"]["external_signals"]["salary_estimate"]["source"] == "Glassdoor"


def test_merge_vacancy_preserves_manual_edits_on_rerun(isolated_data_dir):
    vacancies = {}
    kb.merge_vacancy(vacancies, make_normalized(), DUMMY_COMPUTED)
    vacancies["vac-1"]["manual"]["status"] = "applied"
    vacancies["vac-1"]["manual"]["notes"] = "Applied on 2026-07-30, waiting to hear back."
    first_seen_before = vacancies["vac-1"]["first_seen"]

    # Второй запуск пайплайна видит ту же вакансию снова (тот же id)
    action = kb.merge_vacancy(vacancies, make_normalized(title="Senior .NET Developer (updated title)"), DUMMY_COMPUTED)

    assert action == "updated"
    v = vacancies["vac-1"]
    assert v["manual"]["status"] == "applied", "статус, выставленный владельцем, не должен затираться повторным запуском"
    assert v["manual"]["notes"] == "Applied on 2026-07-30, waiting to hear back."
    assert v["first_seen"] == first_seen_before, "first_seen не должен сдвигаться при повторном обнаружении"
    assert v["title"] == "Senior .NET Developer (updated title)", "но сами данные вакансии обновляются"


def test_build_companies_from_vacancies_preserves_notes_and_first_seen(isolated_data_dir):
    vacancies = {}
    kb.merge_vacancy(vacancies, make_normalized(), DUMMY_COMPUTED)
    companies_v1 = kb.build_companies_from_vacancies(vacancies, previous_companies={})
    slug = list(companies_v1.keys())[0]
    companies_v1[slug]["notes"] = "Известно: нанимает контракторов, платит вовремя."
    first_seen_v1 = companies_v1[slug]["first_seen"]

    # добавляем вторую вакансию той же компании и пересобираем
    kb.merge_vacancy(vacancies, make_normalized(vid_suffix="2", company="Acme Corp"), DUMMY_COMPUTED)
    companies_v2 = kb.build_companies_from_vacancies(vacancies, previous_companies=companies_v1)

    assert companies_v2[slug]["notes"] == "Известно: нанимает контракторов, платит вовремя."
    assert companies_v2[slug]["first_seen"] == first_seen_v1
    assert len(companies_v2[slug]["vacancy_ids"]) == 2


def test_build_companies_does_not_duplicate_vacancy_ids_on_rebuild(isolated_data_dir):
    vacancies = {}
    kb.merge_vacancy(vacancies, make_normalized(), DUMMY_COMPUTED)
    companies = kb.build_companies_from_vacancies(vacancies, previous_companies={})
    # пересобираем ещё раз с теми же данными - не должно расти бесконечно
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
    # каноническая запись - та, у которой выше score
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

    # если один из дублей "исчез" (например, удалили руками), пометка не должна залипать навечно
    del vacancies["vac-2"]
    kb.mark_duplicates(vacancies)
    assert vacancies["vac-1"].get("duplicate_of") is None


def test_set_status_rejects_invalid_status(isolated_data_dir, capsys):
    vacancies = {}
    kb.merge_vacancy(vacancies, make_normalized(), DUMMY_COMPUTED)
    kb.save_vacancies(vacancies)

    class Args:
        id = "vac-1"
        status = "definitely-not-a-real-status"
        notes = None

    import pytest as _pytest

    with _pytest.raises(SystemExit):
        kb.cmd_set_status(Args())


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
    # score должен быть пересчитан немедленно, а не только на следующем pipeline.py
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
