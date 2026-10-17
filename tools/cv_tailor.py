"""
A CV tailored to one vacancy, as .docx and .pdf.

    python tools/cv_tailor.py --identity sharp --vacancy 35bf096fae2ac0e4b101
    python tools/cv_tailor.py --identity sharp --vacancy ID --content edited.json
    python tools/cv_tailor.py --identity sharp --vacancy ID --json   # for the app
    python tools/cv_tailor.py --identity sharp --vacancy ID --instructions "Lead with Azure"

Three sources go to the model (`claude -p`, no tools, structured output):

  * the COMMON CV — the one the person sends by default (owner.primary_cv in
    the profile; its .docx twin from owner.cv_files is read);
  * the PARENT CV — every achievement of the person's working life, far
    longer than one CV (cv.parent in the profile; .md, .txt or .docx;
    optional, and can be added at any time). When it is there, it is where
    the facts come from, and the common CV is the example of the layout and
    of what to include first when the vacancy asks for nothing special;
  * the vacancy's text from the shared base;
  * the person's instructions for this one CV, when given (`--instructions`,
    typed in the app under "Generate CV"). The CV is in English unless they
    ask for another language.

The model returns the CV as JSON (CONTENT_SCHEMA) plus a report for the
person. Then, without the model:

  1. check_facts() compares every company, title, date range, number and
     technology with the two CVs and lists what it cannot find there. It
     does not block: the list goes to the person with the files.
  2. cv_docx renders the .docx in the common CV's layout; Word converts it to
     .pdf and counts the pages (cv_convert).
  3. fit_length() cuts the bullets the model marked least needed (priority 3,
     then 2; oldest jobs first) until the CV fits cv.target_pages (3); with
     only priority-1 bullets left it may stay at cv.max_pages (3 as well
     unless the profile raises it), and only past that do priority-1 bullets
     of the oldest jobs go. The owner, 2026-10-12: a CV is 2-3 pages.
  4. The files go into the vacancy's folder of documents (tools/documents.py:
     <folder>/<identity>/<vacancy id>/) under the common CV's own name. The
     current pair moves into "Old versions" as V<n> (or "V<n> failed", when
     the model reads the person's message as a rejection of it), and "CV
     log.md" gets the new version and its message. The model gets that log
     and the current version's text with every new version, so earlier
     corrections stay made. Nothing moves until everything succeeded.

Every run is kept in data/identities/<prefix>/cvs/<vacancy id>/<time>/: the
model's input, its answer, the fact check, the final content and both files.
`--content` renders a content file from such a folder (or an edited copy)
without calling the model.

What career-ops (github.com/santifer/career-ops) learned and this follows:
the model returns content only and never writes files; the vacancy is data,
not instructions; the fact gate runs in code, not only in the prompt; jobs
stay in reverse chronological order with titles and dates as in the source;
the page count comes from the rendered document.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import re
import sqlite3
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import cv_convert  # noqa: E402
import cv_docx  # noqa: E402
import documents  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = ROOT / "config" / "cv_tailor_prompt.md"

DEFAULTS = {
    "model": "opus",
    "target_pages": 3,
    # Was 4 until 2026-10-12, when the parent CV came in: it is longer than
    # any CV, and the owner wants the result at 2-3 pages.
    "max_pages": 3,
}
CLAUDE_TIMEOUT_SECONDS = 900
DESCRIPTION_LIMIT = 20000
MAX_FIT_ROUNDS = 8

# The printed page: A4 at the margins of cv_docx.LAYOUT, in points.
PAGE_HEIGHT_PT = cv_docx.LAYOUT["page_height_cm"] / 2.54 * 72
MARGIN_PT = cv_docx.LAYOUT["margin_cm"] / 2.54 * 72
BODY_HEIGHT_PT = PAGE_HEIGHT_PT - 2 * MARGIN_PT
# A bullet line at 11 pt Arial, single spacing, and how many characters fit
# in it on the A4 body width: measured on the owner's CV, 2026-10-06.
BULLET_LINE_PT = 12.65
BULLET_LINE_CHARS = 92


def _string(description: str = "") -> dict:
    return {"type": "string", "description": description} if description else {"type": "string"}


def _strings(description: str = "") -> dict:
    schema = {"type": "array", "items": {"type": "string"}}
    if description:
        schema["description"] = description
    return schema


# The model's verdict on the version before this one (tools/documents.py):
# rejected as a whole, or the base this one was edited from.
PREVIOUS_VERSION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["failed", "reason"],
    "properties": {
        "failed": {"type": "boolean",
                   "description": "the person's message rejects the previous version as a whole"},
        "reason": {"type": "string"},
    },
}

CONTENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name", "headline", "tagline", "contacts", "summary", "skills",
                 "experience", "sections", "previous_version", "report"],
    "properties": {
        "name": _string("exactly as in the common CV"),
        "headline": _string("the title line under the name"),
        "tagline": _string("the stack line under the headline"),
        "contacts": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["label", "value"],
                "properties": {"label": _string(), "value": _string()},
            },
        },
        "summary": _strings("1-2 paragraphs"),
        "skills": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["category", "items"],
                "properties": {"category": _string(), "items": _strings()},
            },
        },
        "experience": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["dates", "title", "company", "context", "bullets", "tech_stack"],
                "properties": {
                    "dates": _string("as in the CVs, e.g. 'July 2024 – November 2025'"),
                    "title": _string(),
                    "company": _string(),
                    "context": _string(),
                    "bullets": {
                        "type": "array",
                        "items": {
                            "type": "object", "additionalProperties": False,
                            "required": ["text", "priority", "source"],
                            "properties": {
                                "text": _string(),
                                "priority": {"type": "integer", "enum": [1, 2, 3]},
                                "source": {"type": "string", "enum": ["common", "parent"]},
                            },
                        },
                    },
                    "tech_stack": _strings(),
                },
            },
        },
        "sections": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["heading", "lines"],
                "properties": {"heading": _string(), "lines": _strings()},
            },
        },
        "previous_version": PREVIOUS_VERSION_SCHEMA,
        "report": {
            "type": "object", "additionalProperties": False,
            "required": ["jd_keywords", "covered", "gaps", "from_parent", "notes"],
            "properties": {
                "jd_keywords": _strings(), "covered": _strings(), "gaps": _strings(),
                "from_parent": _strings(), "notes": _strings(),
            },
        },
    },
}


class TailorError(RuntimeError):
    pass


# A vacancy with a dead link, or with less description than this, is taken
# for gone (an old one, most likely): nothing is generated, and the
# document's log says so (the owner, 2026-10-13).
MIN_DESCRIPTION = 100
GONE = "Vacancy not found, possibly outdated"


def gone_reason(vacancy: dict) -> Optional[str]:
    if (vacancy.get("link_check") or {}).get("status") == "dead":
        return "the link is dead"
    if len((vacancy.get("description_text") or "").strip()) < MIN_DESCRIPTION:
        return "it has no description"
    return None


def refuse_gone(vacancy: dict, document) -> None:
    """Raises TailorError, after writing it into the document's log, when
    the vacancy is gone."""
    reason = gone_reason(vacancy)
    if reason:
        text = f"{GONE}: {reason}."
        document.record_error(text)
        raise TailorError(text)


# --- inputs -----------------------------------------------------------------

def cv_settings(profile: dict, identity_dir: Path) -> dict:
    """Where the CVs are and the length limits, from the resolved profile.

    owner.primary_cv names the common CV; its file name (without the
    extension) is the name of the output files. The text is read from a .docx
    (or .md/.txt): the primary one when it is one, else the first .docx in
    owner.cv_files. cv.common overrides that choice, cv.parent names the
    parent CV. Paths are relative to the identity's folder."""
    owner = profile.get("owner") or {}
    cv = profile.get("cv") or {}
    primary = owner.get("primary_cv") or ""
    if not primary:
        raise TailorError("the profile names no owner.primary_cv: there is no common CV to start from")
    readable = (".docx", ".md", ".txt")
    common_path = cv.get("common")
    if not common_path:
        candidates = [primary] + list(owner.get("cv_files") or [])
        common_path = next((c for c in candidates if Path(c).suffix.lower() in readable), None)
    if not common_path:
        raise TailorError(
            f"no .docx of the common CV: owner.primary_cv is {primary}, and owner.cv_files has "
            "no .docx (the CV is read from a .docx; set cv.common to one)")
    parent = cv.get("parent")
    return {
        "output_stem": Path(primary).stem,
        "common": (identity_dir / common_path).resolve(),
        "parent": (identity_dir / parent).resolve() if parent else None,
        "model": cv.get("model") or DEFAULTS["model"],
        "target_pages": int(cv.get("target_pages") or DEFAULTS["target_pages"]),
        "max_pages": int(cv.get("max_pages") or DEFAULTS["max_pages"]),
    }


