"""The screening brief: one page about the person, for the cheap model that
screens postings (tools/ai_screen.py).

The owner, 2026-10-17: a cheap model such as Haiku reads every top posting
with a short digest of the person in mind; a strong model such as Opus writes
that digest once; it lives as a file in the local identity and is rewritten
whenever the CV changes.

The brief is <identity folder>/<p>_ai_brief.md. Its first line records the
hash of what it was written from: the CV text, the identity's description
(template and local), the personal profile and criteria, and the prompt. When
any of them changes the hash changes and the next `ensure` writes it again.
The owner's reasons for turning postings down go into the request too, but
not into the hash: new feedback alone does not rewrite the brief (`--force`
does).

    python tools/ai_brief.py --identity sharp            # write it if stale
    python tools/ai_brief.py --identity sharp --force    # write it anyway
    python tools/ai_brief.py --identity sharp --check    # say whether it is stale
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import common
import db

ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = ROOT / "config" / "ai_brief_prompt.md"
MODEL = "opus"
TIMEOUT_SECONDS = 600
FEEDBACK_LIMIT = 200
HEADER_RE = re.compile(r"^<!-- ai brief: inputs ([0-9a-f]{16})")


class BriefError(RuntimeError):
    pass


def brief_path(prefix: str) -> Path:
    import identity as identity_mod

    return identity_mod.identity_dir(prefix) / f"{prefix}_ai_brief.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def documents(prefix: str) -> dict:
    """{name: text} of what the brief is written from (the hashed part)."""
    import cv_docx
    import cv_tailor
    import identity as identity_mod

    folder = identity_mod.identity_dir(prefix)
    docs = {
        "search description (template)": _read(folder / "template" / f"{prefix}_identity.md"),
        "search description (personal)": _read(folder / f"{prefix}_identity.md"),
        "profile (personal)": _read(folder / f"{prefix}_profile.yaml"),
        "criteria (personal)": _read(folder / f"{prefix}_criteria.yaml"),
    }
    try:
        settings = cv_tailor.cv_settings(common.load_profile(prefix), folder)
        docs["CV"] = cv_docx.read_cv_text(settings["common"])
    except Exception as exc:  # noqa: BLE001 — a brief without the CV says so
        raise BriefError(f"the CV could not be read: {exc}")
    return docs


def inputs_hash(docs: dict) -> str:
    digest = hashlib.sha256(_read(PROMPT_PATH).encode("utf-8"))
    for name in sorted(docs):
        digest.update(f"\0{name}\0{docs[name]}".encode("utf-8"))
    return digest.hexdigest()[:16]


def stored_hash(path: Path) -> Optional[str]:
    first = _read(path).splitlines()[:1]
    match = HEADER_RE.match(first[0]) if first else None
    return match.group(1) if match else None


def feedback_reasons(prefix: str, limit: int = FEEDBACK_LIMIT) -> list:
    """The owner's own words on postings they turned down or marked wrong,
    newest first: "title | company | status: reason"."""
    if not db.exists():
        return []
    with db.session() as conn:
        rows = conn.execute(
            "SELECT json_extract(d.data, '$.title'), json_extract(d.data, '$.company'), "
            "v.feedback_status, COALESCE(v.rejected_reason, v.bugged_reason) "
            "FROM vacancy_identity v JOIN vacancies d ON d.id = v.vacancy_id "
            "WHERE v.identity_id = ? AND v.feedback_status IN ('rejected', 'bugged') "
            "AND COALESCE(v.rejected_reason, v.bugged_reason, '') <> '' "
            "ORDER BY v.feedback_at DESC LIMIT ?", (prefix, limit)).fetchall()
    return [f"{t} | {c} | {s}: {r}" for t, c, s, r in rows]


def build_message(docs: dict, reasons: list) -> str:
    parts = [f"# {name}\n\n{text.strip()}" for name, text in docs.items() if text.strip()]
    if reasons:
        parts.append("# The owner's reasons for turning postings down (title | company | status: reason)\n\n"
                     + "\n".join(f"- {r}" for r in reasons))
    return "\n\n".join(parts)


def call_model(message: str, *, model: str = MODEL, claude: str = "claude", run=subprocess.run) -> str:
    """One `claude -p` call with no tools, in an empty folder (no project
    CLAUDE.md in its context); returns the answer's text."""
    command = [claude, "-p", "--output-format", "json", "--tools", "", "--no-session-persistence",
               "--model", model, "--system-prompt-file", str(PROMPT_PATH)]
    with tempfile.TemporaryDirectory() as workdir:
        try:
            completed = run(command, input=message, capture_output=True, text=True, encoding="utf-8",
                            cwd=workdir, timeout=TIMEOUT_SECONDS)
        except FileNotFoundError:
            raise BriefError("the `claude` command was not found (Claude Code CLI)")
        except subprocess.TimeoutExpired:
            raise BriefError(f"claude did not answer in {TIMEOUT_SECONDS} s")
    try:
        answer = json.loads(completed.stdout or "")
    except json.JSONDecodeError:
        raise BriefError(f"claude's answer is not JSON: {(completed.stdout or completed.stderr or '')[:300]}")
    if answer.get("is_error") or not (answer.get("result") or "").strip():
        raise BriefError(f"claude: {answer.get('result') or answer.get('subtype')}")
    return answer["result"].strip()


def ensure(prefix: str, force: bool = False, call=None) -> dict:
    """Writes the brief when it is missing or stale. Returns {"path",
    "written", "hash"}. `call` stands in for call_model (tests)."""
    call = call or call_model
    docs = documents(prefix)
    current = inputs_hash(docs)
    path = brief_path(prefix)
    if not force and stored_hash(path) == current:
        return {"path": str(path), "written": False, "hash": current}
    text = call(build_message(docs, feedback_reasons(prefix)))
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    header = (f"<!-- ai brief: inputs {current}, written {stamp} by {MODEL} (tools/ai_brief.py). "
              "Rewritten when the CV or the identity documents change; edits here are lost then. -->")
    path.write_text(f"{header}\n\n{text}\n", encoding="utf-8")
    return {"path": str(path), "written": True, "hash": current}


def load(prefix: str) -> str:
    """The brief's text without its header line; '' when there is none."""
    lines = _read(brief_path(prefix)).splitlines()
    if lines and HEADER_RE.match(lines[0]):
        lines = lines[1:]
    return "\n".join(lines).strip()


def main() -> None:
    import identity as identity_mod

    parser = argparse.ArgumentParser(description="Write the screening brief of an identity")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--force", action="store_true", help="write it even when it is current")
    parser.add_argument("--check", action="store_true", help="only say whether it is current")
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)
    prefix = common.ACTIVE_IDENTITY
    try:
        if args.check:
            current = inputs_hash(documents(prefix))
            stale = stored_hash(brief_path(prefix)) != current
            print(f"{brief_path(prefix)}: {'stale' if stale else 'current'}")
            sys.exit(1 if stale else 0)
        result = ensure(prefix, force=args.force)
    except BriefError as exc:
        print(f"!! {exc}", file=sys.stderr)
        sys.exit(2)
    print(f"{'written' if result['written'] else 'current'}: {result['path']}")


if __name__ == "__main__":
    main()
