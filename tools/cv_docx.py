"""
A CV as a Word document: the content of a tailored CV -> .docx, and the text
of an existing .docx CV -> plain text for the model to read.

The layout copies the owner's parent CV (2026-11-14; the common CV it copied
before is gone): A4, 1.27 cm margins, Arial 10. The header has three columns:
the name, headline, stack line and location line on the left, the contact
labels in the middle, the contact values (links) on the right. Section titles
are bold 14 pt. A project is a bold underlined title with its link on the
right, an intro paragraph, bullets and a "Technologies:" line, then any
labelled lines of its own ("AI Systems: ..."). A job is a bold "Title,
Company" line with the dates on the right, one line of context, bullets and
a "Technologies:" line; a job written as one paragraph has the context alone.
LAYOUT holds the numbers, so another person's look is a change in one place.

The content is a plain dict (see cv_tailor.CONTENT_SCHEMA):

    {"name": ..., "headline": ..., "tagline": ..., "location": ...,
     "contacts": [{"label": "Email", "value": "..."}],
     "summary": ["paragraph", ...],
     "skills": [{"category": "Back End", "items": ["C#", ...]}],
     "projects": {"placement": "before_experience" | "after_experience",
                  "form": "full" | "compact" | "none",
                  "items": [{"title": ..., "link": ..., "intro": ...,
                             "bullets": [{"text": ..., "priority": 1}], "tech_stack": [...],
                             "extra_lines": [{"label": "AI Systems", "items": [...]}]}],
                  "compact": {"bullets": [...], "tech_stack": [...]}},
     "experience": [{"dates": ..., "title": ..., "company": ..., "context": ...,
                     "bullets": [{"text": ..., "priority": 1}], "tech_stack": [...]}],
     "sections": [{"heading": "Education", "lines": ["..."]}]}

A bullet may also be a plain string. `priority` is used by the length fitting
in cv_tailor and is not printed. Content without `location` or `projects`
(made before 2026-11-14) renders without them.

render_letter() writes a cover letter (cover_letter.LETTER_SCHEMA) under the
same header as the CV, so the two read as one set:

    {"name": ..., "headline": ..., "location": ..., "contacts": [...], "date": ...,
     "recipient": ["Hiring Team", "Contoso"], "greeting": "Dear Hiring Team,",
     "paragraphs": ["...", ...], "closing": "Kind regards,"}
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_BREAK, WD_PARAGRAPH_ALIGNMENT, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.shared import Cm, Pt

LAYOUT = {
    "page_width_cm": 21.0,
    "page_height_cm": 29.7,
    "margin_cm": 1.27,
    "font": "Arial",
    "font_size_pt": 10,
    "line_spacing": 1.15,          # Summary and intro paragraphs; bullets are single
    "letter_size_pt": 11,          # the body of a cover letter
    "header_size_pt": 12,          # name, headline, stack line
    "location_size_pt": 10,
    "contact_size_pt": 9,
    # the header's three columns: name, contact labels, contact values
    "header_columns_cm": (9.70, 2.67, 6.10),
    "heading_size_pt": 14,         # a section title
    "heading_space_before_pt": 12,
    "heading_space_after_pt": 6,
    "paragraph_space_pt": 6,       # after a Summary paragraph, an intro, a head line
    "bullet_indent_cm": 0.635,
    "bullet_space_pt": 2,           # after a bullet but the last (the parent CV, 2026-11-14)
    "block_space_pt": 12,          # after a project or a job
    "tech_label": "Technologies:",
    "tech_separator": " · ",
    "link_color": "0563C1",
    "section_titles": {"summary": "Summary", "skills": "Technologies",
                       "projects": "Independent Projects", "experience": "Work Experience"},
}

URL_RE = re.compile(r"^(https?://\S+)$", re.IGNORECASE)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?[\d\s()\-]{7,}$")


# --- reading ----------------------------------------------------------------

def docx_text(path: Path) -> str:
    """The text of a .docx in reading order, tables included, one paragraph
    per line. Tabs survive as tabs: "Tech stack:\t.NET" stays one line."""
    document = Document(str(path))
    lines: List[str] = []
    body = document.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            lines.append(_paragraph_text(child))
        elif child.tag == qn("w:tbl"):
            for paragraph in child.iter(qn("w:p")):
                lines.append(_paragraph_text(paragraph))
    text = "\n".join(line.rstrip() for line in lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def _paragraph_text(p) -> str:
    # Only what is inside runs: a <w:tab> in the paragraph properties is a tab
    # stop, not a tab character.
    parts = []
    for run in p.iter(qn("w:r")):
        for node in run:
            if node.tag == qn("w:t"):
                parts.append(node.text or "")
            elif node.tag == qn("w:tab"):
                parts.append("\t")
            elif node.tag in (qn("w:br"), qn("w:cr")) and node.get(qn("w:type")) in (None, "textWrapping"):
                parts.append("\n")
    return "".join(parts)


def read_cv_text(path: Path) -> str:
    """A CV file as text: .docx through docx_text, .md/.txt as they are."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return docx_text(path)
    if suffix in (".md", ".txt", ".markdown"):
        return path.read_text(encoding="utf-8")
    raise ValueError(f"cannot read a CV from {path.name}: .docx, .md or .txt expected")