def load_vacancy(db_path: Path, vacancy_id: str) -> dict:
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = connection.execute("SELECT data FROM vacancies WHERE id = ?", (vacancy_id,)).fetchone()
    finally:
        connection.close()
    if not row:
        raise TailorError(f"no vacancy {vacancy_id} in {db_path}")
    return json.loads(row[0])


def history_parts(log_text: str, previous_text: Optional[str], version: int, what: str) -> List[str]:
    """The earlier versions for the message: the log of every version and
    the person's messages, and the current version's text — the base to edit,
    unless the new message rejects it as a whole."""
    if not previous_text and not log_text.strip():
        return [f"This is the first version of the {what} (V1): there is no earlier one.", ""]
    parts = [f"This is version V{version} of the {what}. The log of the earlier versions, "
             "oldest first, with the person's message for each:", "",
             "<log>", log_text.strip() or "(no log)", "</log>", ""]
    if previous_text:
        parts += [f"The current version (V{version - 1}) as the file is now, the person's own edits "
                  "included:", "", "<previous_version>", previous_text.strip(), "</previous_version>", ""]
    return parts


def build_message(common_text: str, parent_text: Optional[str], vacancy: dict,
                  instructions: Optional[str] = None, *, log_text: str = "",
                  previous_text: Optional[str] = None, version: int = 1) -> str:
    description = (vacancy.get("description_text") or "").strip()
    if len(description) > DESCRIPTION_LIMIT:
        description = description[:DESCRIPTION_LIMIT] + "\n[cut]"
    parts = [
        f"The common CV is {len(common_text)} characters long as plain text.",
        "",
        "<common_cv>", common_text.strip(), "</common_cv>",
        "",
    ]
    if parent_text:
        parts += ["<parent_cv>", parent_text.strip(), "</parent_cv>", "",
                  "Both CVs are given: the facts come from both; the common CV shows the layout "
                  "and what to include first when the vacancy asks for nothing special.", ""]
    else:
        parts += ["There is no parent CV this time: work from the common CV alone.", ""]
    parts += history_parts(log_text, previous_text, version, "CV")
    instructions = (instructions or "").strip()
    if instructions:
        parts += ["<person_instructions>", instructions, "</person_instructions>", ""]
    else:
        parts += ["The person gave no instructions this time: the CV is in English.", ""]
    parts += [
        "<vacancy>",
        f"Title: {vacancy.get('title', '')}",
        f"Company: {vacancy.get('company', '')}",
        f"Location: {vacancy.get('location_raw', '')}",
        "",
        description or "(the vacancy has no description text; tailor to the title)",
        "</vacancy>",
    ]
    return "\n".join(parts)


