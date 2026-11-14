"""
A CV tailored to one vacancy, as .docx and .pdf.

    python tools/cv_tailor.py --identity sharp --vacancy 35bf096fae2ac0e4b101
    python tools/cv_tailor.py --identity sharp --vacancy ID --content edited.json
    python tools/cv_tailor.py --identity sharp --vacancy ID --json   # for the app
    python tools/cv_tailor.py --identity sharp --vacancy ID --instructions "Lead with Azure"

What goes to the model (`claude -p`, no tools, structured output):

  * the PARENT CV (cv.parent in the profile; .docx, .md or .txt): every
    achievement of the person's working life, longer than any one CV. It is
    the one source: the facts, the header, the contacts, the skill
    categories and the projects come from it. The owner, 2026-11-14: the
    common CV that was the example of the layout before is gone, and every
    tailored CV is cut from the parent CV to fit the vacancy;
  * the person's languages from the profile (owner.languages), for the
    languages a vacancy asks for;
  * the vacancy's text from the shared base;
  * the person's instructions for this one CV, when given (`--instructions`,
    typed in the app under "Generate CV"). The CV is in English unless they
    ask for another language.

The model returns the CV as JSON (CONTENT_SCHEMA) plus a report for the
person. Then, without the model:

  1. check_facts() compares every company, title, date range, number,
     project, location and technology with the parent CV and the person's
     messages (this one and the log's) and lists what it cannot find there.
     It does not block: the list goes to the person with the files. The
     person's word outranks the CV (the owner, 2026-10-22): what they state
     in a message is a source.
  2. cv_docx renders the .docx in the parent CV's layout; Word converts it
     to .pdf and counts the pages (cv_convert).
  3. fit_length() cuts the bullets the model marked least needed (priority
     3, then 2; the section printed second first, then its oldest job or
     last project) until the CV fits cv.target_pages (2); with only
     priority-1 bullets left it may stay at cv.max_pages (3), and only past
     that do priority-1 bullets and then whole projects go. The owner,
     2026-11-14: a CV is 2 pages, a third only when what the vacancy needs
     does not fit in two.
  4. The files go into the vacancy's folder of documents (tools/documents.py:
     <folder>/<identity>/<vacancy id>/) named after the CV's headline: "CV
     Ivan Petrov Senior Full Stack Engineer" (headline_stem, task 0116), or
     cv.output_name for every version when the person set it.
     The current pair moves into "Old versions" as V<n> (or "V<n> failed",
     when the model reads the person's message as a rejection of it), and "CV
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
import ai_limit  # noqa: E402
import common  # noqa: E402
import cv_convert  # noqa: E402
import cv_docx  # noqa: E402
import documents  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = ROOT / "config" / "cv_tailor_prompt.md"

DEFAULTS = {
    "model": "opus",
    # The owner, 2026-11-14: two pages, a third only when what the vacancy
    # needs does not fit in two (3 and 3 from 2026-10-12, 4 before that).
    "target_pages": 2,
    "max_pages": 3,
}
CLAUDE_TIMEOUT_SECONDS = 900
DESCRIPTION_LIMIT = 20000
MAX_FIT_ROUNDS = 10

# The printed page: A4 at the margins of cv_docx.LAYOUT, in points.
PAGE_HEIGHT_PT = cv_docx.LAYOUT["page_height_cm"] / 2.54 * 72
MARGIN_PT = cv_docx.LAYOUT["margin_cm"] / 2.54 * 72
BODY_HEIGHT_PT = PAGE_HEIGHT_PT - 2 * MARGIN_PT
# A bullet line at 10 pt Arial, single spacing, and how many characters fit
# in it on the A4 body width beside the bullet indent: scaled from the
# 11 pt measure on the owner's CV (2026-10-06: 12.65 pt, 92 characters).
BULLET_LINE_PT = 11.5
BULLET_LINE_CHARS = 100
BULLET_SPACE_PT = cv_docx.LAYOUT["bullet_space_pt"]
# Two pages of the layout hold about this much plain text (the owner's parent
# CV: about 16,500 characters on 5 pages, 2026-11-14). Told to the model as
# the budget; the page count after rendering is what decides.
CHARS_PER_PAGE = 3300


def _string(description: str = "") -> dict:
    return {"type": "string", "description": description} if description else {"type": "string"}


def _strings(description: str = "") -> dict:
    schema = {"type": "array", "items": {"type": "string"}}
    if description:
        schema["description"] = description
    return schema


def _object(properties: dict) -> dict:
    return {"type": "object", "additionalProperties": False,
            "required": list(properties), "properties": properties}


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

BULLETS_SCHEMA = {
    "type": "array",
    "items": _object({"text": _string(),
                      "priority": {"type": "integer", "enum": [1, 2, 3]}}),
}

CONTACTS_SCHEMA = {"type": "array", "items": _object({"label": _string(), "value": _string()})}

CONTENT_SCHEMA = _object({
    "name": _string("exactly as in the CV"),
    "headline": _string("the title line under the name"),
    "tagline": _string("the stack line under the headline"),
    "location": _string("the CV's location line, with only the additions the rules allow"),
    "contacts": CONTACTS_SCHEMA,
    "summary": _strings("1-3 paragraphs"),
    "skills": {"type": "array", "items": _object({"category": _string(), "items": _strings()})},
    "projects": _object({
        "placement": {"type": "string", "enum": ["before_experience", "after_experience"]},
        "form": {"type": "string", "enum": ["full", "compact", "none"]},
        "items": {"type": "array", "description": "the projects when form is full, else empty",
                  "items": _object({
                      "title": _string("exactly as in the CV"),
                      "link": _string("exactly as in the CV, or empty"),
                      "intro": _string(),
                      "bullets": BULLETS_SCHEMA,
                      "tech_stack": _strings(),
                      "extra_lines": {"type": "array",
                                      "items": _object({"label": _string(), "items": _strings()})},
                  })},
        "compact": _object({"bullets": BULLETS_SCHEMA, "tech_stack": _strings()}),
    }),
    "experience": {
        "type": "array",
        "items": _object({
            "dates": _string("as in the CV, e.g. 'July 2024 – November 2025'"),
            "title": _string(),
            "company": _string(),
            "context": _string("the project line, or the whole job as one paragraph"),
            "bullets": BULLETS_SCHEMA,
            "tech_stack": _strings(),
        }),
    },
    "sections": {"type": "array", "items": _object({"heading": _string(), "lines": _strings()})},
    "previous_version": PREVIOUS_VERSION_SCHEMA,
    "report": _object({
        "vacancy_type": {"type": "string", "enum": ["ai", "engineering", "mixed"]},
        "jd_keywords": _strings(), "covered": _strings(), "gaps": _strings(),
        "stretched": _strings("each place worded toward the vacancy beyond the CV's own words"),
        "from_instructions": _strings(), "notes": _strings(),
    }),
})


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

READABLE = (".docx", ".md", ".txt", ".markdown")


def output_stem(parent: str) -> str:
    """The name of the output files from the parent CV's file name: "Parent
    CV Ivan Petrov" -> "CV Ivan Petrov". A tailored CV goes out as the
    person's CV, not as their parent CV."""
    stem = re.sub(r"^(parent|master)\s+", "", Path(parent).stem, flags=re.IGNORECASE).strip()
    return stem or "CV"


