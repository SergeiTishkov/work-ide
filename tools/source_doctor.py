"""
The deterministic half of /source-doctor: what a repair may touch, whether the
person running it publishes, and the publishing itself.

The agent does the judgement — reading what changed at the source, fixing the
fetcher. This script does the parts that must not depend on judgement:

python tools/source_doctor.py scope linkedin       -> the files a repair of this source may change
python tools/source_doctor.py can-publish          -> is the person running this a maintainer
python tools/source_doctor.py publish linkedin -m "LinkedIn pages are ten cards long"

`publish`, in order, stopping at the first thing that is not right:

  1. only files in the source's scope are taken; anything else changed in the
     working copy is left exactly as it is — it may be the person's own work;
  2. not a maintainer (config/maintainers.yaml) -> the fix stays in the working
     copy and that is a normal outcome, exit 0. Somebody without push rights
     must not have their run stall on a push that was always going to fail;
  3. no branch or no upstream to push to -> kept local, exit 0;
  4. the source's live contract must pass, and the whole offline test suite
     must be green — otherwise nothing is committed, exit 1;
  5. commit the scoped files only, push the current branch to its upstream.
     A failed push leaves the commit in place and says so, exit 2. Never forced.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

MAINTAINERS_PATH = common.ROOT / "config" / "maintainers.yaml"

PUBLISHED, KEPT_LOCAL, REFUSED, PUSH_FAILED, NOTHING = (
    "published", "kept-local", "refused", "push-failed", "nothing-to-publish")
EXIT_CODES = {PUBLISHED: 0, KEPT_LOCAL: 0, NOTHING: 0, REFUSED: 1, PUSH_FAILED: 2}


def git(*args: str) -> Tuple[int, str]:
    proc = subprocess.run(["git", *args], cwd=common.ROOT, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def scope(source: str) -> List[str]:
    """What a repair of one source may change: its fetcher, its tests, its
    snapshots, its instructions, and the catalogue that describes it. A fix
    that needs anything else is not a source repair any more — it is a change
    to shared code, and that goes to a person."""
    import source_contract

    module = source_contract.fetcher_modules().get(source)
    if module is None:
        raise KeyError(f"unknown source '{source}'")
    return [
        f"tools/{module}.py",
        f"tests/test_{module}.py",
        f"tests/test_{module}_*.py",
        f"tests/fixtures/sources/{source}/",
        f"docs/sources/{source}.md",
        "config/sources.catalog.yaml",
    ]


def in_scope(path: str, patterns: List[str]) -> bool:
    from fnmatch import fnmatch

    for pattern in patterns:
        if pattern.endswith("/"):
            if path.startswith(pattern):
                return True
        elif fnmatch(path, pattern):
            return True
    return False


def changed_paths() -> List[str]:
    """Every path git sees as changed or new, relative to the repository root."""
    code, out = git("status", "--porcelain", "--untracked-files=all")
    if code != 0:
        raise RuntimeError(out)
    paths = []
    for line in out.splitlines():
        entry = line[3:]
        if " -> " in entry:            # a rename: the new name is what gets committed
            entry = entry.split(" -> ", 1)[1]
        paths.append(entry.strip().strip('"'))
    return paths


def maintainer_emails() -> List[str]:
    data = common.load_yaml(MAINTAINERS_PATH) if MAINTAINERS_PATH.exists() else {}
    return [str(email).strip().lower()
            for person in (data.get("maintainers") or [])
            for email in (person.get("emails") or [])]


def who_runs() -> Tuple[bool, str]:
    """(is a maintainer, the reason in words)."""
    code, email = git("config", "user.email")
    email = email.strip().lower() if code == 0 else ""
    if not email:
        return False, "git has no user.email here, so nobody is identified as a maintainer"
    if email in maintainer_emails():
        return True, f"{email} is a maintainer"
    return False, f"{email} is not listed in config/maintainers.yaml"


def push_target() -> Tuple[Optional[str], str]:
    code, branch = git("symbolic-ref", "--quiet", "--short", "HEAD")
    if code != 0:
        return None, "HEAD is detached: there is no branch to push"
    code, upstream = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if code != 0:
        return None, f"branch '{branch}' has no upstream to push to"
    return branch, f"'{branch}' -> '{upstream}'"


def run_offline_tests() -> Tuple[bool, str]:
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                          cwd=common.ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-15:])
    return proc.returncode == 0, tail


def publish(source: str, message: str, check_contract=None, run_tests=run_offline_tests) -> dict:
    patterns = scope(source)
    changed = changed_paths()
    mine = [p for p in changed if in_scope(p, patterns)]
    others = [p for p in changed if p not in mine]
    outcome = {"source": source, "files": mine, "left_untouched": others}

    if not mine:
        return dict(outcome, outcome=NOTHING, reason="no file in this source's scope has changed")

    maintainer, why = who_runs()
    if not maintainer:
        return dict(outcome, outcome=KEPT_LOCAL,
                    reason=f"{why}: the fix stays in this working copy and can be "
                           "offered as a pull request")
    branch, where = push_target()
    if branch is None:
        return dict(outcome, outcome=KEPT_LOCAL, reason=where)

    if check_contract is None:
        import source_contract

        check_contract = source_contract.check_source
    contract = check_contract(source)
    if contract["status"] != "ok":
        return dict(outcome, outcome=REFUSED,
                    reason=f"the live contract is {contract['status']}: {contract.get('detail', '')}")
    green, tail = run_tests()
    if not green:
        return dict(outcome, outcome=REFUSED, reason="the test suite is not green:\n" + tail)

    code, out = git("add", "--", *mine)
    if code != 0:
        return dict(outcome, outcome=REFUSED, reason=f"git add failed: {out}")
    # Paths after `--` make this commit take ONLY these files, whatever else
    # the person may have staged.
    code, out = git("commit", "-m", message, "--", *mine)
    if code != 0:
        return dict(outcome, outcome=REFUSED, reason=f"git commit failed: {out}")
    code, out = git("push")
    if code != 0:
        return dict(outcome, outcome=PUSH_FAILED,
                    reason=f"committed on {where}, but the push failed — the commit stays "
                           f"local, nothing was forced:\n{out}")
    return dict(outcome, outcome=PUBLISHED, reason=f"committed and pushed {where}")


def main() -> None:
    parser = argparse.ArgumentParser(description="The deterministic half of /source-doctor")
    sub = parser.add_subparsers(dest="command", required=True)
    p_scope = sub.add_parser("scope", help="the files a repair of this source may change")
    p_scope.add_argument("source")
    sub.add_parser("can-publish", help="is the person running this a maintainer")
    p_pub = sub.add_parser("publish", help="commit and push a repair, if this is a maintainer")
    p_pub.add_argument("source")
    p_pub.add_argument("-m", "--message", required=True)
    args = parser.parse_args()

    if args.command == "scope":
        print("\n".join(scope(args.source)))
    elif args.command == "can-publish":
        maintainer, why = who_runs()
        branch, where = push_target()
        print(f"maintainer: {'yes' if maintainer else 'no'} — {why}")
        print(f"push target: {where}")
        sys.exit(0 if maintainer and branch else 1)
    else:
        result = publish(args.source, args.message)
        print(f"{result['outcome']}: {result['reason']}")
        for path in result["files"]:
            print(f"   fix:  {path}")
        for path in result["left_untouched"]:
            print(f"   left untouched: {path}")
        sys.exit(EXIT_CODES[result["outcome"]])


if __name__ == "__main__":
    main()
