"""
Vacancy scoring against the identity's criteria and profile.

The score is 0..100 and always decomposes into named components in
`score_breakdown`, alongside a separate list of dealbreakers and a
`needs_manual_review` flag. Nothing here is a magic number: every point a
vacancy gains or loses can be traced to a component and, through the
comments, to the day something went wrong and why the rule exists.

What counts as good is NOT decided here. A search for calm legacy work and
a search for an ambitious startup role are opposite rubrics; both are
expressed as data in the identity, and this module only applies them.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import textclean  # noqa: E402

_AMOUNT_RE = re.compile(
    r"\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*"
    r"(k\b|m\b|mm\b|bn\b|million\b|billion\b"
    r"|/\s?(?:hour|hr)\b|per\s?hour|/\s?(?:month|mo)\b|per\s?month)?",
    re.IGNORECASE,
)

# Magnitude suffixes after which an amount is certainly NOT a salary.
# Millions and billions in a job ad are company revenue, funding raised, or
# — a real case — how much a marketplace has paid out to its freelancers.
#
# Found 2026-07-31 by the manual checklist: Lemon.io writes "We've already
# paid out over $11M to our engineers", and the report told the owner
# "salary: $11/hour". Direct misinformation in the field that decides most.
# Ignoring the suffix is not enough: the bare 11 then fell into the branch
# "under 500, so it must be an hourly rate".
_MAGNITUDE_SUFFIXES = {"m", "mm", "bn", "million", "billion"}

# An amount in this company is not the candidate's rate.
_NON_SALARY_CONTEXT_WORDS = (
    "bonus",
    "signing",
    "stipend",
    "budget",
    "allowance",
    "raised",
    "funding",
    "revenue",
    "arr ",
    "valuation",
    "paid out",
    "referral",
)


# The cache MUST be keyed by identity. It used to be one global set filled on
# first call; once the project became multi-identity that turned into a
# cross-identity leak, where identity A's list of remote-only sources drove
# identity B's remote gate — and that gate decides between "disqualify this
# vacancy" and "give it four points". The failure would have been silent.
#
# The cache earns its place: this runs for EVERY vacancy during a rescore,
# and the database holds thousands. Re-reading YAML each time would turn a
# scoring pass into a parsing pass.
_REMOTE_ONLY_SOURCES_CACHE: dict = {}


def _reset_caches() -> None:
    """Runs on every identity activation (common.register_identity_hook).

    Belt and braces: the caches are keyed by identity already, and this is
    what keeps them correct if someone ever breaks that keying."""
    _REMOTE_ONLY_SOURCES_CACHE.clear()


common.register_identity_hook(_reset_caches)


def _remote_only_sources() -> set:
    """Sources flagged remote_only — boards that publish nothing but remote
    roles, so the board itself is sufficient proof of remoteness
    (docs/SOURCES.md)."""
    common.require_identity()
    key = common.ACTIVE_IDENTITY
    if key not in _REMOTE_ONLY_SOURCES_CACHE:
        _REMOTE_ONLY_SOURCES_CACHE[key] = {
            s.get("name")
            for s in common.load_sources()
            if s.get("remote_only") and s.get("enabled", True) and s.get("name")
        }
    return _REMOTE_ONLY_SOURCES_CACHE[key]


def load_criteria() -> dict:
    """Criteria with every layer applied in a fixed order.

    Until 2026-08-05 exactly one file was read — the identity's own. The
    local layer could therefore reach the profile but not a single threshold
    or list in the criteria, which is where most of the decisions actually
    live. Layer order and merge rules: settings.py.
    """
    import settings

    merged, _ = settings.resolve("criteria", common.ACTIVE_IDENTITY)
    return merged


def load_profile() -> dict:
    # Through common.load_profile rather than reading a file: the profile is
    # assembled from layers, and the identity's own file holds differences
    # only. Reading it directly would hand scoring a profile with no stack.
    return common.load_profile()


def _vacancy_text(vacancy: dict) -> str:
    # Emails and links are stripped BEFORE any keyword search: a domain inside
    # an address is indistinguishable from a technology name (".net" inside
    # "harnly.net"), and a URL path can contain anything at all
    # ("react-native" in a job link). See tools/textclean.py, which also
    # explains why this is shape recognition rather than address validation.
    parts = [
        vacancy.get("title") or "",
        vacancy.get("company") or "",
        vacancy.get("location_raw") or "",
        " ".join(vacancy.get("tags") or []),
        vacancy.get("description_text") or "",
        vacancy.get("salary_raw") or "",
    ]
    return common.normalize_for_matching(
        textclean.strip_contact_noise(" \n ".join(parts))
    )


_TECH_PATTERNS_CACHE = {}


def tech_matching_patterns() -> dict:
    """The shared "how to find a technology in text" vocabulary.

    How ".NET" is written is a fact about the world, identical for everyone
    who clones this repository, so it lives in config/ rather than in an
    identity (CLAUDE.md §13). An identity names the technology by its
    canonical name in its tech_stack and gets correct matching for free.
    """
    if "data" not in _TECH_PATTERNS_CACHE:
        path = common.ROOT / "config" / "tech_vocabulary.yaml"
        data = common.load_yaml(path) if path.exists() else {}
        _TECH_PATTERNS_CACHE["data"] = (data or {}).get("matching_patterns") or {}
    return _TECH_PATTERNS_CACHE["data"]


def _substring_unsafe_names() -> set:
    """Technologies that must never be matched as a substring, in any list."""
    return {name for name, spec in tech_matching_patterns().items()
            if spec.get("substring_unsafe")}


def _pattern_specs_for(names: list) -> list:
    """Vocabulary entries for the technologies this identity names."""
    vocabulary = tech_matching_patterns()
    specs = []
    for name in names or []:
        spec = vocabulary.get(name)
        if not spec:
            continue
        for pattern in spec.get("patterns") or []:
            specs.append({"name": name, "pattern": pattern,
                          "redundant_if": spec.get("redundant_if")})
    return specs


def _matches_patterns(text: str, patterns: list, already_found: list = ()) -> list:
    """Matching by regular expression rather than by substring.

    Needed wherever a technology name cannot be written as a safe substring.
    ".NET" is the canonical case: ".net" occurs inside every mail domain —
    "(firstname)@harnly.net" is a real record that arrived as a job title —
    so it cannot simply be added to the keyword list. Without it, though,
    the title "Senior .NET Backend Developer" matches NOTHING in the core
    stack, because every key there is longer (".NET Core", "ASP.NET", "C#").

    The cost was measured on 2026-08-05: 754 vacancies with .NET in the
    title, every single one rejected, 325 of them with the reason "not a
    .NET/JS developer role".

    An entry is {name, pattern, redundant_if}. The report shows `name` — a
    readable ".NET" rather than a raw regex — and `redundant_if` lists keys
    whose presence cancels the match. That last part is not optional:
    ".NET" also matches inside "ASP.NET", and without it one platform would
    be counted twice.
    """
    found = []
    for spec in patterns or []:
        if isinstance(spec, str):  # short form: the regex is its own name
            spec = {"name": spec, "pattern": spec}
        name, pattern = spec.get("name"), spec.get("pattern")
        if not pattern or name in found or name in already_found:
            continue
        if any(key in already_found for key in spec.get("redundant_if") or []):
            continue
        if re.search(pattern, text, re.IGNORECASE):
            found.append(name)
    return found


def _matches(text: str, keywords: list) -> list:
    """Substring matching. Technologies marked `substring_unsafe` in the shared
    vocabulary are skipped here and matched only by _matches_patterns.

    Without that skip, ".NET" in a keyword list starts matching inside
    "asp.net" again — precisely the mistake the vocabulary exists to stop.
    """
    unsafe = _substring_unsafe_names()
    found = []
    for kw in keywords or []:
        if kw in unsafe:
            continue
        needle = common.normalize_for_matching(kw)
        if needle and needle in text and kw not in found:
            found.append(kw)
    return found


def _check_location_field_arrangement(vacancy: dict, rl: dict) -> Optional[str]:
    """The work arrangement as the BOARD's own structured location field states it.

    Separate from the description patterns for one reason: this field is short
    and functional, so "hybrid" in it can only mean commuting. The same word in
    a description is ambiguous — "hybrid cloud", "hybrid architecture", 58
    vacancies in the base use it that way — which is why the description needs
    patterns with a neighbouring word and this field does not.

    Measured 2026-08-11 over 13605 vacancies: 272 name an arrangement here, and
    every distinct value is unambiguous — "Hybrid" (210), "In-Office" (48),
    "Luzern / hybrid", "🇩🇪 Munich (hybrid)", "ONSITE: Houston, TX".

    Except three, which is what `unless_also` is for: "Hybrid or Remote",
    "Dallas, TX (Remote US or Hybrid)" and "Distributed; Hybrid" all offer
    remote as an option. Rejecting those would be the exact false negative the
    owner warned against when this rule was written.
    """
    cfg = rl.get("location_field_arrangement") or {}

    # A declared arrangement outranks everything below. Nothing sets this
    # automatically to anything but "remote" — the on-site/hybrid badge is not
    # served to anonymous requests — so a non-remote value here is always
    # something a PERSON read and entered by hand, through kb.py. That is the
    # division of labour CLAUDE.md §5 describes, and it is the only way what
    # the owner sees on the page can reach the scoring at all.
    declared = (vacancy.get("workplace_type") or "").strip().lower()
    if declared and declared != "remote":
        return f"entered by hand: the employer states \"{declared}\""

    field = common.normalize_for_matching(vacancy.get("location_raw"))
    if not field:
        return None
    hit = next((k for k in cfg.get("not_remote") or [] if k in field), None)
    if not hit:
        return None
    if any(k in field for k in cfg.get("unless_also") or []):
        return None
    return f"the board's location field says \"{hit}\""


def _check_structured_location(vacancy: dict, criteria: dict, profile: dict = None):
    """Checks the STRUCTURED location field, which boards return separately
    from the description text. Returns (is_restricted, detail).

    The field is authoritative where it says something explicit, and
    deliberately powerless where it merely names a country — see the long
    note further down about why geography stopped being an objection.

    It exists at all because of a bug found 2026-07-30: boards deliver the
    restriction as structured data (jobGeo="USA", locationRestrictions=
    ["Canada"], candidate_required_location="Brazil") while only the
    description text was being read, and about 20 of 32 candidates turned
    out to be unreachable."""
    cfg = criteria["remote_location_fit"].get("structured_location_gate")
    if not cfg:
        return False, None

    loc_raw = (vacancy.get("location_raw") or "").strip()
    if not loc_raw:
        return False, None  # empty field: nothing to judge, the text logic decides

    loc = common.normalize_for_matching(loc_raw)

    worldwide_marker_hits = [m for m in cfg["worldwide_markers"] if m in loc]
    # "USA Only" contains "only" but is not a marker of freedom, so explicit
    # worldwide markers are checked first.
    if worldwide_marker_hits:
        # Note that "Europe only" / "US only" may contain a continent name
        # without being a worldwide marker; only genuinely open phrasings
        # reach this branch ("Anywhere in the World", "100% Remote (Global)").
        return False, {"verdict": "worldwide", "matched_markers": worldwide_marker_hits, "value": loc_raw}

    # "Remote job" / "Distributed" / "Remote" describe the work format, not a
    # country. If nothing survives crossing those words out, the board simply
    # did not name a place, which is not a restriction.
    residual = loc
    for token in cfg.get("remote_without_country_tokens", []):
        residual = residual.replace(token, " ")
    residual = re.sub(r"[^a-z]+", "", residual)
    if not residual:
        return False, {"verdict": "remote_without_country", "value": loc_raw}

    # An explicit "and only here" overrides everything below it. Found
    # 2026-08-05: the location field "United States only" contains "United
    # States", so a rule keyed on country names let it through. What the
    # employer states outranks what a country name happens to match.
    exclusivity_hits = [m for m in cfg.get("exclusivity_markers", []) if m in loc]
    if exclusivity_hits:
        return True, {"verdict": "restricted_explicitly", "matched": exclusivity_hits,
                      "value": loc_raw}

    continent_hits = [c for c in cfg["continent_names"] if c in loc]
    if len(continent_hits) >= cfg["continent_threshold"]:
        # Nearly every continent listed is worldwide in practice
        # (Remotive: "Americas, Europe, Asia, Africa, Oceania").
        return False, {"verdict": "worldwide_by_continents", "continents": continent_hits, "value": loc_raw}

    # A NAMED COUNTRY IS NO LONGER AN OBJECTION BY ITSELF.
    #
    # Revised 2026-08-05 on the owner's direct instruction: forget target
    # regions, what does a region give me, the work matters and not where.
    #
    # The history is worth keeping here. First, any country in the location
    # field was a full rejection — of 3281 European vacancies exactly one
    # reached the report. Then an exception appeared for "target markets" and
    # the world split into countries that earned points and countries that
    # earned a refusal. Both editions decided the same thing on the person's
    # behalf: where they are allowed to look.
    #
    # Geography now contributes NOTHING. Ranking is done by properties of the
    # work itself: stack, pay, ageing technologies, what former employees say
    # about work-life balance. A country affects exactly one thing — net
    # exporters of software work take a penalty (_score_market_penalty),
    # because rates there compete downwards. That is not a ban: a vacancy
    # from such a country simply has to be better on the merits.
    #
    # Refusal remains only where the EMPLOYER says no: exclusivity_markers
    # above, absolute_residency_phrases, and hard_dealbreakers.
    return False, {"verdict": "country_named", "value": loc_raw}


# "Nobody ever said this was remote." Kept as a constant because the
# classification has to recognise it exactly: it is the one objection that
# does not mean the vacancy is unsuitable, only that we do not know.
REMOTE_UNCONFIRMED = "location: the employer never states this is remote"

# Can a contractor sitting where this person sits actually take the work?
#
# A SEPARATE AXIS FROM THE SCORE, and the separation is the point. A vacancy
# can fit the stack perfectly, pay well and be genuinely remote, and still be
# unreachable because "remote" meant "remote within Canada". Points cannot
# express that: a high score with no eligibility is worse than a middling score
# with it, because the first cannot be acted on at all.
#
#     "$100/hour — Remote — US"   is worth LESS than
#     "$70/hour — Remote Worldwide — Contractor"
#
# ELIGIBILITY_CONFIRMED  the employer names this person's country among the
#                        places they hire
# ELIGIBILITY_LIKELY     explicitly worldwide, or an international-contractor
#                        arrangement, with nothing contradicting it
# ELIGIBILITY_UNKNOWN    remote, but the employer said nothing about where from
# ELIGIBILITY_NO         restricted to somewhere this person is not
ELIGIBILITY_CONFIRMED = "confirmed"
ELIGIBILITY_LIKELY = "likely"
ELIGIBILITY_UNKNOWN = "unknown"
ELIGIBILITY_NO = "no"

# Best first. Used for ordering and for "at least this good" comparisons.
ELIGIBILITY_ORDER = (ELIGIBILITY_CONFIRMED, ELIGIBILITY_LIKELY,
                     ELIGIBILITY_UNKNOWN, ELIGIBILITY_NO)


def _owner_country(profile: dict) -> str:
    return ((profile or {}).get("owner") or {}).get("location", {}).get("country") or ""


def _names_owner_country_as_a_hiring_place(text: str, criteria: dict,
                                           profile: dict) -> Optional[str]:
    """Does the employer name THIS person's country as somewhere they hire?

    The country name alone proves nothing, and for this project's first owner
    it proves less than nothing: "Georgia" is a US state as well as a country,
    and "Atlanta, Georgia" is not an offer to hire in Tbilisi. So a match needs
    the country name close to a phrase about WHERE THEY HIRE — "we hire in",
    "accepted countries", "contractors located in".

    Returns the phrase that matched, or None.
    """
    country = common.normalize_for_matching(_owner_country(profile))
    if not country or country not in text:
        return None
    cfg = (criteria.get("remote_location_fit") or {}).get("residency_eligibility") or {}
    window = int(cfg.get("context_window_chars") or 120)
    phrases = [common.normalize_for_matching(p)
               for p in cfg.get("hiring_context_phrases") or []]
    if not phrases:
        return None
    for match in re.finditer(re.escape(country), text):
        around = text[max(0, match.start() - window): match.end() + window]
        for phrase in phrases:
            if phrase and phrase in around:
                return phrase
    return None


def _residency_eligibility(rl_bd: dict, dealbreakers: list, vacancy: dict,
                           criteria: dict, profile: dict):
    """(verdict, human-readable reason).

    Derived from what the location gate already extracted rather than by
    matching the text again: every signal used here is in `rl_bd`, and a second
    independent implementation of "is this worldwide" is exactly how two parts
    of a configuration end up disagreeing (docs/OVERRIDES.md).
    """
    location_objections = [d for d in dealbreakers if d.startswith("location:")]
    blocking = [d for d in location_objections if d != REMOTE_UNCONFIRMED]
    if blocking:
        return ELIGIBILITY_NO, blocking[0][len("location: "):]

    text = _vacancy_text(vacancy)
    named = _names_owner_country_as_a_hiring_place(text, criteria, profile)
    if named:
        return (ELIGIBILITY_CONFIRMED,
                f"the posting names {_owner_country(profile)} where it says "
                f"'{named}'")

    worldwide = rl_bd.get("worldwide_remote_hits") or []
    if worldwide:
        return ELIGIBILITY_LIKELY, f"says {', '.join(worldwide[:2])}"

    contractor = rl_bd.get("eor_or_contractor_hits") or []
    if contractor:
        return (ELIGIBILITY_LIKELY,
                f"an international contractor arrangement "
                f"({', '.join(contractor[:2])})")

    if REMOTE_UNCONFIRMED in dealbreakers:
        return ELIGIBILITY_UNKNOWN, "nobody said this was remote at all"
    return ELIGIBILITY_UNKNOWN, "remote, but the employer never said from where"


_AVOIDED_MARKETS_CACHE = {}


def _score_market_penalty(vacancy: dict, criteria: dict, profile: dict):
    """Penalty for net exporters of software work — the only place geography
    touches the score at all.

    The owner, 2026-08-05: there is such a thing as a NON-target region —
    India, Pakistan, the Philippines — give them a minus; a target region is
    worth nothing. Even in India something suitable could exist, it is just
    that most of it will not be his kind of work.

    Hence a penalty rather than a gate: a vacancy from there has to be better
    on the merits to rise, which is exactly what a penalty expresses.

    The country list is shared (config/derivation/market_tiers.yaml, tiers
    exporter_avoid and excluded_practical): the direction work flows in
    describes the market, not the person.
    """
    cfg = (criteria.get("remote_location_fit") or {}).get("net_exporter_penalty")
    if not cfg:
        return 0, {}

    key = id(profile)
    if key not in _AVOIDED_MARKETS_CACHE:
        import markets as markets_mod

        names = markets_mod.avoided_countries(profile)
        _AVOIDED_MARKETS_CACHE[key] = {
            common.normalize_for_matching(n): n for n in names
        }
    avoided = _AVOIDED_MARKETS_CACHE[key]
    if not avoided:
        return 0, {}

    for tag in vacancy.get("tags") or []:
        tag = str(tag)
        if tag.startswith("market:"):
            name = tag[7:]
            if common.normalize_for_matching(name) in avoided:
                return cfg.get("points", -10), {"country": name, "source": "board tag",
                                                "points": cfg.get("points", -10)}

    loc = common.normalize_for_matching(vacancy.get("location_raw") or "")
    for needle, name in avoided.items():
        if needle and needle in loc:
            return cfg.get("points", -10), {"country": name, "source": "location field",
                                            "points": cfg.get("points", -10)}
    return 0, {}


_TARGET_MARKETS_CACHE = {}


def _target_market_of(vacancy: dict, profile: dict):
    """The vacancy's target market, or None.

    The board tag comes first (`market:United Kingdom` — the LinkedIn
    fetcher records the country it queried, which is a fact rather than a
    guess), then a country name in the location field.
    """
    if not profile:
        return None
    key = id(profile)
    if key not in _TARGET_MARKETS_CACHE:
        import markets as markets_mod

        names = markets_mod.target_locations(profile)
        _TARGET_MARKETS_CACHE[key] = (
            set(names),
            {common.normalize_for_matching(n): n for n in names},
        )
    names, normalized = _TARGET_MARKETS_CACHE[key]
    if not names:
        return None

    for tag in vacancy.get("tags") or []:
        tag = str(tag)
        if tag.startswith("market:") and tag[7:] in names:
            return tag[7:]

    loc = common.normalize_for_matching(vacancy.get("location_raw") or "")
    for needle, name in normalized.items():
        if needle and needle in loc:
            return name
    return None


def _check_header_hiring_scope(vacancy: dict, criteria: dict):
    """A structured header INSIDE the description (WeWorkRemotely prepends a
    "Headquarters: … / URL: …" block). Returns (is_restricted, detail).

    Why a separate check. Found 2026-07-31 by the manual checklist, two
    candidates sitting at the top of the shortlist:
      * Stripe — the board's region field said "Anywhere in the World"
        while the first line of the description said "Headquarters: US
        Remote";
      * Airtable — same field, header "Headquarters: San Francisco, CA;
        New York, NY; Remote - US".
    Both were US-residents-only roles, and both were hot leads.

    A category feed like WWR's "Programming" does not distinguish hiring
    country, so its region field is filled in broadly; the Headquarters line
    comes from the employer and is therefore more precise. Only header lines
    are read, never the whole text: "our US remote team" in the body is a
    description of the company, not a requirement of the candidate.

    A plain "Headquarters: Saudi Arabia" is NOT a restriction — that is the
    company's address. Only "remote + a country or region" counts, because
    only that states WHERE the company hires remotely.
    """
    cfg = (criteria.get("remote_location_fit") or {}).get("header_scope_gate")
    if not cfg:
        return False, None

    description = vacancy.get("description_text") or ""
    header_lines = []
    for line in description.splitlines()[: cfg.get("scan_first_lines", 6)]:
        line_norm = common.normalize_for_matching(line)
        if any(re.search(p, line_norm) for p in cfg.get("header_line_patterns", [])):
            header_lines.append(line_norm)
    if not header_lines:
        return False, None

    for line in header_lines:
        for pattern in cfg.get("restriction_patterns", []):
            m = re.search(pattern, line)
            if m:
                return True, {
                    "verdict": "restricted_by_header",
                    "header_line": line,
                    "matched": m.group(0),
                }
    return False, {"verdict": "header_without_restriction", "header_lines": header_lines}


def _check_infrastructure_role(text: str, title: str, criteria: dict):
    """A DevOps or platform role hiding behind a neutral title.

    The title gate already lists devops/sre/platform engineer, but that is a
    check of the TITLE. Found 2026-07-31: "Software Engineer, Compute (8+
    YOE)" @ Airtable — a completely neutral title over a body that is
    entirely a Kubernetes platform (~70 clusters, a CNI plugin, operators,
    Terraform, ArgoCD, SLOs). It scored 45 and sat second in the shortlist.

    The threshold is not optional. One or two mentions of Kubernetes, Docker
    or CI/CD appear in almost any modern application-developer posting and
    prove nothing. Only a dense concentration of infrastructure signals means
    the role itself is about running systems rather than building them.
    """
    cfg = (criteria.get("role_relevance_signal") or {}).get("infrastructure_role_gate")
    if not cfg:
        return False, {}

    hits = _matches(text, cfg.get("description_keywords", []))
    title_norm = common.normalize_for_matching(title)
    exempt = [p for p in cfg.get("title_exemption_patterns", []) if re.search(p, title_norm)]
    threshold = cfg.get("threshold_hits", 4)
    triggered = len(hits) >= threshold and not exempt
    return triggered, {
        "gate_triggered": triggered,
        "hits": hits,
        "threshold": threshold,
        "title_exemptions": exempt,
    }


_TZ_WINDOW_RE = re.compile(
    r"\b(?P<tz>[a-z]{2,9})\s*(?:time\s?zone|timezone|time)?\s*"
    r"\(?\s*(?:\+/-|±|\+\s?/\s?-)\s*(?P<hours>\d{1,2})\s*(?:hours?|hrs?)?\s*\)?"
)

# The same requirement in words. Found 2026-07-31: "We need a developer
# located within three hours of Pacific timezone" (RedLine Solutions, HN) —
# the only C#/.NET vacancy in the shortlist that day, and unreachable from
# UTC+4: Pacific ±3 is UTC-11..-5.
_TZ_WITHIN_RE = re.compile(
    r"within\s+(?P<hours>\d{1,2}|one|two|three|four|five|six)\s*(?:hours?|hrs?)"
    r"\s*(?:of|from)\s*(?:the\s+)?(?P<tz>[a-z]{2,9})"
)

_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}

# A third form: an explicit RANGE of offsets. Found 2026-08-04: SuperPlane
# writes "We currently work across GMT+2 to GMT-3 and welcome candidates in
# that range". Neither "±N hours" nor "within N hours of X", and a candidate
# at UTC+4 falls outside it.
_TZ_RANGE_RE = re.compile(
    r"(?:gmt|utc)\s*(?P<a>[+-]\s*\d{1,2})\s*(?:to|through|\.\.|-)\s*"
    r"(?:gmt|utc)?\s*(?P<b>[+-]\s*\d{1,2})"
)



def _check_timezone_requirement(text: str, criteria: dict, profile: dict):
    """A requirement on the candidate's time zone.

    Nothing covered this: the geography gates look at countries, while
    "Located in CET timezone (+/- 3 hours), we are unable to consider
    applications from candidates in other time zones" (Proxify, five
    vacancies in the shortlist on 2026-07-31) is a separate axis. That
    particular window happens to fit, but we learned it by reading with our
    eyes rather than by checking.

    Returns (is_dealbreaker, needs_review, detail).

    A deliberate limit: only explicit forms are parsed. Looser phrasings
    ("significant overlap with PST") produce needs_review rather than a
    rejection — hiding a real vacancy is worse than showing a doubtful one
    (a principle from the constitution).
    """
    cfg = (criteria.get("remote_location_fit") or {}).get("timezone_gate")
    if not cfg:
        return False, False, None

    # The profile keeps location under owner; the top level is supported too,
    # in case another identity lays its profile out differently.
    my_offset = ((profile.get("owner") or {}).get("location") or {}).get("utc_offset")
    if my_offset is None:
        my_offset = (profile.get("location") or {}).get("utc_offset")
    exclusive_hits = _matches(text, cfg.get("exclusive_phrases", []))
    # "within N hours of <TZ>" is a requirement in itself — no separate
    # prohibitive sentence accompanies it.
    within_matches = list(_TZ_WITHIN_RE.finditer(text))
    range_matches = list(_TZ_RANGE_RE.finditer(text))
    if not exclusive_hits and not within_matches and not range_matches:
        return False, False, None
    if my_offset is None:
        return False, True, {"verdict": "no_utc_offset_in_profile", "phrases": exclusive_hits}

    # Ranges are parsed first: they are less ambiguous than any window around
    # a zone name.
    for m in range_matches:
        lo, hi = sorted(int(m.group(g).replace(" ", "")) for g in ("a", "b"))
        detail = {
            "verdict": "fits" if lo <= my_offset <= hi else "outside",
            "range_utc": [lo, hi],
            "my_utc_offset": my_offset,
            "phrases": exclusive_hits,
        }
        return (detail["verdict"] == "outside"), False, detail

    zones = {common.normalize_for_matching(k): v for k, v in (cfg.get("zone_offsets") or {}).items()}
    matches = list(_TZ_WINDOW_RE.finditer(text)) + within_matches
    for m in matches:
        tz = m.group("tz")
        if tz not in zones:
            continue
        raw_hours = m.group("hours")
        window = _NUMBER_WORDS.get(raw_hours, None)
        if window is None:
            window = int(raw_hours)
        base = zones[tz]
        # Daylight saving shifts a zone by an hour. The candidate is accepted
        # if either variant fits — otherwise someone who genuinely qualifies
        # for half the year would be rejected on a technicality.
        fits = any(
            base + shift - window <= my_offset <= base + shift + window
            for shift in (0, 1)
        )
        detail = {
            "verdict": "fits" if fits else "outside",
            "zone": tz.upper(),
            "zone_utc_offset": base,
            "window_hours": window,
            "my_utc_offset": my_offset,
            "phrases": exclusive_hits,
        }
        return (not fits), False, detail

    return False, True, {"verdict": "unparsed_requirement", "phrases": exclusive_hits}


def _strip_stack_noise_sections(text: str, criteria: dict):
    """Cuts away "stack spam" — blocks that list every technology on earth.

    Found 2026-07-31: every Lemon.io posting ends with a "NOT YOUR TECH
    STACK?" paragraph listing some 60 technologies, ".NET & C#", Angular and
    Scala among them. Because of it EVERY vacancy of theirs — down to
    "Senior Graphic Designer" — collected core hits ["C#", "Angular"] and
    cleared the stack relevance gate with full marks.

    This is not about one board: agencies and outstaffing companies use the
    same trick of listing every stack so as to appear in every search. The
    text is cut ONLY for stack scoring — geography and language still read
    the whole description, which is where the list of hiring countries is.
    """
    markers = (criteria.get("stack_fit") or {}).get("noise_section_markers") or []
    cut_at = len(text)
    matched = []
    for marker in markers:
        needle = common.normalize_for_matching(marker)
        pos = text.find(needle) if needle else -1
        if pos != -1:
            matched.append(marker)
            cut_at = min(cut_at, pos)
    return text[:cut_at], matched


def _score_ambiguous_places(text: str, criteria: dict):
    """Ambiguous place names: one name, two different places.

    A generalisation of what used to be a hardcoded check for "georgia". The
    trap is not unique to one identity: Cambridge (UK / Massachusetts),
    Washington (state / capital), Ontario (Canada / California), Odessa
    (Ukraine / Texas), Birmingham (England / Alabama) — the same class of
    error for other people.

    A vacancy is flagged only when BOTH meanings have context, or NEITHER
    does. One clear meaning is not a reason to interrupt anyone.
    """
    rules = (criteria.get("remote_location_fit") or {}).get("ambiguous_place_names") or []
    flagged = False
    detail = []

    for rule in rules:
        triggers = rule.get("trigger_keywords") or []
        if not any(common.normalize_for_matching(k) in text for k in triggers):
            continue

        a = _matches(text, (rule.get("meaning_a") or {}).get("context_keywords") or [])
        b = _matches(text, (rule.get("meaning_b") or {}).get("context_keywords") or [])

        if bool(a) == bool(b):  # both contexts, or neither — undecidable
            flagged = True
            detail.append({
                "name": rule.get("name"),
                "verdict": "ambiguous",
                "meaning_a_hits": a,
                "meaning_b_hits": b,
            })
        else:
            detail.append({
                "name": rule.get("name"),
                "verdict": "meaning_a" if a else "meaning_b",
                "resolved_as": (rule.get("meaning_a") if a else rule.get("meaning_b")).get("label"),
            })

    return flagged, detail


def _score_remote_location(text: str, vacancy: dict, criteria: dict, profile: dict):
    rl = criteria["remote_location_fit"]
    breakdown = {}
    dealbreakers = []
    needs_review = False

    hard_hits = _matches(text, rl["hard_dealbreakers"]["keywords"])
    # Patterns, not only substrings. A requirement is written a dozen ways —
    # "must be a US Citizen", "Must be US Citizen", "U.S. Citizen or Green
    # Card holder" — and a literal list catches whichever variants somebody
    # happened to see. Measured 2026-08-11: the substring list held "must be
    # a us citizen" and missed BOTH "must be a U.S. Citizen" (the dots) and
    # "Must be US Citizen" (no article). Five vacancies with a hard
    # citizenship requirement were sitting in the shortlist, two of them in
    # the top five. Punctuation cannot be normalised away globally: it is
    # what makes "c#" and "asp.net" matchable at all.
    hard_hits += _matches_patterns(
        text, rl["hard_dealbreakers"].get("patterns"), hard_hits)
    arrangement = _check_location_field_arrangement(vacancy, rl)
    if arrangement:
        hard_hits.append(arrangement)
    if hard_hits:
        dealbreakers.extend(f"location: {h}" for h in hard_hits)

    worldwide_hits = _matches(text, rl["worldwide_remote"]["keywords"])
    # NOTE: a bare "eor" is deliberately absent. Found 2026-07-30: "eor" is a
    # substring of ordinary English words ("th-EOR-etical", "th-EOR-y") and
    # matched falsely, clearing the "not confirmed as remote" gate for a
    # vacancy that was Hybrid/Munich without the word "remote" anywhere in
    # it. The same class of bug as "LESS" or ".NET" inside "VB.NET": short
    # acronyms match as substrings far too easily.
    eor_keywords = list(profile.get("eor_platforms_signal") or []) + [
        "contractor",
        "1099",
        "freelance",
    ]
    eor_hits = _matches(text, eor_keywords)
    # A NAMED employer-of-record platform, as opposed to the generic words.
    # The difference matters in exactly one place — the override below — and it
    # matters a lot. "Deel" or "Employer of Record" is evidence that a company
    # is set up to engage somebody across a border. "freelance" is a word that
    # appears in postings which are nonetheless tied to one continent.
    #
    # Measured 2026-08-12: "Backend Developer (.NET/Azure)" @ NTT DATA led the
    # WORLDWIDE shortlist at 76 while its own text read "Location Preference:
    # 100% remote in LATAM working EST Time Zone" — the region tie cancelled by
    # the word "freelance" elsewhere in the description. It was the only
    # vacancy in the whole shortlist resting on that override, so tightening it
    # cost nothing and fixed the top of the file that matters most.
    eor_platform_hits = _matches(text, list(profile.get("eor_platforms_signal") or []))
    region_hits = _matches(text, rl["acceptable_region_signal"]["keywords"])

    # A hard tie to a specific region (LATAM/APAC/UK-only/US-only/…) is a
    # dealbreaker UNLESS a worldwide or EOR signal outweighs it. Confirmed
    # explicitly 2026-07-30: a "remote LATAM" role is physically unreachable
    # from outside, so it should be removed rather than merely deprioritised.
    #
    # A direct residency requirement from the employer is overridden by
    # nothing at all — not by a marketing "worldwide" in the text, and not by
    # a board's broad-brush label.
    absolute_hits = _matches(text, rl["restrictive_region_signal"].get("absolute_residency_phrases", []))
    if absolute_hits:
        dealbreakers.extend(f"location: explicit residency requirement ('{h}')" for h in absolute_hits)
        breakdown["absolute_residency_hits"] = absolute_hits

    restrictive_hits = _matches(text, rl["restrictive_region_signal"]["keywords"])
    # Patterns as well as literals, for the same reason hard_dealbreakers grew
    # them: a region tie has too many spellings to list. Measured 2026-08-12 —
    # the list held "remote latam" and missed "100% remote in LATAM", one
    # preposition away, which was leading the worldwide shortlist at 76.
    #
    # Deliberately HERE rather than in hard_dealbreakers: a region phrase is
    # still outranked by an explicit worldwide or contractor signal a few lines
    # below, and a posting that says "worldwide, and we already have people in
    # LATAM" must survive.
    restrictive_hits += _matches_patterns(
        text, rl["restrictive_region_signal"].get("patterns"), restrictive_hits)
    if restrictive_hits and not (worldwide_hits or eor_platform_hits):
        dealbreakers.extend(f"location: restricted to '{h}'" for h in restrictive_hits)
        breakdown["restrictive_region_hits"] = restrictive_hits

    # The structured location field from the source (WWR region / Remotive
    # candidate_required_location / Jobicy jobGeo / Himalayas
    # locationRestrictions) is a more reliable signal than phrases in prose.
    structured_restricted, structured_detail = _check_structured_location(vacancy, criteria, profile)
    if structured_detail:
        breakdown["structured_location"] = structured_detail
    # IMPORTANT: a structured restriction is lifted by nothing in the
    # description — not by a mention of EOR or contracting, not by marketing
    # "worldwide" phrasing. The board's location field is an authoritative
    # statement about WHERE the company will hire; sentences in the body are
    # not. Two bugs found on 2026-07-30:
    #  * LawnStarter: location = "Brazil"/"Uruguay"/"Mexico" plus a mention
    #    of Multiplier (an EOR) — eleven Latin American vacancies passed. An
    #    EOR says HOW someone is employed, not WHERE they will be hired.
    #  * Prima: location = "London" plus "work from anywhere" in the benefits
    #    section (the usual "work from anywhere for N weeks a year") — five
    #    London insurance vacancies passed as worldwide.
    if structured_restricted:
        dealbreakers.append(
            f"location: source restricts hiring to '{vacancy.get('location_raw', '').strip()}'"
        )

    # The employer's own header block inside the description is more precise
    # than a category feed's broad region field. Also not lifted by prose.
    header_restricted, header_detail = _check_header_hiring_scope(vacancy, criteria)
    if header_detail:
        breakdown["header_scope"] = header_detail
    if header_restricted:
        dealbreakers.append(
            f"location: employer header says remote hiring is limited "
            f"('{header_detail['matched']}')"
        )

    tz_dealbreaker, tz_needs_review, tz_detail = _check_timezone_requirement(text, criteria, profile)
    if tz_detail:
        breakdown["timezone_requirement"] = tz_detail
    if tz_dealbreaker:
        if "range_utc" in tz_detail:
            lo, hi = tz_detail["range_utc"]
            dealbreakers.append(
                f"timezone: requires UTC{lo:+d}..{hi:+d}, "
                f"candidate is at UTC{tz_detail['my_utc_offset']:+d}"
            )
        else:
            dealbreakers.append(
                f"timezone: requires {tz_detail['zone']} ±{tz_detail['window_hours']}h, "
                f"candidate is at UTC{tz_detail['my_utc_offset']:+d}"
            )

    points = 0
    # A country named by the board cancels the worldwide BONUS from the text.
    #
    # The rule "the structured field outranks a marketing phrase" has existed
    # since 2026-07-30, but it worked as a rejection: a vacancy with
    # location="London" was simply dropped, and whatever the benefits section
    # said did not matter. When a named country stopped being an objection on
    # 2026-08-05, "work from anywhere for a few weeks a year" from the list of
    # perks began earning full marks for international hiring. The regression
    # was caught by a test written for the previous edition of the rule, which
    # is exactly why that test was kept.
    #
    # The meaning is unchanged: if the board named a city, the employer is not
    # hiring worldwide, whatever the section about snacks claims.
    structured_named_country = (structured_detail or {}).get("verdict") == "country_named"
    if worldwide_hits and not structured_named_country:
        points = max(points, rl["worldwide_remote"]["points"])
        breakdown["worldwide_remote_hits"] = worldwide_hits
    elif worldwide_hits:
        breakdown["worldwide_remote_hits_ignored"] = {
            "hits": worldwide_hits,
            "why": "the board named a country: %s" % (structured_detail or {}).get("value"),
        }
    if eor_hits:
        points = max(points, rl["eor_or_contractor_international"]["points"])
        breakdown["eor_or_contractor_hits"] = eor_hits
    if region_hits:
        points = max(points, rl["acceptable_region_signal"]["points"])
        breakdown["acceptable_region_hits"] = region_hits

    location_unknown = False
    # NOTE: region_hits is deliberately NOT in this exemption, unlike
    # worldwide_hits/eor_hits/restrictive_hits. Found 2026-09-01 by the manual
    # checklist (docs/VACANCY_CHECKLIST.md), independently in three separate
    # batches: dozens of vacancies for companies physically IN Israel/UAE
    # (abra, WalkMe, Bagira, Mobisoft, Elspec, Deloitte Israel, SQLink, ARAN,
    # Mobile Group, Yael Korentec, Hays/Dubai, TAT/Argyll Scott UAE...) had NO
    # remote confirmation anywhere in the text — plainly onsite office roles —
    # yet sailed straight into hot_lead/worth_a_look/long_shot. The cause:
    # acceptable_region_signal keywords are bare place names ("israel", "tel
    # aviv", "uae", "dubai", "abu dhabi") that match just as often in a street
    # address as in a claim of international remote hiring, but their mere
    # presence used to exempt the vacancy from the remote-confirmation check
    # entirely, on top of granting it a bonus. worldwide_hits/eor_hits are
    # actual signals of remote/international intent and stay exempted;
    # restrictive_hits already implies the text is discussing hiring
    # geography at all. A bare mention of a target country's name implies
    # neither. The bonus itself (above) is untouched — a genuinely remote
    # Israel/UAE role still gets it; an unconfirmed one now correctly lands in
    # `remote_unconfirmed` instead of the confident tiers, same as any other
    # vacancy nobody ever called remote.
    if not (worldwide_hits or eor_hits or restrictive_hits):
        remote_word_hits = _matches(text, rl["remote_synonym_keywords"])
        # A board that publishes ONLY remote roles (WWR, RemoteOK, Remotive,
        # Jobicy, Himalayas — see remote_only in the sources catalogue) is
        # sufficient proof of remoteness by itself. Found 2026-07-30:
        # vacancies from such boards were rejected as "not confirmed as
        # remote" purely because the word "remote" did not appear in the
        # description — a pure false negative that cut dozens of live
        # candidates.
        from_remote_only_source = vacancy.get("source") in _remote_only_sources()
        # The employer's own structured declaration, where a source provides
        # one. schema.org marks a genuinely remote posting TELECOMMUTE; the
        # absence of it means the employer said nothing, NOT that the job is
        # onsite. See fetch_linkedin.workplace_type.
        declared_remote = vacancy.get("workplace_type") == "remote"
        # max(), not an overwrite: a region_hits bonus already computed above
        # (e.g. 16 for Israel/UAE) must survive even when this branch runs.
        points = max(points, 4)  # remote-ish, unclear about hiring abroad
        location_unknown = True
        if not (declared_remote or vacancy.get("remote") is True
                or remote_word_hits or from_remote_only_source):
            # Nobody ever said this was remote — not the employer, not the
            # source. That is a statement about our knowledge, not about the
            # job, so it is NOT scored down: the points above stand and the
            # uncertainty is carried by the classification instead.
            #
            # Revised 2026-08-11 at the owner's direction, after LinkedIn was
            # caught claiming every vacancy was remote (see below). It used to
            # be a flat rejection, which was right while the flag could be
            # trusted and wrong once it could not: 109 vacancies with a full
            # description that simply never mentions the arrangement would
            # have vanished on an inference rather than on anybody's words.
            # What the employer DOES say — "hybrid", "on-site" — still
            # disqualifies through hard_dealbreakers, as before.
            dealbreakers.append(REMOTE_UNCONFIRMED)

    places_ambiguous, place_detail = _score_ambiguous_places(text, criteria)
    if place_detail:
        breakdown["ambiguous_place_hits"] = place_detail

    breakdown["points"] = points
    # An ambiguous place name is always worth a human glance. General location
    # uncertainty is returned separately and filtered in score_vacancy() by
    # final classification: on real data that flag fires on almost everything
    # — most vacancies simply never write "worldwide" or "US only" — and the
    # review section of the report would become useless.
    needs_review = places_ambiguous or tz_needs_review
    return points, breakdown, dealbreakers, needs_review, location_unknown


def _score_stack_fit(text: str, criteria: dict, profile: dict):
    cfg = criteria["stack_fit"]
    text, noise_markers = _strip_stack_noise_sections(text, criteria)
    core_hits = _matches(text, profile["tech_stack"].get("core", []))
    # Technologies whose name cannot be written as a safe substring — see
    # _matches_patterns. Without this, ".NET Developer" in a title scored
    # exactly zero for stack fit.
    core_hits += _matches_patterns(
        text, _pattern_specs_for(profile["tech_stack"].get("core", [])), core_hits)
    strong_hits = _matches(text, profile["tech_stack"]["strong"])
    familiar_hits = _matches(text, profile["tech_stack"]["familiar"])
    raw = (
        len(core_hits) * cfg["points_per_core_keyword"]
        + len(strong_hits) * cfg["points_per_strong_keyword"]
        + len(familiar_hits) * cfg["points_per_familiar_keyword"]
    )
    points = min(raw, cfg["cap"])
    # Depth of match beats breadth of list. Measured 2026-08-05: a posting in
    # pure C#/ASP.NET earned 7 stack points, while an agency advert listing
    # TypeScript, JavaScript, React, HTML and CSS earned 14. A point per match
    # systematically lifts those who enumerate technologies above those whose
    # stack is exactly the one wanted. So without a single core match, stack
    # fit cannot exceed what one real core match is worth.
    cap_no_core = cfg.get("cap_when_no_core")
    if cap_no_core is not None and not core_hits:
        points = min(points, cap_no_core)
    breakdown = {
        "points": points,
        "core_hits": core_hits,
        "strong_hits": strong_hits,
        "familiar_hits": familiar_hits,
    }
    if noise_markers:
        breakdown["noise_sections_ignored"] = noise_markers
    return points, breakdown


def _score_role_complexity(text: str, title: str, criteria: dict):
    """The "this is not simple work" gate, deliberately separate from the
    legacy/enterprise signal.

    Confirmed 2026-07-30 on "Principal Machine Learning Scientist" and
    "Staff Software Engineer, Agentic Platform": legacy and enterprise words
    in a company description say nothing about whether the ROLE is simple."""
    cfg = criteria["role_complexity_signal"]
    title_norm = common.normalize_for_matching(title)
    title_hits = [p for p in cfg["title_red_flag_patterns"] if re.search(p, title_norm, re.IGNORECASE)]
    description_hits = _matches(text, cfg["description_red_flag_keywords"])
    # Found 2026-07-30 by the manual checklist: "Staff Software Engineer (AI
    # CICD)" @ Chainguard mentioned "agentic AI foundation" once — below the
    # threshold of two for vague words, but "agentic", "llm systems" and
    # "genai" are unambiguous on their own, so one mention is enough.
    strong_hits = _matches(text, cfg.get("description_red_flag_keywords_strong_single_hit", []))
    gate_triggered = bool(title_hits) or bool(strong_hits) or len(description_hits) >= cfg["threshold_hits"]
    return gate_triggered, {
        "gate_triggered": gate_triggered,
        "title_hits": title_hits,
        "description_hits": description_hits,
        "strong_single_hit_matches": strong_hits,
    }


def _check_stack_relevance(text: str, core_hits: list, strong_hits: list, criteria: dict):
    """The stack relevance gate — a full rejection, not merely a low score.

    Confirmed explicitly 2026-07-30: a role outside the profile's stack,
    with no sign that the company is tech agnostic, is a zero-percent chance.

    A core or strong match suffices on its own. Java and Scala BY THEMSELVES
    do not count — this profile is not a fit for a Java web role — but
    Java or Scala PLUS a data-pipeline context (Spark, Databricks, ETL) is an
    acceptable variant, confirmed explicitly against real experience from a
    previous job. An explicit tech agnostic statement from the company lifts
    the requirement entirely."""
    cfg = criteria["stack_fit"]
    # The same stack-spam cut as in _score_stack_fit: otherwise the relevance
    # gate would pass on the technology list from an advertising block.
    text, _ = _strip_stack_noise_sections(text, criteria)
    tech_agnostic_hits = _matches(
        text, criteria["role_relevance_signal"]["tech_agnostic_override_keywords"]
    )
    data_pipeline_language_hits = _matches(text, cfg["data_pipeline_language_keywords"])
    data_pipeline_context_hits = _matches(text, cfg["data_pipeline_context_keywords"])
    data_pipeline_relevant = bool(data_pipeline_language_hits) and bool(data_pipeline_context_hits)

    # A real language or framework is required, not just an infrastructure
    # word. Docker, Azure, HTML and CSS appear in almost every posting and
    # say nothing about whether the role suits this profile.
    primary_language_hits = _matches(text, cfg.get("primary_language_keywords", []))
    primary_language_hits += _matches_patterns(
        text, _pattern_specs_for(cfg.get("primary_language_keywords", [])),
        primary_language_hits)

    relevant = bool(primary_language_hits) or data_pipeline_relevant or bool(tech_agnostic_hits)
    return relevant, {
        "primary_language_hits": primary_language_hits,
        "tech_agnostic_override_hits": tech_agnostic_hits,
        "data_pipeline_exception_applied": data_pipeline_relevant,
    }


def _check_title_stack(title: str, criteria: dict, profile: dict):
    """The title names a technology the person does not have — full rejection.

    A leak the owner spotted in a finished shortlist on 2026-08-04: "Senior
    Ruby on Rails Developer", "Senior Fullstack Developer (Python)", "Senior
    Vue Developer". The relevance gate searched the WHOLE text for a familiar
    language, and a Rails posting lists HTML, CSS and JavaScript among
    adjacent skills. The match is technically there; the role is about
    something else entirely.

    The title defines the role. So: if it names at least one role-defining
    technology and NONE of those named is in core or strong, the vacancy is
    rejected. The familiar tier deliberately does not count — that means
    "touched it twice in a career", and nobody is hired for such a role on
    that basis.
    """
    cfg = criteria.get("title_stack_gate")
    if not cfg:
        return False, {}

    title_norm = common.normalize_for_matching(title)
    named = [tech for tech in cfg.get("role_defining_technologies", [])
             if common.normalize_for_matching(tech) in title_norm]
    if not named:
        return False, {"named_technologies": []}

    stack = profile.get("tech_stack") or {}
    known = {common.normalize_for_matching(k)
             for k in (stack.get("core") or []) + (stack.get("strong") or [])}
    # An EXACT comparison, not a substring test. Bug found 2026-08-05: "java"
    # counted as known because it is a substring of "javascript" in the strong
    # tier, and "Java Engineer" cleared the gate again. The same class of
    # error as ".NET" inside "VB.NET" and "LESS" inside "no less than".
    mine = [tech for tech in named if common.normalize_for_matching(tech) in known]

    return (not mine), {
        "named_technologies": named,
        "known_among_them": mine,
    }


def _score_role_relevance(text: str, title: str, criteria: dict):
    """The "is this a software developer role at all" gate — a full rejection.

    Confirmed 2026-07-30 on real finds: "CFO Controller" and "Product
    Manager, Mapping and Weather Visualization" are not developer roles,
    whatever legacy or enterprise words appear in the company description.

    It fires on the title. A developer-role override pattern in the title
    ("Engineer", "Developer") lifts the gate, as does an explicit tech
    agnostic statement anywhere in the text."""
    cfg = criteria["role_relevance_signal"]
    title_norm = common.normalize_for_matching(title)

    # When the title is uninformative, the first line of the description is
    # examined as well.
    #
    # Found 2026-08-04: a Hacker News record arrived with the title "YC 19"
    # and company "Ashby" — the thread parser split "Ashby | YC 19 | REMOTE |
    # Hiring Engineering Leaders | $200k-$275k" on separators and took the
    # wrong piece. The profession gate reads the TITLE, and "YC 19" contains
    # no profession at all, so a management role sailed through as an
    # ordinary one and took a place in the shortlist.
    #
    # The search widens ONLY when the title holds no developer-role word.
    # A normal vacancy has an informative title, and its first description
    # line — usually a paragraph about the company — stays out of the check;
    # otherwise the word "manager" in a corporate blurb would start throwing
    # good vacancies away.
    developer_override_hits = [
        p for p in cfg["developer_role_override_patterns"] if re.search(p, title_norm, re.IGNORECASE)
    ]
    search_area = title_norm
    uninformative_title = not developer_override_hits
    if uninformative_title:
        # _vacancy_text has already collapsed line breaks, so take the head.
        search_area = f"{title_norm} {(text or '')[:300]}"

    wrong_profession_hits = [
        p for p in cfg["wrong_profession_title_patterns"] if re.search(p, search_area, re.IGNORECASE)
    ]
    # The hard tier: management, sales, GTM and presales are certainly not an
    # individual contributor role, even with "engineer" or "architect" in the
    # title.
    hard_wrong_hits = [
        p for p in cfg.get("hard_wrong_profession_title_patterns", [])
        if re.search(p, search_area, re.IGNORECASE)
    ]
    tech_agnostic_hits = _matches(text, cfg["tech_agnostic_override_keywords"])

    soft_gate = bool(wrong_profession_hits) and not developer_override_hits and not tech_agnostic_hits
    gate_triggered = soft_gate or bool(hard_wrong_hits)
    return gate_triggered, {
        "gate_triggered": gate_triggered,
        "wrong_profession_hits": wrong_profession_hits + hard_wrong_hits,
        "hard_wrong_profession_hits": hard_wrong_hits,
        "developer_override_hits": developer_override_hits,
    }


def _score_language_fit(text: str, criteria: dict):
    """The language gate — a full rejection.

    Which languages disqualify a vacancy is derived from the languages the
    person speaks (owner.languages in the profile), never copied from another
    identity. A real find: "Web-Administration / Webmaster TYPO3" required
    "sehr gute Deutschkenntnisse".

    Many postings from German boards are written entirely in German without
    any English sentence about language, so a heuristic over frequent German
    words and the "(m/w/d)" marker catches those too."""
    cfg = criteria["language_requirement_signal"]
    explicit_hits = _matches(text, cfg["explicit_requirement_keywords"])
    german_market_hits = _matches(text, cfg["german_market_indicator_keywords"])
    # The gender marker "(m/w/d)" / "(f/m/d)" is unambiguous on its own: it
    # exists only in German-language postings, where anti-discrimination law
    # requires it. A threshold of three matches is excessive for it — the
    # Hygraph and Boardwise vacancies of 2026-07-31 carried exactly one such
    # marker each and passed.
    german_strong_hits = _matches(text, cfg.get("german_market_strong_single_markers", []))
    german_market_flagged = (
        len(german_market_hits) >= cfg["german_market_indicator_threshold"]
        or bool(german_strong_hits)
    )

    # The same technique as for German, generalised to any language. Found
    # 2026-07-31 by the manual checklist: a Work and Study Travel posting
    # entirely in Spanish and a Base.com posting entirely in Polish, both of
    # which passed because the heuristic existed for exactly one language.
    # The German block above stays separate: its threshold and tests are
    # calibrated on it.
    foreign_language_hits = {}
    for entry in cfg.get("foreign_language_posting_indicators", []):
        hits = _matches(text, entry.get("markers", []))
        if len(hits) >= entry.get("threshold", 3):
            foreign_language_hits[entry["language"]] = hits

    # Script is a more reliable signal than a word list. A posting in Hebrew,
    # Arabic, Chinese or Greek is unreadable to someone who knows only Latin
    # and Cyrillic, and establishing that by enumerating frequent words is
    # pointless: the alphabet is visible at once and in full.
    #
    # Found 2026-08-05 by reading the shortlist with human eyes: a Hebrew
    # vacancy sat thirteenth. Word lists existed for five European languages,
    # and none of them could catch a different script even in principle.
    script_detail = _check_unreadable_script(text, cfg)

    gate_triggered = (bool(explicit_hits) or german_market_flagged
                      or bool(foreign_language_hits) or bool(script_detail))
    return gate_triggered, {
        "gate_triggered": gate_triggered,
        "explicit_requirement_hits": explicit_hits,
        "german_market_indicator_hits": german_market_hits,
        "german_market_flagged": german_market_flagged,
        "foreign_language_posting_hits": foreign_language_hits,
        "unreadable_script": script_detail,
    }


# Code ranges for scripts that actually turn up in job ads. Latin and
# Cyrillic are absent by design: they are readable to the owner of any
# identity that lists English or Russian among its languages.
_SCRIPT_RANGES = (
    ("hebrew", 0x0590, 0x05FF),
    ("arabic", 0x0600, 0x06FF),
    ("greek", 0x0370, 0x03FF),
    ("thai", 0x0E00, 0x0E7F),
    ("devanagari", 0x0900, 0x097F),
    ("hangul", 0xAC00, 0xD7AF),
    ("cjk", 0x4E00, 0x9FFF),
    ("kana", 0x3040, 0x30FF),
)


def _check_unreadable_script(text: str, cfg: dict):
    """How much of the text is in a script the person cannot read.

    The threshold is a share rather than a count: an English posting from an
    Israeli company may well contain a word or two of Hebrew — its own name,
    an address. A posting written entirely in it runs to tens of percent.
    """
    readable = set(cfg.get("readable_scripts") or ["latin", "cyrillic"])
    threshold = cfg.get("unreadable_script_threshold", 0.15)

    counts = {}
    letters = 0
    for char in text:
        if not char.isalpha():
            continue
        letters += 1
        code = ord(char)
        for name, low, high in _SCRIPT_RANGES:
            if low <= code <= high:
                counts[name] = counts.get(name, 0) + 1
                break

    if letters < 80:
        return None
    for name, count in counts.items():
        if name in readable:
            continue
        share = count / letters
        if share >= threshold:
            return {"script": name, "share": round(share, 3)}
    return None


def _check_industry_dealbreaker(text: str, criteria: dict):
    """An industry the person will not work in on principle — full rejection.

    The threshold is not optional: an ordinary company's posting may mention
    crypto among its clients or integrations, and one word is not enough.
    Two or more is about the company itself.
    """
    cfg = criteria.get("industry_dealbreaker_gate")
    if not cfg:
        return False, {}
    # The same stack-spam cut as in stack scoring. Found 2026-08-04: this gate
    # rejected every Lemon.io vacancy because their "NOT YOUR TECH STACK?"
    # advertising paragraph lists Blockchain, Ethereum and Solana. The company
    # has nothing to do with crypto — that is a list of stacks they match
    # projects against. A false rejection hides live vacancies, which is worse
    # than one extra vacancy in the shortlist.
    text, _ = _strip_stack_noise_sections(text, criteria)
    hits = _matches(text, cfg.get("keywords", []))
    threshold = cfg.get("threshold_hits", 2)
    return len(hits) >= threshold, {
        "gate_triggered": len(hits) >= threshold,
        "hits": hits,
        "threshold": threshold,
    }


def _check_mobile_role(text: str, title: str, criteria: dict):
    """Mobile development behind a neutral title — full rejection.

    The same class as `_check_infrastructure_role`: the title says "Lead
    Full-stack Developer" while the product is a React Native app and all the
    work happens inside it. A title gate cannot see that.

    The threshold is not optional: an ordinary web posting may mention a
    mobile app among the company's other products. Nor is the advertising
    cut: agency stack lists contain React Native and Flutter, and without it
    "Senior Vue Developer" and "Senior Graphic Designer" from Lemon.io fell
    under this gate.
    """
    cfg = criteria.get("mobile_role_gate")
    if not cfg:
        return False, {}
    text, _ = _strip_stack_noise_sections(text, criteria)
    hits = _matches(common.normalize_for_matching(title) + " " + text,
                    cfg.get("keywords", []))
    threshold = cfg.get("threshold_hits", 2)
    triggered = len(hits) >= threshold
    return triggered, {
        "gate_triggered": triggered,
        "hits": hits,
        "threshold": threshold,
    }


def _check_talent_pipeline(text: str, criteria: dict):
    """An advertisement with no vacancy behind it.

    An employer collecting CVs against roles that may open later. Formally it
    is a vacancy; in substance there is nothing to apply to, and no date by
    which there will be.

    It scores well for a reason that is worth naming: such a posting is
    assembled from what candidates want to read, so it matches a profile more
    tidily than a real vacancy does. Found 2026-08-11 — "Senior .NET Developer"
    @ Mariner Innovations led the shortlist at 50 with stack, remote and legacy
    enterprise all matching.

    A gate rather than a penalty, on the same reasoning as the crowdwork gate:
    the chance is not low, it is undefined, and points cannot express that.
    """
    cfg = criteria.get("talent_pipeline_gate")
    if not cfg:
        return False, {}
    hits = _matches(text, cfg.get("keywords", []))
    return bool(hits), {"gate_triggered": bool(hits), "hits": hits}


def _check_ai_training_crowdwork(text: str, criteria: dict):
    """AI-training crowdwork wearing an engineering title.

    A distinct genre that appeared on job boards between 2024 and 2026: a
    platform hires developers not to build software but to produce training
    data — write reference solutions, annotate, rate model answers, assemble
    RL environments. Formally it is a "Senior Software Engineer"; in
    substance it is piecework with no project, no team and no product.

    Such postings win at scoring systematically, and not by accident: they
    list every language at once ("JavaScript, Python, Go, C++, Ruby"), write
    "no set schedules" quite honestly (which reads as low intensity), and
    almost always quote an hourly rate. Measured 2026-08-05: four of the top
    nine positions in the shortlist, including the first.

    A gate rather than a penalty: paid-per-task work is not what someone
    looking for a permanent position wants, and no number of points
    compensates for that. The markers are deliberately long — short ones
    ("ai", "training") would catch half the market.
    """
    cfg = criteria.get("ai_training_crowdwork_gate")
    if not cfg:
        return False, {}
    hits = _matches(text, cfg.get("keywords", []))
    return bool(hits), {"gate_triggered": bool(hits), "hits": hits}


def _score_legacy_enterprise(text: str, criteria: dict):
    cfg = criteria["legacy_enterprise_signal"]
    hits = _matches(text, cfg["keywords"])
    points = min(len(hits) * cfg["points_per_keyword"], cfg["cap"])
    return points, {"points": points, "hits": hits}


def _score_low_intensity(text: str, criteria: dict):
    cfg = criteria["low_intensity_signal"]
    pos_hits = _matches(text, cfg["positive_keywords"])
    neg_hits = _matches(text, cfg["negative_keywords"])
    raw = len(pos_hits) * cfg["positive_points_per_keyword"] + len(neg_hits) * cfg[
        "negative_points_per_keyword"
    ]
    points = max(min(raw, cfg["cap"]), cfg["floor"])
    return points, {"points": points, "positive_hits": pos_hits, "negative_hits": neg_hits}


def _extract_amounts(text: str):
    """Best-effort extraction of money amounts. Returns a list of
    (annual_or_None, hourly_or_None, monthly_or_None) tuples.

    Monthly forms ("$X/month", "$X per month", "$X/mo") are recognised
    separately. Without that, an ordinary "$5,000/month" was read as an
    ANNUAL figure — any number at or above 500 was — and unfairly penalised
    as far below the target annual range."""
    results = []
    for m in _AMOUNT_RE.finditer(text):
        # Context around the amount. Found 2026-07-31: Sticker Mule writes
        # "Salary: $150,000–$250,000 USD" and then "$20,000 signing bonus",
        # and the report showed a range of "$20,000-$250,000/year" — a badly
        # understated lower bound. Bonuses, stipends and company revenue have
        # nothing to do with the rate.
        #
        # The window looks further back than forward: "signing bonus" follows
        # its own amount immediately, whereas looking 40 characters ahead
        # would discard the real range in "$150,000-$250,000 USD. $20,000
        # signing bonus" because of the bonus sitting next to it.
        window = text[max(0, m.start() - 40):m.end() + 15]
        if any(w in window for w in _NON_SALARY_CONTEXT_WORDS):
            continue
        raw_num, suffix = m.group(1), (m.group(2) or "").strip().lower()
        try:
            value = float(raw_num.replace(",", ""))
        except ValueError:
            continue
        if suffix in _MAGNITUDE_SUFFIXES:
            continue  # revenue, funding or total payouts, not a rate
        if suffix == "k":
            results.append((value * 1000, None, None))
        elif suffix and ("month" in suffix or suffix.lstrip("/per ").strip() == "mo"):
            results.append((None, None, value))
        elif suffix and ("hour" in suffix or "hr" in suffix):
            results.append((None, value, None))
        elif value < 500:
            # a small number with no suffix is most likely an hourly rate
            results.append((None, value, None))
        else:
            results.append((value, None, None))
    return results


def _score_external_salary_estimate(vacancy: dict, criteria: dict, profile: dict):
    """Scoring a manually found salary range (Glassdoor and similar) when the
    vacancy states none. Confirmed explicitly 2026-07-30: if no salary is
    stated but third-party sources give a rough range, that is a SMALL plus.
    Filled in via `tools/kb.py set-salary-estimate` into
    vacancy.external_signals — a top-level field rather than "manual", so it
    takes part in rescoring."""
    cfg = criteria["compensation_signal"]
    estimate = (vacancy.get("external_signals") or {}).get("salary_estimate")
    if not estimate:
        return None

    points = cfg["external_estimate_points"]
    low, high = estimate.get("low"), estimate.get("high")
    period = estimate.get("period", "year")
    target = profile["goal"]["target_compensation"]
    range_key = {
        "year": "annual_parttime_usd",
        "month": "monthly_parttime_usd",
        "hour": "hourly_contractor_usd",
    }.get(period)
    if range_key and low is not None and high is not None:
        lo, hi = target[range_key]
        if high < lo:
            points += cfg["below_target_penalty"]
        elif low > hi:
            points += cfg["above_target_bonus"]
    return {
        "points": points,
        "explicit": False,
        "external_estimate": estimate,
    }


def _score_compensation(text: str, vacancy: dict, criteria: dict, profile: dict):
    cfg = criteria["compensation_signal"]
    target = profile["goal"]["target_compensation"]
    # IMPORTANT: "explicitly stated" is decided by the amounts that were
    # PARSED, not by the presence of a dollar sign. Otherwise "$11M paid out
    # to engineers" would count as a stated salary even though _extract_amounts
    # rightly discards it — and the vacancy would collect full marks for
    # "transparent compensation" with an empty list of amounts.
    amounts = _extract_amounts(text)
    has_explicit = bool(vacancy.get("salary_raw")) or bool(amounts)
    if not has_explicit:
        external = _score_external_salary_estimate(vacancy, criteria, profile)
        if external is not None:
            return external["points"], external
        return cfg["no_range_points"], {"points": cfg["no_range_points"], "explicit": False}

    points = cfg["has_explicit_range_points"]
    annuals = [a for a, h, mo in amounts if a is not None]
    hourlies = [h for a, h, mo in amounts if h is not None]
    monthlies = [mo for a, h, mo in amounts if mo is not None]

    # An unfilled range simply sits out the comparison.
    #
    # This used to read target["annual_parttime_usd"] unguarded, and a profile
    # describing pay in another shape killed the WHOLE run with a KeyError
    # mid-scoring. Found by emulating onboarding on 2026-08-05: an agent
    # writing down "five to eight thousand a month" naturally writes
    # monthly_min/monthly_target. The expected shape is documented in the
    # profile template; a missing key is no reason to fall over.
    def _range(name):
        value = target.get(name)
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return value[0], value[1]
        return None

    below = above = False
    annual_range = _range("annual_parttime_usd")
    if annuals and annual_range:
        lo, hi = annual_range
        if max(annuals) < lo:
            below = True
        elif min(annuals) > hi:
            above = True
    hourly_range = _range("hourly_contractor_usd")
    if hourlies and hourly_range:
        lo, hi = hourly_range
        if max(hourlies) < lo:
            below = True
        elif min(hourlies) > hi:
            above = True
    monthly_range = _range("monthly_parttime_usd")
    if monthly_range is None and annual_range:
        monthly_range = (annual_range[0] / 12, annual_range[1] / 12)
    if monthlies and monthly_range:
        lo, hi = monthly_range
        if max(monthlies) < lo:
            below = True
        elif min(monthlies) > hi:
            above = True

    if below:
        points += cfg["below_target_penalty"]
    elif above:
        points += cfg["above_target_bonus"]

    return points, {
        "points": points,
        "explicit": True,
        "annual_amounts_found": annuals,
        "hourly_amounts_found": hourlies,
        "monthly_amounts_found": monthlies,
    }


_RED_FLAG_CATALOGUE_CACHE = {}


def red_flag_catalogue() -> dict:
    """The shared red-flag catalogue (config/derivation/company_red_flags.yaml)."""
    if "data" not in _RED_FLAG_CATALOGUE_CACHE:
        path = common.ROOT / "config" / "derivation" / "company_red_flags.yaml"
        _RED_FLAG_CATALOGUE_CACHE["data"] = common.load_yaml(path) if path.exists() else {}
    return _RED_FLAG_CATALOGUE_CACHE["data"] or {}


def classify_red_flag(flag: str):
    """The category of a free-text flag, or None."""
    text = common.normalize_for_matching(flag)
    for name, spec in (red_flag_catalogue().get("categories") or {}).items():
        if any(common.normalize_for_matching(p) in text for p in spec.get("phrases") or []):
            return name
    return None


def _score_red_flags(flags: list, profile: dict):
    """Total weight of a company's red flags, with overrides applied.

    Priority runs from general to specific, and the specific wins:
      1. the default weight from the shared catalogue;
      2. `company_red_flag_severity` from the identity profile;
      3. the same field in the local layer, which lives outside git.

    An override works IN EITHER DIRECTION. A positive value is a legitimate
    case rather than a typo: "unpredictable work availability" reads as a
    threat to someone living on the income and as a promise to someone who
    wants to be left alone. There is deliberately no clamp to non-positive
    values here.
    """
    catalogue = red_flag_catalogue()
    categories = catalogue.get("categories") or {}
    overrides = (profile or {}).get("company_red_flag_severity")
    # An unfilled local sentinel arrives here as a string. That is not a
    # dictionary of weights but a sign that the local layer said nothing.
    if not isinstance(overrides, dict):
        overrides = {}

    total = 0
    detail = []
    for flag in flags:
        category = classify_red_flag(flag)
        if category is None:
            points = catalogue.get("unrecognised_points", -5)
            source = "unrecognised"
        elif category in overrides:
            points = overrides[category]
            source = "override"
        else:
            points = (categories.get(category) or {}).get("default_points", -5)
            source = "catalogue"
        total += points
        detail.append({"flag": flag, "category": category,
                       "points": points, "source": source})
    return total, detail


def _score_company_reputation(vacancy: dict, criteria: dict, profile: dict = None):
    """Employer reputation from external sources (Glassdoor and similar),
    gathered by the agent by hand and stored at company level.

    Returns (points, breakdown, needs_review). Work-life balance weighs more
    than the overall rating here: a company can score well overall on the
    strength of pay and career growth while grinding people down, and this
    search wants exactly the opposite."""
    cfg = criteria.get("company_reputation_signal")
    rep = vacancy.get("_company_reputation")
    if not cfg or not rep:
        return (cfg or {}).get("no_data_points", 0), {"has_data": False}, False

    # "Checked and found nothing" neither adds nor removes points: the absence
    # of reviews about a small company says nothing about what working there
    # is like. But it must reach the report as its own state, or it merges
    # back into "not checked" — and those differ (see reputation.py).
    if rep.get("verdict") == "insufficient_sources":
        return (cfg.get("no_data_points", 0), {
            "has_data": False,
            "verdict": "insufficient_sources",
            "checked_at": rep.get("checked_at"),
            "searched": rep.get("searched"),
        }, False)

    points = 0
    detail = {
        "has_data": True,
        "source": rep.get("source"),
        "retrieval": rep.get("retrieval"),
        "checked_at": rep.get("checked_at"),
    }
    needs_review = False

    rating = rep.get("overall_rating")
    if rating is not None:
        rc = cfg["overall_rating"]
        detail["overall_rating"] = rating
        if rating >= rc["excellent_threshold"]:
            points += rc["excellent_points"]
        elif rating >= rc["decent_threshold"]:
            points += rc["decent_points"]
        elif rating <= rc["poor_threshold"]:
            points += rc["poor_points"]
        if rating <= rc["alarming_threshold"]:
            needs_review = True
            detail["alarming_rating"] = True

    wlb = rep.get("work_life_balance")
    if wlb is not None:
        wc = cfg["work_life_balance"]
        detail["work_life_balance"] = wlb
        if wlb >= wc["excellent_threshold"]:
            points += wc["excellent_points"]
        elif wlb <= wc["poor_threshold"]:
            points += wc["poor_points"]

    red_flags = rep.get("red_flags") or []
    if red_flags:
        detail["red_flags"] = red_flags
        needs_review = True
        # A red flag has to cost points, not merely raise a marker. Found
        # 2026-08-05: a platform whose reviews said "late payments" and
        # "unpredictable work availability" was collecting +14 for a 3.5
        # rating and 4.0 work-life balance — and leading the shortlist.
        #
        # The weight depends on WHICH flag it is and comes from the shared
        # catalogue; an identity or the local layer may override it in either
        # direction, positive included (docs/OVERRIDES.md).
        flag_points, flag_detail = _score_red_flags(red_flags, profile)
        points += flag_points
        detail["red_flag_penalty"] = flag_points
        detail["red_flag_breakdown"] = flag_detail

    detail["points"] = points
    return points, detail, needs_review


def _score_company_age(vacancy: dict, criteria: dict):
    """Company maturity from open data (Wikidata, collected automatically by
    tools/company_intel.py).

    The profile asks for a mature company because an older one usually has
    settled processes and legacy systems — which is the point of this
    search."""
    cfg = (criteria.get("company_reputation_signal") or {}).get("company_age")
    intel = vacancy.get("_company_intel")
    if not cfg or not intel or not intel.get("found"):
        return 0, {"has_data": False}

    age = intel.get("age_years")
    if age is None:
        return 0, {"has_data": False}

    if age >= cfg["mature_threshold_years"]:
        points = cfg["mature_points"]
    elif age >= cfg["established_threshold_years"]:
        points = cfg["established_points"]
    elif age <= cfg["very_young_threshold_years"]:
        points = cfg["very_young_points"]
    else:
        points = 0

    return points, {
        "has_data": True,
        "founded_year": intel.get("founded_year"),
        "age_years": age,
        "employees": intel.get("employees"),
        "points": points,
    }


def _score_contractor_friendliness(text: str, criteria: dict):
    cfg = criteria["contractor_friendliness"]
    hits = _matches(text, cfg["keywords"])
    points = min(len(hits) * cfg["points_per_keyword"], cfg["cap"])
    return points, {"points": points, "hits": hits}


def _score_personal_market_bonus(vacancy: dict, profile: dict):
    """A personal bonus for a particular market.

    Why a separate signal, and why its values live outside the repository.

    There are reasons to prefer a country that appear neither in the market
    nor in the search profile: tax residency, pension contributions, family,
    plans to move. Those are circumstances of ONE person. They belong neither
    in the shared machinery, where they have no place by definition, nor in
    the template, which anyone else may reuse.

    So the countries and their weights live in the local identity, outside
    git, and the template does not declare them at all.

    The bonus is deliberately SOFT: it moves a vacancy up the shortlist but
    never makes an impossible one possible — the gates run first and
    independently.
    """
    bonuses = (profile or {}).get("personal_market_bonus")
    if not isinstance(bonuses, dict) or not bonuses:
        return 0, {}

    haystack = " ".join(str(x) for x in (
        vacancy.get("location_raw") or "",
        " ".join(vacancy.get("tags") or []),
    )).lower()

    hits = {}
    for country, cfg in bonuses.items():
        if common.normalize_for_matching(country) not in haystack:
            continue
        points = cfg.get("points", 0) if isinstance(cfg, dict) else cfg
        # Some bonuses only make sense for remote work: paying tax at home
        # works if the work can be done from anywhere.
        if isinstance(cfg, dict) and cfg.get("remote_only") and not vacancy.get("remote"):
            continue
        hits[country] = points

    if not hits:
        return 0, {}
    total = sum(hits.values())
    return total, {"points": total, "hits": hits}


def _score_title_role_penalty(title: str, criteria: dict):
    """A soft penalty for roles the person can do but is less likely to be
    hired for.

    Not a gate: this is about odds, not possibility. A pure Frontend Developer
    role is work this profile can do, but the experience behind it is mostly
    full-stack, and against specialist frontend candidates it loses. Throwing
    such vacancies away would be wrong; showing them level with on-profile
    ones would be wrong too.
    """
    cfg = criteria.get("title_role_penalty")
    if not cfg:
        return 0, {}
    title_norm = common.normalize_for_matching(title)

    hits = []
    points = 0
    for rule in cfg.get("rules", []):
        pattern = rule.get("pattern")
        if not pattern or not re.search(pattern, title_norm, re.IGNORECASE):
            continue
        # Exceptions: "Fullstack (React)" must not count as pure frontend.
        if any(re.search(x, title_norm, re.IGNORECASE) for x in rule.get("unless", [])):
            continue
        hits.append(rule.get("label") or pattern)
        points += rule.get("points", 0)

    return points, ({"points": points, "hits": hits} if hits else {})


def _score_personal_tech_bonus(text: str, title: str, profile: dict, criteria: dict = None):
    """Personal bonuses and penalties for particular technologies.

    Why separate from stack_fit. That answers "can this person do it at all"
    and is the same for everyone using the template. How much one familiar
    stack is preferred over another is a matter of personal experience: two
    developers with the same ".NET/JS" line on a CV may be strong in quite
    different parts of it. So the values live in the local identity, outside
    git.

    The weight counts ONCE per group rather than per match: otherwise a
    vacancy spelling Node five different ways would take a fivefold penalty,
    while one mentioning .NET once would get a single bonus.
    """
    groups = (profile or {}).get("personal_tech_bonus")
    if not isinstance(groups, dict) or not groups:
        return 0, {}

    # The same stack-spam cut as in stack scoring and the industry gate.
    # Without it an outstaffing company with a "NOT YOUR TECH STACK?"
    # paragraph earns the .NET bonus on every vacancy it posts, pure React
    # roles included.
    if criteria:
        text, _ = _strip_stack_noise_sections(text, criteria)
    haystack = f"{common.normalize_for_matching(title)} {text}"
    total = 0
    hits = {}
    for name, cfg in groups.items():
        if not isinstance(cfg, dict):
            continue
        matched = _matches(haystack, cfg.get("keywords") or [])
        if not matched:
            continue
        # Exceptions matter where a technology is mentioned as adjacent rather
        # than as the substance of the role: "React + .NET" is a .NET vacancy,
        # not a Node one.
        if _matches(haystack, cfg.get("unless") or []):
            continue
        points = cfg.get("points", 0)
        total += points
        hits[name] = {"points": points, "matched": matched[:4]}

    return total, ({"points": total, "groups": hits} if hits else {})


def score_vacancy(vacancy: dict, criteria: Optional[dict] = None, profile: Optional[dict] = None) -> dict:
    criteria = criteria or load_criteria()
    profile = profile or load_profile()
    text = _vacancy_text(vacancy)

    rl_points, rl_bd, dealbreakers, needs_review, location_unknown = _score_remote_location(
        text, vacancy, criteria, profile
    )
    stack_points, stack_bd = _score_stack_fit(text, criteria, profile)
    complexity_gate, complexity_bd = _score_role_complexity(text, vacancy.get("title") or "", criteria)
    legacy_points, legacy_bd = _score_legacy_enterprise(text, criteria)
    intensity_points, intensity_bd = _score_low_intensity(text, criteria)
    comp_points, comp_bd = _score_compensation(text, vacancy, criteria, profile)
    contractor_points, contractor_bd = _score_contractor_friendliness(text, criteria)
    reputation_points, reputation_bd, reputation_needs_review = _score_company_reputation(
        vacancy, criteria, profile
    )
    if reputation_needs_review:
        needs_review = True
    age_points, age_bd = _score_company_age(vacancy, criteria)
    market_points, market_bd = _score_personal_market_bonus(vacancy, profile)
    tech_points, tech_bd = _score_personal_tech_bonus(
        text, vacancy.get("title") or "", profile, criteria)
    title_penalty, title_penalty_bd = _score_title_role_penalty(vacancy.get("title") or "", criteria)
    exporter_penalty, exporter_bd = _score_market_penalty(vacancy, criteria, profile)

    # Three FULL rejections (a zero-percent chance), confirmed explicitly on
    # 2026-07-30 — not a lower priority but a dealbreaker:
    stack_relevant, stack_relevance_bd = _check_stack_relevance(
        text, stack_bd["core_hits"], stack_bd["strong_hits"], criteria
    )
    if not stack_relevant:
        stack_label = (criteria.get("stack_fit") or {}).get("stack_label") or "target-stack"
        dealbreakers.append(
            f"stack: not a {stack_label} developer role (and no tech-agnostic signal)"
        )
    stack_bd.update(stack_relevance_bd)

    role_irrelevant, role_relevance_bd = _score_role_relevance(text, vacancy.get("title") or "", criteria)
    if role_irrelevant:
        dealbreakers.append(
            f"role: title suggests non-developer profession ({', '.join(role_relevance_bd['wrong_profession_hits'])})"
        )

    title_mismatch, title_stack_bd = _check_title_stack(
        vacancy.get("title") or "", criteria, profile
    )
    if title_stack_bd:
        stack_bd["title_stack_gate"] = title_stack_bd
    # Data pipelines are a documented exception: Scala or Java in the title,
    # in a Spark/Databricks/ETL context, remains a welcome variant.
    if title_mismatch and not stack_bd.get("data_pipeline_exception_applied"):
        dealbreakers.append(
            "stack: title names technology outside the core/strong stack "
            f"({', '.join(title_stack_bd['named_technologies'][:3])})"
        )

    infra_role, infra_bd = _check_infrastructure_role(text, vacancy.get("title") or "", criteria)
    role_relevance_bd["infrastructure_role_gate"] = infra_bd
    if infra_role:
        dealbreakers.append(
            "role: infrastructure/platform (DevOps) role despite a neutral title "
            f"({', '.join(infra_bd['hits'][:5])})"
        )

    industry_blocked, industry_bd = _check_industry_dealbreaker(text, criteria)
    if industry_bd:
        legacy_bd["industry_dealbreaker_gate"] = industry_bd
    if industry_blocked:
        dealbreakers.append(
            "industry: an industry this search avoids "
            f"({', '.join(industry_bd['hits'][:4])})"
        )

    mobile_role, mobile_bd = _check_mobile_role(text, vacancy.get("title") or "", criteria)
    if mobile_bd:
        role_relevance_bd["mobile_role_gate"] = mobile_bd
    if mobile_role:
        dealbreakers.append(
            "role: mobile app development despite a neutral title "
            f"({', '.join(mobile_bd['hits'][:4])})"
        )

    pipeline_ad, pipeline_bd = _check_talent_pipeline(text, criteria)
    if pipeline_bd:
        role_relevance_bd["talent_pipeline_gate"] = pipeline_bd
    if pipeline_ad:
        dealbreakers.append(
            "no actual opening: a talent-pipeline advertisement "
            f"({', '.join(pipeline_bd['hits'][:3])})"
        )

    crowdwork, crowdwork_bd = _check_ai_training_crowdwork(text, criteria)
    if crowdwork_bd:
        role_relevance_bd["ai_training_crowdwork_gate"] = crowdwork_bd
    if crowdwork:
        dealbreakers.append(
            "role: AI-training crowdwork, not a software engineering job "
            f"({', '.join(crowdwork_bd['hits'][:3])})"
        )

    language_mismatch, language_bd = _score_language_fit(text, criteria)
    if language_mismatch:
        foreign = language_bd.get("foreign_language_posting_hits") or {}
        reason = (
            ", ".join(language_bd["explicit_requirement_hits"])
            or ("posting appears to be written in " + ", ".join(foreign) if foreign else "")
            or "posting appears to be in German"
        )
        dealbreakers.append(f"language: {reason}")

    employment_dealbreakers = _matches(
        text, profile["employment_type_priority"]["dealbreaker_signals"]
    )
    if employment_dealbreakers:
        dealbreakers.extend(f"employment: {d}" for d in employment_dealbreakers)

    raw_total = (
        rl_points
        + stack_points
        + legacy_points
        + intensity_points
        + comp_points
        + contractor_points
        + reputation_points
        + age_points
        + market_points
        + tech_points
        + title_penalty
        + exporter_penalty
    )
    total = max(0, min(100, round(raw_total)))

    thresholds = criteria["classification_thresholds"]

    # A vacancy whose ONLY objection is a country in the structured location
    # field is not dropped silently but placed in its own class.
    #
    # Why this rather than a rejection, revised 2026-08-05 after the owner
    # objected. Measured: 501 vacancies with .NET in the title were rejected
    # for exactly this reason and no other, and ALL 501 were marked remote by
    # their source. Of the 78 that had a description, the employer restricts
    # the right to work in only 16 — in the other 62 the rejection rests on
    # the guess that a vacancy in country N is for residents of N.
    #
    # The guess is usually right, and these must not be mixed into the main
    # shortlist: there are hundreds of them and they would drown a dozen real
    # candidates. But deciding on someone's behalf that a B2B contract with a
    # Dutch company is out of reach is not the system's call either. Hence a
    # separate class and a separate section of the report.
    country_only = bool(dealbreakers) and all(
        d.startswith("location: source restricts hiring to") for d in dealbreakers
    )

    # A vacancy nobody ever called remote. Same shape as the class above, and
    # for the same reason — the objection is about our knowledge rather than
    # about the job — but it is a per-identity choice, because it is only an
    # objection at all for somebody who cannot commute. An identity looking
    # for onsite work sets "accept" and never sees the class.
    #
    # policy: "manual_check" (own class, own section, the person decides) |
    #         "reject" (as before 2026-08-11) | "accept" (ignore entirely)
    policy = (criteria.get("remote_location_fit") or {}).get(
        "unconfirmed_remote_policy", "manual_check")
    if policy == "accept":
        dealbreakers = [d for d in dealbreakers if d != REMOTE_UNCONFIRMED]
    unconfirmed_only = bool(dealbreakers) and all(
        d == REMOTE_UNCONFIRMED for d in dealbreakers)

    if country_only:
        classification = "national_market"
    elif unconfirmed_only and policy == "manual_check":
        # The score is deliberately NOT reduced — a 70 here is the same 70 it
        # would have been in hot_lead. Only the certainty differs, and that is
        # what the separate section communicates.
        classification = "remote_unconfirmed"
    elif dealbreakers:
        classification = "rejected"
    elif complexity_gate:
        classification = "low_priority"
    elif total >= thresholds["hot_lead"]:
        classification = "hot_lead"
    elif total >= thresholds["worth_a_look"]:
        classification = "worth_a_look"
    elif total >= thresholds["long_shot"]:
        classification = "long_shot"
    else:
        classification = "low_priority"

    # General location uncertainty — no explicit "worldwide", no "US only", no
    # EOR signal — is worth a human glance only for records already in view
    # (long_shot and above). On real data the flag otherwise fires on almost
    # everything, and the review section of the report becomes useless.
    if location_unknown and classification in ("hot_lead", "worth_a_look", "long_shot"):
        needs_review = True

    breakdown = {
        "remote_location_fit": rl_bd,
        "stack_fit": stack_bd,
        "role_complexity_signal": complexity_bd,
        "role_relevance_signal": role_relevance_bd,
        "language_requirement_signal": language_bd,
        "legacy_enterprise_signal": legacy_bd,
        "low_intensity_signal": intensity_bd,
        "compensation_signal": comp_bd,
        "contractor_friendliness": contractor_bd,
        "company_reputation_signal": reputation_bd,
        "company_age_signal": age_bd,
        "net_exporter_penalty": exporter_bd,
        "personal_market_bonus": market_bd,
        "personal_tech_bonus": tech_bd,
        "title_role_penalty": title_penalty_bd,
        "raw_total_before_clamp": raw_total,
    }

    eligibility, eligibility_reason = _residency_eligibility(
        rl_bd, dealbreakers, vacancy, criteria, profile)

    return {
        "score": total,
        "score_breakdown": breakdown,
        "classification": classification,
        "dealbreakers": dealbreakers,
        "needs_manual_review": needs_review,
        # Can a contractor sitting where this person sits actually take the
        # work? A separate axis from the score, deliberately — see
        # _residency_eligibility.
        "residency_eligibility": eligibility,
        "residency_eligibility_reason": eligibility_reason,
    }