FILE_NAME_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
HEADLINE_IN_NAME_LIMIT = 60


def headline_stem(fixed_stem: str, name: str, headline: str, keep_fixed: bool = False) -> str:
    """The file name of one tailored version (task 0116): the fixed name up
    to the person's name, then the headline of the version. "CV Ivan Petrov
    Software Engineer", "IVAN PETROV", "Senior Full Stack Engineer" -> "CV
    Ivan Petrov Senior Full Stack Engineer". The fixed name as it is when
    `keep_fixed` (the person set cv.output_name), when there is no headline,
    or when the person's name is not in it."""
    title = re.sub(r"\s+", " ", FILE_NAME_BAD.sub(" ", headline or "")).strip(" .")
    if len(title) > HEADLINE_IN_NAME_LIMIT:
        title = title[:HEADLINE_IN_NAME_LIMIT].rsplit(" ", 1)[0].strip(" .")
    words = (name or "").split()
    if keep_fixed or not title or not words:
        return fixed_stem
    found = re.search(r"\s+".join(re.escape(w) for w in words), fixed_stem, flags=re.IGNORECASE)
    if not found:
        return fixed_stem
    return f"{fixed_stem[:found.end()].strip()} {title}"


def person_languages(profile: dict) -> List[str]:
    """owner.languages as written for a CV: "Russian (native)" from
    {name: Russian, level: native}, a plain name as it is."""
    out = []
    for entry in (profile.get("owner") or {}).get("languages") or []:
        if isinstance(entry, dict):
            name = (entry.get("name") or "").strip()
            level = str(entry.get("level") or "").strip()
            if name:
                out.append(f"{name} ({level})" if level else name)
        elif str(entry).strip():
            out.append(str(entry).strip())
    return out


