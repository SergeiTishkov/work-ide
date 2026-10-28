"""The screening brief (tools/ai_brief.py) and the cheap model's check of the
top vacancies (tools/ai_screen.py). No model is called: every test passes a
`call` of its own (conftest refuses the real one)."""
import ai_brief
import ai_screen
import db
import score


def _record(vid="a", cls="hot_lead", text="Fully remote, worldwide. C# and .NET.", score_=50):
    return {"id": vid, "title": "Senior .NET Engineer", "company": "Acme", "source": "arbeitnow",
            "url": f"https://example.com/{vid}", "location_raw": "Remote", "description_text": text,
            "computed": {"classification": cls, "score": score_}}


def test_the_brief_is_written_once_per_set_of_documents(tmp_path, monkeypatch):
    path = tmp_path / "x_ai_brief.md"
    docs = {"CV": "C# for eight years", "profile (personal)": "lives in Georgia"}
    monkeypatch.setattr(ai_brief, "brief_path", lambda prefix: path)
    monkeypatch.setattr(ai_brief, "documents", lambda prefix: dict(docs))
    monkeypatch.setattr(ai_brief, "feedback_reasons", lambda prefix, limit=200: ["Go role | X | rejected: not .NET"])
    asked = []

    def call(message):
        asked.append(message)
        return "## Who\n\nA .NET engineer."

    first = ai_brief.ensure("x", call=call)
    assert first["written"] is True
    assert "C# for eight years" in asked[0] and "not .NET" in asked[0]
    assert path.read_text(encoding="utf-8").startswith(f"<!-- ai brief: inputs {first['hash']}")
    assert ai_brief.load("x") == "## Who\n\nA .NET engineer."

    assert ai_brief.ensure("x", call=call)["written"] is False, "the same documents: no new brief"
    assert len(asked) == 1

    docs["CV"] = "C# for nine years"
    assert ai_brief.ensure("x", call=call)["written"] is True, "a changed CV writes it again"
    assert ai_brief.ensure("x", force=True, call=call)["written"] is True
    assert len(asked) == 3


def test_the_worklist_is_the_top_classes_without_a_current_answer():
    vacancies = {
        "hot": _record("hot", "hot_lead", score_=60),
        "look": _record("look", "worth_a_look", score_=40),
        "unconfirmed": _record("unconfirmed", "remote_unconfirmed"),
        "low": _record("low", "low_priority"),
        "dup": {**_record("dup"), "duplicate_of": "hot"},
        "done": _record("done", "long_shot", score_=30),
    }
    digest = "b" * 16
    stored = {"done": {"verdict": "keep", "text_hash": ai_screen.text_hash(vacancies["done"]), "brief_hash": digest}}
    assert ai_screen.worklist(vacancies, stored, digest) == ["hot", "look"]
    assert ai_screen.worklist(vacancies, stored, "c" * 16) == ["hot", "look"], "a new brief keeps the answer"
    assert ai_screen.worklist(vacancies, stored, "c" * 16, reread=True) == ["hot", "look", "done"],         "the re-read the owner asked for asks again"
    vacancies["done"]["description_text"] += " Hybrid, 2 days in the office."
    assert "done" in ai_screen.worklist(vacancies, stored, digest), "a new text asks again"


def test_stretches_waiting_for_a_read_follow_the_top_within_their_own_budget():
    def stretch(vid, score_):
        record = _record(vid, "rejected", score_=score_)
        record["computed"]["screen_wanted"] = True
        return record

    vacancies = {"hot": _record("hot", "hot_lead", score_=60), "s1": stretch("s1", 20),
                 "s2": stretch("s2", 35), "s3": stretch("s3", 10), "out": _record("out", "rejected")}
    digest = "b" * 16
    assert ai_screen.worklist(vacancies, {}, digest, stretch_limit=2) == ["hot", "s2", "s1"]
    assert ai_screen.worklist(vacancies, {}, digest, limit=1, stretch_limit=None) == ["hot", "s2", "s1", "s3"]
    assert ai_screen.worklist(vacancies, {}, digest, classes=(), stretch_limit=0) == []


