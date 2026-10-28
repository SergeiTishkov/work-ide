"""The list of work in tasks/ (format: tasks/README.md).

  python tools/tasks.py next                      the next free number
  python tools/tasks.py find <words>              tasks whose text has every word
  python tools/tasks.py new <stage> <slug> <title> --scope "tools, docs"
                                                  a new task with the next number;
                                                  stage is potential, triage or to-do
  python tools/tasks.py log <number>              the commits that name the task

Every commit names its task with a "Task: NNNN" line, checked by
.githooks/commit-msg (CLAUDE.md §12, "Tasks"). Every task from 0052 on names
its scope on a "Scope:" line (SCOPES below), checked by tests/test_tasks.py.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS = ROOT / "tasks"
STAGES = {"potential": "0-potential", "triage": "1-triage", "to-do": "2-to-do", "done": "3-done", "cancelled": "4-cancelled"}
NAME = re.compile(r"^(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# What a task is about (the owner, 2026-10-20): one or more, comma-separated.
SCOPES = {
    "identity:<prefix>": "one identity: its template, its documents",
    "tools": "tools/ and their tests",
    "app": "the desktop app",
    "config": "shared configuration in config/, sources included",
    "rules": "CLAUDE.md, skills, commands, hooks: how the agent works",
    "docs": "README, RUNBOOK, docs/",
    "tasks": "the task system: tasks/README.md, tools/tasks.py, the commit hook",
    "other": "anything else",
}
IDENTITY_SCOPE = re.compile(r"^identity:[a-z][a-z0-9]*$")
# Tasks before this one were written before the rule, and are left as they are.
FIRST_WITH_SCOPE = 52

SKELETON = """# {number} {title}

Source: {source}
Scope: {scope}

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


def _numbers_in_history() -> set:
    """Numbers of tasks git has seen, deleted ones included: a task deleted
    because it needed no commit keeps its number (tasks/README.md)."""
    result = subprocess.run(
        ["git", "log", "--all", "--format=", "--name-only", "--", "."],
        cwd=TASKS, capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0:
        return set()
    names = (Path(line).name for line in result.stdout.splitlines())
    return {int(match.group(1)) for match in map(NAME.match, names) if match}


def next_number() -> str:
    used = {int(NAME.match(path.name).group(1)) for path in tasks()} | _numbers_in_history()
    return "%04d" % (max(used) + 1 if used else 0)


def scope_errors(value: str) -> list:
    """What is wrong with the value of a "Scope:" line; empty when nothing."""
    parts = [part.strip() for part in value.split(",")]
    if not any(parts):
        return ["no scope: name one or more of " + ", ".join(SCOPES)]
    errors = []
    for part in parts:
        if part not in SCOPES or part == "identity:<prefix>":
            if not IDENTITY_SCOPE.match(part):
                errors.append(f"'{part}' is not a scope; the scopes are " + ", ".join(SCOPES))
    if len(set(parts)) != len(parts):
        errors.append("a scope is named twice")
    return errors


def find(words):
    words = [word.lower() for word in words]
    return [path for path in tasks() if all(word in path.read_text(encoding="utf-8").lower() for word in words)]


def new(stage: str, slug: str, title: str, source: str, business: str, scope: str) -> Path:
    if stage not in ("potential", "triage", "to-do"):
        raise SystemExit("a new task starts in potential, triage or to-do")
    if not SLUG.match(slug):
        raise SystemExit("the slug is a few lowercase English words joined by hyphens")
    errors = scope_errors(scope)
    if errors:
        raise SystemExit("; ".join(errors))
    scope = ", ".join(part.strip() for part in scope.split(","))
    number = next_number()
    path = TASKS / STAGES[stage] / f"{number}-{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)   # git keeps no empty stage folder
    text = SKELETON.format(number=number, title=title, source=source, business=business, scope=scope)
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
    p_new.add_argument("stage", choices=("potential", "triage", "to-do"))
    p_new.add_argument("slug")
    p_new.add_argument("title")
    p_new.add_argument("--source", default="the owner")
    p_new.add_argument("--business", default="What the person needs and why.")
    p_new.add_argument("--scope", required=True,
                       help="comma-separated: " + "; ".join(f"{k} = {v}" for k, v in SCOPES.items()))
    p_log = sub.add_parser("log")
    p_log.add_argument("number")
    args = parser.parse_args(argv)

    if args.command == "next":
        print(next_number())
    elif args.command == "find":
        for path in find(args.words):
            print(path.relative_to(ROOT).as_posix())
    elif args.command == "new":
        print(new(args.stage, args.slug, args.title, args.source, args.business, args.scope)
              .relative_to(ROOT).as_posix())
    elif args.command == "log":
        sys.stdout.write(log(args.number))


if __name__ == "__main__":
    main()
