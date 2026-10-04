"""
Source contracts: does each source still answer the way its fetcher expects,
today.

A fetcher is built on a handful of facts about somebody else's server — the
endpoint answers, a card has these fields, the next page starts
here, this filter is honoured. Any of them can change without notice, and the
fetcher's own defences only catch the loudest case (cards arrive, none parse).
The quiet cases — a page that got shorter, a filter that stopped filtering —
look exactly like "the market has less today". The contract checks those facts
directly, live, with a fixed probe that belongs to the source rather than to
any identity.

A fetcher opts in by defining `contract(c)` in its module; `c` is a
ContractRun. Sources without one are reported as having no contract.

python tools/source_contract.py                     -> every source with a contract
python tools/source_contract.py --source linkedin
python tools/source_contract.py --identity kisel    -> the sources that identity has enabled
python tools/source_contract.py --json

Four outcomes, and they call for different things:

  ok           the source answers as the fetcher expects
  broken       it answers, but not as expected: the FETCHER needs fixing —
               this is what /source-doctor is for
  unreachable  network error, timeout, 429, 5xx: transient, nothing to fix
  blocked      401/403/999 or a login wall: the source closed the door to
               anonymous requests. Not a fetcher bug — it goes to the owner

Exit code 1 when any checked source is broken or blocked, 0 otherwise: an
unreachable source is the network's problem today, not the code's.
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

OK, BROKEN, UNREACHABLE, BLOCKED, NO_CONTRACT = (
    "ok", "broken", "unreachable", "blocked", "no_contract")

# Rate limiting and server trouble say nothing about our code.
_TRANSIENT_CODES = {408, 425, 429, 500, 502, 503, 504}
# The door is shut to anonymous requests. 999 is LinkedIn's own way of saying so.
_BLOCKED_CODES = {401, 403, 451, 999}
_LOGIN_WALL_MARKERS = ("authwall", "/login", "/uas/login", "/checkpoint/")


class Unreachable(Exception):
    """The source could not be asked today."""


class Blocked(Exception):
    """The source refuses anonymous requests."""


class ContractRun:
    """What a fetcher's contract() is handed: an HTTP getter that sorts
    failures into unreachable/blocked, and a place to record expectations.

    `expect` is a fact the fetcher depends on — one false expectation makes
    the source broken. `note` is a fact worth seeing that the fetcher does not
    depend on."""

    def __init__(self, source: str, timeout: int = common.DEFAULT_TIMEOUT,
                 pause: float = 1.5, getter: Optional[Callable] = None):
        self.source = source
        self.timeout = timeout
        self.pause = pause
        self.checks: List[dict] = []
        self.notes: List[dict] = []
        self.requests = 0
        self._getter = getter

    def get(self, url: str) -> str:
        if self.requests:
            time.sleep(self.pause)
        self.requests += 1
        if self._getter is not None:
            return self._getter(url)
        import requests

        user_agent = common.USER_AGENT or common._build_user_agent("", {})
        try:
            resp = requests.get(url, headers={"User-Agent": user_agent}, timeout=self.timeout)
        except requests.RequestException as exc:
            raise Unreachable(f"{type(exc).__name__} on {url}") from exc
        if resp.status_code in _TRANSIENT_CODES:
            raise Unreachable(f"HTTP {resp.status_code} on {url}")
        if resp.status_code in _BLOCKED_CODES:
            raise Blocked(f"HTTP {resp.status_code} on {url}")
        final_url = str(getattr(resp, "url", "") or "")
        if any(marker in final_url for marker in _LOGIN_WALL_MARKERS):
            raise Blocked(f"redirected to a login wall: {final_url}")
        if resp.status_code >= 400:
            # Any other 4xx: the endpoint moved or the request shape is wrong —
            # that is the fetcher's to fix.
            self.expect("endpoint answers", False, f"HTTP {resp.status_code} on {url}")
            return ""
        return resp.text

    def expect(self, name: str, ok: bool, detail: str = "") -> bool:
        self.checks.append({"name": name, "ok": bool(ok), "detail": detail})
        return bool(ok)

    def note(self, name: str, detail: str) -> None:
        self.notes.append({"name": name, "detail": detail})


def fetcher_modules() -> Dict[str, str]:
    """source name -> fetcher module, from the pipeline's own registry, so a
    new source cannot be wired in without also being visible here."""
    import pipeline

    return {name: fn.__module__ for name, fn in pipeline.FETCHERS.items()}


def contract_of(source: str):
    module_name = fetcher_modules().get(source)
    if module_name is None:
        raise KeyError(f"unknown source '{source}'")
    return getattr(importlib.import_module(module_name), "contract", None)


def check_source(source: str, timeout: int = common.DEFAULT_TIMEOUT,
                 getter: Optional[Callable] = None, pause: float = 1.5) -> dict:
    """Runs one source's contract. Never raises."""
    started = time.monotonic()
    result = {"source": source, "status": NO_CONTRACT, "checks": [], "notes": [],
              "detail": "", "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        contract = contract_of(source)
    except KeyError as exc:
        result.update(status=BROKEN, detail=str(exc))
        return result
    if contract is None:
        result["detail"] = "the fetcher defines no contract() yet"
        return result

    run = ContractRun(source, timeout=timeout, pause=pause, getter=getter)
    try:
        contract(run)
    except Unreachable as exc:
        result.update(status=UNREACHABLE, detail=str(exc))
    except Blocked as exc:
        result.update(status=BLOCKED, detail=str(exc))
    except Exception as exc:  # noqa: BLE001 — a contract that crashes is a broken one
        result.update(status=BROKEN, detail=f"the contract crashed: {type(exc).__name__}: {exc}")
    else:
        failed = [c for c in run.checks if not c["ok"]]
        if not run.checks:
            result.update(status=BROKEN, detail="the contract checked nothing")
        elif failed:
            result.update(status=BROKEN, detail="; ".join(
                f"{c['name']}: {c['detail']}" if c["detail"] else c["name"] for c in failed))
        else:
            result["status"] = OK
    result["checks"] = run.checks
    result["notes"] = run.notes
    result["requests"] = run.requests
    result["seconds"] = round(time.monotonic() - started, 1)
    return result


def sources_with_contracts() -> List[str]:
    return [name for name in fetcher_modules() if contract_of(name) is not None]


def enabled_sources() -> List[str]:
    """The active identity's enabled sources, in its own order."""
    return [s.get("name") for s in common.load_sources()
            if s.get("enabled", True) and s.get("kind") != "manual_ingest"
            and s.get("name") in fetcher_modules()]


def format_result(result: dict) -> str:
    mark = {OK: "ok", BROKEN: "BROKEN", UNREACHABLE: "unreachable",
            BLOCKED: "BLOCKED", NO_CONTRACT: "-"}[result["status"]]
    line = f"[{mark}] {result['source']}"
    if result["status"] == NO_CONTRACT:
        return line + " — no contract yet"
    if result.get("detail"):
        line += f" — {result['detail']}"
    lines = [line]
    for check in result.get("checks", []):
        lines.append(f"      {'+' if check['ok'] else 'x'} {check['name']}"
                     + (f": {check['detail']}" if check["detail"] else ""))
    for note in result.get("notes", []):
        lines.append(f"      · {note['name']}: {note['detail']}")
    if result["status"] == BROKEN:
        lines.append(f"      -> the fetcher needs fixing: /source-doctor {result['source']}")
    elif result["status"] == BLOCKED:
        lines.append("      -> the source refuses anonymous requests; tell the owner")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check live that sources still answer "
                                                 "the way their fetchers expect")
    parser.add_argument("--source", action="append",
                        help="a source name (repeatable); default: every source with a contract")
    parser.add_argument("--identity", help="check the sources this identity has enabled")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    if args.identity:
        import identity as identity_mod

        identity_mod.activate_or_exit(args.identity)
    if args.source:
        names = args.source
    elif args.identity:
        names = [n for n in enabled_sources() if contract_of(n) is not None]
    else:
        names = sources_with_contracts()

    results = [check_source(name) for name in names]
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=1))
    else:
        for result in results:
            print(format_result(result))
        if not results:
            print("no source with a contract to check")
    sys.exit(1 if any(r["status"] in (BROKEN, BLOCKED) for r in results) else 0)


if __name__ == "__main__":
    main()
