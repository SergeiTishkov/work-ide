"""A cheap model reads each top posting with the person's brief in mind.

The owner, 2026-10-17: keyword gates miss what a person sees at once — an
office job whose location says "Hybrid", "at least 50% of the time in the
local office", a comment on Hacker News that is not a posting, a Go role with
.NET in the company blurb. Most of the wrong picks in the feedback of that
day were of this kind. So every vacancy in the top classes is read by a cheap
model (Haiku) that has the screening brief (tools/ai_brief.py) as its system
prompt, and answers in a fixed schema.

The answer only ever REMOVES: a "reject" becomes the dealbreaker
"ai: <reason>" in score.py; a "keep" changes nothing. remote_unconfirmed and
the classes below are never sent: the owner, 2026-10-17, "after the remote
check, no further processing for them".

Answers are stored per identity in the `ai_screens` table (schemas/db.sql), with the hash of
the brief and of the text the model read. score.py uses an answer only while
the text is the same; the pipeline asks again when the text or the brief
changes.

    python tools/ai_screen.py --identity sharp --limit 20      # screen the top
    python tools/ai_screen.py --identity sharp --show <id>     # the stored answer
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import common
import db

ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = ROOT / "config" / "ai_screen_prompt.md"
MODEL = "haiku"
WORKERS = 6
TIMEOUT_SECONDS = 180
TEXT_LIMIT = 12000
# The classes worth a model's reading: what the scripts kept as remote and
# fitting. The rest are either out already or parked for a person.
SCREENED_CLASSES = ("hot_lead", "worth_a_look", "long_shot", "engagement_unconfirmed")

SCHEMA = {
    "type": "object",
    "properties": {
        "is_job_posting": {"type": "boolean"},
        "work_arrangement": {"type": "string", "enum": ["remote", "hybrid", "onsite", "unclear"]},
        "location_ok": {"type": "string", "enum": ["yes", "no", "unclear"]},
        "role_fit": {"type": "string", "enum": ["good", "partial", "poor"]},
        "verdict": {"type": "string", "enum": ["keep", "reject"]},
        "reason": {"type": "string"},
        "quote": {"type": "string"},
    },
    "required": ["is_job_posting", "work_arrangement", "location_ok", "role_fit", "verdict", "reason"],
    "additionalProperties": False,
}

class ScreenError(RuntimeError):
    pass


def _text(record: dict) -> str:
    return (record.get("description_text") or "").strip()[:TEXT_LIMIT]


def message(record: dict) -> str:
    """What the model reads about one posting."""
    facts = {
        "title": record.get("title"),
        "company": record.get("company"),
        "location": record.get("location_raw"),
        "board": record.get("source"),
        "url": record.get("url"),
        "tags": record.get("tags") or [],
        "salary": record.get("salary_raw"),
        "workplace type the board declares": record.get("workplace_type"),
        "employment types": record.get("employment_types"),
    }
    lines = [f"{k}: {v}" for k, v in facts.items() if v not in (None, "", [])]
    text = _text(record)
    return "\n".join(lines) + "\n\ntext:\n" + (text or "(the board gave no text)")


def text_hash(record: dict) -> str:
    """The hash of what the model reads: an answer is valid while it holds."""
    return hashlib.sha256(message(record).encode("utf-8")).hexdigest()[:16]


def brief_hash(brief: str) -> str:
    return hashlib.sha256((PROMPT_PATH.read_text(encoding="utf-8") + brief).encode("utf-8")).hexdigest()[:16]


def load(conn, prefix: str) -> dict:
    """{vacancy id: stored answer} of one identity; each answer carries
    text_hash and brief_hash next to the model's fields."""
    out = {}
    for vid, th, bh, result in conn.execute(
            "SELECT vacancy_id, text_hash, brief_hash, result FROM ai_screens WHERE identity_id = ?", (prefix,)):
        try:
            out[vid] = {**json.loads(result), "text_hash": th, "brief_hash": bh}
        except json.JSONDecodeError:
            continue
    return out


def current(record: dict) -> Optional[dict]:
    """The record's stored answer when it was given for this very text."""
    screen = record.get("_ai_screen")
    if not isinstance(screen, dict) or screen.get("text_hash") != text_hash(record):
        return None
    return screen


