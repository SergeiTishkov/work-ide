"""
Generates the human-readable Markdown report from the current knowledge base.

The report is the owner's main interface: over ten minutes of morning coffee
they should be able to look through the top vacancies and decide where to
apply.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import i18n  # noqa: E402
import kb  # noqa: E402

# The English text is the source; a translation is looked up in the catalogue.
# The reasoning behind "the key IS the English phrase" is in tools/i18n.py.
t = i18n.translate

TOP_N_PER_SECTION = 15

# The classes a person actually reads. Everything else is in the database for
# the record, not in the report for a decision.
LISTED_CLASSES = ("hot_lead", "worth_a_look", "long_shot", "national_market",
                  "remote_unconfirmed")


def _fmt_amount(value: float) -> str:
    if value == int(value):
        return f"${int(value):,}"
    return f"${value:,.2f}"


def _fmt_salary_info(vacancy: dict, comp_bd: dict) -> str:
    """Always returns a pay line that names its source. Confirmed explicitly by
    the owner (2026-07-30): whether the salary is stated in the vacancy itself,
    was found by the agent on an external site (Glassdoor and the like), or is
    absent altogether has to be visible in the report rather than only
    affecting the score."""
    if comp_bd.get("explicit"):
        raw = vacancy.get("salary_raw")
        if raw:
            return f"{raw} _({t('source: stated in the vacancy')})_"
        periods = {"annual_amounts_found": t("year"),
                   "monthly_amounts_found": t("month"),
                   "hourly_amounts_found": t("hour")}
        parts = []
        for key, unit in periods.items():
            amounts = comp_bd.get(key) or []
            if not amounts:
                continue
            lo, hi = min(amounts), max(amounts)
            parts.append(f"{_fmt_amount(lo)}/{unit}" if lo == hi else f"{_fmt_amount(lo)}-{_fmt_amount(hi)}/{unit}")
        text = (", ".join(parts) if parts
                else t("amount mentioned in the description but not parsed reliably"))
        return f"{text} _({t('source: stated in the vacancy')})_"

    estimate = comp_bd.get("external_estimate")
    if estimate:
        period = {"year": t("year"), "month": t("month"),
                  "hour": t("hour")}.get(estimate.get("period"), estimate.get("period"))
        source = estimate.get("source", t("unknown third-party source"))
        note = estimate.get("note")
        note_str = f", {t('note')}: {note}" if note else ""
        return (
            f"{_fmt_amount(estimate['low'])}-{_fmt_amount(estimate['high'])}/{period} "
            f"_({t('source')}: {source}, {t('found manually on a third-party site')}{note_str})_"
        )

    return (t("not stated") + " _("
            + t("source: no data — neither in the vacancy nor found manually") + ")_")


def _fmt_reputation(rep_bd: dict, classification: str = "") -> str:
    """The employer-reputation line. As with pay, the source is always named,
    and "no data" is kept distinct from "bad"."""
    # Three states rather than two. The distinction was added at the owner's
    # direct request on 2026-08-06 and closes a genuine ambiguity: "not
    # checked" read as "no data exists" while it actually meant "we never even
    # tried". The first is a property of the company, the second a defect in
    # the process, and which of the two a person is looking at matters.
    if rep_bd.get("verdict") == "insufficient_sources":
        when = (rep_bd.get("checked_at") or "")[:10]
        where = rep_bd.get("searched") or "Glassdoor, Indeed, Trustpilot, web search"
        return (f"{t('checked')}{' ' + when if when else ''}, "
                f"{t('not determined — not enough sources')} "
                f"_({t('searched')}: {where}; "
                f"{t('usually the case for small, little-known companies')})_")

    if not rep_bd.get("has_data"):
        import reputation

        if classification in reputation.REQUIRED_CLASSES:
            return (
                "❗ " + t("not checked yet") + " _("
                + t("this is a gap in the process, not a property of the company")
                + ": `python tools/reputation.py worklist`)_"
            )
        # The tail of the shortlist is deliberately left unchecked — see
        # reputation.py.
        return (t("not checked") + " _("
                + t("tail of the shortlist: companies at worth_a_look and above are checked")
                + ")_")
    parts = []
    if rep_bd.get("overall_rating") is not None:
        parts.append(f"{t('overall')} {rep_bd['overall_rating']}/5")
    if rep_bd.get("work_life_balance") is not None:
        parts.append(f"{t('work-life balance')} {rep_bd['work_life_balance']}/5")
    text = ", ".join(parts) if parts else t("rating without numbers")
    source = rep_bd.get("source", "?")
    # Show not only WHAT the source was but HOW the data was obtained: numbers
    # taken from search results are second-hand — the primary source (Glassdoor
    # and the like) answers 403 to scripts and was never opened by the agent.
    retrieval_note = {
        "web_search": ", " + t("data from search results — the primary source was not opened"),
        "direct": ", " + t("the primary source page was read"),
        "owner": ", " + t("as told by the owner"),
    }.get(rep_bd.get("retrieval"), "")
    flags = rep_bd.get("red_flags") or []
    flag_str = f" ⚠ {t('red flags')}: {', '.join(flags)}" if flags else ""
    alarming = " 🚨 " + t("very low rating") if rep_bd.get("alarming_rating") else ""
    return f"{text} _({t('source')}: {source}{retrieval_note})_{alarming}{flag_str}"


_TECH_VOCABULARY_CACHE = {}


def _tech_vocabulary() -> dict:
    """The technology vocabulary: canonical name -> ways of writing it.

    Shared by every identity: the list of what appears in vacancies does not
    depend on who is searching. It lives in config/tech_vocabulary.yaml.
    """
    if not _TECH_VOCABULARY_CACHE:
        path = common.SHARED_CONFIG_DIR / "tech_vocabulary.yaml"
        data = (common.load_yaml(path) or {}).get("technologies") or {}
        _TECH_VOCABULARY_CACHE.update(data)
    return _TECH_VOCABULARY_CACHE


def expected_technologies(vacancy: dict, limit: int = 24) -> list:
    """The technologies a project expects — including ones the person does not
    know.

    Separate from stack_fit: that shows overlaps with a particular person's
    stack, whereas what is wanted here is the project's composition as it is.
    Seeing an unfamiliar technology in the report is no less useful than a
    familiar one: it tells you straight away whether the vacancy fits, without
    opening the link.
    """
    haystack = common.normalize_for_matching(chr(10).join([
        vacancy.get("title") or "",
        " ".join(vacancy.get("tags") or []),
        vacancy.get("description_text") or "",
    ]))
    if not haystack:
        return []

    found = []
    for canonical, forms in _tech_vocabulary().items():
        for form in (forms or []):
            if common.normalize_for_matching(form) in haystack:
                found.append(canonical)
                break
        if len(found) >= limit:
            break
    return found


# Countries, spelled the way the job boards spell them.
_COUNTRY_ALIASES = {
    "usa": "United States", "us": "United States", "u.s.": "United States",
    "united states of america": "United States", "america": "United States",
    "uk": "United Kingdom", "u.k.": "United Kingdom", "england": "United Kingdom",
    "scotland": "United Kingdom", "wales": "United Kingdom",
    "northern ireland": "United Kingdom", "great britain": "United Kingdom",
    "uae": "United Arab Emirates", "u.a.e.": "United Arab Emirates",
    "ksa": "Saudi Arabia", "holland": "Netherlands", "deutschland": "Germany",
    "schweiz": "Switzerland", "suisse": "Switzerland", "österreich": "Austria",
    "españa": "Spain", "italia": "Italy", "sverige": "Sweden", "norge": "Norway",
    "danmark": "Denmark", "suomi": "Finland", "éire": "Ireland",
    "czechia": "Czech Republic", "czech republic": "Czech Republic",
}

# How the country was learned. Constants rather than inline strings: these are
# COMPARED, and translating a compared value is a classic way to break logic
# silently.
HIRING_OFFICE = "hiring office"
COMPANY_HOME = "company home country"

_COUNTRY_INDEX_CACHE = {}


def _country_index() -> dict:
    """Normalised country name -> canonical name.

    The country list comes from the shared markets table: it already enumerates
    everything the project cares about, and maintaining a second list would buy
    nothing.
    """
    if "data" not in _COUNTRY_INDEX_CACHE:
        import markets

        index = {}
        for spec in (markets.load_tiers() or {}).values():
            for country in spec.get("countries") or []:
                name = country.get("name")
                if name:
                    index[common.normalize_for_matching(name)] = name
        for alias, canonical in _COUNTRY_ALIASES.items():
            index.setdefault(alias, canonical)
        _COUNTRY_INDEX_CACHE["data"] = index
    return _COUNTRY_INDEX_CACHE["data"]


def hiring_country(vacancy: dict):
    """(country, how it was learned) — or (None, None).

    What is wanted is the HIRING COUNTRY, not where the company was founded.
    For an international company those differ: Google's Swiss office hires in
    Switzerland, and Switzerland is what matters to a person — that is where
    the contract is signed, where the money comes from, which time zone
    applies. Hence this order of sources:

      1. the board tag `market:<country>` — the country the fetcher queried,
         that is, the office that posted the vacancy. A fact, not a guess;
      2. the last element of the location field ("Barendrecht, South Holland,
         Netherlands");
      3. any mention of a country in the location field ("Remote, Israel");
      4. a "Headquarters:" heading in the description — that is the head
         office rather than the hiring one, so it comes last and is labelled
         explicitly.
    """
    index = _country_index()

    for tag in vacancy.get("tags") or []:
        tag = str(tag)
        if tag.startswith("market:"):
            name = index.get(common.normalize_for_matching(tag[7:]), tag[7:])
            return name, HIRING_OFFICE

    location = (vacancy.get("location_raw") or "").strip()
    if location:
        parts = [p.strip() for p in location.split(",") if p.strip()]
        if parts:
            direct = index.get(common.normalize_for_matching(parts[-1]))
            if direct:
                return direct, HIRING_OFFICE
        normalized = common.normalize_for_matching(location)
        for needle, canonical in index.items():
            if needle and needle in normalized:
                return canonical, HIRING_OFFICE

    header = (vacancy.get("computed", {}).get("score_breakdown", {})
              .get("remote_location_fit", {}).get("header_scope", {}))
    for line in header.get("header_lines") or []:
        if not line.startswith("headquarters:"):
            continue
        for needle, canonical in index.items():
            if needle and needle in line:
                return canonical, COMPANY_HOME

    return None, None


def _eligibility_rank(v: dict) -> int:
    """Position in score.ELIGIBILITY_ORDER; anything unrecognised sorts last."""
    import score as score_mod

    verdict = (v.get("computed") or {}).get("residency_eligibility")
    try:
        return score_mod.ELIGIBILITY_ORDER.index(verdict)
    except ValueError:
        return len(score_mod.ELIGIBILITY_ORDER)


def _fmt_eligibility(v: dict) -> list:
    """Can a contractor sitting where this person sits actually take the work?

    Shown separately from the score and never folded into it. A vacancy that
    pays well and cannot be taken is worth less than one that pays adequately
    and can, and a single number cannot say that — see
    score._residency_eligibility.
    """
    c = v.get("computed") or {}
    verdict = c.get("residency_eligibility")
    if not verdict:
        return []
    label = {
        "confirmed": "✅ " + t("eligibility: confirmed"),
        "likely": "🟢 " + t("eligibility: likely"),
        "unknown": "❔ " + t("eligibility: not stated"),
        "no": "⛔ " + t("eligibility: no"),
    }.get(verdict, verdict)
    reason = c.get("residency_eligibility_reason")
    return [f"  - {label}" + (f" — _{reason}_" if reason else "")]


def _salary_benchmark_block(segment) -> list:
    """What the UK market pays for this stack, beside the shortlist.

    Rendered only where UK vacancies appear. The source is British: putting
    British medians at the top of the Canada file would be noise dressed as
    information.

    Nothing else reads this. It is context for a person, never a component of
    a score and never a salary written onto a vacancy — see
    tools/salary_benchmark.py for why both would be wrong.
    """
    import salary_benchmark
    import segments as segments_mod

    if segment is not None:
        claimed = segments_mod._claimed_groups([segment])
        if not segment.holds("united_kingdom", claimed):
            return []

    data = salary_benchmark.load()
    rows = (data or {}).get("technologies") or {}
    if not rows:
        return []

    lines = [
        f"## 💷 {t('What the UK market pays for this stack')}",
        "",
        t("A yardstick, not an offer. These are market medians over the last "
          "six months — they say whether a stated salary is generous or poor, "
          "and they are never written onto a vacancy or into a score.") +
        f" _({data.get('source')}, {(data.get('collected_at') or '?')[:10]})_",
        "",
        f"| {t('technology')} | {t('permanent, per year')} | {t('contract, per day')} |",
        "|---|---|---|",
    ]
    for name, entry in rows.items():
        permanent = entry.get("permanent") or {}
        contract = entry.get("contract") or {}

        def cell(item):
            if not item.get("median"):
                return "—"
            change = item.get("year_on_year")
            return item["median"] + (f" _({change})_" if change else "")

        lines.append(f"| {name} | {cell(permanent)} | {cell(contract)} |")
    lines.append("")
    return lines


def _fmt_apply_channels(v: dict) -> list:
    """Where to apply without going through the board.

    Only looked up for the top of the shortlist (tools/apply_channels.py), so
    most vacancies have nothing here — and that is different from "we looked
    and found nothing", which the owner asked to be told about explicitly.
    """
    found = v.get("apply_channels")
    if not found:
        return []
    lines = []
    if found.get("direct_apply_url"):
        lines.append(f"  - 📨 {t('apply directly')}: {found['direct_apply_url']}")
    elif found.get("board_url"):
        lines.append(
            f"  - 📨 {t('the company hires through')} "
            f"{found.get('board_provider') or '?'}: {found['board_url']} "
            f"_({t('this vacancy is not on the board — possibly placed through an agency')})_")
    if found.get("emails"):
        lines.append(f"  - ✉️ {t('address given in the vacancy')}: "
                     + ", ".join(found["emails"]))
    if not lines:
        lines.append(f"  - 📨 _{t('no direct way to apply found — only through the board')}_")
    return lines


def _fmt_vacancy_line(v: dict) -> str:
    c = v.get("computed", {})
    score = c.get("score", 0)
    title = v.get("title", "?")
    company = v.get("company", "?")
    url = v.get("url", "")
    manual = v.get("manual", {})
    status = manual.get("status", "new")

    bd = c.get("score_breakdown", {})
    highlights = []
    legacy_hits = bd.get("legacy_enterprise_signal", {}).get("hits", [])
    if legacy_hits:
        highlights.append("legacy/enterprise: " + ", ".join(legacy_hits[:5]))
    rl = bd.get("remote_location_fit", {})
    if rl.get("worldwide_remote_hits"):
        highlights.append("worldwide remote")
    if rl.get("eor_or_contractor_hits"):
        highlights.append("EOR/contractor: " + ", ".join(rl["eor_or_contractor_hits"][:3]))
    intensity = bd.get("low_intensity_signal", {})
    if intensity.get("positive_hits"):
        highlights.append(t("low intensity") + ": " + ", ".join(intensity["positive_hits"][:4]))
    complexity = bd.get("role_complexity_signal", {})
    if complexity.get("gate_triggered"):
        highlights.append("⚠ " + t("looks like a complex/R&D role, not a simple one"))
    if c.get("needs_manual_review"):
        highlights.append("🔎 " + t("needs a manual check (see below)"))
    link_status = v.get("link_check", {}).get("status")
    if link_status == "unknown":
        highlights.append("🔗 " + t("the link could not be verified conclusively"))

    highlight_str = f" — _{'; '.join(highlights)}_" if highlights else ""
    salary_line = _fmt_salary_info(v, bd.get("compensation_signal", {}))
    lines = [
        f"- **[{score}] {title}** @ {company} — [{t('link')}]({url}) — "
        f"{t('status')}: `{status}`{highlight_str}",
        f"  - 💰 {t('salary')}: {salary_line}",
    ]
    # The employer's own site, when known — so the same vacancy can be found on
    # their careers page and applied to without an account on the job board
    # (WWR keeps the application funnel to itself, see docs/SOURCES.md).
    company_url = v.get("company_url")
    if company_url:
        lines.append(f"  - 🏢 {t('company site (apply directly)')}: {company_url}")
    lines.extend(_fmt_eligibility(v))
    lines.extend(_fmt_apply_channels(v))
    techs = expected_technologies(v)
    if techs:
        lines.append(f"  - 🧰 {t('technologies')}: {', '.join(techs)}")
    lines.append("  - ⭐ " + t("reputation") + ": " + _fmt_reputation(
        bd.get("company_reputation_signal", {}), c.get("classification", "")))
    country, country_source = hiring_country(v)
    if country:
        suffix = "" if country_source == HIRING_OFFICE else f" _({t(country_source)})_"
        lines.append(f"  - 🌍 {t('hiring country')}: {country}{suffix}")
    else:
        # A missing country comes in two different kinds, worth keeping apart:
        # either the vacancy is deliberately geography-free, or the board did
        # not say.
        verdict = (bd.get("remote_location_fit", {})
                   .get("structured_location", {}).get("verdict"))
        location = (v.get("location_raw") or "").strip()
        if verdict in ("worldwide", "worldwide_by_continents", "remote_without_country"):
            lines.append(f"  - 🌍 {t('hiring country')}: {t('without a country')}")
        else:
            lines.append(f"  - 🌍 {t('hiring country')}: {t('not determined')}"
                         + (f" _({t('the board said')}: «{location}»)_" if location else ""))
    age_bd = bd.get("company_age_signal", {})
    if age_bd.get("has_data"):
        emp = f", ~{age_bd['employees']} {t('employees')}" if age_bd.get("employees") else ""
        lines.append(
            f"  - 🏛 {t('company')}: {t('founded')} {age_bd['founded_year']} "
            f"({age_bd['age_years']} {t('years old')}{emp}) _(Wikidata)_"
        )
    if manual.get("notes"):
        lines.append(f"  - {t('note')}: {manual['notes']}")
    return "\n".join(lines)


# How many national-market vacancies to show. There are hundreds; the point of
# the section is to let a person see that the market exists, not to page
# through all of it.
NATIONAL_MARKET_LIMIT = 25


def _section(title: str, items: list) -> str:
    if not items:
        return f"### {title}\n\n_{t('Empty for now.')}_\n"
    body = "\n".join(_fmt_vacancy_line(v) for v in items[:TOP_N_PER_SECTION])
    extra = len(items) - TOP_N_PER_SECTION
    footer = (f"\n\n_({t('and one more')} {extra} — `python tools/kb.py list`)_"
              if extra > 0 else "")
    return f"### {title} ({len(items)})\n\n{body}{footer}\n"


def _rel(path: Optional[Path]) -> str:
    """A path relative to the repository root — easier to copy that way."""
    if path is None:
        return "?"
    try:
        return str(path.relative_to(common.ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


_DEFAULT_PHILOSOPHY = (
    "The higher the score (0-100), the closer the vacancy is to this "
    "identity's profile."
)


def _scoring_philosophy() -> str:
    """The explanation of the score scale — different for every identity.

    This used to be a hard-coded line about a "boring, legacy, well-paid"
    vacancy. It was printed in the report of EVERY identity, including one
    looking for onsite work at a startup — that is, shared machinery imposing
    one search profile's philosophy on everybody. An artefact of the days when
    there was only one profile.
    """
    try:
        philosophy = ((common.load_profile().get("identity") or {})
                      .get("scoring_philosophy") or "").strip()
        return philosophy or _DEFAULT_PHILOSOPHY
    except Exception:  # noqa: BLE001 — a caption must not bring the report down
        return _DEFAULT_PHILOSOPHY


def _identity_display_name() -> str:
    try:
        import identity as identity_mod

        return identity_mod.describe(common.ACTIVE_IDENTITY)
    except Exception:  # noqa: BLE001 - a caption must not bring the report down
        return common.ACTIVE_IDENTITY or t("not determined")


def _ambiguous_places_hint(criteria: Optional[dict]) -> str:
    """The hint about ambiguous place names — taken from the active identity's
    settings rather than hard-coded. Everyone has their own trap: for one
    person it is Georgia (the country vs the state), for another Cambridge
    (UK vs Massachusetts)."""
    rules = ((criteria or {}).get("remote_location_fit") or {}).get("ambiguous_place_names") or []
    names = [r.get("name") for r in rules if r.get("name")]
    if not names:
        return t("an ambiguous place name")
    quoted = ", ".join(f'"{n}"' for n in names[:3])
    return f"{t('an ambiguous place name')} ({t('for example')} {quoted})"


def _format_link_check_stats(stats: Optional[dict]) -> str:
    if not stats:
        return f"_{t('no data')} ({t('first run after link checking was added')})_"
    return (
        f"{t('checked on this run')}: {stats.get('checked', 0)} "
        f"({t('skipped — recently checked or duplicates')}: "
        f"{stats.get('skipped_recent_or_duplicate', 0)}). "
        f"{t('alive')}: {stats.get('ok', 0)}, "
        f"{t('removed as dead (404/410)')}: {stats.get('dead', 0)}, "
        f"{t('could not be verified conclusively (kept visible)')}: "
        f"{stats.get('unknown', 0)}."
    )


def _source_usefulness(vacancies: dict) -> str:
    """How many records a source brought in, and how many reached the shortlist.

    WHY. The source registry stores VOLUME, and by volume the sources look
    nothing like what they are. Measured 2026-08-05: devitjobs produced 4033
    records and ZERO in the shortlist, while weworkremotely, with its 251,
    produced more than half of all candidates. Volume with no yield is only run
    time and a bloated database.

    So what is counted is "yield per 100 records". A source with zero yield is
    not disabled automatically: rare sources deliver in bursts, and deciding on
    one run would be hasty. But the number has to be in front of you.
    """
    stats = {}
    for v in vacancies.values():
        if v.get("duplicate_of"):
            continue
        src = v.get("source") or "?"
        entry = stats.setdefault(src, {"total": 0, "shortlist": 0})
        entry["total"] += 1
        if (v.get("computed") or {}).get("classification") in (
                "hot_lead", "worth_a_look", "long_shot"):
            entry["shortlist"] += 1

    if not stats:
        return f"_{t('no data')}_"

    rows = sorted(stats.items(), key=lambda kv: -kv[1]["shortlist"])
    lines = [f"| {t('Source')} | {t('Records')} | {t('In shortlist')} | "
             f"{t('Per 100 records')} |", "|---|---:|---:|---:|"]
    for name, s in rows:
        rate = (100.0 * s["shortlist"] / s["total"]) if s["total"] else 0.0
        lines.append(f"| {name} | {s['total']} | {s['shortlist']} | {rate:.1f} |")
    return chr(10).join(lines)


def _reputation_coverage_block(vacancies: dict, companies: dict) -> str:
    """How many companies at the head of the shortlist were checked, and who is
    left.

    The section exists because work not done has to be visible. Measured
    2026-08-06: hot_lead and worth_a_look held 55 companies, reputation was
    known for zero of them, and the report said nothing about it — writing "not
    checked" against each, which reads as a property of the company rather than
    as a gap.
    """
    import reputation

    stats = reputation.coverage(vacancies, companies)
    if not stats["companies"]:
        return f'_{t("The shortlist has no hot_lead / worth_a_look companies yet.")}_'

    lines = [
        f"{t('Companies at the head of the shortlist (hot_lead + worth_a_look)')}: "
        f"**{stats['companies']}**",
        "",
        f"- {t('reputation found')}: **{stats['found']}**",
        f"- {t('checked, no credible reviews exist')}: **{stats['insufficient']}** "
        f"_({t('usually the case for small, little-known companies')})_",
        f"- **{t('not checked')}: {stats['unchecked']}**",
    ]
    if stats["unchecked"]:
        todo = reputation.worklist(vacancies, companies, limit=12)
        lines += [
            "",
            "> ⚠ " + t("Unchecked companies are a gap in the process, not a property "
            "of the companies. Until the check is done the report cannot tell "
            "'no reviews exist' from 'we did not look', and for a decision "
                       "those are different things."),
            "",
            t('Still to check') + ':',
            "",
        ] + [f"- {item['classification']}: {item['company']}" for item in todo]
        if stats["unchecked"] > len(todo):
            lines.append(f"- _…{t('and one more')} {stats['unchecked'] - len(todo)}_")
        lines += [
            "",
            "```bash",
            "python tools/reputation.py worklist          # the full list",
            "python tools/kb.py set-company-reputation \\",
            "    --company \"<name>\" --rating 4.2 --wlb 4.4 --source Glassdoor",
            "python tools/reputation.py mark-insufficient --company \"<name>\"",
            "```",
        ]
    else:
        lines += ['', t('No gaps: every company at the head of the shortlist has a result.')]
    return "\n".join(lines)


def segment_filename(slug: str, prefix: Optional[str] = None) -> str:
    """The file one segment is written to.

    An empty slug is the whole shortlist and keeps the historical name, because
    `reports/<prefix>_latest.md` is what RUNBOOK.md, the archive and a person's
    habit all point at.
    """
    prefix = prefix if prefix is not None else (common.FILE_PREFIX or "")
    return f"{prefix}{slug}_latest.md" if slug else f"{prefix}latest.md"


def _segment_banner(segment, siblings, shown: int, listed=()) -> str:
    """Which shortlist this is, and where the others are.

    Without this, splitting the report would quietly hide work: a person
    opening the UK file has no way of knowing that the worldwide one — the one
    where geography is not in the way at all — exists at all.
    """
    if segment is None:
        return ""
    others = [s for s in (siblings or []) if s.slug != segment.slug]
    links = ", ".join(
        f"[{s.name}]({segment_filename(s.slug)})" for s in others)
    line = (f"**{t('This shortlist')}: {segment.name}** — "
            f"{shown} {t('vacancies')}.")

    # A segment holding several markets — `rest` above all — is otherwise a
    # bag: 338 vacancies with no way of telling that two thirds of them are
    # Singapore. The breakdown makes it legible without another file, and
    # shows a person whether one is worth asking for.
    if segment.rest or segment.everything:
        import segments as segments_mod

        tally = segments_mod.counts_by_group(
            listed, lambda v: hiring_country(v)[0])
        if len(tally) > 1:
            parts = ", ".join(
                f"{segments_mod.group_name(key)} {n}"
                for key, n in sorted(tally.items(), key=lambda kv: -kv[1]))
            line += f"\n\n_{t('Markets inside')}: {parts}._"

    if links:
        line += f"\n\n_{t('Other shortlists from this search')}: {links}._"
    return line + "\n"


def build_report_markdown(vacancies: dict, companies: dict, state: dict,
                          criteria: Optional[dict] = None,
                          segment=None, siblings=None) -> str:
    """The shortlist as Markdown.

    `segment` (tools/segments.Segment) narrows it to one market group; without
    one the report covers everything, exactly as it did before splitting
    existed. `siblings` are the other segments, so each file can point at the
    others — a person who opens the UK shortlist should not have to remember
    that a worldwide one exists.
    """
    import score

    now = datetime.now(timezone.utc)
    # Report text that depends on settings (the ambiguous-place-names hint, for
    # one) comes from the active identity.
    if criteria is None:
        try:
            criteria = score.load_criteria()
        except Exception:  # noqa: BLE001 - a hint must not break the report
            criteria = {}
    live = [v for v in vacancies.values() if not v.get("duplicate_of")]
    dead_link_count = sum(1 for v in live if v.get("link_check", {}).get("status") == "dead")
    items = [v for v in live if v.get("link_check", {}).get("status") != "dead"]
    duplicate_count = len(vacancies) - len(live)

    # One market group's worth of the same shortlist. The counts above stay
    # global on purpose: "collapsed N duplicates" is a fact about the run, and
    # restating it per file would make eight different numbers for one thing.
    # What the banner counts. NOT len(items): that includes everything the
    # gates rejected, which in a segment banner reads as "this market has ten
    # thousand vacancies for you" when it has eleven.
    def _listed(candidates):
        return sum(1 for v in candidates
                   if (v.get("computed") or {}).get("classification") in LISTED_CLASSES)

    segment_total = _listed(items)
    if segment is not None:
        import segments as segments_mod

        claimed = segments_mod._claimed_groups(list(siblings or [segment]))
        items = [v for v in items
                 if segment.holds(segments_mod.group_of(hiring_country(v)[0]), claimed)]
        segment_total = _listed(items)

    def by_class(cls):
        matching = [v for v in items if v.get("computed", {}).get("classification") == cls]
        # Reachability first, score second. The owner's instruction, and the
        # reason the two are separate axes at all: "$100/hour — Remote — US" is
        # worth less than "$70/hour — Remote Worldwide" to somebody who cannot
        # take the first. The score is still shown, so nothing is hidden — only
        # reordered.
        matching.sort(key=lambda v: (
            _eligibility_rank(v), -v.get("computed", {}).get("score", 0)))
        return matching

    hot = by_class("hot_lead")
    worth = by_class("worth_a_look")
    long_shot = by_class("long_shot")
    # Vacancies whose only objection is the country in the location field. Not
    # in the main shortlist — there are hundreds and they would drown a dozen
    # live candidates — but not thrown away either: the guess "a vacancy in
    # country N is for residents of N" is not always right, and whether to
    # apply is the person's decision rather than the system's. The top of them
    # by score is shown, grouped by country.
    national = by_class("national_market")[:NATIONAL_MARKET_LIMIT]
    # Vacancies whose only objection is that nobody ever said they were
    # remote. Their own section, their own decision — and their score
    # untouched, at the owner's explicit direction (2026-08-11).
    unconfirmed = by_class("remote_unconfirmed")[:NATIONAL_MARKET_LIMIT]
    # Only vacancies whose fate is still undecided need manual review.
    #
    # An actual complaint from the owner, 2026-08-05: this section contained
    # Sales Manager, Business Partner Analyst, Patient Outreach Specialist and
    # Data Entry — all of them REJECTED. The "needs review" flag is set
    # independently of classification, so the section gathered the discarded
    # along with the doubtful. There is nothing to review in a rejected
    # vacancy: the gate has already decided, and the person spends attention on
    # rubbish in the one place they actually look.
    visible = {"hot_lead", "worth_a_look", "long_shot"}
    review_items = [v for v in items
                    if v.get("computed", {}).get("needs_manual_review")
                    and v.get("computed", {}).get("classification") in visible]
    review_items.sort(key=lambda v: -v.get("computed", {}).get("score", 0))

    class_counts = {}
    for v in items:
        cls = v.get("computed", {}).get("classification", "unknown")
        class_counts[cls] = class_counts.get(cls, 0) + 1

    source_lines = []
    for name, info in sorted((state.get("sources") or {}).items()):
        status = "OK" if not info.get("last_error") else f"ERROR: {info['last_error']}"
        source_lines.append(
            f"- **{name}**: {info.get('fetched_count', 0)} "
            f"{t('records on the last run')}, "
            f"{status}, {t('consecutive failures')}: "
            f"{info.get('consecutive_failures', 0)}"
        )

    run_stats = state.get("last_run_stats", {})

    parts = [
        # The identity goes in the title: a report is often opened in its own
        # tab or forwarded, and it has to identify itself without context.
        f"# Work IDE [{common.ACTIVE_IDENTITY or '?'}] — {t('report of')} "
        f"{now.strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"_{t('Search identity')}: {_identity_display_name()}_",
        "",
        _segment_banner(segment, siblings, segment_total,
                        [v for v in items
                         if (v.get('computed') or {}).get('classification')
                         in LISTED_CLASSES]),
        f"{t('Run')} #{state.get('run_count', '?')}. "
        f"{t('Vacancies shown')}: {len(items)} "
        f"({t('collapsed')} {duplicate_count} {t('near-duplicates')}, "
        f"{t('removed')} {dead_link_count} "
        f"{t('with a confirmed dead link')} — `python tools/kb.py stats`). "
        f"{t('New on this run')}: {run_stats.get('new_vacancies', '?')}. "
        f"{t('Companies in the database')}: {len(companies)}.",
        "",
        f"## {t('How to read this report')}",
        "",
        f"{_scoring_philosophy()} "
        f"`hot_lead` — {t('look at these first')}. "
        f"{t('Full score breakdown for any vacancy')}: "
        "`python tools/kb.py show --id <id>`.",
        "",
        f"## 🔥 {t('Hot leads — look at these first')}",
        "",
        _section("hot_lead", hot),
        f"## 👀 {t('Worth a look')}",
        "",
        _section("worth_a_look", worth),
        f"## 🕰️ {t('Long shot (low priority, but not impossible)')}",
        "",
        _section("long_shot", long_shot),
        f"## 🌍 {t('National markets — strong vacancies tied to a country')}",
        "",
        t("These vacancies have no objection against them except one: the "
        "board named a country. Almost always that means remote within that "
        "country, and then it is a miss. But not always: some employers "
        "happily sign a B2B contract with a contractor abroad, and the text "
        "of the vacancy does not show it.") + " " +
        f"{t('Showing')} {len(national)} {t('best of')} "
        f"{class_counts.get('national_market', 0)}.",
        "",
        _section("national_market", national),
        f"## 🏢 {t('Work arrangement not confirmed — check by hand')}",
        "",
        t("Nobody ever called these remote — neither the employer nor the "
        "board. That is not the same as knowing they are onsite, so they are "
        "not thrown away, and their score is NOT reduced: a 70 here is the "
        "same 70 it would have been above. What is missing is the "
        "confirmation, not the quality.") + " " +
        t("The reason this class exists: LinkedIn's guest search ignores its "
        "own remote filter, measured 2026-08-11 — the same vacancy comes back "
        "under 'on-site', 'remote' and 'hybrid' alike. Where an employer does "
        "say 'hybrid' or 'on-site', the vacancy is rejected outright and is "
        "not here.") + " " +
        f"{t('Showing')} {len(unconfirmed)} {t('best of')} "
        f"{class_counts.get('remote_unconfirmed', 0)}.",
        "",
        _section("remote_unconfirmed", unconfirmed),
        f"## 🔎 {t('Needs a manual check by the agent or the owner')}",
        "",
        t("These are vacancies the automation is unsure about — most often ") +
        f"{_ambiguous_places_hint(criteria)}, " +
        t("or it is unclear whether the company will hire someone from your "
        "country. Worth re-checking with a web search and, if needed, "
        "updating the record through `tools/kb.py`."),
        "",
        _section("needs_manual_review", review_items),
        *_salary_benchmark_block(segment),
        f"## ⭐ {t('Company reputation checks')}",
        "",
        # The shortlist THIS file shows, not the whole base: a person
        # reading the UK list is not helped by a to-do list of Singapore
        # companies, and before the split this block quietly named them.
        _reputation_coverage_block(
            {v.get('id') or i: v for i, v in enumerate(items)}, companies),
        "",
        f"## 📊 {t('Class statistics')}",
        "",
        "\n".join(f"- {cls}: {n}" for cls, n in sorted(class_counts.items(), key=lambda kv: -kv[1])) or f"_{t('no data')}_",
        "",
        f"## 📡 {t('Source health')}",
        "",
        "\n".join(source_lines) or f"_{t('no data')}_",
        "",
        f"## 📈 {t('Source usefulness')}",
        "",
        t("Volume and usefulness are different things. A source bringing "
        "thousands of records and zero candidates costs only run time."),
        "",
        _source_usefulness(vacancies),
        "",
        f"## 🔗 {t('Link check')}",
        "",
        _format_link_check_stats(state.get("last_link_check")),
        "",
        f"## {t('What next')}",
        "",
        f"- {t('Accumulated market findings')}: `{_rel(common.INSIGHTS_PATH)}`",
        f"- {t('Full vacancy database')}: `{_rel(common.VACANCIES_PATH)}` "
        f"(or `python tools/kb.py list --identity {common.ACTIVE_IDENTITY}`)",
        f"- {t('Archive of past reports')}: `{_rel(common.REPORTS_ARCHIVE_DIR)}`",
        f"- {t('Mark status after applying')}: `python tools/kb.py set-status "
        f"--identity {common.ACTIVE_IDENTITY} --id <id> --status applied --notes \"...\"`",
        "",
    ]
    return "\n".join(parts)


def write_segmented_reports(vacancies: dict, companies: dict, state: dict,
                            criteria: Optional[dict] = None,
                            run_date: Optional[str] = None) -> dict:
    """Every shortlist this identity is configured to produce.

    Returns {slug: path}, in configured order. An identity that has said
    nothing about markets gets exactly one file, at the historical path — the
    split is opt-in and costs nothing to ignore.

    A broken `reports` document must not cost somebody their whole run: the
    report is the last step of a cycle that has already done all the work, so a
    configuration mistake falls back to the single undivided shortlist and says
    so loudly.
    """
    import segments as segments_mod

    try:
        configured = segments_mod.load_segments()
    except Exception as exc:  # noqa: BLE001 — see the docstring
        common.eprint(f"[report] cannot read the report segmentation ({exc}); "
                      "writing the single undivided shortlist instead")
        configured = []
    if not configured:
        return {"": write_report(
            build_report_markdown(vacancies, companies, state, criteria),
            run_date)}

    written = {}
    for segment in configured:
        markdown = build_report_markdown(
            vacancies, companies, state, criteria,
            segment=segment, siblings=configured)
        written[segment.slug] = write_report(markdown, run_date, slug=segment.slug)
        if segment.default and segment.slug:
            # The same text at the historical path as well. Written rather than
            # linked: a symlink would not survive being copied out of the
            # repository, and this file gets forwarded.
            written[""] = write_report(markdown, run_date)
    return written


def write_report(markdown_text: str, run_date: Optional[str] = None,
                 slug: str = "") -> Path:
    """Writes the latest report and files a dated copy in the archive.

    The layout (at the owner's direct request; an improvement for everyone):
        reports/<prefix>_latest.md          — the latest shortlist of each identity
        reports/archive/<prefix>/<date>.md  — history, split per identity

    Two separate decisions, each with its own reason:
      * `reports/` sits at the repository ROOT rather than inside
        `data/<prefix>/`. The report is the one file a person opens by hand,
        and hunting for it in a tree of accumulated data is a nuisance.
      * latest is kept apart from the dated copies. Otherwise, after a couple
        of months, the folder becomes a hundred files to search by eye for the
        newest.
    """
    common.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    common.REPORTS_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    run_date = run_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prefix = common.FILE_PREFIX or ""

    latest_path = common.REPORTS_DIR / segment_filename(slug, prefix)
    # No prefix is needed in the archive: the folder already belongs to the
    # identity. The slug is, so that a day's several shortlists do not
    # overwrite one another.
    archived_path = common.REPORTS_ARCHIVE_DIR / (
        f"{run_date}_{slug}.md" if slug else f"{run_date}.md")

    latest_path.write_text(markdown_text, encoding="utf-8")
    archived_path.write_text(markdown_text, encoding="utf-8")
    return latest_path


def main() -> None:
    import identity as identity_mod

    parser = argparse.ArgumentParser(
        description="Rebuild the report from the current knowledge base")
    identity_mod.add_identity_arg(parser)
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)

    vacancies = kb.load_vacancies()
    companies = kb.load_companies()
    state = common.load_json(common.STATE_PATH, default={})
    written = write_segmented_reports(vacancies, companies, state)
    for slug, path in written.items():
        print(f"Report saved: {path}" + (f"  [{slug}]" if slug else ""))


if __name__ == "__main__":
    main()
