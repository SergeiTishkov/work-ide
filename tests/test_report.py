"""
Тесты для tools/report.py - в первую очередь для отображения зарплаты с
явным указанием источника (подтверждено владельцем явно, 2026-07-30):
указано ли прямо в вакансии, найдено вручную на стороннем сайте, или
данных нет вообще.
"""
import common
import report


def test_salary_info_shows_raw_text_when_present():
    vacancy = {"salary_raw": "$65/hour"}
    comp_bd = {"explicit": True, "hourly_amounts_found": [65.0]}
    text = report._fmt_salary_info(vacancy, comp_bd)
    assert "$65/hour" in text
    assert "stated in the vacancy" in text


def test_salary_info_falls_back_to_extracted_amounts_when_no_raw_field():
    vacancy = {}
    comp_bd = {"explicit": True, "annual_amounts_found": [70000.0, 90000.0]}
    text = report._fmt_salary_info(vacancy, comp_bd)
    assert "70,000" in text or "$70,000" in text
    assert "90,000" in text
    assert "stated in the vacancy" in text


def test_salary_info_shows_external_estimate_with_source():
    vacancy = {}
    comp_bd = {
        "explicit": False,
        "external_estimate": {
            "low": 60000,
            "high": 80000,
            "period": "year",
            "source": "Glassdoor",
            "note": "average for similar roles",
        },
    }
    text = report._fmt_salary_info(vacancy, comp_bd)
    assert "Glassdoor" in text
    assert "found manually" in text
    assert "average for similar roles" in text
    assert "60,000" in text and "80,000" in text


def test_salary_info_shows_no_data_when_nothing_found():
    vacancy = {}
    comp_bd = {"explicit": False}
    text = report._fmt_salary_info(vacancy, comp_bd)
    assert "not stated" in text
    assert "no data" in text


def test_vacancy_line_always_includes_salary_sub_line():
    vacancy = {
        "title": "Senior .NET Developer",
        "company": "Acme Corp",
        "url": "https://example.com/1",
        "salary_raw": None,
        "manual": {"status": "new", "notes": ""},
        "computed": {
            "score": 50,
            "score_breakdown": {"compensation_signal": {"explicit": False}},
            "needs_manual_review": False,
        },
    }
    line = report._fmt_vacancy_line(vacancy)
    assert "💰 salary:" in line
    assert "not stated" in line


def test_scoring_philosophy_comes_from_the_identity_profile(monkeypatch):
    """Раньше объяснение шкалы было зашито в общую машинерию и печаталось в
    отчёт любой идентичности — включая ту, что ищет онсайт в стартапе."""
    import report

    monkeypatch.setattr(
        common, "load_profile",
        lambda *a, **k: {"identity": {"scoring_philosophy": "Своя философия этой идентичности."}},
    )
    assert report._scoring_philosophy() == "Своя философия этой идентичности."


def test_scoring_philosophy_falls_back_to_a_neutral_line(monkeypatch):
    import report

    monkeypatch.setattr(common, "load_profile", lambda *a, **k: {"identity": {}})
    text = report._scoring_philosophy()
    assert "identity's profile" in text
    assert "legacy" not in text, (
        "a neutral default must not impose one profile's philosophy on every identity"
    )


def test_hiring_country_prefers_the_office_that_posted_over_company_hq():
    """Просьба владельца 2026-08-05: у международной компании нужна страна
    ОФИСА, разместившего вакансию, а не родина компании. Швейцарский офис
    Google нанимает в Швейцарии — там договор, оттуда платят, тот часовой
    пояс."""
    swiss_office = {
        "title": "Software Engineer",
        "company": "Google",
        "location_raw": "Zurich, Zurich, Switzerland",
        "computed": {"score_breakdown": {"remote_location_fit": {
            "header_scope": {"header_lines": ["headquarters: united states"]}}}},
    }
    assert report.hiring_country(swiss_office) == ("Switzerland", report.HIRING_OFFICE)


def test_hiring_country_trusts_the_market_tag_over_the_location_string():
    """Тег `market:<страна>` записывает фетчер — это страна, по которой он
    делал запрос, то есть факт, а не разбор строки."""
    v = {"tags": ["market:United Kingdom"], "location_raw": "Remote"}
    assert report.hiring_country(v) == ("United Kingdom", report.HIRING_OFFICE)


def test_hiring_country_falls_back_to_headquarters_and_says_so():
    """Когда офис неизвестен, штаб-квартира лучше пустоты — но человек должен
    видеть, что это другое."""
    v = {
        "location_raw": "Anywhere in the World",
        "computed": {"score_breakdown": {"remote_location_fit": {
            "header_scope": {"header_lines": ["headquarters: sweden"]}}}},
    }
    assert report.hiring_country(v) == ("Sweden", report.COMPANY_HOME)


def test_hiring_country_handles_common_platform_spellings():
    for raw, expected in [("USA", "United States"),
                          ("London, England, United Kingdom", "United Kingdom"),
                          ("Dubai, Dubai, United Arab Emirates", "United Arab Emirates"),
                          ("Remote, Israel", "Israel")]:
        assert report.hiring_country({"location_raw": raw})[0] == expected, raw


def test_reputation_has_three_states_not_two():
    """Просьба владельца 2026-08-06. «Не проверялась» читалось как «данных
    нет», а означало «мы даже не пытались». Первое — свойство компании,
    второе — дефект процесса, и человеку важно, какое из двух он видит."""
    found = report._fmt_reputation(
        {"has_data": True, "overall_rating": 4.2, "work_life_balance": 4.4,
         "source": "Glassdoor", "retrieval": "web_search"}, "hot_lead")
    assert "4.2" in found and "4.4" in found

    checked_empty = report._fmt_reputation(
        {"has_data": False, "verdict": "insufficient_sources",
         "checked_at": "2026-08-06T10:00:00+00:00", "searched": "Glassdoor, Indeed"},
        "hot_lead")
    assert "not enough sources" in checked_empty
    assert "2026-08-06" in checked_empty
    assert "Glassdoor, Indeed" in checked_empty

    gap = report._fmt_reputation({"has_data": False}, "hot_lead")
    assert "❗" in gap, "пробел в голове выдачи обязан быть заметен"

    tail = report._fmt_reputation({"has_data": False}, "long_shot")
    assert "❗" not in tail, "в хвосте проверка не делается по замыслу — это не пробел"


def test_reputation_coverage_block_names_what_is_left():
    """Невыполненная работа обязана быть видна в отчёте, а не в чьей-то
    памяти: замер 2026-08-06 показал 55 компаний в голове выдачи и ноль
    проверок, и отчёт об этом молчал."""
    vacancies = {
        "a": {"company": "Известная", "computed": {"classification": "hot_lead"}},
        "b": {"company": "Незнакомая", "computed": {"classification": "worth_a_look"}},
    }
    companies = {
        "известная": {"name": "Известная",
                      "reputation": {"overall_rating": 4.0,
                                     "checked_at": "2026-08-06T10:00:00+00:00"}},
        "незнакомая": {"name": "Незнакомая"},
    }
    block = report._reputation_coverage_block(vacancies, companies)
    assert "not checked: 1" in block
    assert "Незнакомая" in block
    assert "Известная" not in block.split("Осталось проверить")[-1]