# --- the model --------------------------------------------------------------

def call_model(message: str, *, model: str, workdir: Path, claude: str = "claude",
               run=subprocess.run, prompt_path: Optional[Path] = None,
               schema: Optional[dict] = None) -> dict:
    """One `claude -p` call with no tools and a JSON schema; returns the
    structured output. Runs in `workdir` so no project CLAUDE.md is loaded
    into the context. The prompt and the schema are the CV's unless given
    (cover_letter.py passes its own)."""
    command = [
        claude, "-p",
        "--output-format", "json",
        "--tools", "",
        "--no-session-persistence",
        "--model", model,
        "--system-prompt-file", str(prompt_path or PROMPT_PATH),
        "--json-schema", json.dumps(schema or CONTENT_SCHEMA),
    ]
    try:
        completed = run(command, input=message, capture_output=True, text=True, encoding="utf-8",
                        cwd=str(workdir), timeout=CLAUDE_TIMEOUT_SECONDS)
    except FileNotFoundError:
        raise TailorError("the `claude` command was not found (Claude Code CLI)")
    except subprocess.TimeoutExpired:
        raise TailorError(f"claude did not answer in {CLAUDE_TIMEOUT_SECONDS} s")
    (workdir / "model_output.json").write_text(completed.stdout or "", encoding="utf-8")
    if completed.returncode != 0 and not completed.stdout:
        raise TailorError(f"claude exited with {completed.returncode}: {(completed.stderr or '').strip()[:500]}")
    try:
        answer = json.loads(completed.stdout)
    except json.JSONDecodeError:
        raise TailorError(f"claude's answer is not JSON: {(completed.stdout or '')[:300]}")
    if answer.get("is_error"):
        raise TailorError(f"claude: {answer.get('result') or answer.get('subtype')}")
    content = answer.get("structured_output")
    if not isinstance(content, dict):
        raise TailorError("claude returned no structured output")
    return content


