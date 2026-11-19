"""A vacancy the person adds by its link (tools/add_vacancy.py, task 0122):
found in the base by its LinkedIn job number, its page's facts merged in,
scored alone, remembered as a pick and listed under "Added by hand" — now in
the latest selection, and on every later run."""
import json

import pytest

import add_vacancy
import db
import kb
import segments
import selections

CONFIG = {"segments": [
    {"slug": "worldwide", "name": "Worldwide", "groups": ["worldwide"]},
    {"slug": "rest", "name": "Rest of the world", "rest": True},
    {"slug": "full", "name": "Everything", "everything": True, "default": True},
]}
JOB = "4474971398"
CARD_URL = f"https://es.linkedin.com/jobs/view/forward-deployed-engineer-at-endgame-{JOB}"
OWNER_URL = (f"https://www.linkedin.com/jobs/view/{JOB}/?alternateChannel=search"
             "&refId=KarZOVDi4SPK3sqNttp%2BuQ%3D%3D")
TEXT = ("Location: Remote-First - Europe (including the UK). Senior engineer: C#, .NET, "
        "ASP.NET Core, SQL Server, Azure. Remote-first (GMT-1 to GMT+4).")


@pytest.fixture(autouse=True)
def _segments(monkeypatch):
    monkeypatch.setattr(segments, "load_segments",
                        lambda prefix=None: segments.parse_segments(CONFIG))


def _vacancy(vid, score=60, classification="hot_lead", **extra):
    return {
        "id": vid, "source": "remotive", "external_id": vid,
        "title": f"Senior .NET Developer {vid}", "company": f"Company {vid}",
        "url": f"https://example.test/{vid}", "location_raw": "Anywhere in the World",
        "description_text": "C# and SQL Server.", "tags": [],
        "computed": {"score": score, "classification": classification,
                     "score_breakdown": {}, "dealbreakers": []},
        **extra,
    }


def _card():
    """The LinkedIn card as the base held it: no description, rejected blind."""
    return _vacancy("card1", score=4, classification="rejected", source="linkedin",
                    external_id=CARD_URL, url=CARD_URL, title="Forward Deployed Engineer",
                    company="ENDGAME", location_raw="Spain", description_text="",
                    first_seen="2026-11-06T07:39:46+00:00")


def _page(**extra):
    return {"description": TEXT, "workplace_type": None, "salary_raw": None, "closed": False,
            "employment_types": ["full-time"], "title": "Forward Deployed Engineer",
            "company": "ENDGAME", "location": "Spain",
            "url": f"https://www.linkedin.com/jobs/view/{JOB}/", **extra}


@pytest.fixture
def base(isolated_data_dir, monkeypatch):
    """A run's selection with one listed vacancy, and the card beside it."""
    vacancies = {"v1": _vacancy("v1"), "card1": _card()}
    kb.save_vacancies(vacancies)
    selection_id = selections.record(vacancies, {"run_count": 1}, kind="run")
    pages = []

    def fake_read(job_id):
        pages.append(job_id)
        return _page()

    monkeypatch.setattr(add_vacancy, "read_linkedin", fake_read)
    return {"selection_id": selection_id, "pages": pages}


def _items(selection_id):
    with db.session() as conn:
        return sorted(conn.execute(
            "SELECT segment, vacancy_id, class, class_position FROM selection_items "
            "WHERE selection_id = ?", (selection_id,)).fetchall())


def _listed(selection_id, segment="full"):
    chosen = selections.view([segment], selections.NEW, ("fresh",))
    with db.session() as conn:
        return [(r["vacancy_id"], r["class"]) for r in selections.listing(conn, selection_id, chosen)]


@pytest.mark.parametrize("url,expected", [
    (OWNER_URL, JOB),
    (CARD_URL, JOB),
    (f"https://uk.linkedin.com/jobs/view/{JOB}", JOB),
    ("https://www.linkedin.com/jobs/search/?currentJobId=4474971398", None),
    ("https://example.test/jobs/view/4474971398", None),
    ("", None),
])
def test_linkedin_job_number(url, expected):
    assert add_vacancy.linkedin_job_id(url) == expected