def call_model(system_prompt: Path, text: str, *, model: str = MODEL, claude: str = "claude",
               run=subprocess.run, workdir: Optional[str] = None) -> tuple:
    """One `claude -p` call; returns (structured answer, cost in USD)."""
    command = [claude, "-p", "--output-format", "json", "--tools", "", "--no-session-persistence",
               "--model", model, "--system-prompt-file", str(system_prompt),
               "--json-schema", json.dumps(SCHEMA)]
    # No extended thinking: measured 2026-10-17 on one posting, $0.018 and
    # 2566 output tokens with it, $0.0059 and 237 without; the verdict is a
    # lookup against the brief, not a chain of reasoning.
    env = {**os.environ, "MAX_THINKING_TOKENS": "0"}
    try:
        completed = run(command, input=text, capture_output=True, text=True, encoding="utf-8",
                        cwd=workdir, timeout=TIMEOUT_SECONDS, env=env)
    except FileNotFoundError:
        raise ScreenError("the `claude` command was not found (Claude Code CLI)")
    except subprocess.TimeoutExpired:
        raise ScreenError(f"claude did not answer in {TIMEOUT_SECONDS} s")
    try:
        answer = json.loads(completed.stdout or "")
    except json.JSONDecodeError:
        raise ScreenError(f"not JSON: {(completed.stdout or completed.stderr or '')[:200]}")
    if answer.get("is_error"):
        raise ScreenError(f"claude: {answer.get('result') or answer.get('subtype')}")
    content = answer.get("structured_output")
    if not isinstance(content, dict) or content.get("verdict") not in ("keep", "reject"):
        raise ScreenError("no structured answer")
    return content, float(answer.get("total_cost_usd") or 0)


def worklist(vacancies: dict, stored: dict, brief_digest: str, classes=SCREENED_CLASSES,
             limit: Optional[int] = None) -> list:
    """Top-class vacancies with no answer for their current text and brief,
    highest score first."""
    todo = []
    for vid, record in vacancies.items():
        computed = record.get("computed") or {}
        if computed.get("classification") not in classes or record.get("duplicate_of"):
            continue
        answer = stored.get(vid)
        if answer and answer.get("text_hash") == text_hash(record) and answer.get("brief_hash") == brief_digest:
            continue
        todo.append((computed.get("score") or 0, vid))
    todo.sort(reverse=True)
    keys = [vid for _, vid in todo]
    return keys[:limit] if limit else keys


def screen(vacancies: dict, prefix: str, brief: str, *, classes=SCREENED_CLASSES,
           limit: Optional[int] = None, workers: int = WORKERS, call=None) -> dict:
    """Screens what needs it and attaches every answer as `_ai_screen`.
    Mutates `vacancies` in place; never raises for one posting. `call`
    stands in for call_model (tests)."""
    call = call or call_model
    import progress

    stats = {"screened": 0, "rejected": 0, "kept": 0, "errors": 0, "cost_usd": 0.0}
    if not brief.strip():
        stats["skipped"] = "no brief"
        return stats
    digest = brief_hash(brief)
    with db.session() as conn:
        stored = load(conn, prefix)
    keys = worklist(vacancies, stored, digest, classes, limit)
    stats["considered"] = len(keys)
    lock = threading.Lock()
    tick = progress.Progress(len(keys), "ai screen")
    with tempfile.TemporaryDirectory() as workdir:
        system_prompt = Path(workdir) / "screen_prompt.md"
        system_prompt.write_text(PROMPT_PATH.read_text(encoding="utf-8") + "\n" + brief + "\n", encoding="utf-8")

        def one(vid):
            record = vacancies[vid]
            try:
                answer, cost = call(system_prompt, message(record), workdir=workdir)
            except Exception as exc:  # noqa: BLE001 — one posting must not stop the rest
                with lock:
                    stats["errors"] += 1
                    stats["last_error"] = str(exc)[:200]
                    tick()
                return None
            with lock:
                stats["screened"] += 1
                stats["cost_usd"] += cost
                stats["rejected" if answer["verdict"] == "reject" else "kept"] += 1
                tick()
            return vid, answer, text_hash(record)

        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            results = [r for r in pool.map(one, keys) if r]
    now = datetime.now(timezone.utc).isoformat()
    with db.session() as conn:
        conn.executemany(
            "INSERT INTO ai_screens (identity_id, vacancy_id, text_hash, brief_hash, result, model, screened_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(identity_id, vacancy_id) DO UPDATE SET "
            "text_hash = excluded.text_hash, brief_hash = excluded.brief_hash, result = excluded.result, "
            "model = excluded.model, screened_at = excluded.screened_at",
            [(prefix, vid, th, digest, json.dumps(answer, ensure_ascii=False), MODEL, now)
             for vid, answer, th in results])
    for vid, answer, th in results:
        stored[vid] = {**answer, "text_hash": th, "brief_hash": digest}
    attach(vacancies, stored)
    stats["cost_usd"] = round(stats["cost_usd"], 3)
    return stats


def attach(vacancies: dict, stored: dict) -> None:
    for vid, record in vacancies.items():
        if vid in stored:
            record["_ai_screen"] = stored[vid]
        else:
            record.pop("_ai_screen", None)


def main() -> None:
    import ai_brief
    import identity as identity_mod
    import kb

    parser = argparse.ArgumentParser(description="Screen the top vacancies with a cheap model")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--show", default=None, help="print the stored answer for one vacancy id")
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)
    prefix = common.ACTIVE_IDENTITY
    if args.show:
        with db.session() as conn:
            print(json.dumps(load(conn, prefix).get(args.show), ensure_ascii=False, indent=2))
        return
    ai_brief.ensure(prefix)
    vacancies = kb.load_vacancies()
    stats = screen(vacancies, prefix, ai_brief.load(prefix), limit=args.limit)
    print(json.dumps(stats))


if __name__ == "__main__":
    sys.exit(main())