def cv_settings(profile: dict, identity_dir: Path) -> dict:
    """Where the parent CV is, the output name and the length limits, from
    the resolved profile. cv.parent names the parent CV (relative to the
    identity's folder); cv.output_name overrides the output name."""
    cv = profile.get("cv") or {}
    parent = cv.get("parent") or ""
    if not parent:
        raise TailorError("the profile names no cv.parent: there is no CV to tailor from "
                          "(cv.parent: the person's CV with everything in it, .docx, .md or .txt)")
    if Path(parent).suffix.lower() not in READABLE:
        raise TailorError(f"cv.parent is {parent}: the CV is read from a .docx, .md or .txt")
    return {
        "output_stem": cv.get("output_name") or output_stem(parent),
        "output_fixed": bool(cv.get("output_name")),
        "parent": (identity_dir / parent).resolve(),
        "languages": person_languages(profile),
        "model": cv.get("model") or DEFAULTS["model"],
        "target_pages": int(cv.get("target_pages") or DEFAULTS["target_pages"]),
        "max_pages": int(cv.get("max_pages") or DEFAULTS["max_pages"]),
    }


def read_parent(settings: dict) -> str:
    path = Path(settings["parent"])
    if not path.exists():
        raise TailorError(f"the parent CV {path} does not exist (cv.parent in the profile)")
    return cv_docx.read_cv_text(path)


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
        if version > 1:
            return [f"This version (V{version}) of the {what} is made anew, from the inputs below "
                    "alone: no earlier version is given.", ""]
        return [f"This is the first version of the {what} (V1): there is no earlier one.", ""]
    parts = [f"This is version V{version} of the {what}. The log of the earlier versions, "
             "oldest first, with the person's message for each:", "",
             "<log>", log_text.strip() or "(no log)", "</log>", ""]
    if previous_text:
        parts += [f"The current version (V{version - 1}) as the file is now, the person's own edits "
                  "included:", "", "<previous_version>", previous_text.strip(), "</previous_version>", ""]
    return parts


def build_message(cv_text: str, vacancy: dict, instructions: Optional[str] = None, *,
                  languages: Optional[List[str]] = None, target_pages: int = DEFAULTS["target_pages"],
                  max_pages: int = DEFAULTS["max_pages"], log_text: str = "",
                  previous_text: Optional[str] = None, version: int = 1) -> str:
    description = (vacancy.get("description_text") or "").strip()
    if len(description) > DESCRIPTION_LIMIT:
        description = description[:DESCRIPTION_LIMIT] + "\n[cut]"
    budget = target_pages * CHARS_PER_PAGE
    parts = [
        f"The parent CV is {len(cv_text)} characters long as plain text. The tailored CV is "
        f"{target_pages} pages, {max_pages} at most; {target_pages} pages of the layout hold about "
        f"{budget:,} characters of plain text.",
        "",
        "<parent_cv>", cv_text.strip(), "</parent_cv>",
        "",
    ]
    if languages:
        parts += ["The person's languages, from their profile (a fact, not printed unless the rules "
                  "say so): " + ", ".join(languages) + ".", ""]
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
    ai_limit.check(completed)
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
LOCATION_LINE_LIMIT = 58


def layout_warnings(content: dict) -> List[str]:
    """Lines the layout cannot hold well: the header's left column is about
    half a page wide, 45 characters in 12 pt bold, 58 in the 10 pt location
    line."""
    warnings = []
    for key, limit in (("headline", HEADER_LINE_LIMIT), ("tagline", HEADER_LINE_LIMIT),
                       ("location", LOCATION_LINE_LIMIT)):
        value = content.get(key) or ""
        if len(value) > limit:
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
        if not (job.get("context") or "").strip() and not job.get("bullets"):
            problems.append(f"experience[{index}] has neither a context nor bullets")
    for index, group in enumerate(content.get("skills") or []):
        if not isinstance(group.get("items"), list):
            problems.append(f"skills[{index}].items is not a list")
    projects = cv_docx.projects_of(content)
    if projects["form"] == "full":
        for index, project in enumerate(projects["items"]):
            if not (project.get("title") or "").strip():
                problems.append(f"projects.items[{index}].title is missing or empty")
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


