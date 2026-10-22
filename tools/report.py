"""
The shortlist as the desktop app shows it: one vacancy row as data
(vacancy_view), the market a vacancy is listed under, and the order inside a
class. tools/selections.py records it; the app reads it from the database.

Until 2026-10-20 this module also wrote a Markdown report per market into
reports/. The owner reads and answers the shortlist only in the app, so the
files went (tasks/3-done/0052-no-markdown-reports.md).

  python tools/report.py --identity <p>     record a selection without fetching
"""
from __future__ import annotations

import argparse
import re
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

# The same as the app's "Show 10 more" step (app/renderer/app.js, PAGE): the
# owner asked on 2026-10-05 for the first page to match the step.
TOP_N_PER_SECTION = 10

# The classes a person actually reads. Everything else is in the database for
# the record, not in the shortlist for a decision.
LISTED_CLASSES = ("hot_lead", "worth_a_look", "long_shot", "ai_unscreened",
                  "remote_unconfirmed", "engagement_unconfirmed")


def _fmt_amount(value: float) -> str:
    if value == int(value):
        return f"${int(value):,}"
    return f"${value:,.2f}"


def _fmt_salary_info(vacancy: dict, comp_bd: dict) -> str:
    """Always returns a pay line that names its source. Confirmed explicitly by
    the owner (2026-07-30): whether the salary is stated in the vacancy itself,
    was found by the agent on an external site (Glassdoor and the like), or is
    absent altogether has to be visible on the vacancy rather than only
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
    if rep_bd.get("off"):
        return ""
    if rep_bd.get("verdict") == "insufficient_sources":
        when = (rep_bd.get("checked_at") or "")[:10]
        where = rep_bd.get("searched") or "Glassdoor, Indeed, Trustpilot, web search"
        return (f"{t('checked')}{' ' + when if when else ''}, "
                f"{t('not determined — not enough sources')} "
                f"_({t('searched')}: {where}; "
                f"{t('usually the case for small, little-known companies')})_")

    if not rep_bd.get("has_data"):
        # Looked up on request since 2026-10-17 (the owner: not worth the
        # time of every collection), by the vacancy's button in the app.
        return (t("not collected") + " _("
                + t("the vacancy's “Collect reputation” button in the app")
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
    Seeing an unfamiliar technology on the card is no less useful than a
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
    for canonical, forms in _normalized_tech_vocabulary():
        if any(form in haystack for form in forms):
            found.append(canonical)
        if len(found) >= limit:
            break
    return found


_NORMALIZED_VOCABULARY_CACHE = []


def _normalized_tech_vocabulary() -> list:
    """[(canonical, [normalised forms])], normalised once. Normalising every
    form again for every vacancy made rendering the whole base take minutes."""
    if not _NORMALIZED_VOCABULARY_CACHE:
        for canonical, forms in _tech_vocabulary().items():
            _NORMALIZED_VOCABULARY_CACHE.append(
                (canonical, [common.normalize_for_matching(f) for f in (forms or [])]))
    return _NORMALIZED_VOCABULARY_CACHE


# How the country was learned. Constants rather than inline strings: these are
# COMPARED, and translating a compared value is a classic way to break logic
# silently.
HIRING_OFFICE = "hiring office"
COMPANY_HOME = "company home country"

def hiring_country(vacancy: dict):
    """(country, how it was learned) — or (None, None).

    What is wanted is the HIRING COUNTRY, not where the company was founded.
    For an international company those differ: Google's Swiss office hires in
    Switzerland, and Switzerland is what matters to a person — that is where
    the contract is signed, where the money comes from, which time zone
    applies. Hence this order of sources:

      1. the board tag `market:<country>` — the country the fetcher queried,
         that is, the office that posted the vacancy. A fact, not a guess;
      2. the location field: a country, a state or province, a city
         (places.country_in — "Barendrecht, South Holland, Netherlands",
         "Remote, Israel", "Seattle, WA", "Berlin");
      3. a "Headquarters:" heading in the description — that is the head
         office rather than the hiring one, so it comes last and is labelled
         explicitly.

    The countries are every country (config/derivation/countries.yaml), not
    only the markets of market_tiers.yaml as until 2026-10-06: "Bucharest,
    Romania" named no country the code knew, and was listed as worldwide.
    """
    import places

    for tag in vacancy.get("tags") or []:
        tag = str(tag)
        if tag.startswith("market:"):
            return places.canonical(tag[7:]) or tag[7:], HIRING_OFFICE

    country = places.country_in(vacancy.get("location_raw"))
    if country:
        return country, HIRING_OFFICE

    header = (vacancy.get("computed", {}).get("score_breakdown", {})
              .get("remote_location_fit", {}).get("header_scope", {}))
    for line in header.get("header_lines") or []:
        if line.startswith("headquarters:"):
            country = places.country_in(line[len("headquarters:"):])
            if country:
                return country, COMPANY_HOME

    return None, None


def market_group(vacancy: dict) -> str:
    """The market group a vacancy is listed under (segments.vacancy_group)."""
    import segments as segments_mod

    return segments_mod.vacancy_group(vacancy, lambda v: hiring_country(v)[0])


def _eligibility_rank(v: dict) -> int:
    """Position in score.ELIGIBILITY_ORDER; anything unrecognised sorts last."""
    import score as score_mod

    verdict = (v.get("computed") or {}).get("residency_eligibility")
    try:
        return score_mod.ELIGIBILITY_ORDER.index(verdict)
    except ValueError:
        return len(score_mod.ELIGIBILITY_ORDER)


def _eligibility_parts(v: dict) -> Optional[dict]:
    """Can a contractor sitting where this person sits actually take the work?

    Shown separately from the score and never folded into it. A vacancy that
    pays well and cannot be taken is worth less than one that pays adequately
    and can, and a single number cannot say that — see
    score._residency_eligibility.
    """
    c = v.get("computed") or {}
    verdict = c.get("residency_eligibility")
    if not verdict:
        return None
    label = {
        "confirmed": "✅ " + t("eligibility: confirmed"),
        "likely": "🟢 " + t("eligibility: likely"),
        "unknown": "❔ " + t("eligibility: not stated"),
        "no": "⛔ " + t("eligibility: no"),
    }.get(verdict, verdict)
    return {"level": verdict, "label": label,
            "reason": c.get("residency_eligibility_reason")}


def _apply_channel_items(v: dict) -> list:
    """Where to apply without going through the board.

    Only looked up for the top of the shortlist (tools/apply_channels.py), so
    most vacancies have nothing here — and that is different from "we looked
    and found nothing", which the owner asked to be told about explicitly.
    """
    items = []
    # The board's own "Apply" target, from the fetcher (devitjobs). Not a link
    # anybody checked: the board publishes it, and requesting it would count
    # as a paid click.
    if v.get("apply_url"):
        from urllib.parse import urlparse

        host = urlparse(v["apply_url"]).netloc.removeprefix("www.")
        items.append(f"📨 {t('the board sends applications to')} {host}: {v['apply_url']}")
    found = v.get("apply_channels")
    if not found:
        return items
    if found.get("direct_apply_url"):
        items.append(f"📨 {t('apply directly')}: {found['direct_apply_url']}")
    elif found.get("board_url"):
        items.append(
            f"📨 {t('the company hires through')} "
            f"{found.get('board_provider') or '?'}: {found['board_url']} "
            f"_({t('this vacancy is not on the board — possibly placed through an agency')})_")
    if found.get("emails"):
        items.append(f"✉️ {t('address given in the vacancy')}: "
                     + ", ".join(found["emails"]))
    if not items:
        items.append(f"📨 _{t('no direct way to apply found — only through the board')}_")
    return items


def _hiring_country_text(v: dict, bd: dict) -> str:
    country, country_source = hiring_country(v)
    if country:
        suffix = "" if country_source == HIRING_OFFICE else f" _({t(country_source)})_"
        return f"{country}{suffix}"
    # A missing country comes in two different kinds, worth keeping apart:
    # either the vacancy is deliberately geography-free, or the board did not
    # say.
    verdict = (bd.get("remote_location_fit", {})
               .get("structured_location", {}).get("verdict"))
    location = (v.get("location_raw") or "").strip()
    if verdict in ("worldwide", "worldwide_by_continents", "remote_without_country"):
        return t("without a country")
    return (t("not determined")
            + (f" _({t('the board said')}: «{location}»)_" if location else ""))


_ISO_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def calendar_date(value) -> Optional[str]:
    """YYYY-MM-DD from whatever a source put in posted_at, or None.

    Every board says it its own way — measured on the sharp base 2026-09-29:
    unix seconds (4dayweek), ISO with and without an offset or milliseconds
    (most), a bare date (LinkedIn, Reed), RFC 2822 (the RSS boards), nothing at
    all (Jobserve). The date is taken as the source wrote it: shifting it into
    another time zone would move "posted on the 29th" to the 28th for no gain.
    """
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = value / 1000 if value > 1e11 else value   # milliseconds, sometimes
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc).strftime("%Y-%m-%d")
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    match = _ISO_DATE.match(text)
    if match:
        return match.group(1)
    if text.isdigit():
        return calendar_date(int(text))
    try:
        from email.utils import parsedate_to_datetime

        return parsedate_to_datetime(text).strftime("%Y-%m-%d")
    except (TypeError, ValueError, IndexError):
        return None


def vacancy_view(v: dict) -> dict:
    """Everything one vacancy row shows, as data. The desktop app reads it
    from the selection rows in the database.

    Texts are already in the identity's language and may carry light Markdown
    (_italic_, **bold**, `code`), which the app renders.
    """
    c = v.get("computed", {})
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
    # Axes an identity declared for itself (score._score_extra_signals). The
    # label is the identity's own words, so it is shown as written.
    for signal in (bd.get("extra_signals") or {}).values():
        if signal.get("hits"):
            highlights.append(f"{signal.get('label')}: " + ", ".join(signal["hits"][:4]))
        if signal.get("negative_hits"):
            highlights.append(f"⚠ {signal.get('label')}: "
                              + ", ".join(signal["negative_hits"][:3]))
    for domain in (bd.get("domain_fit_signals") or {}).values():
        if domain.get("verdict") == "core_required":
            highlights.append(f"{domain.get('label')}: " + t("the core stack is required")
                              + f" ({', '.join(domain.get('core_required', [])[:3])})")
    engagement = bd.get("engagement_fit") or {}
    if engagement.get("verdict") == "confirmed":
        highlights.append("⏱ " + t("engagement confirmed") + f" ({engagement.get('reason')})")
    complexity = bd.get("role_complexity_signal", {})
    if complexity.get("gate_triggered"):
        highlights.append("⚠ " + t("looks like a complex/R&D role, not a simple one"))
    if c.get("needs_manual_review"):
        highlights.append("🔎 " + t("needs a manual check"))
    link_status = v.get("link_check", {}).get("status")
    if link_status == "unknown":
        highlights.append("🔗 " + t("the link could not be verified conclusively"))

    salary_line = _fmt_salary_info(v, bd.get("compensation_signal", {}))
    # The rate the graded pay component actually compared, when it ran. Shown
    # because "$150k-$350k" and "$90-150/hour" are not comparable at a glance,
    # and comparing them is the whole question for a search that ranks by pay.
    hourly = (bd.get("compensation_signal") or {}).get("hourly_equivalent_usd")
    if hourly:
        salary_line += f" — ≈ ${hourly:,.0f}/{t('hour')}"
    # What is still unknown, for a vacancy parked in a "check by hand" class.
    # A vacancy can be missing both confirmations, and the section it sits in
    # names only one of them.
    pending = []
    for objection in c.get("dealbreakers") or []:
        if objection.startswith("location: the employer never states"):
            pending.append(t("that it is remote"))
        elif objection.startswith("engagement: the employer never states"):
            pending.append(t("the hours (part-time, freelance)"))
    age_bd = bd.get("company_age_signal", {})
    company_age = None
    if age_bd.get("has_data"):
        emp = f", ~{age_bd['employees']} {t('employees')}" if age_bd.get("employees") else ""
        company_age = (f"{t('founded')} {age_bd['founded_year']} "
                       f"({age_bd['age_years']} {t('years old')}{emp}) _(Wikidata)_")

    return {
        "id": v.get("id"),
        "title": v.get("title", "?"),
        "company": v.get("company", "?"),
        "url": v.get("url", ""),
        "score": c.get("score", 0),
        "classification": c.get("classification"),
        "highlights": highlights,
        "salary": salary_line,
        "to_confirm": pending,
        # The vacancy's exclusivity clause, in its own words: a fact for the
        # person to weigh, not a refusal (the owner, 2026-10-05).
        "exclusivity": (bd.get("employment_exclusivity") or {}).get("hits") or [],
        # The employer's own site, when known — so the same vacancy can be
        # found on their careers page and applied to without an account on the
        # job board (WWR keeps the application funnel to itself, see
        # docs/SOURCES.md).
        "company_url": v.get("company_url"),
        "eligibility": _eligibility_parts(v),
        "apply_channels": _apply_channel_items(v),
        "technologies": expected_technologies(v),
        "reputation": _fmt_reputation(bd.get("company_reputation_signal", {}),
                                      c.get("classification", "")),
        # The app shows "Collect reputation" while this is false: found and
        # "too few sources" are both results (tools/reputation_lookup.py).
        # An identity with reputation off has nothing to collect.
        "reputation_collected": bool(
            (bd.get("company_reputation_signal") or {}).get("has_data")
            or (bd.get("company_reputation_signal") or {}).get("off")
            or (bd.get("company_reputation_signal") or {}).get("verdict") == "insufficient_sources"),
        "hiring_country": _hiring_country_text(v, bd),
        "company_age": company_age,
        "needs_manual_review": bool(c.get("needs_manual_review")),
        "first_seen": v.get("first_seen"),
        # Two different dates, both shown in the app: when the employer put
        # the vacancy up at the source, and when it first entered our base.
        "posted_on": calendar_date(v.get("posted_at")),
        "first_seen_on": calendar_date(v.get("first_seen")),
        # The board it came from: the app's "Source" filter reads it here.
        "source": v.get("source"),
        # Each part of the score with its range: the card's "Score" bars.
        # Empty for a vacancy last scored before 2026-10-17.
        "score_parts": c.get("score_parts") or [],
        # What the screening model said (tools/ai_screen.py): {verdict,
        # reason, quote, ...}, or null when it has not read this text.
        "ai_screen": bd.get("ai_screen") or None,
        # Off the stack or level and let through by the model's read against
        # the CV (score.py, criteria stretch_roles): {fit, work_kind, reason},
        # or null. The card's "a stretch for the CV" mark.
        "stretch": _stretch_mark(bd),
    }


def _stretch_mark(bd: dict):
    stretch = bd.get("stretch_roles") or {}
    if stretch.get("fit") not in ("fits", "stretch"):
        return None
    return {"fit": stretch["fit"], "work_kind": stretch.get("work_kind"),
            "reason": (bd.get("ai_screen") or {}).get("reason")}


def vacancy_views(v: dict) -> dict:
    """vacancy_view() in every language the app's interface offers, keyed by
    language: the app shows the lines in whichever the person picked, while
    vacancies.view keeps the identity's own for feedback."""
    views = {}
    for lang in i18n.LANGUAGES:
        with i18n.speaking(lang):
            views[lang] = vacancy_view(v)
    return views


def main() -> None:
    import identity as identity_mod

    parser = argparse.ArgumentParser(
        description="Record a selection from the current knowledge base, without fetching")
    identity_mod.add_identity_arg(parser)
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)

    vacancies = kb.load_vacancies()
    state = common.load_json(common.STATE_PATH, default={})
    import selections

    selection_id = selections.record(vacancies, state, kind="rebuild")
    print(f"Selection #{selection_id} recorded (what the desktop app lists).")


if __name__ == "__main__":
    main()
