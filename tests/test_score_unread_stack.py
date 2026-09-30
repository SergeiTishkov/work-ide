"""A stack nobody has read is not a stack that does not fit.

Found 2026-10-01: of 1510 vacancies new in one run, 1100 arrived with no
description, and 238 developer titles among them ("Frontend Developer",
"Software Engineer") were refused as "not a .NET/JS role" — a verdict on text
nobody had. They stay refused, but as STACK_UNREAD and `description_wanted`,
so enrich_descriptions reads them and the rescore decides. Also here: the
title gate's two misses from the same run, ".NET and Umbraco Developer" and
"Sr. Dot Net Developer"."""
import pytest

import score
from test_score import CRITERIA, PROFILE, make_vacancy


def _score(**overrides):
    return score.score_vacancy(make_vacancy(**overrides), CRITERIA, PROFILE)


@pytest.mark.parametrize("title", [
    "Frontend Developer", "Software Engineer", "Full-Stack Engineer", "Senior Software Developer",
])
def test_a_developer_title_with_no_text_waits_for_its_description(title):
    r = _score(title=title)
    assert score.STACK_UNREAD in r["dealbreakers"]
    assert r["classification"] == "rejected", "hundreds a day must not flood the shortlist"
    assert r["description_wanted"] is True


def test_once_the_text_is_there_it_decides():
    r = _score(title="Software Engineer",
               description_text="We build our back office in C#, ASP.NET and SQL Server.")
    assert score.STACK_UNREAD not in r["dealbreakers"]
    assert r["classification"] != "rejected"
    assert r["description_wanted"] is False

    r = _score(title="Software Engineer",
               description_text="A Go and Rust shop: distributed systems in Go.")
    assert score.STACK_UNREAD not in r["dealbreakers"]
    assert any(d.startswith("stack: not a") for d in r["dealbreakers"])
    assert r["description_wanted"] is False


@pytest.mark.parametrize("overrides", [
    {"title": "Java Developer"},                           # the title names a stack
    {"title": "Software Engineer", "tags": ["SAP"]},       # the board's tags do
])
def test_a_named_foreign_stack_is_a_real_answer(overrides):
    r = _score(**overrides)
    assert score.STACK_UNREAD not in r["dealbreakers"]
    assert r["classification"] == "rejected"
    assert r["description_wanted"] is False


def test_no_request_for_a_title_that_is_not_a_developer_s():
    r = _score(title="Fiber Splicer")
    assert r["classification"] == "rejected"
    assert r["description_wanted"] is False


def test_another_real_objection_makes_reading_pointless():
    r = _score(title="Software Engineer", location_raw="Onsite - Austin, TX", remote=False)
    assert score.STACK_UNREAD in r["dealbreakers"]
    assert any(d.startswith("location:") and d != score.REMOTE_UNCONFIRMED
               for d in r["dealbreakers"])
    assert r["description_wanted"] is False


def test_a_title_naming_the_core_stack_passes_the_title_gate():
    r = _score(title=".NET and Umbraco Developer")
    assert not any("outside the core/strong stack" in d for d in r["dealbreakers"])
    assert r["classification"] != "rejected"


def test_a_title_naming_only_the_strong_tier_does_not():
    r = _score(title="Java + React Full-Stack Developer",
               description_text="Java 17, Spring Boot and React.")
    assert any("outside the core/strong stack (java" in d for d in r["dealbreakers"])


@pytest.mark.parametrize("title", ["Sr. Dot Net Developer", "Dot-Net Developer"])
def test_dot_net_spelled_out_is_dot_net(title):
    r = _score(title=title)
    assert not any(d.startswith("stack:") for d in r["dealbreakers"])
    assert ".NET" in r["score_breakdown"]["stack_fit"]["primary_language_hits"]
