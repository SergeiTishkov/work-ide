"""
Finding where a person can apply directly, and refusing to invent it.

Asked for by the owner 2026-08-12: for the top of the shortlist, try to find a
way to apply that is not the board — and say plainly when there is none.

The two traps in this file are both mistakes that were actually made while
building it, on the first and second attempts respectively:

  1. Every one of these systems answers HTTP 200 to a slug nobody owns. A first
     version trusted the status code and reported an application channel for
     18 companies out of 18 — including "tatittechnolgies", a typo in the
     vacancy's own company name.
  2. Trusting a board because its slug matched found Accenture at
     accenture.recruitee.com: two postings, one of them literally titled
     "Senior Marketer (Sample)". A squatted trial account, offered to the owner
     as the place to send his CV.

No network here: the fetch is replaced, as everywhere else in this suite.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import apply_channels  # noqa: E402


def _vacancy(company, title, score=60, classification="hot_lead", description="", **extra):
    record = {
        "company": company,
        "title": title,
        "description_text": description,
        "computed": {"score": score, "classification": classification},
    }
    record.update(extra)
    return record


def _boards(mapping):
    """Replaces the network with a fixed set of boards, keyed by API url."""
    def fake(url, timeout):
        return mapping.get(url)
    return fake


GREENHOUSE = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
RECRUITEE = "https://{slug}.recruitee.com/api/offers/"


# --- the two traps ---------------------------------------------------------

def test_a_board_with_no_openings_is_not_a_channel(monkeypatch):
    """The first mistake: 200 with an empty list is what every one of these
    systems returns for a company that is not on it."""
    monkeypatch.setattr(apply_channels, "_fetch_json",
                        _boards({GREENHOUSE.format(slug="ghostcorp"): {"jobs": []}}))

    found = apply_channels.find_channels(_vacancy("Ghostcorp", "Senior .NET Developer"))

    assert found["direct_apply_url"] is None
    assert found["board_url"] is None


def test_a_squatted_trial_account_is_not_the_companys_board(monkeypatch):
    """The second mistake, quoted from the real response: Accenture — a company
    of several hundred thousand people — "found" on a Recruitee board holding a
    sales executive and a "Senior Marketer (Sample)"."""
    monkeypatch.setattr(apply_channels, "_fetch_json", _boards({
        RECRUITEE.format(slug="accenture"): {"offers": [
            {"title": "sales executive", "careers_url": "https://accenture.recruitee.com/o/sales-executive"},
            {"title": "Senior Marketer (Sample)", "careers_url": "https://accenture.recruitee.com/o/senior-marketer-sample"},
        ]},
    }))

    found = apply_channels.find_channels(
        _vacancy("Accenture Southeast Asia", ".Net Developer"))

    assert found["board_url"] is None, "a trial account must not be offered as a channel"


# --- what a real find looks like -------------------------------------------

def test_the_exact_vacancy_on_the_employers_own_system(monkeypatch):
    """The best possible result, and a real one: Ypto's ".NET developer" is on
    their Recruitee board, so the link opens the application form itself."""
    monkeypatch.setattr(apply_channels, "_fetch_json", _boards({
        RECRUITEE.format(slug="ypto"): {"offers": [
            {"title": "Frontend developer", "careers_url": "https://ypto.recruitee.com/o/frontend"},
            {"title": "ASP.NET MVC C# / .NET developer",
             "careers_url": "https://ypto.recruitee.com/o/aspnet-mvc-c-net-developer"},
            {"title": "Data engineer", "careers_url": "https://ypto.recruitee.com/o/data-engineer"},
        ]},
    }))

    found = apply_channels.find_channels(
        _vacancy("Ypto", "ASP.NET MVC C# /.NET Developer"))

    assert found["direct_apply_url"] == "https://ypto.recruitee.com/o/aspnet-mvc-c-net-developer"
    assert found["board_provider"] == "recruitee"


def test_a_title_match_is_trusted_even_on_a_small_board(monkeypatch):
    """The minimum-openings rule exists only for boards we could not confirm.
    A vacancy found by title proves the board belongs to the employer, so a
    small board is fine — plenty of real companies have two jobs open."""
    monkeypatch.setattr(apply_channels, "_fetch_json", _boards({
        GREENHOUSE.format(slug="tinyshop"): {"jobs": [
            {"title": "Senior .NET Developer", "absolute_url": "https://boards.greenhouse.io/tinyshop/jobs/1"},
        ]},
    }))

    found = apply_channels.find_channels(_vacancy("TinyShop", "Senior .NET Developer"))

    assert found["direct_apply_url"] == "https://boards.greenhouse.io/tinyshop/jobs/1"


def test_a_different_role_on_the_same_board_is_not_our_vacancy(monkeypatch):
    """The board is real and the company is right, but this vacancy is not on
    it — which happens when a posting came through an agency. That is reported
    as the weaker fact it is, not as a direct link."""
    monkeypatch.setattr(apply_channels, "_fetch_json", _boards({
        GREENHOUSE.format(slug="realcorp"): {"jobs": [
            {"title": "Marketing Manager", "absolute_url": "https://boards.greenhouse.io/realcorp/jobs/1"},
            {"title": "Account Executive", "absolute_url": "https://boards.greenhouse.io/realcorp/jobs/2"},
            {"title": "Office Administrator", "absolute_url": "https://boards.greenhouse.io/realcorp/jobs/3"},
        ]},
    }))

    found = apply_channels.find_channels(_vacancy("Realcorp", "Senior .NET Developer"))

    assert found["direct_apply_url"] is None
    assert found["board_url"] == "https://boards.greenhouse.io/realcorp"


# --- addresses the employer published themselves ---------------------------

def test_an_address_written_into_the_vacancy_is_kept(monkeypatch):
    """"send your CV to careers@…" is the employer publishing their own way in.
    Three of the eighteen hot leads had one."""
    monkeypatch.setattr(apply_channels, "_fetch_json", _boards({}))

    found = apply_channels.find_channels(_vacancy(
        "Assemblysoft", "ASP.NET Developer",
        description="Send your CV to careers@assemblysoft.com and we will be in touch."))

    assert found["emails"] == ["careers@assemblysoft.com"]


def test_boilerplate_addresses_are_not_a_way_to_apply(monkeypatch):
    """A description also carries legal footers and tracking. Nobody gets a job
    by writing to privacy@."""
    monkeypatch.setattr(apply_channels, "_fetch_json", _boards({}))

    found = apply_channels.find_channels(_vacancy(
        "Somecorp", "Senior .NET Developer",
        description=("Questions about our policy: privacy@somecorp.com. "
                     "Do not reply to noreply@somecorp.com. "
                     "Applications: jobs@somecorp.com")))

    assert found["emails"] == ["jobs@somecorp.com"]


# --- "not found" is a result, and it is recorded ---------------------------

def test_nothing_found_is_still_written_down_with_a_date(monkeypatch):
    """The owner asked for this explicitly: if nothing was found, say so. It
    also stops the same fruitless search running on every cycle."""
    monkeypatch.setattr(apply_channels, "_fetch_json", _boards({}))
    vacancies = {"a": _vacancy("Nowhere Ltd", "Senior .NET Developer")}

    stats = apply_channels.collect(vacancies, threshold=38)

    assert stats["nothing"] == 1
    assert vacancies["a"]["apply_channels"]["checked_at"]
    assert vacancies["a"]["apply_channels"]["direct_apply_url"] is None

    again = apply_channels.collect(vacancies, threshold=38)
    assert again["considered"] == 0, "a recorded search must not repeat every run"


# --- who is in scope -------------------------------------------------------

def test_only_the_top_of_the_shortlist_is_worth_the_requests():
    """The owner's scope: hot_lead, plus anything scoring as high that is
    waiting in another class for a human decision. Not the tail."""
    vacancies = {
        "hot": _vacancy("A", "t", score=60, classification="hot_lead"),
        "unconfirmed_high": _vacancy("B", "t", score=88, classification="remote_unconfirmed"),
        "unconfirmed_low": _vacancy("C", "t", score=20, classification="remote_unconfirmed"),
        "worth": _vacancy("D", "t", score=30, classification="worth_a_look"),
        "rejected": _vacancy("E", "t", score=90, classification="rejected"),
    }
    assert set(apply_channels.worklist(vacancies, threshold=38)) == {
        "hot", "unconfirmed_high"}


def test_a_dead_link_is_not_worth_a_single_request():
    """36 of the 260 vacancies in view on 2026-08-11 had already stopped
    accepting applications."""
    vacancies = {
        "closed": _vacancy("A", "t", link_check={"status": "dead"}),
        "open": _vacancy("B", "t"),
    }
    assert apply_channels.worklist(vacancies, threshold=38) == ["open"]


def test_slug_candidates_drop_the_legal_tail():
    """"JAC RECRUITMENT PTE. LTD." is not a board slug; "jacrecruitment" might
    be."""
    assert apply_channels.slug_candidates("JAC RECRUITMENT PTE. LTD.")[0] == "jacrecruitment"
    assert "aubay" in apply_channels.slug_candidates("Aubay Belgium")


def test_the_summary_counts_what_has_nowhere_to_apply():
    """So that "we found nothing for 40 of them" is visible rather than
    implied by absence."""
    vacancies = {
        "a": _vacancy("A", "t", apply_channels={"direct_apply_url": "https://x/1"}),
        "b": _vacancy("B", "t", apply_channels={"direct_apply_url": None,
                                                "board_url": "https://x/b"}),
        "c": _vacancy("C", "t", apply_channels={"direct_apply_url": None,
                                                "board_url": None, "emails": []}),
        "d": _vacancy("D", "t"),
    }
    assert apply_channels.summary(vacancies, threshold=38) == {
        "in_scope": 4, "direct": 1, "board": 1, "email_only": 0,
        "nothing": 1, "not_checked": 1,
    }


# --- a slug is a guess, and a guess has to be confirmed ---------------------

def test_a_board_belonging_to_a_different_company_is_refused(monkeypatch):
    """The third mistake, and the reason the board's own name is checked.

    "ITS Group Benelux" was offered boards.greenhouse.io/its — which belongs to
    Intelligent Technical Solutions. "MCS (FE) PTE. LTD." was offered
    boards.greenhouse.io/mcs, the board of Minnesota Cannabis Services. Both
    came from taking the first word of the name as a slug.
    """
    monkeypatch.setattr(apply_channels, "_fetch_json", _boards({
        GREENHOUSE.format(slug="its"): {"jobs": [
            {"title": "Alignment Engineer (Remote)", "absolute_url": "https://x/1"},
            {"title": "Centralized Services Engineer", "absolute_url": "https://x/2"},
            {"title": "Client Account Manager", "absolute_url": "https://x/3"},
        ]},
        "https://boards-api.greenhouse.io/v1/boards/its":
            {"name": "Intelligent Technical Solutions"},
    }))

    found = apply_channels.find_channels(
        _vacancy("ITS Group Benelux", "Back-end C# .NET Developer"))

    assert found["board_url"] is None


def test_a_board_whose_name_matches_is_accepted(monkeypatch):
    """The other direction: Aubay Belgium really does hire at
    aubay.recruitee.com, and the board says so itself."""
    monkeypatch.setattr(apply_channels, "_fetch_json", _boards({
        RECRUITEE.format(slug="aubay"): {"offers": [
            {"title": "Java Developer", "company_name": "Aubay", "careers_url": "https://x/1"},
            {"title": "Business Analyst", "company_name": "Aubay", "careers_url": "https://x/2"},
            {"title": "Test Engineer", "company_name": "Aubay", "careers_url": "https://x/3"},
        ]},
    }))

    found = apply_channels.find_channels(
        _vacancy("Aubay Belgium", "Senior Dotnet Developer"))

    assert found["board_url"] == "https://aubay.recruitee.com/"


def test_sharing_only_a_generic_word_is_not_a_match():
    """"Evolution Recruitment Solutions" and "Nordic Consulting Group" share
    "consulting" and "group" and nothing else. Those words identify nobody."""
    assert not apply_channels._board_belongs_to(
        "Evolution Recruitment Solutions", "Nordic Consulting Group", False)
    assert apply_channels._board_belongs_to(
        "Accion Labs", "Accion Labs Inc", False)
