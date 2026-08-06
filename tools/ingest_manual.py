"""
Manual entry of findings into the Work IDE knowledge base.

Why this is needed: some of the best sources (LinkedIn Jobs, Indeed, Dice,
particular companies' careers pages) CANNOT be parsed by script dependably and
within the project's bounds without authorisation (see CLAUDE.md,
docs/SOURCES.md). Instead, the agent in an interactive session uses its own
tools (WebSearch/WebFetch) the way a person would, and enters what it finds
here — where it goes through the same normalize + score + report path as the
automatic sources.

The input JSON file is a list of objects:
[
  {
    "title": "Senior .NET Developer (Legacy Systems)",
    "company": "Acme Insurance Co",
    "url": "https://www.linkedin.com/jobs/view/1234567890",
    "location_raw": "Remote - United States",
    "remote": true,
    "description_text": "... (HTML is fine, it will be cleaned) ...",
    "tags": ["linkedin", ".NET", "insurance"],
    "salary_raw": "$60-70/hr contractor",
    "posted_at": "2026-07-20T00:00:00+00:00",   // optional
    "external_id": "li-1234567890"              // optional; defaults to url
  },
  ...
]

Usage:
  python tools/ingest_manual.py --file path/to/found.json
  python tools/ingest_manual.py --file path/to/found.json --source-name linkedin
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import kb  # noqa: E402
import normalize  # noqa: E402
import pipeline  # noqa: E402
import score  # noqa: E402


def load_manual_file(path: Path) -> list:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Expected a JSON list of vacancy objects")
    return data


def ingest(records: list, source_name: str = "manual") -> dict:
    common.ensure_dirs()
    criteria = score.load_criteria()
    profile = score.load_profile()

    for r in records:
        r.setdefault("source", source_name)
        r.setdefault("external_id", r.get("url"))

    normalized, skipped = normalize.normalize_batch(records)

    vacancies = kb.load_vacancies()
    prev_companies = kb.load_companies()
    state = common.load_json(common.STATE_PATH, default={"run_count": 0, "sources": {}})
    state.setdefault("sources", {})

    new_count = updated_count = 0
    for rec in normalized:
        computed = score.score_vacancy(rec, criteria, profile)
        action = kb.merge_vacancy(vacancies, rec, computed)
        if action == "new":
            new_count += 1
        else:
            updated_count += 1

    src_state = state["sources"].setdefault(source_name, {"consecutive_failures": 0})
    src_state["last_manual_ingest_at"] = kb.now_iso()
    src_state["last_ingest_count"] = len(normalized)
    src_state["last_ingest_skipped"] = skipped

    report_path = pipeline.finalize_and_report(vacancies, prev_companies, state)

    return {
        "new_vacancies": new_count,
        "updated_vacancies": updated_count,
        "skipped_records": skipped,
        "report_path": report_path,
    }


def main() -> None:
    import identity as identity_mod

    parser = argparse.ArgumentParser(description="Enter manually found vacancies into the knowledge base")
    parser.add_argument("--file", required=True, help="Path to the JSON file with the vacancy list")
    parser.add_argument("--source-name", default="manual", help="Source label, e.g. 'linkedin'")
    identity_mod.add_identity_arg(parser)
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)

    path = Path(args.file)
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    records = load_manual_file(path)
    result = ingest(records, source_name=args.source_name)
    print("Manual import finished:")
    for k, v in result.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