# --- writing ----------------------------------------------------------------

def bullet_text(bullet) -> str:
    return bullet["text"] if isinstance(bullet, dict) else str(bullet)


def _texts(bullets) -> List[str]:
    return [bullet_text(b).strip() for b in bullets or [] if bullet_text(b).strip()]


def _items(items) -> List[str]:
    return [i.strip() for i in items or [] if i and i.strip()]


def projects_of(content: dict) -> dict:
    """The projects part with its defaults: a missing one is none."""
    projects = content.get("projects") or {}
    form = projects.get("form") or ("full" if projects.get("items") else "none")
    return {"placement": projects.get("placement") or "after_experience", "form": form,
            "items": projects.get("items") or [], "compact": projects.get("compact") or {}}


def render(content: dict, path: Path, *, layout: dict = None, author: str = "") -> Path:
    """Writes the CV to `path` (.docx) and returns it."""
    lay = dict(LAYOUT, **(layout or {}))
    document = Document()
    _base_style(document, lay)
    _page(document.sections[0], lay)
    _header(document, content, lay)

    titles = lay["section_titles"]
    summary = [p for p in content.get("summary") or [] if p and p.strip()]
    if summary:
        _heading(document, titles["summary"], lay)
        for text in summary:
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(lay["paragraph_space_pt"])
            _run(paragraph, text.strip())

    skills = [s for s in content.get("skills") or [] if _items(s.get("items"))]
    if skills:
        _heading(document, titles["skills"], lay)
        for group in skills:
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(lay["bullet_space_pt"])
            paragraph.paragraph_format.line_spacing = 1.0
            _run(paragraph, f"{group.get('category', '').strip()}:", bold=True)
            _run(paragraph, " " + ", ".join(_items(group["items"])))

    projects = projects_of(content)
    if projects["placement"] == "before_experience":
        _projects(document, projects, lay)
        _experience(document, content, lay)
    else:
        _experience(document, content, lay)
        _projects(document, projects, lay)

    for section in content.get("sections") or []:
        lines = [line for line in section.get("lines") or [] if line and line.strip()]
        if not section.get("heading") or not lines:
            continue
        _heading(document, section["heading"], lay)
        for line in lines:
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(lay["bullet_space_pt"])
            _run(paragraph, line.strip())

    properties = document.core_properties
    properties.author = author or content.get("name", "")
    properties.last_modified_by = properties.author
    properties.title = f"CV {content.get('name', '')}".strip()
    properties.comments = ""
    properties.subject = content.get("headline", "")
    properties.keywords = ""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(path))
    return path


