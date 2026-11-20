"""
A cover letter for one vacancy, as .docx and .pdf.

    python tools/cover_letter.py --identity sharp --vacancy 35bf096fae2ac0e4b101
    python tools/cover_letter.py --identity sharp --vacancy ID --content edited.json
    python tools/cover_letter.py --identity sharp --vacancy ID --json   # for the app
    python tools/cover_letter.py --identity sharp --vacancy ID --instructions "Mention Azure"

The sibling of cv_tailor.py, with the same inputs (the owner, 2026-10-12: a
"Generate Cover Letter" button beside "Generate CV", behaving the same): the
parent CV (cv.parent, the one source since 2026-11-14), the person's
languages from the profile, the vacancy from the shared base and the
person's instructions for this one letter. The letter is in English unless
the instructions ask for another language.

The model (`claude -p`, no tools, LETTER_SCHEMA) writes the letter; then,
without the model:

  1. check_facts() looks up the name, the contacts, every number and every
     technology the letter names in the parent CV and the person's messages
     (cv_tailor.person_text) and lists what it cannot find.
     It does not block: the list goes to the person with the files.
  2. cv_docx.render_letter() writes the .docx under the CV's header (a
     headline or stack line too long for its column is a warning, as for the
     CV) and signs with the name as a person writes it; Word (or
     LibreOffice) converts it to .pdf and counts the pages. More than one page
     is a warning, nothing is cut.
  3. The files go into the vacancy's folder of documents beside its CV
     (tools/documents.py) named as the CV is, after the letter's headline,
     with CV turned into Cover Letter ("Cover Letter Ivan Petrov Senior
     Full Stack Engineer.pdf"), versioned as the CV is, with "Cover Letter
     log.md".

The letter's headline is the title of the vacancy's latest CV
(cv_tailor.current_title, task 0134): the model is told it, and the code
puts it in, so the CV and the letter carry one title inside and in their
file names. With no CV yet the model picks the title by the CV's rule.

Every run is kept in data/identities/<prefix>/cover_letters/<vacancy id>/<time>/.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_limit  # noqa: E402
import common  # noqa: E402
import cv_convert  # noqa: E402
import cv_docx  # noqa: E402
import cv_tailor  # noqa: E402
import documents  # noqa: E402
from cv_tailor import TailorError, _string, _strings  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = ROOT / "config" / "cover_letter_prompt.md"
MAX_PAGES = 1

LETTER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name", "headline", "tagline", "location", "contacts", "date", "recipient", "greeting",
                 "paragraphs", "closing", "technologies", "previous_version", "report"],
    "properties": {
        "name": _string("exactly as in the CV"),
        "headline": _string("the title line under the name"),
        "tagline": _string("the stack line under the headline"),
        "location": cv_tailor.CONTENT_SCHEMA["properties"]["location"],
        "contacts": cv_tailor.CONTACTS_SCHEMA,
        "date": _string("today's date as written in the letter"),
        "recipient": _strings("the address block, from the vacancy only"),
        "greeting": _string(),
        "paragraphs": _strings("3-4 paragraphs, 250-350 words in all"),
        "closing": _string(),
        "technologies": _strings("every technology the letter names"),
        "previous_version": cv_tailor.PREVIOUS_VERSION_SCHEMA,
        "report": {
            "type": "object", "additionalProperties": False,
            "required": ["covered", "gaps", "stretched", "from_instructions", "notes"],
            "properties": {
                "covered": _strings(), "gaps": _strings(),
                "stretched": cv_tailor.CONTENT_SCHEMA["properties"]["report"]["properties"]["stretched"],
                "from_instructions": _strings(), "notes": _strings(),
            },
        },
    },
}


def letter_stem(cv_stem: str) -> str:
    """The output name: the CV's output name with "CV" turned into "Cover
    Letter", or "Cover Letter" in front when the name has no "CV" in it."""
    if re.search(r"\bCV\b", cv_stem):
        return re.sub(r"\bCV\b", "Cover Letter", cv_stem, count=1)
    return f"Cover Letter {cv_stem}".strip()