def test_a_linkedin_link_finds_the_card_from_another_subdomain(base):
    assert add_vacancy.find_existing(OWNER_URL) == "card1"


def test_the_job_number_in_a_description_is_not_a_match(base):
    kb.save_vacancies({"other": _vacancy("other", description_text=f"see job {JOB} too")})
    assert add_vacancy.find_existing(OWNER_URL) == "card1"
    assert add_vacancy.find_existing("https://www.linkedin.com/jobs/view/9999999999/") is None


def test_the_card_gets_its_page_and_is_listed_first_in_every_market(base):
    result = add_vacancy.add(OWNER_URL, {})

    assert result["id"] == "card1" and result["found"]
    assert result["selection_id"] == base["selection_id"]
    assert base["pages"] == [JOB]
    stored = db.load_vacancy("card1")
    assert stored["description_text"] == TEXT
    assert stored["employment_types"] == ["full-time"]
    assert stored["first_seen"] == "2026-11-06T07:39:46+00:00"
    assert stored["computed"]["classification"] == result["class"]
    assert json.loads(selections.picks_path().read_text("utf-8"))["card1"]["url"] == OWNER_URL
    items = _items(base["selection_id"])
    assert [i for i in items if i[1] == "card1"] == [
        (slug, "card1", selections.HAND_CLASS, selections.HAND_CLASS_POSITION)
        for slug in ("full", "rest", "worldwide")]
    # nothing else in the selection moved
    assert [i for i in items if i[1] != "card1"] == [
        ("full", "v1", "hot_lead", 0), ("worldwide", "v1", "hot_lead", 0)]
    assert _listed(base["selection_id"]) == [("card1", selections.HAND_CLASS), ("v1", "hot_lead")]
    assert _listed(base["selection_id"], "rest") == [("card1", selections.HAND_CLASS)]


def test_the_row_carries_the_scripts_score(base):
    result = add_vacancy.add(OWNER_URL, {})
    with db.session() as conn:
        scores = {row[0] for row in conn.execute(
            "SELECT score FROM selection_items WHERE vacancy_id = 'card1'")}
        view = json.loads(conn.execute(
            "SELECT view FROM vacancy_identity WHERE vacancy_id = 'card1'").fetchone()[0])
    assert scores == {result["score"]}
    assert view["title"] == "Forward Deployed Engineer"


def test_adding_twice_keeps_one_row_per_market_and_the_first_date(base):
    add_vacancy.add(OWNER_URL, {})
    first = selections.load_picks()["card1"]["added_at"]
    add_vacancy.add(CARD_URL, {})
    assert selections.load_picks()["card1"]["added_at"] == first
    assert len([i for i in _items(base["selection_id"]) if i[1] == "card1"]) == 3


def test_the_next_run_lists_the_pick_once_in_its_own_section(base):
    add_vacancy.add(OWNER_URL, {})
    vacancies = kb.load_vacancies()
    vacancies["card1"]["computed"]["classification"] = "hot_lead"   # even a listed class
    selection_id = selections.record(vacancies, {"run_count": 2}, kind="run")
    assert [i for i in _items(selection_id) if i[1] == "card1"] == [
        (slug, "card1", selections.HAND_CLASS, selections.HAND_CLASS_POSITION)
        for slug in ("full", "rest", "worldwide")]


@pytest.mark.parametrize("extra", [{"duplicate_of": "v1"}, {"link_check": {"status": "dead"}}])
def test_a_duplicate_or_dead_pick_leaves_the_list(base, extra):
    add_vacancy.add(OWNER_URL, {})
    vacancies = kb.load_vacancies()
    vacancies["card1"].update(extra)
    selection_id = selections.record(vacancies, {"run_count": 2}, kind="run")
    assert not [i for i in _items(selection_id) if i[1] == "card1"]