def render_letter(content: dict, path: Path, *, layout: dict = None, author: str = "") -> Path:
    """Writes the cover letter to `path` (.docx) and returns it."""
    lay = dict(LAYOUT, **(layout or {}))
    document = Document()
    _base_style(document, lay)
    _page(document.sections[0], lay)
    _header(document, content, lay)
    size = lay["letter_size_pt"]

    def block(lines, space_before=0.0, space_after=0.0):
        lines = [line.strip() for line in lines if line and line.strip()]
        for index, line in enumerate(lines):
            paragraph = document.add_paragraph()
            if index == 0:
                paragraph.paragraph_format.space_before = Pt(space_before)
            if index == len(lines) - 1:
                paragraph.paragraph_format.space_after = Pt(space_after)
            _run(paragraph, line, size=size)

    gap = lay["block_space_pt"]
    block([content.get("date", "")], space_before=2 * gap, space_after=gap)
    block(content.get("recipient") or [], space_after=gap)
    block([content.get("greeting", "")], space_after=gap)
    for text in content.get("paragraphs") or []:
        block([text], space_after=gap)
    block([content.get("closing", "")])
    block([signature(content.get("name", ""))], space_before=gap)

    properties = document.core_properties
    properties.author = author or content.get("name", "")
    properties.last_modified_by = properties.author
    properties.title = f"Cover letter {content.get('name', '')}".strip()
    properties.comments = ""
    properties.subject = content.get("headline", "")
    properties.keywords = ""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(path))
    return path


def signature(name: str) -> str:
    """The name under a letter: as a person signs it. A CV header often has
    it in capitals ("ALEX EXAMPLE"); those become "Alex Example"."""
    name = (name or "").strip()
    return name.title() if name.isupper() else name


def _header(document, content: dict, lay: dict) -> None:
    """The header: three columns, as in the parent CV. Left: name, headline,
    stack line, location line. Middle: the contact labels. Right: the contact
    values, aligned right. A column break starts each of the two contact
    columns, so nothing flows from one column into the next. The body after
    it is one column."""
    _set_columns(document.sections[0], lay["header_columns_cm"])
    for line in (content.get("name", ""), content.get("headline", ""), content.get("tagline", "")):
        if line and line.strip():
            paragraph = document.add_paragraph()
            _run(paragraph, line.strip(), bold=True, size=lay["header_size_pt"])
    location = (content.get("location") or "").strip()
    if location:
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.space_before = Pt(2)
        _run(paragraph, location, size=lay["location_size_pt"])

    contacts = [c for c in content.get("contacts") or [] if (c.get("value") or "").strip()]
    for column in ("label", "value"):
        for index, contact in enumerate(contacts or [{}]):
            paragraph = document.add_paragraph()
            if index == 0:
                paragraph.add_run().add_break(WD_BREAK.COLUMN)
                # one line down, level with the headline (as in the parent CV)
                _run(paragraph, "", size=lay["contact_size_pt"]).add_break()
            if column == "label":
                label = (contact.get("label") or "").strip().rstrip(":")
                if label:
                    _run(paragraph, f"{label}:", size=lay["contact_size_pt"])
            else:
                paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.RIGHT
                value = (contact.get("value") or "").strip()
                if value:
                    _link(paragraph, value, _target(value), lay, size=lay["contact_size_pt"])

    body = document.add_section(WD_SECTION.CONTINUOUS)
    _page(body, lay)
    _set_columns(body, None)


def _experience(document, content: dict, lay: dict) -> None:
    jobs = content.get("experience") or []
    if not jobs:
        return
    _heading(document, lay["section_titles"]["experience"], lay)
    for job in jobs:
        head = ", ".join(x for x in ((job.get("title") or "").strip(), (job.get("company") or "").strip()) if x)
        dates = (job.get("dates") or "").strip()
        paragraph = _head_line(document, lay)
        _run(paragraph, head, bold=True)
        if dates:
            _run(paragraph, "\t" + dates, bold=True)
        _item_body(document, job.get("context"), job.get("bullets"), job.get("tech_stack"), [], lay)