def clean_text(value):
    """Every string of the content as plain text: the model wrote "&amp;"
    for "&" in a headline on the first real run (2026-10-06), and Markdown
    bold would print its asterisks."""
    if isinstance(value, str):
        text = html.unescape(value).replace("**", "").replace("​", "")
        return re.sub(r"[ 	]+", " ", text).strip()
    if isinstance(value, list):
        return [clean_text(v) for v in value]
    if isinstance(value, dict):
        return {k: clean_text(v) for k, v in value.items()}
    return value


HEADER_LINE_LIMIT = 45


def layout_warnings(content: dict) -> List[str]:
    """Lines the layout cannot hold well: the header column is half a page
    wide in 12 pt bold, about 45 characters."""
    warnings = []
    for key in ("headline", "tagline"):
        value = content.get(key) or ""
        if len(value) > HEADER_LINE_LIMIT:
            warnings.append(f"the {key} is {len(value)} characters and wraps in the header: \"{value}\"")
    return warnings


def validate_content(content: dict) -> List[str]:
    """Problems that make the content unrenderable: named, so a wrong key
    does not turn into an empty section (career-ops 9f6efb5)."""
    problems = []
    for key in ("name", "experience"):
        if not content.get(key):
            problems.append(f"'{key}' is missing or empty")
    for index, job in enumerate(content.get("experience") or []):
        for key in ("dates", "title", "company"):
            if not (job.get(key) or "").strip():
                problems.append(f"experience[{index}].{key} is missing or empty")
        for b_index, bullet in enumerate(job.get("bullets") or []):
            if not isinstance(bullet, (dict, str)) or not cv_docx.bullet_text(bullet).strip():
                problems.append(f"experience[{index}].bullets[{b_index}] has no text")
    for index, group in enumerate(content.get("skills") or []):
        if not isinstance(group.get("items"), list):
            problems.append(f"skills[{index}].items is not a list")
    return problems


# --- the fact check ---------------------------------------------------------

DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")
QUOTES = {ord("‘"): "'", ord("’"): "'", ord("“"): '"', ord("”"): '"'}


def normalize(text: str) -> str:
    """The one normalization both sides of every comparison go through."""
    text = unicodedata.normalize("NFKC", text or "").translate(DASHES).translate(QUOTES)
    text = text.replace(" ", " ").replace("​", "")
    text = re.sub(r"\s*-\s*", " - ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


NUMBER_RE = re.compile(r"(?<![\w.])[~<>]?\$?\d+(?:[.,]\d+)*\s?(?:%|[kKmMbB]\b|x\b|\+)?")


def _numbers(text: str) -> List[str]:
    found = []
    for match in NUMBER_RE.finditer(text or ""):
        token = re.sub(r"\s", "", match.group(0)).lower().lstrip("~<>")
        found.append(token)
    return found


def _contains_term(haystack: str, term: str) -> bool:
    needle = normalize(term)
    if not needle:
        return True
    pattern = r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])"
    return re.search(pattern, haystack) is not None


MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}


def _start_of(dates: str) -> Optional[tuple]:
    match = re.match(r"\s*([a-z]+)\.?\s+(\d{4})", normalize(dates))
    if match:
        month = next((n for name, n in MONTHS.items() if name.startswith(match.group(1)[:3])), None)
        if month:
            return int(match.group(2)), month
    match = re.match(r"\s*(\d{4})", normalize(dates))
    return (int(match.group(1)), 0) if match else None


def check_facts(content: dict, common_text: str, parent_text: Optional[str]) -> dict:
    """Every factual claim in the tailored CV, looked up in the two source CVs.

    Returns {"findings": [{"kind", "text", "where", "message"}], "not_checked": [...]}.
    Kinds: name, contact, company, title, dates, order, number, term,
    missing_job, missing_category. A finding is a thing to look at, not a
    proof of invention: "MS SQL" written as "SQL Server" is a finding too."""
    sources = normalize(common_text + "\n" + (parent_text or ""))
    common_norm = normalize(common_text)
    source_numbers = set(_numbers(common_text + "\n" + (parent_text or "")))
    findings = []
    not_checked = []

    def add(kind, text, where, message):
        findings.append({"kind": kind, "text": text, "where": where, "message": message})

    if normalize(content.get("name", "")) not in common_norm:
        add("name", content.get("name", ""), "header", "the name is not written this way in the common CV")
    for contact in content.get("contacts") or []:
        value = contact.get("value", "")
        if value and normalize(value) not in common_norm:
            add("contact", value, "header", "this contact is not in the common CV")

    starts = []
    for index, job in enumerate(content.get("experience") or []):
        where = f"{job.get('company', '')} ({job.get('dates', '')})"
        for key, kind in (("company", "company"), ("title", "title"), ("dates", "dates")):
            value = job.get(key) or ""
            if value and normalize(value) not in sources:
                add(kind, value, where, f"this {key} is not written this way in the CVs")
        start = _start_of(job.get("dates") or "")
        if start is None:
            not_checked.append(f"the order of '{job.get('dates')}': the start date is not readable")
        starts.append(start)
        texts = [job.get("context") or ""] + [cv_docx.bullet_text(b) for b in job.get("bullets") or []]
        for text in texts:
            for number in _numbers(text):
                if number not in source_numbers:
                    add("number", number, where, f"the number is not in the CVs: \"{text[:90]}\"")
    known = [s for s in starts if s is not None]
    if any(a < b for a, b in zip(known, known[1:])):
        add("order", "", "Work experience", "the jobs are not in reverse chronological order")

    for paragraph in content.get("summary") or []:
        for number in _numbers(paragraph):
            if number not in source_numbers:
                add("number", number, "Summary", f"the number is not in the CVs: \"{paragraph[:90]}\"")

    seen = set()
    for term in cv_docx.iter_terms(content):
        key = normalize(term)
        if key in seen:
            continue
        seen.add(key)
        if not _contains_term(sources, term):
            add("term", term, "Skills / Tech stack", "this technology is not named in the CVs")

    tailored_companies = {normalize(j.get("company", "")) for j in content.get("experience") or []}
    for company in _common_companies(common_text):
        if normalize(company) not in tailored_companies:
            add("missing_job", company, "Work experience", "a job of the common CV is left out")
    tailored_categories = {normalize(g.get("category", "")) for g in content.get("skills") or []}
    for category in _common_categories(common_text):
        if normalize(category) not in tailored_categories:
            add("missing_category", category, "Skills", "a skills category of the common CV is left out")
    return {"findings": findings, "not_checked": not_checked}