def test_given_facts_replace_the_stored_ones(base):
    add_vacancy.add(OWNER_URL, {"title": "Forward Deployed Engineer (.NET)", "location": "Remote, Europe"})
    stored = db.load_vacancy("card1")
    assert stored["title"] == "Forward Deployed Engineer (.NET)"
    assert stored["location_raw"] == "Remote, Europe"
    assert stored["company"] == "ENDGAME"


def test_a_longer_stored_description_is_kept(base):
    longer = TEXT + " " + "More text. " * 50
    kb.save_vacancies({"card1": {**_card(), "description_text": longer}})
    add_vacancy.add(OWNER_URL, {})
    assert db.load_vacancy("card1")["description_text"] == longer


def test_a_new_linkedin_posting_is_created(base, monkeypatch):
    monkeypatch.setattr(add_vacancy, "read_linkedin",
                        lambda job_id: _page(title="Senior .NET Engineer", company="Acme",
                                             url=f"https://www.linkedin.com/jobs/view/{job_id}/"))
    result = add_vacancy.add("https://www.linkedin.com/jobs/view/1234567890/", {})
    assert not result["found"]
    stored = db.load_vacancy(result["id"])
    assert (stored["source"], stored["company"], stored["title"]) == ("linkedin", "Acme", "Senior .NET Engineer")
    assert stored["external_id"] == "https://www.linkedin.com/jobs/view/1234567890/"
    assert ("full", result["id"], selections.HAND_CLASS, -1) in _items(base["selection_id"])


@pytest.mark.parametrize("page,given,why", [
    (_page(closed=True), {}, "no longer accepts"),
    (_page(description="", title=None, company=None), {}, "no description"),
    (_page(title=None, company=None), {}, "needs a title and a company"),
])
def test_nothing_is_saved_when_the_vacancy_cannot_be_added(base, monkeypatch, page, given, why):
    monkeypatch.setattr(add_vacancy, "read_linkedin", lambda job_id: page)
    with pytest.raises(add_vacancy.NotAdded, match=why):
        add_vacancy.add("https://www.linkedin.com/jobs/view/1234567890/", given)
    assert not selections.picks_path().exists()
    assert len(kb.load_vacancies()) == 2


def test_another_board_without_a_reader_takes_the_description_file(base, monkeypatch):
    monkeypatch.setattr(add_vacancy, "read_page", lambda url, source: {})
    with pytest.raises(add_vacancy.NotAdded, match="no description"):
        add_vacancy.add("https://careers.example.test/job/7", {"title": "Dev", "company": "Ex"})
    result = add_vacancy.add("https://careers.example.test/job/7",
                             {"title": "Dev", "company": "Ex", "description": TEXT})
    stored = db.load_vacancy(result["id"])
    assert (stored["source"], stored["description_text"]) == ("manual", TEXT)


def test_no_selection_yet_means_the_first_run_lists_it(isolated_data_dir, monkeypatch):
    monkeypatch.setattr(add_vacancy, "read_linkedin", lambda job_id: _page())
    result = add_vacancy.add(OWNER_URL, {})
    assert result["selection_id"] is None
    selection_id = selections.record(kb.load_vacancies(), {"run_count": 1}, kind="run")
    assert _listed(selection_id) == [(result["id"], selections.HAND_CLASS)]


def test_load_vacancy_reads_one_record_with_its_screening_answer(isolated_data_dir):
    assert db.load_vacancy("nope") is None
    kb.save_vacancies({"v1": _vacancy("v1")})
    with db.session() as conn:
        conn.execute("INSERT INTO ai_screens (identity_id, vacancy_id, text_hash, brief_hash, result, "
                     "model, screened_at) VALUES (?, 'v1', 't', 'b', ?, 'haiku', 'now')",
                     (db.identity(), json.dumps({"verdict": "keep"})))
    one = db.load_vacancy("v1")
    assert one == kb.load_vacancies()["v1"]
    assert one["_ai_screen"]["verdict"] == "keep"
