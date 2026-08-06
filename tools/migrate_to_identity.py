"""
A one-off migration: one person's configuration and data -> an identity.

Moves the "single owner" legacy (config/*.yaml + data/knowledge + data/reports
+ data/raw + data/state.json) into the identity structure:

    config/profile.yaml            -> identities/<p>/<p>_profile.yaml
    config/criteria.yaml           -> identities/<p>/<p>_criteria.yaml
    config/sources.yaml            -> identities/<p>/<p>_sources.yaml
    config/ats_targets.yaml        -> identities/<p>/<p>_ats_targets.yaml
    data/knowledge/vacancies.json  -> data/<p>/knowledge/<p>_vacancies.json
    data/knowledge/companies.json  -> data/<p>/knowledge/<p>_companies.json
    data/knowledge/insights.md     -> data/<p>/knowledge/<p>_insights.md
    data/state.json                -> data/<p>/<p>_state.json
    data/reports/latest.md         -> reports/<p>_latest.md
    data/reports/<date>.md         -> reports/archive/<p>/<date>.md
    data/raw/<source>/*.jsonl      -> data/<p>/raw/<source>/*.jsonl

SAFETY: a dry run by default, touching nothing. It copies rather than moves;
the originals are deleted only by a separate --cleanup call, and only after the
copies have been verified. The accumulated knowledge base is the project's most
valuable artefact, and there is nowhere to restore it from.

The script is idempotent: a repeated --apply simply overwrites the copies.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

LEGACY_CONFIG_DIR = common.ROOT / "config"
LEGACY_DATA_DIR = common.ROOT / "data"

CONFIG_FILES = ("profile.yaml", "criteria.yaml", "sources.yaml", "ats_targets.yaml")
KNOWLEDGE_FILES = (
    ("vacancies.json", "vacancies.json"),
    ("companies.json", "companies.json"),
    ("recruiters.json", "recruiters.json"),
    ("insights.md", "insights.md"),
)


def plan_moves(prefix: str, data_root: Optional[Path] = None) -> List[Tuple[Path, Path]]:
    """A list of (from, to). Missing sources are skipped silently: not everyone
    has a recruiters.json or an archive of reports."""
    root = data_root or common.DATA_ROOT
    identity_dir = common.IDENTITIES_DIR / prefix
    data_dir = root / prefix
    moves: List[Tuple[Path, Path]] = []

    for name in CONFIG_FILES:
        src = LEGACY_CONFIG_DIR / name
        if src.exists():
            moves.append((src, identity_dir / f"{prefix}_{name}"))

    for src_name, dst_name in KNOWLEDGE_FILES:
        src = LEGACY_DATA_DIR / "knowledge" / src_name
        if src.exists():
            moves.append((src, data_dir / "knowledge" / f"{prefix}_{dst_name}"))

    state = LEGACY_DATA_DIR / "state.json"
    if state.exists():
        moves.append((state, data_dir / f"{prefix}_state.json"))

    # Reports go NOT into data/<p>/ but into the shared reports/ folder at the
    # repository root: they are the only files a person opens by hand.
    reports_dir = LEGACY_DATA_DIR / "reports"
    if reports_dir.is_dir():
        for src in sorted(reports_dir.glob("*.md")):
            if src.name == "latest.md":
                moves.append((src, common.REPORTS_ROOT / f"{prefix}_latest.md"))
            else:
                # Dated ones go into the archive, split per identity: only the
                # latest shortlists should remain at the root of reports/, or in
                # six months there will be a hundred files there.
                moves.append((src, common.REPORTS_ROOT / "archive" / prefix / src.name))

    raw_dir = LEGACY_DATA_DIR / "raw"
    if raw_dir.is_dir():
        for src in sorted(raw_dir.rglob("*.jsonl")):
            moves.append((src, data_dir / "raw" / src.relative_to(raw_dir)))

    return moves


def verify_copy(src: Path, dst: Path) -> Optional[str]:
    """Verifies a copy: size, and for JSON, that it parses. Returns a
    description of the problem, or None."""
    if not dst.exists():
        return "file was not created"
    if src.stat().st_size != dst.stat().st_size:
        return f"size mismatch: {src.stat().st_size} -> {dst.stat().st_size}"
    if dst.suffix == ".json":
        try:
            json.loads(dst.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            return f"the copy does not parse as JSON: {type(exc).__name__}"
    return None


def do_migration(prefix: str, moves: List[Tuple[Path, Path]], apply: bool) -> int:
    total_bytes = sum(src.stat().st_size for src, _ in moves)
    print(f"Files to move: {len(moves)} ({total_bytes / 1024 / 1024:.1f} MB)")
    print()

    problems = 0
    for src, dst in moves:
        rel_src = src.relative_to(common.ROOT)
        rel_dst = dst.relative_to(common.ROOT) if common.ROOT in dst.parents else dst
        size_mb = src.stat().st_size / 1024 / 1024
        size_str = f"{size_mb:6.1f} MB" if size_mb >= 0.1 else "        "

        if not apply:
            print(f"  [dry-run] {size_str}  {rel_src}  ->  {rel_dst}")
            continue

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        problem = verify_copy(src, dst)
        if problem:
            problems += 1
            print(f"  [FAIL]    {size_str}  {rel_src}  ->  {rel_dst}   {problem}")
        else:
            print(f"  [ok]      {size_str}  {rel_src}  ->  {rel_dst}")

    if apply and not problems:
        marker = (common.DATA_ROOT / prefix / ".identity")
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(f"{prefix}\n", encoding="utf-8")
        print(f"\n  [ok]      data owner marker: {marker}")

    return problems


def do_cleanup(moves: List[Tuple[Path, Path]], apply: bool) -> int:
    """Deletes originals — only those whose copies are in place and intact."""
    removed = 0
    for src, dst in moves:
        problem = verify_copy(src, dst) if dst.exists() else "no copy"
        if problem:
            print(f"  [SKIP] {src.relative_to(common.ROOT)} — copy not confirmed ({problem})")
            continue
        if apply:
            src.unlink()
        removed += 1
        prefix_label = "[removed]" if apply else "[dry-run]"
        print(f"  {prefix_label} {src.relative_to(common.ROOT)}")
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Moves one person's configuration and data into an identity"
    )
    parser.add_argument("--prefix", required=True, help="Prefix of the target identity")
    parser.add_argument("--apply", action="store_true",
                        help="Perform the move (without this flag it is a dry run)")
    parser.add_argument("--cleanup", action="store_true",
                        help="Delete the originals after a confirmed move")
    args = parser.parse_args()

    moves = plan_moves(args.prefix)
    if not moves:
        print("Nothing to move: the old layout was not found.")
        return

    if args.cleanup:
        print(f"=== Deleting originals ({'FOR REAL' if args.apply else 'dry run'}) ===\n")
        removed = do_cleanup(moves, args.apply)
        print(f"\nDone: {'deleted' if args.apply else 'would delete'} {removed} of {len(moves)}")
        if not args.apply:
            print("To delete for real, add --apply")
        return

    print(f"=== Moving into identity '{args.prefix}' "
          f"({'FOR REAL' if args.apply else 'dry run'}) ===\n")
    problems = do_migration(args.prefix, moves, args.apply)

    if not args.apply:
        print("\nThat was a dry run. To move, add --apply")
        print("Originals are NOT deleted: once verified, run with --cleanup --apply")
    elif problems:
        print(f"\nPROBLEMS: {problems}. Originals untouched; sort this out before --cleanup.")
        sys.exit(1)
    else:
        print("\nMove complete, every copy verified. The originals are still there.")
        print(f"Next: python tools/doctor.py --identity {args.prefix}")


if __name__ == "__main__":
    main()
