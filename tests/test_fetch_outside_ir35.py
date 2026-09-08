"""
Outside IR35 Jobs — small, narrow, and narrow on purpose.

Every posting is a UK contract declared outside IR35, which is the shape of
work a contractor invoicing from another country can actually take: inside-IR35
work is taxed as employment and usually run through a UK umbrella company.

The whole board is 50 contracts on one page, so there is no pagination — and
only two of the fifty were .NET on the day this was written. That is the trade:
a tiny source where almost everything is the right KIND of work, against a
large one where almost nothing is.

The snapshot is trimmed from a live page of 2026-09-08. Two details in it are
load-bearing and must not be tidied away:

  * the utility CSS classes, which is why the parser finds cards by the SHAPE
    of their href (`/job/<cuid>`) rather than by a class list that changes
    whenever the design does;
  * the React comment markers (`<!-- -->`) that the framework renders between
    text nodes — they sit right between the company and the location, and a
    parser that does not strip them produces "Experis UK · UK" as one word.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import fetch_outside_ir35 as oir  # noqa: E402

SNAPSHOT = """
<div class="mt-6 space-y-3">
<a class="group block rounded-lg border border-border bg-card p-4 transition-colors" href="/job/cmtnuww5o00hukj5vwcks7kbi">
  <div class="flex items-start justify-between gap-4">
    <div class="flex min-w-0 gap-3">
      <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-md">E</div>
      <div class="min-w-0">
        <h3 class="truncate font-sans text-base font-semibold leading-tight">Senior .Net Developer</h3>
        <p class="mt-0.5 truncate text-sm text-muted-foreground">Exalto Consulting Ltd<!-- --> · <!-- -->London</p>
      </div>
    </div>
    <div class="shrink-0 text-right">
      <span class="tabular text-base font-semibold">£425<span class="ml-0.5 text-xs font-normal">/<!-- -->day</span></span>
      <p class="mt-0.5 text-xs text-muted-foreground tabular">2d ago</p>
    </div>
  </div>
  <div class="mt-3 flex flex-wrap items-center gap-1.5">
    <span class="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs">Outside IR35 · per client</span>
    <span class="inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs"><svg aria-hidden="true" data-icon="house-laptop" class="svg-inline--fa h-3 w-3"><path fill="currentColor" d="M224.8 5.4c8.8-7.2"/></svg>Remote</span>
    <span class="inline-flex items-center rounded-md border px-2 py-0.5 text-xs">6 months</span>
  </div>
</a>
<a class="group block rounded-lg border border-border bg-card p-4" href="/job/cmt0zvdpz002xkj5vcf0b3gnc">
  <div class="flex items-start justify-between gap-4">
    <div class="flex min-w-0 gap-3">
      <div class="min-w-0">
        <h3 class="truncate font-sans text-base font-semibold">.Net Developer</h3>
        <p class="mt-0.5 truncate text-sm text-muted-foreground">Oscar Associates (UK)<!-- --> · <!-- -->Nottingham (NG1)</p>
      </div>
    </div>
    <div class="shrink-0 text-right">
      <span class="tabular text-base font-semibold">£500–£600<span class="ml-0.5 text-xs font-normal">/<!-- -->day</span></span>
      <p class="mt-0.5 text-xs text-muted-foreground tabular">1w ago</p>
    </div>
  </div>
  <div class="mt-3 flex flex-wrap items-center gap-1.5">
    <span class="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs">Outside IR35 · per client</span>
    <span class="inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs"><svg data-icon="building"><path d="M0 0"/></svg>Hybrid</span>
  </div>