def person_text(instructions: Optional[str], log_text: str = "") -> str:
    """What the person wrote for this document: the new message and the log of
    the earlier ones. A source of facts for check_facts, above the CVs."""
    return "\n".join(t for t in ((instructions or "").strip(), (log_text or "").strip()) if t)


def check_facts(content: dict, cv_text: str, person: str = "", languages: Optional[List[str]] = None) -> dict:
    """Every factual claim in the tailored CV, looked up in the parent CV, in
    what the person wrote (`person`, see person_text) and in their languages
    from the profile. The person's word outranks the CV where it speaks; the
    rest is checked as without it. Wording is free (the owner, 2026-11-14:
    the CV is fitted to the vacancy as far as it is true); what is checked
    are the facts an employer can verify: names, employers, titles, dates,
    numbers, project titles and links, the location and the technologies
    listed as used.

    Returns {"findings": [{"kind", "text", "where", "message"}], "not_checked": [...]}.
    Kinds: name, contact, location, company, title, dates, order, number,
    project, link, term, missing_job. A finding is a thing to look at, not a
    proof of invention: "MS SQL" written as "SQL Server" is a finding too."""
    known = "\n".join(languages or [])
    raw = cv_text + "\n" + person + "\n" + known
    sources = normalize(raw)
    source_numbers = set(_numbers(raw))
    findings = []
    not_checked = []

    def add(kind, text, where, message):
        findings.append({"kind": kind, "text": text, "where": where, "message": message})

    def numbers_in(text, where):
        for number in _numbers(text):
            if number not in source_numbers:
                add("number", number, where, f"the number is not in the CV: \"{text[:90]}\"")

    if normalize(content.get("name", "")) not in sources:
        add("name", content.get("name", ""), "header", "the name is not written this way in the CV")
    for contact in content.get("contacts") or []:
        value = contact.get("value", "")
        if value and normalize(value) not in sources:
            add("contact", value, "header", "this contact is not in the CV")
    for part in LOCATION_SPLIT_RE.split(content.get("location") or ""):
        part = part.strip()
        if part and normalize(part) not in ALLOWED_LOCATION_PARTS and normalize(part) not in sources:
            add("location", part, "header", "this part of the location line is not in the CV or the profile")

    starts = []
    for job in content.get("experience") or []:
        where = f"{job.get('company', '')} ({job.get('dates', '')})"
        for key, kind in (("company", "company"), ("title", "title"), ("dates", "dates")):
            value = job.get(key) or ""
            if value and normalize(value) not in sources:
                add(kind, value, where, f"this {key} is not written this way in the CV")
        start = _start_of(job.get("dates") or "")
        if start is None:
            not_checked.append(f"the order of '{job.get('dates')}': the start date is not readable")
        starts.append(start)
        for text in [job.get("context") or ""] + [cv_docx.bullet_text(b) for b in job.get("bullets") or []]:
            numbers_in(text, where)
    known_starts = [s for s in starts if s is not None]
    if any(a < b for a, b in zip(known_starts, known_starts[1:])):
        add("order", "", "Work experience", "the jobs are not in reverse chronological order")

    for paragraph in content.get("summary") or []:
        numbers_in(paragraph, "Summary")

    projects = cv_docx.projects_of(content)
    if projects["form"] == "full":
        for project in projects["items"]:
            title = project.get("title") or ""
            if title and normalize(title) not in sources:
                add("project", title, "Independent projects", "no project of this title in the CV")
            link = project.get("link") or ""
            if link and normalize(link) not in sources:
                add("link", link, title, "this link is not in the CV")
            texts = [project.get("intro") or ""] + [cv_docx.bullet_text(b) for b in project.get("bullets") or []]
            for text in texts:
                numbers_in(text, title or "Independent projects")
    elif projects["form"] == "compact":
        for bullet in projects["compact"].get("bullets") or []:
            numbers_in(cv_docx.bullet_text(bullet), "Independent projects")

    seen = set()
    for term in cv_docx.iter_terms(content):
        key = normalize(term)
        if key in seen:
            continue
        seen.add(key)
        if not _contains_term(sources, term):
            add("term", term, "Technologies", "this technology is not named in the CV or the person's messages")

    tailored_companies = {normalize(j.get("company", "")) for j in content.get("experience") or []}
    for company in source_companies(cv_text):
        if normalize(company) not in tailored_companies:
            add("missing_job", company, "Work experience", "a job of the CV is left out")
    return {"findings": findings, "not_checked": not_checked}