def test_answers_are_stored_attached_and_valid_only_for_their_text(isolated_data_dir):
    with db.session():
        pass
    vacancies = {"a": _record("a"), "b": _record("b", text="Hybrid: 3 days a week in our London office.")}

    def call(system_prompt, text, workdir=None):
        assert "# The brief" in system_prompt.read_text(encoding="utf-8")
        assert "a .NET engineer in Georgia" in system_prompt.read_text(encoding="utf-8")
        if "Hybrid" in text:
            return {"is_job_posting": True, "work_arrangement": "hybrid", "location_ok": "no",
                    "role_fit": "good", "verdict": "reject", "reason": "3 days a week in London",
                    "quote": "3 days a week in our London office"}, 0.002
        return {"is_job_posting": True, "work_arrangement": "remote", "location_ok": "yes",
                "role_fit": "good", "verdict": "keep", "reason": "remote worldwide"}, 0.001

    stats = ai_screen.screen(vacancies, "ftf", "a .NET engineer in Georgia", call=call)
    assert {k: stats[k] for k in ("screened", "rejected", "kept", "errors")} == {
        "screened": 2, "rejected": 1, "kept": 1, "errors": 0}
    assert stats["cost_usd"] == 0.003
    assert ai_screen.current(vacancies["b"])["verdict"] == "reject"
    with db.session() as conn:
        assert set(ai_screen.load(conn, "ftf")) == {"a", "b"}
        assert ai_screen.load(conn, "other") == {}

    again = ai_screen.screen(vacancies, "ftf", "a .NET engineer in Georgia", call=call)
    assert again["screened"] == 0, "stored answers are not asked again"

    vacancies["b"]["description_text"] = "Remote anywhere."
    assert ai_screen.current(vacancies["b"]) is None, "an answer for another text is not used"


def test_one_failed_answer_does_not_stop_the_rest(isolated_data_dir):
    vacancies = {"a": _record("a"), "b": _record("b")}

    def call(system_prompt, text, workdir=None):
        if "example.com/a" in text:
            raise ai_screen.ScreenError("no structured answer")
        return {"is_job_posting": True, "work_arrangement": "remote", "location_ok": "yes",
                "role_fit": "good", "verdict": "keep", "reason": "ok"}, 0.0

    pauses = []
    stats = ai_screen.screen(vacancies, "ftf", "brief", call=call, pause=pauses.append)
    assert (stats["screened"], stats["errors"]) == (1, 1)
    assert stats["retried"] == ai_screen.RETRY_ROUNDS, "the failed one was sent again, every round"
    assert len(pauses) == ai_screen.RETRY_ROUNDS
    assert "_ai_screen" not in vacancies["a"] and vacancies["b"]["_ai_screen"]["verdict"] == "keep"


def test_a_call_that_failed_once_is_read_on_the_retry(isolated_data_dir):
    """Task 0078: a timeout or a broken answer is not the end of the read."""
    vacancies = {"a": _record("a"), "b": _record("b")}
    calls = []

    def call(system_prompt, text, workdir=None):
        calls.append(text)
        if "example.com/a" in text and sum("example.com/a" in t for t in calls) == 1:
            raise ai_screen.ScreenError("claude did not answer in 180 s")
        return {"is_job_posting": True, "work_arrangement": "remote", "location_ok": "yes",
                "role_fit": "good", "verdict": "keep", "reason": "ok"}, 0.0

    stats = ai_screen.screen(vacancies, "ftf", "brief", call=call, pause=lambda _s: None)
    assert (stats["screened"], stats["errors"], stats["retried"]) == (2, 0, 1)
    assert vacancies["a"]["_ai_screen"]["verdict"] == "keep"


def test_the_unscreened_class_is_read():
    """What score.py holds in "not processed with AI" is what the model reads."""
    keys = ai_screen.worklist({"a": _record("a", cls=ai_screen.UNSCREENED)}, {}, "digest")
    assert keys == ["a"]


def test_no_brief_no_check():
    assert ai_screen.screen({"a": _record()}, "ftf", "  ", call=None)["skipped"] == "no brief"