def _projects(document, projects: dict, lay: dict) -> None:
    form = projects["form"]
    if form == "compact":
        compact = projects["compact"]
        if not _texts(compact.get("bullets")):
            return
        _heading(document, lay["section_titles"]["projects"], lay)
        _item_body(document, "", compact.get("bullets"), compact.get("tech_stack"), [], lay)
        return
    items = [p for p in projects["items"] if (p.get("title") or "").strip()] if form == "full" else []
    if not items:
        return
    _heading(document, lay["section_titles"]["projects"], lay)
    for project in items:
        paragraph = _head_line(document, lay)
        _run(paragraph, project["title"].strip(), bold=True, underline=True)
        link = (project.get("link") or "").strip()
        if link:
            _run(paragraph, "\t")
            _link(paragraph, link, _target(link), lay)
        _item_body(document, project.get("intro"), project.get("bullets"), project.get("tech_stack"),
                   project.get("extra_lines") or [], lay)


def _head_line(document, lay: dict):
    """The first line of a job or a project: bold on the left, the dates or
    the link on a right-aligned tab stop at the right margin."""
    paragraph = document.add_paragraph()
    fmt = paragraph.paragraph_format
    fmt.keep_with_next = True
    fmt.space_after = Pt(lay["paragraph_space_pt"])
    fmt.line_spacing = 1.0
    width = lay["page_width_cm"] - 2 * lay["margin_cm"]
    fmt.tab_stops.add_tab_stop(Cm(width), WD_TAB_ALIGNMENT.RIGHT)
    return paragraph


def _item_body(document, intro, bullets, tech_stack, extra_lines, lay: dict) -> None:
    """What follows a head line: an intro paragraph, bullets, the
    Technologies line and any labelled lines. The last of them carries the
    space before the next job or project."""
    intro = (intro or "").strip()
    texts = _texts(bullets)
    lines = []
    stack = _items(tech_stack)
    if stack:
        lines.append((lay["tech_label"], stack))
    for extra in extra_lines:
        items = _items(extra.get("items"))
        label = (extra.get("label") or "").strip().rstrip(":")
        if label and items:
            lines.append((f"{label}:", items))

    last = "lines" if lines else "bullets" if texts else "intro"
    if intro:
        paragraph = document.add_paragraph()
        fmt = paragraph.paragraph_format
        fmt.space_after = Pt(lay["block_space_pt"] if last == "intro" else lay["paragraph_space_pt"])
        fmt.keep_with_next = bool(texts or lines)
        _run(paragraph, intro)
    for index, text in enumerate(texts):
        paragraph = document.add_paragraph(style="List Bullet")
        fmt = paragraph.paragraph_format
        fmt.left_indent = Cm(lay["bullet_indent_cm"])
        fmt.first_line_indent = Cm(-lay["bullet_indent_cm"])
        fmt.line_spacing = 1.0
        final = index == len(texts) - 1
        fmt.space_after = Pt(lay["block_space_pt"] if final and last == "bullets" else
                             lay["paragraph_space_pt"] if final else lay["bullet_space_pt"])
        _run(paragraph, text)
    for index, (label, items) in enumerate(lines):
        paragraph = document.add_paragraph()
        fmt = paragraph.paragraph_format
        fmt.line_spacing = 1.0
        fmt.space_after = Pt(lay["block_space_pt"] if index == len(lines) - 1 else lay["bullet_space_pt"])
        _run(paragraph, label, bold=True)
        _run(paragraph, " " + lay["tech_separator"].join(items))


def _heading(document, title: str, lay: dict) -> None:
    paragraph = document.add_paragraph()
    fmt = paragraph.paragraph_format
    fmt.space_before = Pt(lay["heading_space_before_pt"])
    fmt.space_after = Pt(lay["heading_space_after_pt"])
    fmt.keep_with_next = True
    _run(paragraph, title, bold=True, size=lay["heading_size_pt"])


