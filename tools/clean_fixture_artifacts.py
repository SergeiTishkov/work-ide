"""
Clearing test-fixture traces out of the real data and report folders.

WHY THIS EXISTS
--------------------
The tests run under a frozen fixture (`ftf`). If a test forgets to isolate its
paths, it writes into the REAL `reports/` and `data/` — the very folders a
person looks at. That is how `ftf_latest.md` and `reports/archive/ftf/` turned
up among the reports, and before them empty `aaaa` and `bbbb` from isolation tests.

The safety net in `tests/conftest.py` DETECTS such writes and fails the run.
Practice showed that is not enough: on 2026-08-04 the net did its job, I fixed
the cause, and the file itself simply stayed there — a person found it a day
later. Detection without cleanup leaves litter exactly where it gets in the way.

THE SAFETY PRINCIPLE
--------------------
This module deletes only what is certainly a fixture's trace:

  * the prefix must belong to an identity with `kind: fixture`;
  * EXACTLY two paths are removed: `reports/<p>_latest.md` and
    `reports/archive/<p>/`, plus `data/<p>/` if it appeared;
  * nothing under any other name is touched under any circumstances.

Live identities (`kind: personal`) are never deleted, even if their prefix is
passed explicitly: mixing up a flag is easier than restoring an accumulated base.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402


def fixture_prefixes() -> List[str]:
    """Prefixes of every identity with kind: fixture."""
    import identity as identity_mod

    return [p for p in identity_mod.list_identities(include_fixtures=True)
            if identity_mod._read_kind(p) == "fixture"]


def artifact_paths(prefix: str) -> List[Path]:
    """Paths a fixture may create in the real folders."""
    return [
        common.REPORTS_ROOT / f"{prefix}_latest.md",
        common.REPORTS_ROOT / "archive" / prefix,
        common.DATA_ROOT / prefix,
    ]


def clean(prefixes: List[str] = None, dry_run: bool = False) -> List[str]:
    """Removes fixture traces. Returns a list of what was cleared."""
    import identity as identity_mod

    prefixes = prefixes if prefixes is not None else fixture_prefixes()
    removed: List[str] = []

    for prefix in prefixes:
        # A double check rather than trusting the argument: deleting a live
        # identity's data is irreversible, and a typo in a prefix takes a second.
        if identity_mod._read_kind(prefix) != "fixture":
            raise ValueError(
                f"'{prefix}' is not a test fixture (kind != fixture). "
                "This tool removes fixture traces only."
            )

        for path in artifact_paths(prefix):
            if not path.exists():
                continue
            if not dry_run:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            removed.append(str(path))

    return removed


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Clear test-fixture traces out of reports/ and data/"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be deleted, touching nothing")
    args = parser.parse_args()

    removed = clean(dry_run=args.dry_run)
    if not removed:
        print("No test-fixture traces found — clean.")
        return
    verb = "would be deleted" if args.dry_run else "deleted"
    print(f"{verb.capitalize()}:")
    for path in removed:
        print(f"  - {path}")


if __name__ == "__main__":
    main()