def test_a_reject_is_a_dealbreaker_and_a_keep_changes_nothing():
    criteria = score.load_criteria()
    profile = score.load_profile()
    record = _record()
    plain = score.score_vacancy(record, criteria, profile)

    kept = {**record, "_ai_screen": {"verdict": "keep", "reason": "remote", "text_hash": ai_screen.text_hash(record)}}
    assert score.score_vacancy(kept, criteria, profile)["score"] == plain["score"]

    rejected = {**record, "_ai_screen": {"verdict": "reject", "reason": "Hybrid, 2 days in Austin",
                                         "text_hash": ai_screen.text_hash(record)}}
    computed = score.score_vacancy(rejected, criteria, profile)
    assert computed["classification"] == "rejected"
    assert "ai: Hybrid, 2 days in Austin" in computed["dealbreakers"]
    assert computed["score_breakdown"]["ai_screen"]["verdict"] == "reject"

    stale = {**rejected, "_ai_screen": {**rejected["_ai_screen"], "text_hash": "0" * 16}}
    assert score.score_vacancy(stale, criteria, profile)["classification"] == plain["classification"]


def test_the_scorers_time_zone_window_is_sent_to_the_model_outside_the_hash():
    """On 2026-10-20 Haiku read "CET ±3 hours" as excluding UTC+4 in 3 of 4
    postings; the scorer's arithmetic goes with the posting instead."""
    text = ("Fully remote. C# and .NET. Located in CET timezone (+/- 3 hours), "
            "we are unable to consider applications from candidates in other time zones.")
    record = _record(text=text)
    plain_hash = ai_screen.text_hash(record)
    record["computed"] = score.score_vacancy(record, score.load_criteria(), score.load_profile())
    sent = ai_screen.model_message(record)
    assert sent.startswith("time-zone window, checked by a program: CET ±3h")
    assert "is inside it" in sent.splitlines()[0]
    assert ai_screen.text_hash(record) == plain_hash
    assert ai_screen.model_message(_record()) == ai_screen.message(_record())


def test_the_persons_languages_come_from_the_profile():
    profile = {"owner": {"languages": ["English", "Russian (native)", {"name": "German"}, "english"]}}
    assert ai_screen.person_languages(profile) == ["english", "russian", "german"]
    assert ai_screen.person_languages({}) == []


def test_the_program_compares_the_named_languages_with_the_persons():
    """Task 0084: the model names the languages, the program decides."""
    mine = ["english", "russian"]

    def refusal(written, required=()):
        return ai_screen.language_refusal(
            {"posting_languages": list(written), "required_languages": list(required)}, mine)

    assert refusal(["polish"]) == "posting written in Polish"
    assert refusal(["Finnish"]) == "posting written in Finnish"
    assert refusal(["japanese", "english"]) is None, "an English version is enough"
    assert refusal(["english"], ["english", "spanish", "Spanish"]) == "requires Spanish"
    assert refusal(["russian"], ["russian"]) is None
    assert refusal([], []) is None, "nothing named, nothing decided"
    assert ai_screen.language_refusal({"verdict": "keep"}, mine) is None, "an answer from before the fields"
    assert ai_screen.language_refusal({"posting_languages": ["polish"]}, []) is None, "no languages in the profile"
    assert ai_screen.language_refusal(None, mine) is None


def test_the_system_prompt_names_the_persons_languages_and_its_hash_covers_them(isolated_data_dir):
    with db.session():
        pass
    seen = []

    def call(system_prompt, text, workdir=None):
        seen.append(system_prompt.read_text(encoding="utf-8"))
        return {"is_job_posting": True, "work_arrangement": "remote", "location_ok": "yes",
                "role_fit": "good", "posting_languages": ["english"], "required_languages": [],
                "verdict": "keep", "reason": "ok"}, 0.0

    ai_screen.screen({"a": _record("a")}, "ftf", "brief", call=call)
    assert "The person reads, writes and speaks only: English, Russian." in seen[0], "from the fixture profile"
    assert ai_screen.brief_hash("brief", ["english"]) != ai_screen.brief_hash("brief", ["english", "russian"])
    assert ai_screen.brief_hash("brief", []) == ai_screen.brief_hash("brief")
    assert {"posting_languages", "required_languages"} <= set(ai_screen.SCHEMA["required"])
