"""The list of work in tasks/ (format: tasks/README.md).

  python tools/tasks.py next                      the next free number
  python tools/tasks.py find <words>              tasks whose text has every word
  python tools/tasks.py new <stage> <slug> <title>
                                                  a new task with the next number;
                                                  stage is triage or to-do
  python tools/tasks.py log <number>              the commits that name the task

Every commit names its task with a "Task: NNNN" line, checked by
.githooks/commit-msg (CLAUDE.md §12, "Tasks").
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS = ROOT / "tasks"
STAGES = {"triage": "1-triage", "to-do": "2-to-do", "done": "3-done"}
NAME = re.compile(r"^(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

SKELETON = """# {number} {title}

Source: {source}

## Business
{business}

## Implementation
In outline, once the plan is worked out.

## Items
- TO DO - Work out the plan and write it here as the next items
"""


def tasks():
    for folder in STAGES.values():
        for path in sorted((TASKS / folder).glob("*.md")):
            if NAME.match(path.name):
                yield path


def next_number() -> str:
    used = [int(NAME.match(path.name).group(1)) for path in tasks()]
    return "%04d" % (max(used) + 1 if used else 0)


def find(words):
    words = [word.lower() for word in words]
    return [path for path in tasks() if all(word in path.read_text(encoding="utf-8").lower() for word in words)]


def new(stage: str, slug: str, title: str, source: str, business: str) -> Path:
    if stage not in ("triage", "to-do"):
        raise SystemExit("a new task starts in triage or to-do")
    if not SLUG.match(slug):
        raise SystemExit("the slug is a few lowercase English words joined by hyphens")
    number = next_number()
    path = TASKS / STAGES[stage] / f"{number}-{slug}.md"
    text = SKELETON.format(number=number, title=title, source=source, business=business)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def log(number: str) -> str:
    return subprocess.run(
        ["git", "log", "--format=%h %ad %s", "--date=short", f"--grep=^Task: {number}$"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("next")
    p_find = sub.add_parser("find")
    p_find.add_argument("words", nargs="+")
    p_new = sub.add_parser("new")
    p_new.add_argument("stage", choices=("triage", "to-do"))
    p_new.add_argument("slug")
    p_new.add_argument("title")
    p_new.add_argument("--source", default="the owner")
    p_new.add_argument("--business", default="What the person needs and why.")
    p_log = sub.add_parser("log")
    p_log.add_argument("number")
    args = parser.parse_args(argv)

    if args.command == "next":
        print(next_number())
    elif args.command == "find":
        for path in find(args.words):
            print(path.relative_to(ROOT).as_posix())
    elif args.command == "new":
        print(new(args.stage, args.slug, args.title, args.source, args.business).relative_to(ROOT).as_posix())
    elif args.command == "log":
        sys.stdout.write(log(args.number))


if __name__ == "__main__":
    main()