# The location line's parts are joined by "·" or "|"; these may be added to
# what the CV says (task 0113, G1: a contract vacancy).
LOCATION_SPLIT_RE = re.compile(r"\s*[·|•]\s*")
ALLOWED_LOCATION_PARTS = {"b2b contractor", "b2b", "contractor"}

DATE_RANGE = r"[A-Za-z]+\.?\s+\d{4}\s*[–—-]\s*(?:[A-Za-z]+\.?\s+\d{4}|present|now)"
DATE_LINE_RE = re.compile(rf"^\s*{DATE_RANGE}\s*:?\s*$", re.IGNORECASE)
TITLE_COMPANY_RE = re.compile(r"^[^\t,]{2,60}, [^\t]{2,80}$")


def source_companies(cv_text: str) -> List[str]:
    """The companies of the CV, read from each job's "Title, Company" line:
    the line before or after a date line ("November 2025 – Present"), or the
    part before a tab when the dates share the line (as cv_docx writes it).
    Best effort: a CV laid out otherwise yields none, and the check then has
    nothing to compare."""
    lines = [line.strip() for line in cv_text.splitlines()]
    companies = []
    for index, line in enumerate(lines):
        head, _, tail = line.rpartition("\t")
        if head and DATE_LINE_RE.match(tail):
            candidates = [head.strip()]
        elif DATE_LINE_RE.match(line):
            before = next((l for l in reversed(lines[:index]) if l), "")
            after = next((l for l in lines[index + 1:] if l), "")
            candidates = [before, after]
        else:
            continue
        for candidate in candidates:
            if TITLE_COMPANY_RE.match(candidate) and not candidate.endswith("."):
                companies.append(candidate.split(", ", 1)[1])
                break
    return companies


# --- length -----------------------------------------------------------------

def _bullet_height(text: str) -> float:
    return math.ceil(max(len(text), 1) / BULLET_LINE_CHARS) * BULLET_LINE_PT + BULLET_SPACE_PT


def overflow_pt(pages: int, last_bottom_pt: Optional[float], limit: int) -> float:
    """How much text has to go for the CV to end on page `limit`."""
    if pages <= limit:
        return 0.0
    if last_bottom_pt is None:   # no Word: a third of a page per round
        return BODY_HEIGHT_PT / 3
    return (pages - limit - 1) * BODY_HEIGHT_PT + max(last_bottom_pt - MARGIN_PT, BULLET_LINE_PT)


def _blocks(content: dict) -> List[dict]:
    """Every list of bullets the length fitting may cut from, with its rank:
    the higher, the sooner it is cut. The section printed second (projects
    after the jobs, or the jobs after the projects) goes before the first;
    inside it, the oldest job and the last project first. A job keeps one
    bullet; a project with an intro may lose all of them."""
    projects = cv_docx.projects_of(content)
    projects_first = projects["placement"] == "before_experience"
    job_rank, project_rank = (1, 0) if projects_first else (0, 1)
    blocks = []
    for index, job in enumerate(content.get("experience") or []):
        blocks.append({"owner": job, "rank": (job_rank, index), "keep": 1, "label": job.get("company", "")})
    if projects["form"] == "full":
        for index, project in enumerate(projects["items"]):
            keep = 0 if (project.get("intro") or "").strip() else 1
            blocks.append({"owner": project, "rank": (project_rank, index), "keep": keep,
                           "label": project.get("title", "")})
    elif projects["form"] == "compact":
        blocks.append({"owner": projects["compact"], "rank": (project_rank, 0), "keep": 1,
                       "label": "Independent projects"})
    return blocks


def cut_bullets(content: dict, need_pt: float, max_priority: int) -> List[str]:
    """Removes bullets until about `need_pt` of height is freed: the highest
    priority number first, then the block ranked to go first (_blocks),
    then the last bullet of a block. Returns the removed texts."""
    blocks = _blocks(content)
    candidates = []
    for block_index, block in enumerate(blocks):
        for bullet_index, bullet in enumerate(block["owner"].get("bullets") or []):
            priority = bullet.get("priority", 2) if isinstance(bullet, dict) else 2
            if priority >= max_priority:
                candidates.append((priority, block["rank"], bullet_index, block_index))
    candidates.sort(reverse=True)
    freed, removed = 0.0, []
    doomed = {}
    for priority, _rank, bullet_index, block_index in candidates:
        if freed >= need_pt:
            break
        block = blocks[block_index]
        bullets = block["owner"]["bullets"]
        if len(bullets) - len(doomed.get(block_index, ())) <= block["keep"]:
            continue
        doomed.setdefault(block_index, set()).add(bullet_index)
        text = cv_docx.bullet_text(bullets[bullet_index])
        freed += _bullet_height(text)
        removed.append(f"{block['label']}: {text}")
    for block_index, indexes in doomed.items():
        owner = blocks[block_index]["owner"]
        owner["bullets"] = [b for i, b in enumerate(owner["bullets"]) if i not in indexes]
    return removed