DATE_LINE_RE = re.compile(r"^\s*[A-Za-z]+\.?\s+\d{4}\s*[–—-]\s*(?:[A-Za-z]+\.?\s+\d{4}|present|now)\s*:?\s*$",
                          re.IGNORECASE)


def _common_companies(common_text: str) -> List[str]:
    """The companies of the common CV, read from the line after each date
    line ("Title, Company"). Best effort: a CV laid out differently yields
    none, and the check then has nothing to compare."""
    lines = [line.strip() for line in common_text.splitlines()]
    companies = []
    for index, line in enumerate(lines):
        if DATE_LINE_RE.match(line):
            following = next((l for l in lines[index + 1:] if l), "")
            if ", " in following:
                companies.append(following.split(", ", 1)[1])
    return companies


def _common_categories(common_text: str) -> List[str]:
    lines = [line.strip() for line in common_text.splitlines()]
    try:
        start = next(i for i, l in enumerate(lines) if l.lower() == "skills")
    except StopIteration:
        return []
    categories = []
    for line in lines[start + 1:]:
        if not line:
            continue
        match = re.match(r"^([A-Za-z][\w /&+.-]{1,30}):\s+\S", line)
        if not match:
            break
        categories.append(match.group(1))
    return categories


# --- length -----------------------------------------------------------------

def _bullet_height(text: str) -> float:
    return math.ceil(max(len(text), 1) / BULLET_LINE_CHARS) * BULLET_LINE_PT


def overflow_pt(pages: int, last_bottom_pt: Optional[float], limit: int) -> float:
    """How much text has to go for the CV to end on page `limit`."""
    if pages <= limit:
        return 0.0
    if last_bottom_pt is None:   # no Word: a third of a page per round
        return BODY_HEIGHT_PT / 3
    return (pages - limit - 1) * BODY_HEIGHT_PT + max(last_bottom_pt - MARGIN_PT, BULLET_LINE_PT)


def cut_bullets(content: dict, need_pt: float, max_priority: int) -> List[str]:
    """Removes bullets until about `need_pt` of height is freed: the highest
    priority number first, then the oldest job, then the last bullet of a job.
    Every job keeps at least one bullet. Returns the removed texts."""
    jobs = content.get("experience") or []
    candidates = []
    for job_index, job in enumerate(jobs):
        for bullet_index, bullet in enumerate(job.get("bullets") or []):
            priority = bullet.get("priority", 2) if isinstance(bullet, dict) else 2
            if priority >= max_priority:
                candidates.append((priority, job_index, bullet_index))
    candidates.sort(reverse=True)
    freed, removed = 0.0, []
    doomed = {}
    for priority, job_index, bullet_index in candidates:
        if freed >= need_pt:
            break
        bullets = jobs[job_index]["bullets"]
        if len(bullets) - len(doomed.get(job_index, ())) <= 1:
            continue
        doomed.setdefault(job_index, set()).add(bullet_index)
        text = cv_docx.bullet_text(bullets[bullet_index])
        freed += _bullet_height(text)
        removed.append(f"{jobs[job_index].get('company', '')}: {text}")
    for job_index, indexes in doomed.items():
        jobs[job_index]["bullets"] = [b for i, b in enumerate(jobs[job_index]["bullets"]) if i not in indexes]
    return removed


def fit_length(content: dict, render, *, target_pages: int, max_pages: int) -> dict:
    """Renders, measures, cuts, until the CV fits. `render(content)` writes
    the files and returns {"pages", "last_page_bottom_pt"}.

    Stage 1 cuts priority 3 and 2 bullets down to target_pages. With only
    priority-1 bullets left the CV may stay up to max_pages; past that,
    stage 2 cuts priority-1 bullets too."""
    removed: List[str] = []
    measure = render(content)
    for _ in range(MAX_FIT_ROUNDS):
        pages = measure["pages"]
        if pages <= target_pages:
            break
        need = overflow_pt(pages, measure.get("last_page_bottom_pt"), target_pages)
        cut = cut_bullets(content, need, max_priority=2)
        if not cut and pages > max_pages:
            need = overflow_pt(pages, measure.get("last_page_bottom_pt"), max_pages)
            cut = cut_bullets(content, need, max_priority=1)
        if not cut:
            break
        removed += cut
        measure = render(content)
    return {"pages": measure["pages"], "removed": removed}


