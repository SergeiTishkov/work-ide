"""
Where a person can actually apply, without going through the board.

WHY
---
A vacancy in the report is a link to LinkedIn, and applying there means an
account, a queue and a form somebody may never read. Applying on the employer's
own system is a different thing: it is the channel they actually watch.

Asked for by the owner 2026-08-12, for the top of the shortlist only —
`hot_lead`, and anything scoring as high that is waiting in another class.
There is no point spending requests on the tail nobody will read.

WHAT IS COLLECTED, AND WHAT IS DELIBERATELY NOT
-----------------------------------------------
Collected — things the EMPLOYER published as a way to reach them:

  * the exact vacancy on the company's own applicant-tracking system, so the
    link opens the form rather than a board;
  * the company's board on that system, when the company is clearly there but
    this particular vacancy is not;
  * an address written in the vacancy text itself ("send your CV to
    careers@…"), which is the employer publishing their own contact.

Not collected: the personal contact details of named individuals. A recruiter's
private email or phone number is personal data about a third party who did not
publish it for this, and no amount of it being findable makes harvesting it
part of this project. Where a posting itself names a recruiter and links their
public profile, that link is a fact of the posting and is kept; nothing is
looked up about a person beyond it.

WHY A BOARD ANSWERING 200 IS NOT A BOARD
----------------------------------------
Every one of these systems answers HTTP 200 to an unknown company slug.
Measured 2026-08-12: a first version that trusted the status code "found" an
application channel for 18 companies out of 18 — including one whose slug was a
typo in the vacancy's own company name ("tatittechnolgies"), and Accenture on a
Recruitee board holding two jobs. Both were empty or unrelated responses.

So a hit has to be earned twice: the board must list actual openings, AND the
vacancy we hold must be among them by title. When the board exists but the
vacancy is not on it, that is reported as exactly that — a weaker fact, and an
honest one, because the vacancy may have been posted through an agency.

"Not found" is a result too, and it is recorded with a date so that the same
fruitless search is not repeated on every run — the same reasoning as
link_check's cache and company_intel's.
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

# Which vacancies are worth the requests. Not a taste judgement: these are the
# ones a person will actually open.
TARGET_CLASSES = ("hot_lead", "remote_unconfirmed")

DEFAULT_LIMIT = 60
RETRY_AFTER_DAYS = 21
PAUSE_SECONDS = 0.4

# The application systems this project already knows how to read (fetch_ats.py
# uses the same endpoints to collect vacancies). Each entry is:
#   api      — the machine-readable board
#   apply    — where a human applies, formatted with the slug
_PROVIDERS = {
    "greenhouse": {
        "api": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
        "apply": "https://boards.greenhouse.io/{slug}",
    },
    "lever": {
        "api": "https://api.lever.co/v0/postings/{slug}?mode=json",
        "apply": "https://jobs.lever.co/{slug}",
    },
    "ashby": {
        "api": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
        "apply": "https://jobs.ashbyhq.com/{slug}",
    },
    "recruitee": {
        "api": "https://{slug}.recruitee.com/api/offers/",
        "apply": "https://{slug}.recruitee.com/",
    },
    "workable": {
        "api": "https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true",
        "apply": "https://apply.workable.com/{slug}/",
    },
    "smartrecruiters": {
        "api": "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100",
        "apply": "https://careers.smartrecruiters.com/{slug}",
    },
}

# Suffixes that are part of a legal name and never part of a board slug.
_LEGAL_TAIL = re.compile(
    r"\b(inc|ltd|llc|l\.l\.c|gmbh|b\.?v|a\.?b|pte|plc|sa|srl|s\.?r\.?o|oy|as|"
    r"limited|corporation|corp|company|holdings?|group|international)\b\.?",
    re.IGNORECASE)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Addresses that are never a way to apply for a job.
_EMAIL_NOISE = re.compile(
    r"(noreply|no-reply|donotreply|privacy|legal|abuse|dpo|gdpr|support|"
    r"sales|marketing|info@example|@sentry\.|@example\.)", re.IGNORECASE)

_WORD_RE = re.compile(r"[a-z0-9]+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _checked_recently(record: dict, days: int = RETRY_AFTER_DAYS) -> bool:
    stamp = (record.get("apply_channels") or {}).get("checked_at")
    if not stamp:
        return False
    try:
        when = datetime.fromisoformat(stamp)
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - when).days < days


def slug_candidates(company: str) -> list:
    """Board slugs worth trying for a company name, most specific first.

    The bare first word is included because it is right often enough to matter
    ("Aubay Belgium" really does post at aubay.recruitee.com) — and it is also
    how a first version matched Accenture to a stranger's two-job board. That
    is what the title check downstream is for: a slug is a guess, and a guess
    has to be confirmed against the vacancy.
    """
    name = _LEGAL_TAIL.sub(" ", company or "")
    words = _WORD_RE.findall(name.lower())
    if not words:
        return []
    out = ["".join(words)]
    if len(words) > 1:
        out.append("-".join(words))
        out.append(words[0])
    seen, unique = set(), []
    for slug in out:
        if len(slug) >= 3 and slug not in seen:
            seen.add(slug)
            unique.append(slug)
    return unique


def _title_key(title: str) -> set:
    """Words of a job title that carry meaning, for comparing two spellings of
    the same role. "Senior .NET Developer" and ".Net Developer (Senior)" have
    to match; "Senior .NET Developer" and "Marketing Manager" must not."""
    stop = {"senior", "junior", "lead", "principal", "staff", "mid", "level",
            "the", "a", "an", "and", "or", "of", "for", "in", "at", "to",
            "remote", "hybrid", "onsite", "fulltime", "parttime", "contract",
            "m", "f", "d", "w", "x", "h"}
    return {w for w in _WORD_RE.findall((title or "").lower())
            if w not in stop and len(w) > 1}


def _openings(provider: str, payload) -> list:
    """The board's postings as (title, url) pairs. Empty means "no board here",
    whatever the status code said."""
    try:
        if provider == "greenhouse":
            return [(j.get("title"), j.get("absolute_url"))
                    for j in (payload or {}).get("jobs") or []]
        if provider == "lever":
            return [(j.get("text"), j.get("hostedUrl"))
                    for j in payload or []] if isinstance(payload, list) else []
        if provider == "ashby":
            return [(j.get("title"), j.get("jobUrl"))
                    for j in (payload or {}).get("jobs") or []]
        if provider == "recruitee":
            return [(j.get("title"), j.get("careers_url") or j.get("careers_apply_url"))
                    for j in (payload or {}).get("offers") or []]
        if provider == "workable":
            return [(j.get("title"), j.get("url") or j.get("application_url"))
                    for j in (payload or {}).get("jobs") or []]
        if provider == "smartrecruiters":
            return [(j.get("name"),
                     (j.get("ref") or "").replace("api.smartrecruiters.com/v1/companies",
                                                  "careers.smartrecruiters.com"))
                    for j in (payload or {}).get("content") or []]
    except Exception:  # noqa: BLE001 — somebody else's payload, never fatal
        return []
    return []


# Somebody signed up, posted the trial content and left. The slug is then a
# real 200 with real-looking JSON that belongs to nobody.
_DEMO_TITLE = re.compile(r"\((sample|example|demo)\)|\b(sample|demo) (job|posting|vacancy)\b",
                         re.IGNORECASE)

# Below this, a board is more likely an abandoned trial than a company's
# hiring page. Measured 2026-08-12: accenture.recruitee.com holds two
# postings, one of them Recruitee's own "Senior Marketer (Sample)"; the real
# boards found the same day hold 10, 12, 17 and 159.
MIN_OPENINGS_FOR_A_BOARD = 3


def _looks_like_a_real_board(openings: list) -> bool:
    """Only asked when the vacancy itself was NOT found on the board.

    A title match proves the board belongs to the employer, and needs no
    further test. Without one, all we have is a slug that guessed right — and
    a slug guesses right about squatters too.
    """
    if len(openings) < MIN_OPENINGS_FOR_A_BOARD:
        return False
    return not any(_DEMO_TITLE.search(title or "") for title, _ in openings)


# Words that identify nobody. Two companies sharing only these share nothing.
_GENERIC_NAME_WORDS = {
    "group", "consulting", "consultancy", "solutions", "technologies",
    "technology", "services", "systems", "software", "digital", "global",
    "international", "recruitment", "staffing", "partners", "labs", "tech",
    "the", "and", "of", "hr", "it",
}


def _name_tokens(name: str) -> set:
    stripped = _LEGAL_TAIL.sub(" ", name or "")
    return {w for w in _WORD_RE.findall(stripped.lower())
            if len(w) > 2 and w not in _GENERIC_NAME_WORDS}


def _board_name(provider: str, payload, slug: str, timeout: int) -> Optional[str]:
    """Whose board this actually is, where the system will say.

    Greenhouse needs one extra request; it is only ever made when a board is
    about to be offered on the strength of its slug alone, so at most a handful
    per run.
    """
    try:
        if provider == "greenhouse":
            meta = _fetch_json(
                f"https://boards-api.greenhouse.io/v1/boards/{slug}", timeout)
            return (meta or {}).get("name")
        if provider == "recruitee":
            offers = (payload or {}).get("offers") or []
            return offers[0].get("company_name") if offers else None
        if provider == "smartrecruiters":
            content = (payload or {}).get("content") or []
            return ((content[0].get("company") or {}).get("name")) if content else None
        if provider == "workable":
            return (payload or {}).get("name")
    except Exception:  # noqa: BLE001
        return None
    return None


def _board_belongs_to(company: str, board_name: Optional[str],
                      slug_is_the_full_name: bool) -> bool:
    """Does this board belong to the company in the vacancy?

    Measured 2026-08-12, and the reason this function exists: matching on the
    slug alone offered "ITS Group Benelux" a board belonging to Intelligent
    Technical Solutions, and "MCS (FE) PTE. LTD." one belonging to Minnesota
    Cannabis Services. Both came from taking the first word of a company name
    as a slug — "its", "mcs" — which is a guess dressed up as a finding.

    So: where the system says whose board it is, the names must actually share
    something. Where it does not say, only a slug spelling out the whole
    company name is enough.
    """
    if board_name:
        return bool(_name_tokens(company) & _name_tokens(board_name))
    return slug_is_the_full_name


def _fetch_json(url: str, timeout: int):
    import requests

    # The pause lives here rather than in the caller so that it costs nothing
    # when there is no request — which is the case in every test.
    time.sleep(PAUSE_SECONDS)
    try:
        resp = requests.get(url, headers={"User-Agent": common.USER_AGENT},
                            timeout=timeout)
        if resp.status_code != 200:
            return None
        return json.loads(resp.text)
    except Exception:  # noqa: BLE001
        return None


def emails_in(text: str) -> list:
    """Addresses the employer wrote into the vacancy itself.

    Filtered, because a description also carries tracking pixels and legal
    boilerplate, and "privacy@" is not a way to apply for a job.
    """
    found = []
    for address in _EMAIL_RE.findall(text or ""):
        if _EMAIL_NOISE.search(address):
            continue
        if address.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".svg")):
            continue
        if address not in found:
            found.append(address)
    return found[:3]


def find_channels(vacancy: dict, timeout: int = common.DEFAULT_TIMEOUT) -> dict:
    """Everything found for one vacancy. Never raises.

    The result always records what was looked for and when, so that "nothing
    found" is a fact with a date rather than a silence.
    """
    result = {
        "checked_at": _now(),
        "direct_apply_url": None,   # this exact vacancy, on the employer's system
        "board_url": None,          # the employer's board, without this vacancy
        "board_provider": None,
        "emails": emails_in(vacancy.get("description_text") or ""),
    }

    company = vacancy.get("company") or ""
    wanted = _title_key(vacancy.get("title"))
    candidates = slug_candidates(company)
    for index, slug in enumerate(candidates):
        # The last candidate is the bare first word — a much weaker guess than
        # a slug spelling out the whole name. Tracked so a board offered on the
        # strength of the slug alone can be held to a higher standard.
        full_name_slug = index < 2 or len(candidates) == 1
        for provider, urls in _PROVIDERS.items():
            payload = _fetch_json(urls["api"].format(slug=slug), timeout)
            openings = _openings(provider, payload)
            if not openings:
                continue
            # The board exists. Does it hold OUR vacancy? Two thirds of the
            # title's meaningful words is a deliberate compromise: boards
            # rephrase titles constantly, and demanding an exact match finds
            # almost nothing.
            for title, url in openings:
                shared = wanted & _title_key(title)
                if wanted and url and len(shared) >= max(2, (len(wanted) * 2) // 3):
                    result["direct_apply_url"] = url
                    result["board_provider"] = provider
                    return result
            if result["board_url"] or not _looks_like_a_real_board(openings):
                continue
            if not _board_belongs_to(
                    company, _board_name(provider, payload, slug, timeout),
                    full_name_slug):
                continue
            result["board_url"] = urls["apply"].format(slug=slug)
            result["board_provider"] = provider
    return result


def worklist(vacancies: dict, threshold: int, classes=TARGET_CLASSES,
             limit: Optional[int] = None) -> list:
    """The vacancies worth the requests: the shortlist proper, plus anything
    scoring as high that is waiting in another class for a human decision."""
    todo = []
    for key, record in vacancies.items():
        if record.get("duplicate_of"):
            continue
        if (record.get("link_check") or {}).get("status") == "dead":
            continue
        computed = record.get("computed") or {}
        if computed.get("classification") not in classes:
            continue
        if (computed.get("score") or 0) < threshold:
            continue
        if _checked_recently(record):
            continue
        todo.append((computed.get("score") or 0, key))
    todo.sort(reverse=True)
    keys = [key for _, key in todo]
    return keys[:limit] if limit else keys


def collect(vacancies: dict, threshold: int, classes=TARGET_CLASSES,
            limit: int = DEFAULT_LIMIT) -> dict:
    """Fills in `apply_channels` on the shortlist. Mutates in place.

    Never raises: an application channel is an improvement, and failing to find
    one must not stop a research cycle.
    """
    stats = {"considered": 0, "direct": 0, "board": 0, "email": 0, "nothing": 0}
    for key in worklist(vacancies, threshold, classes, limit):
        record = vacancies[key]
        stats["considered"] += 1
        try:
            found = find_channels(record)
        except Exception:  # noqa: BLE001 — one company must not stop the rest
            continue
        record["apply_channels"] = found
        if found["direct_apply_url"]:
            stats["direct"] += 1
        elif found["board_url"]:
            stats["board"] += 1
        elif found["emails"]:
            stats["email"] += 1
        else:
            stats["nothing"] += 1
    return stats


def summary(vacancies: dict, threshold: int, classes=TARGET_CLASSES) -> dict:
    """How much of the top of the shortlist has somewhere to apply."""
    counts = {"in_scope": 0, "direct": 0, "board": 0, "email_only": 0,
              "nothing": 0, "not_checked": 0}
    for record in vacancies.values():
        if record.get("duplicate_of"):
            continue
        if (record.get("link_check") or {}).get("status") == "dead":
            continue
        computed = record.get("computed") or {}
        if computed.get("classification") not in classes:
            continue
        if (computed.get("score") or 0) < threshold:
            continue
        counts["in_scope"] += 1
        found = record.get("apply_channels")
        if not found:
            counts["not_checked"] += 1
        elif found.get("direct_apply_url"):
            counts["direct"] += 1
        elif found.get("board_url"):
            counts["board"] += 1
        elif found.get("emails"):
            counts["email_only"] += 1
        else:
            counts["nothing"] += 1
    return counts


def main() -> None:
    import argparse

    import identity as identity_mod
    import kb
    import score as score_mod

    parser = argparse.ArgumentParser(
        description="Find where to apply directly, for the top of the shortlist")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--summary", action="store_true",
                        help="Only report coverage, look nothing up")
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)

    vacancies = kb.load_vacancies()
    threshold = score_mod.load_criteria()["classification_thresholds"]["hot_lead"]

    if args.summary:
        counts = summary(vacancies, threshold)
        print("In scope %(in_scope)d: direct link %(direct)d, company board "
              "%(board)d, email only %(email_only)d, nothing found "
              "%(nothing)d, not checked yet %(not_checked)d" % counts)
        return

    stats = collect(vacancies, threshold, limit=args.limit)
    kb.save_vacancies(vacancies)
    print("Checked %(considered)d: direct link %(direct)d, company board "
          "%(board)d, email only %(email)d, nothing found %(nothing)d" % stats)


if __name__ == "__main__":
    main()
