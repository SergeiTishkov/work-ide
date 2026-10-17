"""
Where generated CVs and cover letters live, and their versions.

    python tools/documents.py where                 # the folder, and where it is set
    python tools/documents.py set "D:/Job search"   # choose the folder
    python tools/documents.py where --json          # for the app

THE FOLDER (the owner, 2026-10-13). One folder for every identity, chosen
once — onboarding asks for it — and kept in local-identities/settings.yaml
(outside git, as everything personal):

    documents:
      folder: "C:/Users/me/Downloads/Work IDE CVs and CLs"

`set` takes the person's answer: an existing folder gets a "Work IDE CVs and
CLs" folder inside it; a folder that does not exist yet is created and used as
it is. Unset, the folder is ~/Downloads/Work IDE CVs and CLs.
WORK_IDE_DOCUMENTS_DIR overrides it (tests).

Inside: a folder per identity (its prefix), and in it a folder per vacancy
(the vacancy's id — the app opens these, nobody has to read the names):

    <folder>/sharp/a2b7661172422d8db6c6/
        CV Ivan Petrov.docx           the current CV
        CV Ivan Petrov.pdf
        CV log.md                     every version and what the person asked
        Cover Letter Ivan Petrov.docx
        Cover Letter Ivan Petrov.pdf
        Cover Letter log.md
        Old versions/
            CV Ivan Petrov V1 failed.docx
            CV Ivan Petrov V2.pdf
            ...

VERSIONS. The current files carry no version; when a new version is made,
the current pair moves into "Old versions" as "<name> V<n>", or "<name> V<n>
failed" when the person rejected it as a whole — asked to start over, or asked
for so many changes (about ten or more) that it is a do-over. The generating
model decides that from the person's message (cv_tailor's
`previous_version.failed`) and the log records it.

THE LOG ("CV log.md", "Cover Letter log.md") is the history of one document:
each version, when it was made, and the person's message for it, or that
there was none. The whole log goes to the model with every new version, with
the current version's text as the base to edit (the .docx as it is now, the
person's own edits in Word included), so a version keeps every correction
asked for before it. Its format, parsed by read_log():

    # CV log

    ## V1 · 2026-10-13 14:02
    Without a message.

    ## V2 · 2026-10-13 14:20 · failed
    Message:
    > Start over, the summary is wrong.
    Failed: the person asked to start over.

A generation that found no vacancy to write for — the link is dead, or no
description was ever fetched: an old vacancy, most likely gone — makes no
files and leaves an error in the log instead (the owner, 2026-10-13); the
automatic generation does not try that document again:

    ## Error · 2026-10-13 14:25
    Vacancy not found, possibly outdated: the link is dead.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

FOLDER_NAME = "Work IDE CVs and CLs"
OLD_VERSIONS = "Old versions"
KINDS = {
    "cv": {"title": "CV", "log": "CV log.md"},
    "letter": {"title": "Cover Letter", "log": "Cover Letter log.md"},
}
EXTENSIONS = (".docx", ".pdf")
VACANCY_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class DocumentsError(RuntimeError):
    pass


# --- the folder -------------------------------------------------------------

def settings_path() -> Path:
    return common.IDENTITIES_DIR / "settings.yaml"


def _read_settings() -> dict:
    path = settings_path()
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def default_root() -> Path:
    return Path.home() / "Downloads" / FOLDER_NAME


def root() -> Path:
    """The folder of generated documents: the environment, the settings, the
    default — in that order."""
    env = os.environ.get("WORK_IDE_DOCUMENTS_DIR")
    if env:
        return Path(env)
    folder = ((_read_settings().get("documents") or {}).get("folder") or "").strip()
    return Path(os.path.expanduser(folder)) if folder else default_root()


def choose_folder(answer: str) -> Path:
    """The folder for the person's answer: inside an existing folder, a new
    "Work IDE CVs and CLs"; a folder that does not exist is the folder."""
    path = Path(os.path.expanduser(answer.strip().strip('"'))).resolve()
    if path.exists() and not path.is_dir():
        raise DocumentsError(f"{path} is a file, not a folder")
    if path.is_dir() and path.name != FOLDER_NAME:
        path = path / FOLDER_NAME
    return path


def set_root(answer: str) -> Path:
    folder = choose_folder(answer)
    folder.mkdir(parents=True, exist_ok=True)
    settings = _read_settings()
    settings.setdefault("documents", {})["folder"] = folder.as_posix()
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    header = ("# Settings of this installation, for every identity. Outside git.\n"
              "# documents.folder: where generated CVs and cover letters go (tools/documents.py).\n")
    path.write_text(header + yaml.safe_dump(settings, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return folder


def vacancy_dir(prefix: str, vacancy_id: str, base: Optional[Path] = None) -> Path:
    if not VACANCY_ID_RE.match(vacancy_id or ""):
        raise DocumentsError(f"invalid vacancy id: {vacancy_id!r}")
    return (base or root()) / prefix / vacancy_id


# --- the log ----------------------------------------------------------------

HEAD_RE = re.compile(r"^## V(\d+) · ([^·]+?)( · failed)?\s*$")
ERROR_RE = re.compile(r"^## Error · (.+?)\s*$")


def read_log(path: Path) -> List[dict]:
    """[{"version", "at", "failed", "message", "failed_reason"}], oldest first."""
    if not path.exists():
        return []
    entries: List[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        head = HEAD_RE.match(line)
        if head:
            entries.append({"version": int(head.group(1)), "at": head.group(2).strip(),
                            "failed": bool(head.group(3)), "message": None, "failed_reason": None})
            continue
        if line.startswith("## "):
            entries.append(None)   # an error: not a version
            continue
        if not entries or entries[-1] is None:
            continue
        entry = entries[-1]
        if line.startswith("> "):
            entry["message"] = (entry["message"] + "\n" if entry["message"] else "") + line[2:]
        elif line == ">":
            entry["message"] = (entry["message"] or "") + "\n"
        elif line.startswith("Failed: "):
            entry["failed_reason"] = line[len("Failed: "):]
    return [e for e in entries if e is not None]


def last_error(path: Path) -> Optional[str]:
    """The error the log ends with ("Vacancy not found..."), or None when
    its last section is a version, or there is no log."""
    if not path.exists():
        return None
    error = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if HEAD_RE.match(line):
            error = None
        elif ERROR_RE.match(line):
            error = ""
        elif error == "" and line.strip():
            error = line.strip()
    return error


def render_log(kind: str, entries: List[dict]) -> str:
    lines = [f"# {KINDS[kind]['title']} log", ""]
    for entry in entries:
        lines.append(f"## V{entry['version']} · {entry['at']}" + (" · failed" if entry.get("failed") else ""))
        message = (entry.get("message") or "").strip()
        if message:
            lines.append("Message:")
            lines += [f"> {line}" if line else ">" for line in message.splitlines()]
        else:
            lines.append("Without a message.")
        if entry.get("failed"):
            lines.append(f"Failed: {entry.get('failed_reason') or 'rejected as a whole'}")
        lines.append("")
    return "\n".join(lines)


def error_section(text: str, now: Optional[datetime] = None) -> str:
    return f"## Error · {(now or datetime.now()).strftime('%Y-%m-%d %H:%M')}\n{text.strip()}\n"


# --- one document of one vacancy --------------------------------------------

class Document:
    """The files of one kind ("cv" or "letter") in one vacancy's folder."""

    def __init__(self, folder: Path, kind: str, stem: str):
        if kind not in KINDS:
            raise DocumentsError(f"unknown kind: {kind}")
        self.folder = folder
        self.kind = kind
        self.stem = stem
        self.log_path = folder / KINDS[kind]["log"]

    def current(self, extension: str) -> Path:
        return self.folder / f"{self.stem}{extension}"

    def entries(self) -> List[dict]:
        return read_log(self.log_path)

    def next_version(self) -> int:
        entries = self.entries()
        if not entries and any(self.current(ext).exists() for ext in EXTENSIONS):
            return 2
        return max((e["version"] for e in entries), default=0) + 1

    def log_text(self) -> str:
        return self.log_path.read_text(encoding="utf-8") if self.log_path.exists() else ""

    def record_error(self, text: str, now: Optional[datetime] = None) -> None:
        """No version was made: the reason goes to the end of the log."""
        self.folder.mkdir(parents=True, exist_ok=True)
        existing = self.log_text() or f"# {KINDS[self.kind]['title']} log\n\n"
        if not existing.endswith("\n\n"):
            existing = existing.rstrip("\n") + "\n\n"
        self.log_path.write_text(existing + error_section(text, now), encoding="utf-8")

    def previous_docx(self) -> Optional[Path]:
        path = self.current(".docx")
        return path if path.exists() else None

    def publish(self, files: List[Path], *, message: Optional[str], previous_failed: bool,
                failed_reason: Optional[str], now: Optional[datetime] = None) -> dict:
        """Moves the current pair into Old versions (as "V<n>" or "V<n>
        failed"), copies the new files in as the current ones and appends the
        new version to the log. Returns {"version", "files"}."""
        entries = self.entries()
        current = [self.current(ext) for ext in EXTENSIONS if self.current(ext).exists()]
        if current and not entries:
            # files with no log (put there by hand, or made before the log
            # existed): they are version 1
            made = datetime.fromtimestamp(current[0].stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            entries = [{"version": 1, "at": made, "failed": False, "message": None, "failed_reason": None}]
        version = max((e["version"] for e in entries), default=0) + 1
        if current:
            old = self.folder / OLD_VERSIONS
            old.mkdir(parents=True, exist_ok=True)
            previous = version - 1
            suffix = f" V{previous}" + (" failed" if previous_failed else "")
            for path in current:
                target = old / f"{self.stem}{suffix}{path.suffix}"
                try:
                    if target.exists():
                        target.unlink()
                    path.replace(target)
                except PermissionError:
                    raise DocumentsError(f"{path} is open in another program; close it and generate again")
            if previous_failed and entries:
                entries[-1]["failed"] = True
                entries[-1]["failed_reason"] = failed_reason or "rejected as a whole"
        self.folder.mkdir(parents=True, exist_ok=True)
        published = []
        for file in files:
            target = self.current(file.suffix)
            shutil.copyfile(file, target)
            published.append(target)
        stamp = (now or datetime.now()).strftime("%Y-%m-%d %H:%M")
        entries.append({"version": version, "at": stamp, "failed": False,
                        "message": (message or "").strip() or None, "failed_reason": None})
        # the errors in between are dropped: they made nothing, and the log
        # now ends with a version
        self.log_path.write_text(render_log(self.kind, entries), encoding="utf-8")
        return {"version": version, "files": published, "previous_failed": bool(current) and previous_failed}


def state(prefix: str, vacancy_ids: List[str], base: Optional[Path] = None) -> dict:
    """{vacancy id: {"dir", "cv": versions, "letter": versions, "errors":
    {kind: the error its log ends with}}} for the vacancies that have a
    folder: what the app's buttons show."""
    result = {}
    for vacancy_id in vacancy_ids:
        folder = vacancy_dir(prefix, vacancy_id, base)
        if not folder.is_dir():
            continue
        errors = {kind: last_error(folder / spec["log"]) for kind, spec in KINDS.items()}
        result[vacancy_id] = {
            "dir": str(folder),
            **{kind: len(read_log(folder / spec["log"])) for kind, spec in KINDS.items()},
            "errors": {kind: text for kind, text in errors.items() if text},
        }
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="The folder of generated CVs and cover letters")
    sub = parser.add_subparsers(dest="command", required=True)
    where = sub.add_parser("where", help="Print the folder")
    where.add_argument("--json", action="store_true")
    chosen = sub.add_parser("set", help="Choose the folder (an existing one gets "
                                        f"'{FOLDER_NAME}' inside it)")
    chosen.add_argument("folder")
    args = parser.parse_args(argv)
    if args.command == "set":
        try:
            folder = set_root(args.folder)
        except DocumentsError as exc:
            common.eprint(f"documents: {exc}")
            return 1
        print(folder)
        return 0
    folder = root()
    source = ("WORK_IDE_DOCUMENTS_DIR" if os.environ.get("WORK_IDE_DOCUMENTS_DIR")
              else str(settings_path()) if (_read_settings().get("documents") or {}).get("folder")
              else "the default")
    if args.json:
        print(json.dumps({"folder": str(folder), "source": source}, ensure_ascii=False))
    else:
        print(f"{folder}\n(set by {source})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