def build_message(cv_text: str, vacancy: dict, instructions: Optional[str] = None,
                  today: Optional[date] = None, *, languages: Optional[list] = None, log_text: str = "",
                  previous_text: Optional[str] = None, version: int = 1,
                  title: Optional[str] = None) -> str:
    description = (vacancy.get("description_text") or "").strip()
    if len(description) > cv_tailor.DESCRIPTION_LIMIT:
        description = description[:cv_tailor.DESCRIPTION_LIMIT] + "\n[cut]"
    today = today or date.today()
    parts = [f"Today is {today.day} {today.strftime('%B %Y')}.", "",
             "<parent_cv>", cv_text.strip(), "</parent_cv>", ""]
    if languages:
        parts += ["The person's languages, from their profile: " + ", ".join(languages) + ".", ""]
    if title:
        parts += [f"The person's CV for this vacancy is titled \"{title}\": the letter's headline is this "
                  "title, as it is.", ""]
    parts += cv_tailor.history_parts(log_text, previous_text, version, "cover letter")
    instructions = (instructions or "").strip()
    if instructions:
        parts += ["<person_instructions>", instructions, "</person_instructions>", ""]
    else:
        parts += ["The person gave no instructions this time: the letter is in English.", ""]
    parts += [
        "<vacancy>",
        f"Title: {vacancy.get('title', '')}",
        f"Company: {vacancy.get('company', '')}",
        f"Location: {vacancy.get('location_raw', '')}",
        "",
        description or "(the vacancy has no description text; write to the title)",
        "</vacancy>",
    ]
    return "\n".join(parts)


def validate_content(content: dict) -> list:
    problems = []
    for key in ("name", "greeting", "closing"):
        if not (content.get(key) or "").strip():
            problems.append(f"'{key}' is missing or empty")
    if not [p for p in content.get("paragraphs") or [] if p and p.strip()]:
        problems.append("'paragraphs' is missing or empty")
    return problems


def check_facts(content: dict, cv_text: str, person: str = "", languages: Optional[list] = None) -> dict:
    """The name, the contacts, the location line, every number of the letter
    and every technology it names, looked up in the parent CV. What the
    person wrote (`person`, cv_tailor.person_text) counts as a source for all
    of them: their word outranks the CV (the owner, 2026-10-22). Kinds: name,
    contact, location, number, term — as in cv_tailor.check_facts."""
    normalize = cv_tailor.normalize
    raw = cv_text + "\n" + person + "\n" + "\n".join(languages or [])
    sources = normalize(raw)
    source_numbers = set(cv_tailor._numbers(raw))
    header = cv_tailor.check_facts({"name": content.get("name", ""), "contacts": content.get("contacts"),
                                    "location": content.get("location", "")}, cv_text, person, languages)
    findings = [f for f in header["findings"] if f["kind"] in ("name", "contact", "location")]

    def add(kind, text, where, message):
        findings.append({"kind": kind, "text": text, "where": where, "message": message})

    for index, paragraph in enumerate(content.get("paragraphs") or [], 1):
        for number in cv_tailor._numbers(paragraph):
            if number not in source_numbers:
                add("number", number, f"paragraph {index}", f"the number is not in the CV: \"{paragraph[:90]}\"")
    seen = set()
    for term in content.get("technologies") or []:
        key = normalize(term)
        if not key or key in seen:
            continue
        seen.add(key)
        if not cv_tailor._contains_term(sources, term):
            add("term", term, "letter", "this technology is not named in the CV or the person's messages")
    return {"findings": findings, "not_checked": []}


