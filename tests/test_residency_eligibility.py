"""
Can a contractor sitting where this person sits actually take the work?

Added 2026-08-12, in the direction the owner asked the project to move:

    "Remote" and "Worldwide Remote" are fundamentally different categories.
    Only the second satisfies the requirement.

    "$100/hour — Remote — US" is LESS VALUABLE than
    "$70/hour — Remote Worldwide — Contractor",
    because the first cannot realistically be performed from Georgia.

That is a second axis, not a bigger number. A vacancy can fit the stack
perfectly, pay well, be genuinely remote — and be unreachable because "remote"
meant "remote within Canada". Points cannot express it: a high score with no
eligibility cannot be acted on at all, and averaging the two together hides
exactly the distinction the owner is asking for.

Four verdicts: CONFIRMED, LIKELY, UNKNOWN, NO.

The verdict is DERIVED from what the location gate already extracted, never by
matching the text a second time. Two independent implementations of "is this
worldwide" is precisely how two halves of a configuration end up disagreeing
without any test noticing (docs/OVERRIDES.md).

The country in these tests comes from the fixture profile, not from the code:
the machinery is the same for a person in Brazil or in Finland.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import score  # noqa: E402

from test_score import CRITERIA, PROFILE, make_vacancy  # noqa: E402

OWNER_COUNTRY = (PROFILE.get("owner") or {}).get("location", {}).get("country")


def _verdict(**kwargs):
    kwargs.setdefault("remote", True)
    r = score.score_vacancy(make_vacancy(**kwargs), CRITERIA, PROFILE)
    return r["residency_eligibility"], r


def test_the_fixture_profile_actually_states_a_country():
    """Every test below is meaningless without one, and a silent empty country
    would make them all pass by accident."""
    assert OWNER_COUNTRY, "the frozen fixture profile must declare owner.location.country"


# --- CONFIRMED: the employer names this person's country -------------------

def test_the_employer_naming_this_country_among_where_they_hire():
    """The strongest thing a posting can say, and the only verdict that does
    not rest on inference."""
    verdict, r = _verdict(
        title="Senior .NET Developer",
        location_raw="Anywhere in the World",
        description_text=(
            "Fully remote worldwide. Legacy C#, ASP.NET and SQL Server. "
            f"We hire contractors in {OWNER_COUNTRY}, Portugal and Poland."
        ),
    )
    assert verdict == score.ELIGIBILITY_CONFIRMED, r["residency_eligibility_reason"]
    assert OWNER_COUNTRY in r["residency_eligibility_reason"]


def test_the_country_named_far_from_any_hiring_phrase_is_not_confirmation():
    """The reverse guard, and the reason a bare country name is not enough.

    For this project's first owner it is not a hypothetical: "Georgia" is a US
    state as well as a country, and a posting in Atlanta is not an offer to
    hire in Tbilisi.
    """
    verdict, r = _verdict(
        title="Senior .NET Developer",
        location_raw="Anywhere in the World",
        description_text=(
            "Fully remote worldwide. C#, ASP.NET and SQL Server. Our office "
            f"dog is named after {OWNER_COUNTRY}, which has nothing to do with "
            "where you work from, and the team is spread across many time "
            "zones with no particular centre of gravity anywhere at all."
        ),
    )
    assert verdict != score.ELIGIBILITY_CONFIRMED, r["residency_eligibility_reason"]


# --- LIKELY: worldwide, or an international contractor arrangement ----------

def test_an_explicitly_worldwide_posting_is_likely():
    verdict, r = _verdict(
        title="Senior .NET Developer",
        location_raw="Anywhere in the World",
        description_text=(
            "Work from anywhere in the world. Legacy C#, ASP.NET and SQL "
            "Server maintenance."
        ),
    )
    assert verdict == score.ELIGIBILITY_LIKELY, r["residency_eligibility_reason"]


def test_a_contractor_arrangement_is_likely():
    """An employer engaging contractors rather than payrolled staff is the
    arrangement that makes a border crossable at all."""
    verdict, r = _verdict(
        title="Senior .NET Developer",
        location_raw="Remote",
        description_text=(
            "Remote freelance contractor engagement, invoiced monthly. Legacy "
            "C#, ASP.NET and SQL Server."
        ),
    )
    assert verdict == score.ELIGIBILITY_LIKELY, r["residency_eligibility_reason"]


# --- UNKNOWN: remote, but from where? --------------------------------------

def test_remote_with_nothing_said_about_where_from_is_unknown():
    """The category the owner asked to be kept apart by name. "Fully remote",
    "100% remote" and "remote-first" say nothing whatever about eligibility,
    and treating them as worldwide is the mistake this axis exists to stop."""
    verdict, r = _verdict(
        title="Senior .NET Developer",
        location_raw="Remote",
        description_text=(
            "100% remote, remote-first company with a distributed team. "
            "Maintain a legacy ASP.NET and SQL Server platform in C#."
        ),
    )
    assert verdict == score.ELIGIBILITY_UNKNOWN, r["residency_eligibility_reason"]


def test_a_vacancy_nobody_called_remote_is_unknown_not_no():
    """It is unknown, not refused: silence about the arrangement is not the
    employer refusing anybody, and the same reasoning already governs the
    remote_unconfirmed class."""
    verdict, r = _verdict(
        remote=None,
        title="Senior .NET Developer",
        location_raw="Toronto, Ontario, Canada",
        description_text=(
            "Design and maintain enterprise applications using .NET Core, "
            "ASP.NET MVC, C# and SQL Server."
        ),
    )
    assert verdict == score.ELIGIBILITY_UNKNOWN
    assert r["classification"] == "remote_unconfirmed"


# --- NO: restricted to somewhere this person is not ------------------------

def test_a_country_restricted_remote_role_is_not_eligible():
    """The exact case the owner wrote out: "Remote — US" is not worldwide
    remote, however well it pays."""
    verdict, r = _verdict(
        title="Senior .NET Developer",
        location_raw="Remote, United States",
        description_text=(
            "Remote within the United States. Candidates must be authorized "
            "to work in the United States. C#, ASP.NET, SQL Server. "
            "$100 per hour."
        ),
    )
    assert verdict == score.ELIGIBILITY_NO, r["residency_eligibility_reason"]


def test_a_hybrid_role_is_not_eligible():
    verdict, r = _verdict(
        title="Senior .NET Developer",
        location_raw="Hybrid",
        description_text="Legacy C# and SQL Server work.",
    )
    assert verdict == score.ELIGIBILITY_NO


# --- the axis really is independent of the score ---------------------------

def test_a_high_score_does_not_imply_eligibility():
    """The whole reason this is not a scoring component. If it were points, a
    strong stack match would paper over an impossible location — which is
    exactly what the owner objected to."""
    _, rich_but_closed = _verdict(
        title="Senior .NET Developer",
        location_raw="Remote, United States",
        description_text=(
            "Remote within the United States only. Legacy ASP.NET, C#, SQL "
            "Server, Entity Framework, enterprise on-premise systems. "
            "$100 per hour. Part-time and calm, no on-call."
        ),
    )
    _, modest_but_open = _verdict(
        title="Senior .NET Developer",
        location_raw="Anywhere in the World",
        description_text=(
            "Work from anywhere in the world as a contractor. C# and SQL "
            "Server maintenance. $70 per hour."
        ),
    )
    assert rich_but_closed["residency_eligibility"] == score.ELIGIBILITY_NO
    assert modest_but_open["residency_eligibility"] == score.ELIGIBILITY_LIKELY


def test_every_vacancy_gets_a_verdict_and_a_reason():
    """No silent absence: a missing verdict would read in the report as "fine",
    which is the most expensive possible default here."""
    _, r = _verdict(title="X", location_raw="", description_text="")
    assert r["residency_eligibility"] in score.ELIGIBILITY_ORDER
    assert r["residency_eligibility_reason"]


# --- a region tie written with a preposition -------------------------------

def test_remote_in_latam_is_a_region_tie():
    """Found 2026-08-12 leading the worldwide shortlist at 76: NTT DATA,
    "100% remote in LATAM". The keyword list held "remote latam" and the text
    said "remote in LATAM" — one preposition away, and worth 76 points."""
    verdict, r = _verdict(
        title="Backend Developer (.NET/Azure)",
        location_raw="LATAM",
        description_text=(
            "This is a 100% remote in LATAM position. C#, .NET Core, Azure "
            "and SQL Server."
        ),
    )
    assert verdict == score.ELIGIBILITY_NO, r["residency_eligibility_reason"]
    assert r["classification"] == "rejected"


def test_every_region_in_the_pattern_is_a_tie():
    """EMEA, APAC and North America are named in the owner's brief as examples
    of remote that is not worldwide remote."""
    for region in ("EMEA", "APAC", "North America", "Latin America"):
        verdict, r = _verdict(
            title="Senior .NET Developer",
            location_raw=region,
            description_text=f"Fully remote within {region}. C# and SQL Server.",
        )
        assert verdict == score.ELIGIBILITY_NO, f"{region}: {r['dealbreakers']}"


def test_an_explicit_worldwide_offer_still_outranks_a_region_mention():
    """The reason these patterns sit with the region KEYWORDS rather than in
    hard_dealbreakers. A company that hires worldwide and happens to mention
    where its people already are is not restricting anybody, and rejecting it
    would be the false negative CLAUDE.md section 5 warns about."""
    verdict, r = _verdict(
        title="Senior .NET Developer",
        location_raw="Anywhere in the World",
        description_text=(
            "Work from anywhere in the world. We already have contractors in "
            "LATAM and in APAC. C#, ASP.NET and SQL Server."
        ),
    )
    assert r["classification"] != "rejected", r["dealbreakers"]
    assert verdict == score.ELIGIBILITY_LIKELY, r["residency_eligibility_reason"]


def test_the_word_freelance_does_not_cancel_a_region_tie():
    """A region tie is outranked by evidence that a company can engage across a
    border. A NAMED employer-of-record platform is that; the word "freelance"
    is not.

    Measured 2026-08-12: "Backend Developer (.NET/Azure)" @ NTT DATA led the
    WORLDWIDE shortlist at 76 with "Location Preference: 100% remote in LATAM
    working EST Time Zone" in its own description — the tie cancelled by the
    word "freelance" further down. It was the only vacancy in the entire
    shortlist resting on that override.
    """
    verdict, r = _verdict(
        title="Backend Developer (.NET/Azure)",
        location_raw="LATAM",
        description_text=(
            "Location Preference: 100% remote in LATAM working EST Time Zone. "
            "Duration: 1-Year Assignment, freelance engagement. C#, .NET Core, "
            "Azure and SQL Server."
        ),
    )
    assert verdict == score.ELIGIBILITY_NO, r["residency_eligibility_reason"]
    assert r["classification"] == "rejected"


def test_a_named_employer_of_record_still_outranks_a_region_tie():
    """The other direction, and the reason the override exists at all: a
    company running payroll through an EOR really can engage somebody outside
    the region its team happens to sit in."""
    verdict, r = _verdict(
        title="Senior .NET Developer",
        location_raw="EMEA",
        description_text=(
            "Our team is in EMEA and we hire through Deel as an Employer of "
            "Record, so location is not a constraint. C# and SQL Server."
        ),
    )
    assert r["classification"] != "rejected", r["dealbreakers"]