def drop_project(content: dict) -> List[str]:
    """The last resort: the last project goes whole."""
    projects = content.get("projects") or {}
    if cv_docx.projects_of(content)["form"] != "full" or not projects.get("items"):
        return []
    project = projects["items"].pop()
    if not projects["items"]:
        projects["form"] = "none"
    return [f"the whole project {project.get('title', '')}"]


def fit_length(content: dict, render, *, target_pages: int, max_pages: int) -> dict:
    """Renders, measures, cuts, until the CV fits. `render(content)` writes
    the files and returns {"pages", "last_page_bottom_pt"}.

    Stage 1 cuts priority 3 and 2 bullets down to target_pages. With only
    priority-1 bullets left the CV may stay up to max_pages; past that,
    stage 2 cuts priority-1 bullets too, and then whole projects."""
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
            cut = cut_bullets(content, need, max_priority=1) or drop_project(content)
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


def publish_version(document, files: List[Path], content: dict, instructions: Optional[str],
                    auto: bool = False, anew: bool = False, stem: Optional[str] = None) -> dict:
    verdict = content.get("previous_version") or {}
    try:
        return document.publish(files, message=instructions,
                                previous_failed=bool(verdict.get("failed")) and not anew,
                                failed_reason=(verdict.get("reason") or "").strip() or None,
                                auto=auto, anew=anew, stem=stem)
    except documents.DocumentsError as exc:
        raise TailorError(str(exc))


def tailor(*, settings: dict, vacancy: dict, vacancy_id: str, archive_root: Path, out_dir: Path,
           content: Optional[dict] = None, model_call=call_model, converter=None,
           instructions: Optional[str] = None, auto: bool = False, anew: bool = False) -> dict:
    """The whole run; returns the result the app shows. `out_dir` is the
    vacancy's folder of documents (documents.vacancy_dir): the new version
    goes there, the current one into "Old versions". `converter` is a
    cv_convert.WordSession-like object, or None to pick one here. `anew`:
    the model gets neither the log nor the previous version (task 0114)."""
    document = documents.Document(out_dir, "cv", settings["output_stem"])
    earlier = earlier_versions(document)
    if anew:
        earlier.update(log_text="", previous_text=None)
    say(f"CV V{earlier['version']}: {vacancy.get('title', vacancy_id)} — {vacancy.get('company', '')}")
    if instructions and instructions.strip():
        say(f"message: {instructions.strip()}")
    cv_text = read_parent(settings)
    languages = settings.get("languages") or []
    warnings = []

    workdir = archive_root / vacancy_id / _stamp()
    workdir.mkdir(parents=True, exist_ok=True)
    if content is None:
        message = build_message(cv_text, vacancy, instructions, languages=languages,
                                target_pages=settings["target_pages"], max_pages=settings["max_pages"],
                                **earlier)
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

    facts = check_facts(content, cv_text, person_text(instructions, earlier.get("log_text", "")),
                        languages)
    stem = headline_stem(settings["output_stem"], content.get("name", ""), content.get("headline", ""),
                         keep_fixed=bool(settings.get("output_fixed")))
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
    version = publish_version(document, files, content, instructions, auto, anew, stem)
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
    parser.add_argument("--auto", action="store_true",
                        help="Made by the document batch, not the person (the log says so)")
    parser.add_argument("--anew", action="store_true",
                        help="Make the version from the parent CV and the vacancy alone, without the "
                             "log and the previous version (the log says so)")
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
            auto=args.auto,
            anew=args.anew,
        )
    except ai_limit.UsageLimit as exc:
        # its own exit code: the task queue holds AI work until the reset (task 0057)
        ai_limit.record(exc)
        if args.json:
            print(json.dumps(exc.as_json(), ensure_ascii=False))
        else:
            common.eprint(f"cv_tailor: {exc}")
        return ai_limit.EXIT_CODE
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
