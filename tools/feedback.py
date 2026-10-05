"""
The person's feedback on vacancies, gathered for the agent to act on.

In the desktop app a person marks a vacancy "applied", "not for me"
(rejected) or "wrong pick" (bugged), with an optional reason. A "wrong pick"
is a bug report against the filter: the vacancy should never have been shown.
"Not for me" is a preference the filter may or may not be able to learn.

This script does the gathering, so the agent does not have to dig through the
database by hand:

    python tools/feedback.py --identity sharp count
    python tools/feedback.py --identity sharp collect      # writes a package
    python tools/feedback.py --identity sharp list         # the same, to stdout
    python tools/feedback.py --identity sharp mark-reviewed --id X --id Y \\
        --outcome "role gate now rejects 'Java' titles; test added"

A package (data/<prefix>/feedback/pending_<time>.yaml) holds everything a
diagnosis needs: the person's words, what the vacancy looked like, why the
scorer let it through (the full score breakdown), the class and score when
the feedback was given next to the class and score now, and a summary of what
the pending items have in common. One shared cause is worth more than a patch
per vacancy, so the summary comes first.

The only column this script writes is vacancies.feedback_reviewed_at.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import db  # noqa: E402
import selections  # noqa: E402

DESCRIPTION_LIMIT = 4000
SUMMARY_TOP = 15

_PENDING_WHERE = (
    "feedback_status IN ('bugged', 'rejected') "
    "AND (feedback_reviewed_at IS NULL OR feedback_reviewed_at < feedback_at)"
)


def feedback_dir() -> Path:
    common.require_identity()
    return common.DATA_DIR / "feedback"


def count() -> dict:
    if not db.exists():
        return {"bugged": 0, "rejected": 0}
    with db.session() as conn:
        row = conn.execute(selections.load_queries()["pending_feedback_counts"]).fetchone()
    return {"bugged": row[0], "rejected": row[1]}


def _signal_hits(breakdown: dict) -> list:
    """Every scoring signal that fired, as "axis.kind: hit". Walks one level of
    nesting, which is where identity-declared extra signals live."""
    found = []

    def walk(prefix: str, node: dict, depth: int) -> None:
        for key, value in node.items():
            if isinstance(value, list) and key.endswith("hits"):
                found.extend(f"{prefix}.{key}: {hit}" for hit in value if isinstance(hit, str))
            elif isinstance(value, dict) and depth < 2:
                walk(f"{prefix}.{key}", value, depth + 1)

    for axis, node in (breakdown or {}).items():
        if isinstance(node, dict):
            walk(axis, node, 1)
    return found


def _item(conn, row: tuple, latest_selection: Optional[int]) -> dict:
    (vid, data, view, status, rejected_reason, bugged_reason, at, selection_id) = row
    v = json.loads(data)
    c = v.get("computed") or {}

    def listed_in(sel_id):
        if sel_id is None:
            return None
        hit = conn.execute(
            "SELECT class, score FROM selection_items WHERE selection_id = ? AND vacancy_id = ? "
            "LIMIT 1", (sel_id, vid)).fetchone()
        return {"selection": sel_id, "class": hit[0], "score": hit[1]} if hit else None

    now_listed = listed_in(latest_selection)
    description = v.get("description_text") or ""
    return {
        "id": vid,
        "status": status,
        "reason": (bugged_reason if status == "bugged" else rejected_reason) or None,
        "feedback_at": at,
        "title": v.get("title"),
        "company": v.get("company"),
        "url": v.get("url"),
        "source": v.get("source"),
        "location_raw": v.get("location_raw"),
        # What the person saw when they judged it, and where it stands now:
        # a fix that already worked shows up as a different class here.
        "then": listed_in(selection_id),
        "now": {
            "class": c.get("classification"),
            "score": c.get("score"),
            "listed_in_latest_selection": now_listed is not None,
        },
        "dealbreakers": c.get("dealbreakers") or [],
        "score_breakdown": c.get("score_breakdown") or {},
        "view": json.loads(view) if view else None,
        "description": (description[:DESCRIPTION_LIMIT]
                        + (" […]" if len(description) > DESCRIPTION_LIMIT else "")),
    }


def pending_items(include_reviewed: bool = False, statuses=("bugged", "rejected")) -> list:
    """Feedback waiting for review, bugged first, then by score."""
    if not db.exists():
        return []
    where = (_PENDING_WHERE if not include_reviewed
             else "feedback_status IN ('bugged', 'rejected')")
    marks = ",".join("?" for _ in statuses)
    with db.session() as conn:
        latest = selections.latest_selection_id(conn)
        rows = conn.execute(
            "SELECT id, data, view, feedback_status, rejected_reason, bugged_reason, "
            "feedback_at, feedback_selection_id FROM vacancies "
            f"WHERE {where} AND feedback_status IN ({marks})", tuple(statuses)).fetchall()
        items = [_item(conn, row, latest) for row in rows]
    items.sort(key=lambda it: (it["status"] != "bugged", -(it["now"]["score"] or 0), it["id"]))
    return items


def summarize(items: list) -> dict:
    """What the pending items have in common — where to look for one cause."""
    signals = Counter()
    for item in items:
        signals.update(set(_signal_hits(item["score_breakdown"])))
    return {
        "total": len(items),
        "by_status": dict(Counter(it["status"] for it in items)),
        "by_class_then": dict(Counter((it["then"] or {}).get("class") or "unknown"
                                      for it in items)),
        "by_class_now": dict(Counter(it["now"]["class"] or "unknown" for it in items)),
        "by_source": dict(Counter(it["source"] or "unknown" for it in items).most_common()),
        "most_common_signals": [
            {"signal": name, "items": n}
            for name, n in signals.most_common(SUMMARY_TOP) if n > 1
        ],
    }


def build_package(items: list) -> dict:
    return {
        "identity": common.ACTIVE_IDENTITY,
        "generated_at": db.now_iso(),
        "how_to_use": (
            "Start from `summary`: one shared cause is worth more than a patch "
            "per vacancy. For every `bugged` item find why the filter let it "
            "through (score_breakdown, dealbreakers), fix <prefix>_criteria.yaml "
            "or tools/score.py, and add a test built on this vacancy. Treat "
            "`rejected` as preferences. Then run `feedback.py mark-reviewed`."
        ),
        "summary": summarize(items),
        "items": items,
        "reviewed": [],
    }


def _dump(data: dict) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100)


def collect() -> Optional[Path]:
    items = pending_items()
    if not items:
        return None
    directory = feedback_dir()
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    path = directory / f"pending_{stamp}.yaml"
    path.write_text(_dump(build_package(items)), encoding="utf-8")
    return path


def mark_reviewed(ids: list, outcome: str, package: Optional[Path] = None) -> int:
    """Marks feedback as reviewed and records the outcome in the package it
    came from (the latest one unless named), next to the evidence."""
    reviewed_at = db.now_iso()
    with db.session() as conn:
        changed = 0
        for vid in ids:
            changed += conn.execute(
                "UPDATE vacancies SET feedback_reviewed_at = ? WHERE id = ? "
                "AND feedback_status IN ('bugged', 'rejected')", (reviewed_at, vid)).rowcount
    package = package or _latest_package()
    if package is not None and package.exists():
        data = yaml.safe_load(package.read_text(encoding="utf-8")) or {}
        data.setdefault("reviewed", []).append(
            {"ids": list(ids), "outcome": outcome, "at": reviewed_at})
        package.write_text(_dump(data), encoding="utf-8")
    return changed


def _latest_package() -> Optional[Path]:
    packages = sorted(feedback_dir().glob("pending_*.yaml"))
    return packages[-1] if packages else None


# --- CLI ------------------------------------------------------------------------

def cmd_count(_args) -> None:
    print(json.dumps(count()))


def cmd_collect(_args) -> None:
    path = collect()
    if path is None:
        print("Nothing to review: no pending 'bugged' or 'rejected' feedback.")
        return
    print(f"Package for review: {path}")
    print(json.dumps(count()))


def cmd_list(args) -> None:
    statuses = tuple(s.strip() for s in args.status.split(",") if s.strip())
    items = pending_items(include_reviewed=args.all, statuses=statuses)
    if not items:
        print("Nothing to show.")
        return
    sys.stdout.reconfigure(encoding="utf-8")
    print(_dump({"summary": summarize(items), "items": items}))


def cmd_mark_reviewed(args) -> None:
    changed = mark_reviewed(args.id, args.outcome,
                            Path(args.package) if args.package else None)
    print(f"OK: {changed} marked reviewed. Still pending: {json.dumps(count())}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Gather a person's feedback for review")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("count", help="Pending feedback, as JSON {bugged, rejected}"
                   ).set_defaults(func=cmd_count)
    sub.add_parser("collect", help="Write a review package of pending feedback"
                   ).set_defaults(func=cmd_collect)
    p_list = sub.add_parser("list", help="Print feedback as YAML, without writing a file")
    p_list.add_argument("--status", default="bugged,rejected")
    p_list.add_argument("--all", action="store_true", help="Include reviewed feedback")
    p_list.set_defaults(func=cmd_list)
    p_mark = sub.add_parser("mark-reviewed", help="Mark feedback as reviewed")
    p_mark.add_argument("--id", action="append", required=True)
    p_mark.add_argument("--outcome", required=True, help="What was done about it")
    p_mark.add_argument("--package", default=None,
                        help="The package to record the outcome in (default: the latest)")
    p_mark.set_defaults(func=cmd_mark_reviewed)
    return p


def main(argv: Optional[list] = None) -> None:
    import identity as identity_mod

    parser = build_parser()
    identity_mod.add_identity_arg(parser)
    args = parser.parse_args(argv)
    identity_mod.activate_or_exit(getattr(args, "identity", None))
    args.func(args)


if __name__ == "__main__":
    main()
