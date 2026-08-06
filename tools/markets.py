"""
Labour-market tiers: which countries to search.

WHY THIS IS ITS OWN MODULE
----------------------
The location list is needed by fetchers that can search by country (LinkedIn
above all). Assembling it afresh in each fetcher guarantees they diverge: one
gets updated, another is forgotten.

The country table (`config/derivation/market_tiers.yaml`) is shared by every
identity — it describes the objective state of the market. Which tiers to use
belongs to the identity (`profile.target_markets`), because that is already a
preference of one particular search.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

TIERS_FILE = "market_tiers.yaml"


def load_tiers() -> dict:
    path = common.SHARED_CONFIG_DIR / "derivation" / TIERS_FILE
    return (common.load_yaml(path) or {}).get("tiers", {})


def tier_countries(tier_name: str) -> List[str]:
    tier = load_tiers().get(tier_name) or {}
    return [c.get("name") for c in (tier.get("countries") or []) if c.get("name")]


def target_locations(profile: dict) -> List[str]:
    """The countries to search, per the identity's profile.

    An empty result is not a configuration error but a deliberate choice: if
    the identity named no tier, the country fetchers simply do nothing, and
    their yield shows up in state.json as zero.
    """
    cfg = (profile or {}).get("target_markets") or {}
    names: List[str] = []

    for tier in cfg.get("tiers") or []:
        for country in tier_countries(tier):
            if country not in names:
                names.append(country)

    for extra in cfg.get("extra_locations") or []:
        if extra not in names:
            names.append(extra)

    return names


def avoided_countries(profile: dict) -> List[str]:
    """Countries the search steers around: net exporters of development work,
    plus ones excluded for practical reasons.

    Needed not by the fetchers but by scoring and the report — to explain to a
    person why a vacancy from such a country did not make the shortlist.
    """
    del profile  # the list is the same for everyone: it is about the market
    return tier_countries("exporter_avoid") + tier_countries("excluded_practical")