def write_letter(*, settings: dict, vacancy: dict, vacancy_id: str, archive_root: Path, out_dir: Path,
                 content: Optional[dict] = None, model_call=None, converter=None,
                 instructions: Optional[str] = None, today: Optional[date] = None,
                 auto: bool = False, cv_archive: Optional[Path] = None) -> dict:
    """The whole run; returns the result the app shows. `out_dir` is the
    vacancy's folder of documents, as for cv_tailor.tailor. `converter` is a
    cv_convert.WordSession-like object, or None to pick one here.
    `cv_archive`: the CVs' archive the title comes from (task 0134);
    `archive_root`'s sibling "cvs" when None."""
    say = cv_tailor.say
    document = documents.Document(out_dir, "letter", letter_stem(settings["output_stem"]))
    earlier = cv_tailor.earlier_versions(document)
    say(f"Cover letter V{earlier['version']}: {vacancy.get('title', vacancy_id)} — {vacancy.get('company', '')}")
    if instructions and instructions.strip():
        say(f"message: {instructions.strip()}")
    cv_text = cv_tailor.read_parent(settings)
    languages = settings.get("languages") or []
    warnings = []
    title = cv_tailor.current_title(cv_archive or archive_root.parent / "cvs", vacancy_id)
    if title:
        say(f"title: {title}, as the CV")

    workdir = archive_root / vacancy_id / cv_tailor._stamp()
    workdir.mkdir(parents=True, exist_ok=True)
    if content is None:
        message = build_message(cv_text, vacancy, instructions, today, languages=languages, title=title,
                                **earlier)
        (workdir / "model_input.md").write_text(message, encoding="utf-8")
        say(f"asking the model ({settings['model']}), a minute or two")
        if model_call is None:
            content = cv_tailor.call_model(message, model=settings["model"], workdir=workdir,
                                           prompt_path=PROMPT_PATH, schema=LETTER_SCHEMA)
        else:
            content = model_call(message, model=settings["model"], workdir=workdir)
    (workdir / "content_from_model.json").write_text(json.dumps(content, ensure_ascii=False, indent=2),
                                                     encoding="utf-8")
    content = cv_tailor.clean_text(content)
    # one title with the CV, inside and in the file name (task 0134)
    content["headline"] = title or cv_tailor.file_title(content.get("headline", ""))
    problems = validate_content(content)
    if problems:
        raise TailorError("the letter's content is not usable: " + "; ".join(problems))

    warnings += cv_tailor.layout_warnings(content)

    facts = check_facts(content, cv_text, cv_tailor.person_text(instructions, earlier.get("log_text", "")),
                        languages)
    # named after its headline, as the CV (task 0116)
    stem = letter_stem(cv_tailor.headline_stem(settings["output_stem"], content.get("name", ""),
                                               content.get("headline", ""),
                                               keep_fixed=bool(settings.get("output_fixed"))))
    docx_path = workdir / f"{stem}.docx"
    pdf_path = workdir / f"{stem}.pdf"
    cv_docx.render_letter(content, docx_path, author=content.get("name", ""))

    pages = None
    if converter is not None:
        pages = converter.convert(docx_path, pdf_path)["pages"]
    elif cv_convert.word_available():
        say("Word: the PDF and the page count")
        with cv_convert.WordSession() as session:
            pages = session.convert(docx_path, pdf_path)["pages"]
    elif cv_convert.soffice_path():
        pages = cv_convert.libreoffice_convert(docx_path, pdf_path)["pages"]
    else:
        warnings.append("neither Microsoft Word nor LibreOffice is installed: no PDF, and the page count "
                        "was not measured")
    if pages and pages > MAX_PAGES:
        warnings.append(f"{pages} pages: a cover letter is one page; shorten it before sending")

    files = [docx_path] + ([pdf_path] if pdf_path.exists() else [])
    version = cv_tailor.publish_version(document, files, content, instructions, auto, stem=stem)
    published = version["files"]
    if version.get("previous_failed"):
        say(f"V{version['version'] - 1} marked failed: {(content.get('previous_version') or {}).get('reason') or ''}")
    say(f"V{version['version']}: {pages or '?'} page(s), in {out_dir}")
    result = {
        "ok": True,
        "vacancy": vacancy_id,
        "version": version["version"],
        "dir": str(out_dir),
        "docx": str(next((p for p in published if p.suffix == ".docx"), "")),
        "pdf": str(next((p for p in published if p.suffix == ".pdf"), "")),
        "pages": pages,
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
    parser = argparse.ArgumentParser(description="A cover letter for one vacancy: .docx and .pdf")
    parser.add_argument("--identity", default=None, help="Search identity prefix")
    parser.add_argument("--vacancy", required=True, help="The vacancy id (vacancies.id)")
    parser.add_argument("--documents-dir", default=None,
                        help="The folder of generated documents (default: tools/documents.py where)")
    parser.add_argument("--content", default=None,
                        help="Render this content JSON instead of asking the model")
    parser.add_argument("--model", default=None, help="Override cv.model (a claude --model value)")
    parser.add_argument("--json", action="store_true", help="Print the result as one JSON line")
    parser.add_argument("--instructions", default=None,
                        help="The person's instructions for this letter (what to stress, the language...)")
    parser.add_argument("--auto", action="store_true",
                        help="Made by the document batch, not the person (the log says so)")
    args = parser.parse_args(argv)

    import identity as identity_mod
    prefix = identity_mod.activate_or_exit(args.identity, quiet=args.json)
    try:
        settings = cv_tailor.cv_settings(common.load_profile(prefix), identity_mod.identity_dir(prefix))
        if args.model:
            settings["model"] = args.model
        content = json.loads(Path(args.content).read_text(encoding="utf-8")) if args.content else None
        vacancy = cv_tailor.load_vacancy(common.DB_PATH, args.vacancy)
        out_dir = documents.vacancy_dir(prefix, args.vacancy,
                                        Path(args.documents_dir) if args.documents_dir else None)
        cv_tailor.refuse_gone(vacancy, documents.Document(out_dir, "letter",
                                                          letter_stem(settings["output_stem"])))
        result = write_letter(
            settings=settings,
            vacancy=vacancy,
            vacancy_id=args.vacancy,
            archive_root=common.DATA_DIR / "cover_letters",
            out_dir=out_dir,
            content=content,
            instructions=args.instructions,
            auto=args.auto,
        )
    except ai_limit.UsageLimit as exc:
        # its own exit code: the task queue holds AI work until the reset (task 0057)
        ai_limit.record(exc)
        if args.json:
            print(json.dumps(exc.as_json(), ensure_ascii=False))
        else:
            common.eprint(f"cover_letter: {exc}")
        return ai_limit.EXIT_CODE
    except (TailorError, documents.DocumentsError, cv_convert.ConversionError, OSError, ValueError) as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        else:
            common.eprint(f"cover_letter: {exc}")
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