# --- the run ----------------------------------------------------------------

def _stamp() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d_%H%M%S")


def say(text: str) -> None:
    """A progress line on stderr: the app shows it in the task's log; stdout
    stays for the result."""
    print(text, file=sys.stderr, flush=True)


def earlier_versions(document) -> dict:
    """The log and the current version's text of a documents.Document."""
    previous = document.previous_docx()
    return {"log_text": document.log_text(),
            "previous_text": cv_docx.read_cv_text(previous) if previous else None,
            "version": document.next_version()}


def publish_version(document, files: List[Path], content: dict, instructions: Optional[str]) -> dict:
    verdict = content.get("previous_version") or {}
    try:
        return document.publish(files, message=instructions,
                                previous_failed=bool(verdict.get("failed")),
                                failed_reason=(verdict.get("reason") or "").strip() or None)
    except documents.DocumentsError as exc:
        raise TailorError(str(exc))


def tailor(*, settings: dict, vacancy: dict, vacancy_id: str, archive_root: Path, out_dir: Path,
           content: Optional[dict] = None, model_call=call_model, converter=None,
           instructions: Optional[str] = None) -> dict:
    """The whole run; returns the result the app shows. `out_dir` is the
    vacancy's folder of documents (documents.vacancy_dir): the new version
    goes there, the current one into "Old versions". `converter` is a
    cv_convert.WordSession-like object, or None to pick one here."""
    document = documents.Document(out_dir, "cv", settings["output_stem"])
    earlier = earlier_versions(document)
    say(f"CV V{earlier['version']}: {vacancy.get('title', vacancy_id)} — {vacancy.get('company', '')}")
    if instructions and instructions.strip():
        say(f"message: {instructions.strip()}")
    common_text = cv_docx.read_cv_text(settings["common"])
    parent_text = None
    warnings = []
    if settings.get("parent"):
        if Path(settings["parent"]).exists():
            parent_text = cv_docx.read_cv_text(settings["parent"])
        else:
            warnings.append(f"the parent CV {settings['parent']} does not exist; the common CV alone was used")
    else:
        warnings.append("no parent CV is set (cv.parent in the profile); the common CV alone was used. "
                        "A parent CV with every achievement can be added at any time and gives the "
                        "tailoring more to choose from")

    workdir = archive_root / vacancy_id / _stamp()
    workdir.mkdir(parents=True, exist_ok=True)
    if content is None:
        message = build_message(common_text, parent_text, vacancy, instructions, **earlier)
        (workdir / "model_input.md").write_text(message, encoding="utf-8")
        say(f"asking the model ({settings['model']}), a minute or three")
        content = model_call(message, model=settings["model"], workdir=workdir)
        say("the model answered: checking the facts, rendering")
    (workdir / "content_from_model.json").write_text(json.dumps(content, ensure_ascii=False, indent=2),
                                                     encoding="utf-8")
    content = clean_text(content)
    problems = validate_content(content)
    if problems:
        raise TailorError("the CV content is not usable: " + "; ".join(problems))
    warnings += layout_warnings(content)

    facts = check_facts(content, common_text, parent_text)
    stem = settings["output_stem"]
    docx_path = workdir / f"{stem}.docx"
    pdf_path = workdir / f"{stem}.pdf"
    author = content.get("name", "")

    def finish(session) -> dict:
        def render(current: dict) -> dict:
            cv_docx.render(current, docx_path, author=author)
            if session is None:
                return {"pages": 0, "last_page_bottom_pt": None}
            if session == "libreoffice":
                return cv_convert.libreoffice_convert(docx_path, pdf_path)
            return session.convert(docx_path, pdf_path)

        if session is None:
            render(content)
            return {"pages": None, "removed": []}
        return fit_length(content, render, target_pages=settings["target_pages"],
                          max_pages=settings["max_pages"])

    if converter is not None:
        fitted = finish(converter)
    elif cv_convert.word_available():
        say("Word: the PDF and the page count")
        with cv_convert.WordSession() as session:
            fitted = finish(session)
    elif cv_convert.soffice_path():
        fitted = finish("libreoffice")
    else:
        warnings.append("neither Microsoft Word nor LibreOffice is installed: no PDF, and the page count "
                        "was not measured")
        fitted = finish(None)

    pages = fitted["pages"]
    if pages and pages > settings["max_pages"]:
        warnings.append(f"{pages} pages, more than cv.max_pages ({settings['max_pages']})")
    elif pages and pages > settings["target_pages"]:
        warnings.append(f"{pages} pages: the bullets the vacancy needs did not fit in "
                        f"{settings['target_pages']}")

    files = [docx_path] + ([pdf_path] if pdf_path.exists() else [])
    version = publish_version(document, files, content, instructions)
    published = version["files"]
    verdict = content.get("previous_version") or {}
    if version.get("previous_failed"):
        say(f"V{version['version'] - 1} marked failed: {verdict.get('reason') or ''}")
    say(f"V{version['version']}: {pages or '?'} pages, in {out_dir}")
    result = {
        "ok": True,
        "vacancy": vacancy_id,
        "version": version["version"],
        "dir": str(out_dir),
        "docx": str(next((p for p in published if p.suffix == ".docx"), "")),
        "pdf": str(next((p for p in published if p.suffix == ".pdf"), "")),
        "pages": pages,
        "removed_for_length": fitted["removed"],
        "findings": facts["findings"],
        "not_checked": facts["not_checked"],
        "warnings": warnings,
        "report": content.get("report") or {},
        "archive": str(workdir),
    }
    (workdir / "content.json").write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    (workdir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Tailor the CV to one vacancy: .docx and .pdf")
    parser.add_argument("--identity", default=None, help="Search identity prefix")
    parser.add_argument("--vacancy", required=True, help="The vacancy id (vacancies.id)")
    parser.add_argument("--documents-dir", default=None,
                        help="The folder of generated documents (default: tools/documents.py where)")
    parser.add_argument("--content", default=None,
                        help="Render this content JSON instead of asking the model")
    parser.add_argument("--model", default=None, help="Override cv.model (a claude --model value)")
    parser.add_argument("--json", action="store_true", help="Print the result as one JSON line")
    parser.add_argument("--instructions", default=None,
                        help="The person's instructions for this CV (what to stress, the language...)")
    args = parser.parse_args(argv)

    import identity as identity_mod
    prefix = identity_mod.activate_or_exit(args.identity, quiet=args.json)
    try:
        settings = cv_settings(common.load_profile(prefix), identity_mod.identity_dir(prefix))
        if args.model:
            settings["model"] = args.model
        content = json.loads(Path(args.content).read_text(encoding="utf-8")) if args.content else None
        vacancy = load_vacancy(common.DB_PATH, args.vacancy)
        out_dir = documents.vacancy_dir(prefix, args.vacancy,
                                        Path(args.documents_dir) if args.documents_dir else None)
        refuse_gone(vacancy, documents.Document(out_dir, "cv", settings["output_stem"]))
        result = tailor(
            settings=settings,
            vacancy=vacancy,
            vacancy_id=args.vacancy,
            archive_root=common.DATA_DIR / "cvs",
            out_dir=out_dir,
            content=content,
            instructions=args.instructions,
        )
    except (TailorError, documents.DocumentsError, cv_convert.ConversionError, OSError, ValueError) as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        else:
            common.eprint(f"cv_tailor: {exc}")
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"{result['docx']}\n{result['pdf'] or '(no PDF)'}\npages: {result['pages']}")
        for finding in result["findings"]:
            print(f"  check: [{finding['kind']}] {finding['where']}: {finding['text']} - {finding['message']}")
        for warning in result["warnings"]:
            print(f"  note: {warning}")
        print(f"  kept in {result['archive']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
