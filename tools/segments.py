"""
Splitting one identity's shortlist into several, by market.

WHY
---
A person reads one shortlist at a time and decides where to spend an evening on
applications. A single file sorted by score mixes a Singapore agency posting
with a UK contract at four times the rate, and leaves the reader to do the
sorting the machine could have done. Asked for by the owner 2026-08-12: "a
working identity can produce several shortlists for the different countries the
person asked about".

WHAT IS SHARED AND WHAT IS PERSONAL
-----------------------------------
Two files, and the split between them is the point:

  config/derivation/market_groups.yaml   which countries form a group.
                                         Geography. True for everybody.
  <prefix>_reports.yaml                  which groups deserve a file of their
                                         own. A judgement about this search, so
                                         it lives in the identity and layers
                                         like every other setting
                                         (defaults -> template -> local).

Nothing here ranks a market. An identity that cares about the Gulf and not
about Canada says so in its own file and the machinery is unchanged — which is
the test from CLAUDE.md section 13 for having put a change in the right layer.

THE ONE GROUP THAT IS NOT A PLACE
---------------------------------
`worldwide` holds the vacancies whose employer named no country at all. For
somebody contracting from outside every market in the table, that is not the
leftovers — it is the only group where geography is not an obstacle to begin
with. It is deliberately first in the catalogue and first in the default
segmentation.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

GROUPS_PATH = common.ROOT / "config" / "derivation" / "market_groups.yaml"

# The group a vacancy falls into when its hiring country is known but belongs
# to no group in the catalogue. Not an error: the catalogue names the markets
# somebody wanted split out, and the world is larger than that.
OTHER_GROUP = "other"

_GROUPS_CACHE = {}


def load_groups() -> dict:
    """{group key: {name, countries, matches_missing_country}}."""
    if not _GROUPS_CACHE:
        data = common.load_yaml(GROUPS_PATH) or {}
        _GROUPS_CACHE.update(data.get("groups") or {})
    return _GROUPS_CACHE


def _country_index() -> dict:
    """{normalised country name: group key}. Built from the catalogue."""
    index = {}
    for key, group in load_groups().items():
        for country in group.get("countries") or []:
            index[common.normalize_for_matching(country)] = key
    return index


def group_of(country: Optional[str]) -> str:
    """Which market group a hiring country belongs to.

    `None` — the employer named no country — is a group in its own right rather
    than a missing value. See the module docstring.
    """
    if not country:
        for key, group in load_groups().items():
            if group.get("matches_missing_country"):
                return key
        return OTHER_GROUP
    return _country_index().get(common.normalize_for_matching(country), OTHER_GROUP)


def group_name(key: str) -> str:
    if key == OTHER_GROUP:
        return "Other markets"
    return (load_groups().get(key) or {}).get("name") or key


class Segment:
    """One report file: which groups it holds, and what it is called.

    Three kinds, and they are exclusive:
      * `groups`     — the named market groups;
      * `rest`       — whatever no other segment claimed. Computed from the
                       rest of the configuration rather than listed, so that
                       adding a segment can never silently leave a market out
                       of every file;
      * `everything` — the whole shortlist: the report as it was before any of
                       this existed.
    """

    def __init__(self, slug: str, name: str, groups=(), rest: bool = False,
                 everything: bool = False, default: bool = False):
        self.slug = slug
        self.name = name
        self.groups = tuple(groups)
        self.rest = rest
        self.everything = everything
        # Additionally written to <prefix>_latest.md. Exactly one segment
        # should set it: that path is what RUNBOOK.md, the archive and a
        # person's muscle memory all point at, and it has to keep meaning
        # something.
        self.default = default

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"<Segment {self.slug!r} groups={self.groups} rest={self.rest}>"

    def holds(self, group_key: str, claimed: frozenset) -> bool:
        if self.everything:
            return True
        if self.rest:
            return group_key not in claimed
        return group_key in self.groups


def _claimed_groups(segments: List[Segment]) -> frozenset:
    claimed = set()
    for segment in segments:
        if not (segment.rest or segment.everything):
            claimed.update(segment.groups)
    return frozenset(claimed)


def parse_segments(config: dict) -> List[Segment]:
    """Segments from a resolved `reports` document.

    An unknown group key fails loudly. Producing an empty file instead would be
    exactly the kind of quiet wrongness this project keeps having to dig out
    afterwards.
    """
    known = set(load_groups()) | {OTHER_GROUP}
    segments = []
    for entry in (config or {}).get("segments") or []:
        groups = tuple(entry.get("groups") or ())
        unknown = [g for g in groups if g not in known]
        if unknown:
            raise ValueError(
                f"segment '{entry.get('slug')}' names unknown market group(s) "
                f"{unknown}; known groups are {sorted(known)}")
        segments.append(Segment(
            slug=entry.get("slug") or "",
            name=entry.get("name") or entry.get("slug") or "",
            groups=groups,
            rest=bool(entry.get("rest")),
            everything=bool(entry.get("everything")),
            default=bool(entry.get("default")),
        ))
    return segments


def load_segments(prefix: Optional[str] = None) -> List[Segment]:
    """The active identity's segmentation, resolved through the usual layers."""
    import settings

    prefix = prefix or (common.ACTIVE_IDENTITY or "")
    config, _ = settings.resolve("reports", prefix)
    return parse_segments(config)


def split(vacancies: list, segments: List[Segment], country_of) -> dict:
    """{segment slug: [vacancies]}, in the order the segments were configured.

    `country_of` is passed in rather than imported so that this module knows
    nothing about how a hiring country is worked out — that lives in the
    report, and it is a hard problem of its own.
    """
    claimed = _claimed_groups(segments)
    buckets = {segment.slug: [] for segment in segments}
    for vacancy in vacancies:
        key = group_of(country_of(vacancy))
        for segment in segments:
            if segment.holds(key, claimed):
                buckets[segment.slug].append(vacancy)
    return buckets


def counts_by_group(vacancies: list, country_of) -> dict:
    """{group key: how many}. For showing a person what the split cost them."""
    tally = {}
    for vacancy in vacancies:
        key = group_of(country_of(vacancy))
        tally[key] = tally.get(key, 0) + 1
    return tally
