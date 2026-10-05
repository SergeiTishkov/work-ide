"""
Which country a vacancy's location names — and whether it names a place at all.

The table is config/derivation/countries.yaml; why it exists is written there.
report.hiring_country asks `country_in`, the market split asks `names_a_place`
when no country was found.

THE TWO KINDS OF "NO COUNTRY" (2026-10-06)
------------------------------------------
"Anywhere", "Remote", "Europe", "CET +/- 3h" name no country on purpose: the
work is not tied to one, and the vacancy belongs under "Worldwide — no country
tie". "Denver", "Calgary", "Multiple locations" name a place this table did not
resolve: the work IS tied to a country, just not one the machine could read.
Until this date both were listed as worldwide, so a shortlist meant for "where
geography is no obstacle" held office jobs in North America. Now the second kind
goes to "Rest of the world" (segments.OTHER_GROUP).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

PLACES_PATH = common.ROOT / "config" / "derivation" / "countries.yaml"

# What a location field says when it names no place. Everything is a single
# word, because the field is split into words: "time zone" is "time" + "zone".
# Regions are here on purpose — "Europe" or "LATAM" is a statement about time
# zones and law, not an office.
UNTIED_WORDS = frozenset("""
    remote remotely anywhere worldwide world wide global globally international
    internationally everywhere distributed fully full work working from home wfh
    online virtual flexible hybrid first friendly team position role
    n a na none not specified unspecified tbd tba
    europe european eu eea emea latam latin america americas apac asia pacific
    africa african middle east mena oceania nordics nordic scandinavia cis balkans
    north south central eastern western east west region regions countries country
    continent continents
    timezone timezones time zone zones utc gmt cet cest eet eest wet west bst est
    edt cst cdt mst mdt pst pdt et pt ct hours hour h hrs overlap
    in the of and or only based any with to plus minus within ok also preferred
""".split())

_WORD_RE = re.compile(r"[^\W\d_]+")
_PARENS_RE = re.compile(r"\([^)]*\)")
_CACHE: dict = {}


def _norm(text: str) -> str:
    return common.normalize_for_matching(text).strip(" .;:-–—/|")


def _table() -> dict:
    if _CACHE:
        return _CACHE
    data = common.load_yaml(PLACES_PATH) or {}
    names, iso2 = {}, {}
    for entry in data.get("countries") or []:
        name = entry["name"]
        for spelling in [name, *(entry.get("aliases") or [])]:
            names.setdefault(_norm(spelling), name)
        if entry.get("iso2"):
            iso2[str(entry["iso2"]).upper()] = name
    region_names, region_codes = {}, {}
    for country, regions in (data.get("regions") or {}).items():
        for code, region in (regions or {}).items():
            region_codes.setdefault(_norm(str(code)), country)
            if region:
                region_names.setdefault(_norm(region), country)
    cities = {}
    for country, spellings in (data.get("cities") or {}).items():
        for city in spellings or []:
            cities.setdefault(_norm(city), country)
    # Longest first: "papua new guinea" before "guinea", "south sudan" before
    # "sudan". Whole words only: "oman" is not in "romania", "niger" not in
    # "nigeria", "us" not in "russia".
    pattern = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    _CACHE.update({
        "names": names, "iso2": iso2, "region_names": region_names,
        "region_codes": region_codes, "cities": cities,
        "word_re": re.compile(rf"(?<![\w.])(?:{pattern})(?![\w])"),
    })
    return _CACHE


def canonical(country: Optional[str]) -> Optional[str]:
    """The table's spelling of a country name or alias, or None."""
    return _table()["names"].get(_norm(country or "")) if country else None


def country_of_code(code: Optional[str]) -> Optional[str]:
    """ "PT" -> "Portugal". For boards that send a code in a field of its own."""
    return _table()["iso2"].get(str(code or "").strip().upper())


def country_in(location: Optional[str]) -> Optional[str]:
    """The country a location names, or None.

    In this order, each a stronger word than the next:
      1. the last part is a country ("Barendrecht, South Holland, Netherlands");
      2. the last part is a state or province by name ("Austin, Texas");
      3. a country named anywhere, as a whole word ("Remote - US", "EMEA,
         Portugal") — the first one in the text;
      4. a city ("Berlin", "San Francisco, Seattle, New York") or a state code
         ("Seattle, WA"). When the two point to different countries ("London,
         ON", "Berlin, DE"), neither is taken.
    """
    if not location or not location.strip():
        return None
    t = _table()
    parts = [_norm(_PARENS_RE.sub(" ", p)) for p in location.split(",")]
    parts = [p for p in parts if p]
    if parts:
        last = parts[-1]
        if last in t["names"]:
            return t["names"][last]
        if last in t["region_names"]:
            return t["region_names"][last]
    found = t["word_re"].search(common.normalize_for_matching(location))
    if found:
        return t["names"][found.group(0)]
    city = next((t["cities"][p] for p in parts if p in t["cities"]), None)
    code = t["region_codes"].get(parts[-1]) if len(parts) > 1 else None
    if city and code and city != code:
        return None
    return city or code


def names_a_place(location: Optional[str]) -> bool:
    """Whether a location names somewhere, rather than nowhere in particular.

    True for "Denver" or "Multiple locations"; False for "", "Remote",
    "Anywhere in the World", "Europe", "Time zone: CET (+/- 3 hours)", "N/A".
    """
    words = _WORD_RE.findall(common.normalize_for_matching(location or ""))
    return any(word not in UNTIED_WORDS for word in words)
