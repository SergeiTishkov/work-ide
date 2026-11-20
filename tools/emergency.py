"""
The emergency file (the owner, 2026-11-21, task 0135): `emergency.md` in the
repository's root, the serious breakdowns of the scripts, kept until settled.

    python tools/emergency.py                  # the open entries, or nothing
    python tools/emergency.py add "LinkedIn fetch not merged" "what happened, where the work is kept, the way back"

A script whose failure loses or puts at risk work already done (a fetch of
hours, a batch) appends an entry with report(): what happened, where what was
done is kept, and how to get it back. Entries are appended text, one after
another, each after a line of underscores (in Markdown, a horizontal rule),
so a script needs no parser to add one and two never run together.

The file is never committed: .gitignore holds it and .githooks/commit-msg
refuses a commit that stages it, and prints the open entries at every commit.
What an agent does with an entry is in CLAUDE.md §12, "Emergencies": fix what
has an obvious fix and tell the owner, tell the owner of the rest, remind the
owner of every open entry at the end of each piece of work and at each
commit, and remove an entry once it is settled.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "emergency.md"
SEPARATOR = "_" * 72


def report(title: str, text: str, now: Optional[datetime] = None, path: Optional[Path] = None) -> Optional[Path]:
    """Appends one entry; never raises (it is called while something else is
    failing). Returns the file, or None when it could not be written."""
    path = path or PATH
    stamp = (now or datetime.now()).strftime("%Y-%m-%d %H:%M")
    entry = f"{SEPARATOR}\n\n## {stamp} {title.strip()}\n\n{text.strip()}\n\n"
    try:
        with path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(entry)
        return path
    except Exception as exc:  # noqa: BLE001 - the report must not hide the failure it reports
        print(f"[emergency] could not write {path}: {exc}\n{entry}", file=sys.stderr)
        return None


def entries(path: Optional[Path] = None) -> List[str]:
    """The open entries, each as written, without its separator."""
    path = path or PATH
    if not path.exists():
        return []
    parts, current = [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and set(line.strip()) == {"_"} and len(line.strip()) >= 3:
            parts.append("\n".join(current))
            current = []
        else:
            current.append(line)
    parts.append("\n".join(current))
    return [p.strip() for p in parts if p.strip()]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="The emergency file: serious breakdowns, kept until settled")
    sub = parser.add_subparsers(dest="command")
    add = sub.add_parser("add", help="append an entry")
    add.add_argument("title")
    add.add_argument("text")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.command == "add":
        return 0 if report(args.title, args.text) else 1
    for entry in entries():
        print(SEPARATOR)
        print(entry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
