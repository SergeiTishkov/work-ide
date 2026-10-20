"""The reputation of one vacancy's employer, looked up on request.

The owner, 2026-10-17: reputation lookups were a mandatory step of every
collection (/run, step 6) and did not pay for the time; they are now a button
on the vacancy in the app, shown while the company has no reputation result.
The button queues this tool:

    python tools/reputation_lookup.py --identity sharp --vacancy <id>

It asks a model with web search (`claude -p`, WebSearch and WebFetch only)
for the company's ratings on Glassdoor, Indeed, Trustpilot and the like —
those sites answer 403 to scripts, so search results are what there is — and
records the answer the way the hand commands do: `found` with the numbers
(kb.py set-company-reputation) or `insufficient_sources` (reputation.py
mark-insufficient). Then it rescores the company's vacancies for this
identity and renders their rows in the app again, so the button goes and the
Details show the result.

A company that already has a result is not looked up again: the tool only
rescores and renders, which is what the button needs for an identity whose
rows were rendered before the other identity's lookup.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_limit  # noqa: E402
import common  # noqa: E402
import db  # noqa: E402

MODEL = "sonnet"
TIMEOUT_SECONDS = 600
TOOLS = "WebSearch,WebFetch"

PROMPT = """You look up what employees say about one company, for a person
deciding whether to apply there. Search the web (Glassdoor, Indeed,
Trustpilot, Comparably, Blind, news about layoffs) for the company named
below; the review sites block scripts, so their numbers usually come from
search result snippets.

- `found`: true only when you found ratings for THIS company (check the name,
  the country, the field — many companies share a name).
- `overall_rating` and `work_life_balance`: on a 1-5 scale, from the source
  you name; null when not found.
- `source`: where the numbers come from ("Glassdoor", "Indeed", ...).
- `retrieval`: "web_search" when the numbers come from search result text,
  "direct" when you read the source's own page.
- `review_count`: the number of reviews behind the rating, null when unknown.
- `red_flags`: short phrases for what reviews or news repeat (layoffs,
  unpaid overtime, late pay, toxic management); empty when none.
- `notes`: one or two sentences for the person, in English.
- `searched`: the sites and searches you tried, for the record when nothing
  was found.