</a>
</div>
"""


def test_the_snapshot_parses_into_complete_records():
    records, note = oir.parse_page(SNAPSHOT)

    assert note is None
    assert len(records) == 2

    first = records[0]
    assert first["title"] == "Senior .Net Developer"
    assert first["external_id"] == "outside_ir35:cmtnuww5o00hukj5vwcks7kbi"
    assert first["url"] == "https://www.outsideir35jobs.com/job/cmtnuww5o00hukj5vwcks7kbi"


def test_the_react_comment_markers_are_stripped():
    """The framework renders <!-- --> between text nodes, and they sit exactly
    between the company and the location. A parser that leaves them in produces
    one unusable string instead of two facts."""
    records, _ = oir.parse_page(SNAPSHOT)

    assert records[0]["company"] == "Exalto Consulting Ltd"
    assert records[0]["location_raw"] == "London"
    assert records[1]["company"] == "Oscar Associates (UK)"
    assert records[1]["location_raw"] == "Nottingham (NG1)"


def test_the_day_rate_keeps_its_unit():
    """"£425" alone is ambiguous; "£425/day" is a contract rate. The scoring
    reads the string, so the unit has to survive the split across two tags."""
    records, _ = oir.parse_page(SNAPSHOT)

    assert records[0]["salary_raw"] == "£425/day"
    assert records[1]["salary_raw"] == "£500–£600/day"


def test_the_mode_badge_becomes_the_workplace_type():
    records, _ = oir.parse_page(SNAPSHOT)

    assert records[0]["workplace_type"] == "remote"
    assert records[1]["workplace_type"] == "hybrid"


def test_every_posting_is_tagged_outside_ir35():
    """The board's whole reason to exist, and the thing that makes a UK
    contract takeable from another country at all."""
    records, _ = oir.parse_page(SNAPSHOT)

    assert all("Outside IR35" in r["tags"] for r in records)


def test_relative_dates_become_real_ones():
    from datetime import datetime, timedelta, timezone

    today = datetime.now(timezone.utc).date()
    records, _ = oir.parse_page(SNAPSHOT)

    assert records[0]["posted_at"] == (today - timedelta(days=2)).isoformat()
    assert records[1]["posted_at"] == (today - timedelta(days=7)).isoformat()


def test_remote_is_never_invented():
    records, _ = oir.parse_page(SNAPSHOT)

    assert all(r["remote"] is None for r in records)


# --- the obligation every HTML parser in this project carries --------------

def test_changed_markup_returns_zero_and_an_explicit_error():
    """The href shape is what the parser hangs on, so this breaks that."""
    broken = SNAPSHOT.replace("<h3", "<h4").replace("</h3>", "</h4>")

    records, note = oir.parse_page(broken)

    assert records == []
    assert note and "markup changed" in note and "2 cards" in note


def test_a_page_with_no_cards_is_not_an_error():
    records, note = oir.parse_page('<div class="mt-6"></div>')

    assert records == [] and note is None


def test_utility_class_names_are_not_what_the_parser_hangs_on():
    """The site is built with utility CSS: a class list describes appearance
    and changes whenever the design does. A job's URL does not."""
    import re as _re

    patterns = [v.pattern for v in vars(oir).values() if isinstance(v, _re.Pattern)]
    for pattern in patterns:
        for fragile in ("rounded-lg", "text-muted-foreground", "font-semibold",
                        "space-y-3", "shrink-0"):
            assert fragile not in pattern, (
                f"a utility class reached a parser regex: {pattern}")
    assert any("/job/" in p for p in patterns), (
        "the job URL shape is the stable anchor and should be what is matched")


def test_the_com_domain_is_the_one_that_exists():
    """Only outsideir35jobs.com resolves. The .co.uk is not in DNS at all, and
    a fetcher pointed there fails with a connection error that reads like the
    whole site being down."""
    assert oir.BASE_URL == "https://www.outsideir35jobs.com"


def test_one_failing_query_does_not_stop_the_others(monkeypatch):
    def fake_page(query, timeout):
        if query == "boom":
            raise RuntimeError("network")
        return SNAPSHOT

    monkeypatch.setattr(oir, "_fetch_page", fake_page)

    records, note = oir.fetch(queries=["boom", "fine"])

    assert len(records) == 2
    assert note and "boom" in note