def _base_style(document, lay: dict) -> None:
    normal = document.styles["Normal"]
    normal.font.name = lay["font"]
    normal.font.size = Pt(lay["font_size_pt"])
    fonts = normal.element.rPr.find(qn("w:rFonts"))
    for attribute in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        fonts.set(qn(attribute), lay["font"])
    fmt = normal.paragraph_format
    fmt.line_spacing = lay["line_spacing"]
    fmt.space_before = Pt(0)
    fmt.space_after = Pt(0)
    # The default template gives List Bullet "contextual spacing" and its own
    # indents; the indents are set per paragraph in _item_body.
    bullet = document.styles["List Bullet"]
    bullet.font.name = lay["font"]
    bullet.font.size = Pt(lay["font_size_pt"])


def _page(section, lay: dict) -> None:
    section.page_width = Cm(lay["page_width_cm"])
    section.page_height = Cm(lay["page_height_cm"])
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(section, side, Cm(lay["margin_cm"]))
    section.header_distance = Cm(0)


def _set_columns(section, widths_cm) -> None:
    """Columns of the given widths (cm), or one column for None."""
    sect = section._sectPr
    cols = sect.find(qn("w:cols"))
    if cols is not None:
        sect.remove(cols)
    cols = OxmlElement("w:cols")
    if widths_cm:
        cols.set(qn("w:num"), str(len(widths_cm)))
        cols.set(qn("w:space"), "0")
        cols.set(qn("w:equalWidth"), "0")
        for width in widths_cm:
            col = OxmlElement("w:col")
            col.set(qn("w:w"), str(int(round(width / 2.54 * 1440))))
            col.set(qn("w:space"), "0")
            cols.append(col)
    else:
        cols.set(qn("w:num"), "1")
        cols.set(qn("w:space"), "720")
    sect.append(cols)


def _run(paragraph, text: str, *, bold: bool = False, underline: bool = False, size: float = None):
    run = paragraph.add_run(text)
    run.bold = bold or None
    run.underline = underline or None
    if size:
        run.font.size = Pt(size)
    return run


def _target(value: str):
    if URL_RE.match(value):
        return value
    if EMAIL_RE.match(value):
        return f"mailto:{value}"
    if PHONE_RE.match(value):
        return "tel:" + re.sub(r"[^\d+]", "", value)
    return None


def _link(paragraph, value: str, target, lay: dict, size: float = None) -> None:
    """`value` as a hyperlink to `target`, or as plain text when there is no
    target."""
    if not target:
        _run(paragraph, value, size=size)
        return
    relation = paragraph.part.relate_to(target, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), relation)
    run = OxmlElement("w:r")
    properties = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), lay["link_color"])
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    properties.extend([color, underline])
    if size:
        node = OxmlElement("w:sz")
        node.set(qn("w:val"), str(int(size * 2)))
        properties.append(node)
    run.append(properties)
    text = OxmlElement("w:t")
    text.text = value
    text.set(qn("xml:space"), "preserve")
    run.append(text)
    link.append(run)
    paragraph._p.append(link)


def iter_terms(content: dict) -> Iterable[str]:
    """Every skill and technology entry: the claims the fact check matches
    against the source CV one by one."""
    for group in content.get("skills") or []:
        for item in group.get("items") or []:
            yield item
    for job in content.get("experience") or []:
        for item in job.get("tech_stack") or []:
            yield item
    projects = projects_of(content)
    if projects["form"] == "full":
        for project in projects["items"]:
            for item in project.get("tech_stack") or []:
                yield item
            for extra in project.get("extra_lines") or []:
                for item in extra.get("items") or []:
                    yield item
    elif projects["form"] == "compact":
        for item in projects["compact"].get("tech_stack") or []:
            yield item