Answer with the structured output only."""

SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "overall_rating": {"type": ["number", "null"]},
        "work_life_balance": {"type": ["number", "null"]},
        "source": {"type": "string"},
        "retrieval": {"type": "string", "enum": ["web_search", "direct"]},
        "review_count": {"type": ["integer", "null"]},
        "red_flags": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "string"},
        "searched": {"type": "string"},
    },
    "required": ["found", "overall_rating", "work_life_balance", "source", "retrieval",
                 "review_count", "red_flags", "notes", "searched"],
}


class ReputationLookupError(Exception):
    pass


def message(vacancy: dict) -> str:
    """What the model is told about the company: the name, and what the
    vacancy says about where it is and what it does, to tell namesakes apart."""
    lines = [f"Company: {vacancy.get('company') or '?'}"]
    for key, label in (("company_url", "Company site"), ("location_raw", "Location"),
                       ("title", "The vacancy"), ("url", "Vacancy link")):
        if vacancy.get(key):
            lines.append(f"{label}: {vacancy[key]}")
    text = (vacancy.get("description_text") or "")[:3000]
    if text:
        lines.append("")
        lines.append("The vacancy's text (for context):")
        lines.append(text)
    return "\n".join(lines)


def call_model(text: str, *, model: str = MODEL, claude: str = "claude",
               run=subprocess.run) -> tuple:
    """One `claude -p` call with web search; returns (answer, cost in USD)."""
    with tempfile.TemporaryDirectory() as workdir:
        # An empty folder: no project instructions in the model's context.
        prompt = Path(workdir) / "prompt.md"
        prompt.write_text(PROMPT, encoding="utf-8")
        command = [claude, "-p", "--output-format", "json", "--tools", TOOLS,
                   "--allowedTools", TOOLS, "--no-session-persistence", "--model", model,
                   "--system-prompt-file", str(prompt), "--json-schema", json.dumps(SCHEMA)]
        try:
            completed = run(command, input=text, capture_output=True, text=True, encoding="utf-8",
                            cwd=workdir, timeout=TIMEOUT_SECONDS, env={**os.environ})
        except FileNotFoundError:
            raise ReputationLookupError("the `claude` command was not found (Claude Code CLI)")
        except subprocess.TimeoutExpired:
            raise ReputationLookupError(f"claude did not answer in {TIMEOUT_SECONDS} s")
    ai_limit.check(completed)
    try:
        answer = json.loads(completed.stdout or "")
    except json.JSONDecodeError:
        raise ReputationLookupError(f"not JSON: {(completed.stdout or completed.stderr or '')[:200]}")
    if answer.get("is_error"):
        raise ReputationLookupError(f"claude: {answer.get('result') or answer.get('subtype')}")
    content = answer.get("structured_output")
    if not isinstance(content, dict) or "found" not in content:
        raise ReputationLookupError("no structured answer")
    return content, float(answer.get("total_cost_usd") or 0)


def reputation_of(answer: dict) -> Optional[dict]:
    """The company's reputation entry from the model's answer, in the shape
    kb.py set-company-reputation writes; None when nothing was found."""
    import kb

    if not answer.get("found") or answer.get("overall_rating") is None:
        return None
    return {
        "overall_rating": answer["overall_rating"],
        "work_life_balance": answer.get("work_life_balance"),
        "source": answer.get("source") or "web search",
        "retrieval": answer.get("retrieval") or "web_search",
        "review_count": answer.get("review_count"),
        "red_flags": [f.strip() for f in answer.get("red_flags") or [] if f and f.strip()],
        "notes": answer.get("notes") or "",
        "checked_at": kb.now_iso(),
    }


def refresh_company(vacancies: dict, companies: dict, slug: str) -> int:
    """Rescores this identity's vacancies of the company and renders their
    rows in the app again; returns how many."""
    import kb
    import score
    import selections
    from pipeline import rescore_all

    ids = [vid for vid in (companies.get(slug) or {}).get("vacancy_ids", []) if vid in vacancies]
    subset = {vid: vacancies[vid] for vid in ids}
    rescore_all(subset, score.load_criteria(), score.load_profile(), companies)
    kb.save_vacancies(subset)
    with db.session() as conn:
        shown = {row[0] for row in conn.execute(
            "SELECT vacancy_id FROM vacancy_identity WHERE identity_id = ? AND view IS NOT NULL",
            (db.identity(),))}
    rows = [selections._view_row(v) for vid, v in subset.items() if vid in shown]
    with db.session() as conn:
        conn.executemany(selections.UPDATE_VIEWS, rows)
    return len(subset)


def lookup(vacancy_id: str, *, call=None) -> dict:
    """Looks up the employer of one vacancy unless it has a result, records
    it, rescores and renders. Returns what happened."""
    import kb
    import reputation

    call = call or call_model
    vacancies = kb.load_vacancies()
    vacancy = vacancies.get(vacancy_id)
    if vacancy is None:
        raise ReputationLookupError(f"no vacancy {vacancy_id} in the base")
    name = vacancy.get("company") or ""
    slug = common.normalize_company_name(name)
    companies = kb.load_companies()
    entry = companies.get(slug)
    if entry is None:
        raise ReputationLookupError(f"the company '{name}' is not in the base")

    outcome = {"company": name, "cost_usd": 0.0}
    if entry.get("reputation"):
        outcome["result"] = "already collected"
    else:
        answer, cost = call(message(vacancy))
        outcome["cost_usd"] = cost
        found = reputation_of(answer)
        if found:
            entry["reputation"] = found
            outcome["result"] = (f"found: {found['overall_rating']} overall, "
                                 f"{found['work_life_balance']} work-life balance ({found['source']})")
        else:
            reputation.mark_insufficient(companies, name, answer.get("searched") or "")
            outcome["result"] = "too few sources"
        if answer.get("notes"):
            outcome["notes"] = answer["notes"]
        kb.save_companies(companies)
    outcome["rescored"] = refresh_company(vacancies, companies, slug)
    return outcome


def main() -> None:
    import identity as identity_mod

    parser = argparse.ArgumentParser(description="Look up the reputation of one vacancy's employer")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--vacancy", required=True)
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)
    try:
        outcome = lookup(args.vacancy)
    except ai_limit.UsageLimit as exc:
        ai_limit.record(exc)
        print(f"reputation: {exc}")
        sys.exit(ai_limit.EXIT_CODE)   # the task queue holds AI work until the reset (task 0057)
    except ReputationLookupError as exc:
        print(f"reputation: {exc}")
        sys.exit(1)
    print(f"reputation of {outcome['company']}: {outcome['result']}")
    if outcome.get("notes"):
        print(f"  {outcome['notes']}")
    print(f"  vacancies rescored: {outcome['rescored']}, cost ${outcome['cost_usd']:.3f}")


if __name__ == "__main__":
    main()
