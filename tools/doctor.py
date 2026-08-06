"""
Environment self-check. Run it after cloning the repository on a new machine,
or when the pipeline behaves strangely.

python tools/doctor.py --identity <prefix>

Exit code 0 when every CRITICAL check passes: identity, Python version,
dependencies, configuration, writability of data/. Reachability of external
sources is a warning rather than a fatal error — the network may simply be
down right now, which is no reason to call the environment broken.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

CRITICAL_OK = True


def _report(label: str, ok: bool, detail: str = "", critical: bool = True) -> None:
    global CRITICAL_OK
    status = "OK  " if ok else ("FAIL" if critical else "WARN")
    print(f"[{status}] {label}" + (f" — {detail}" if detail else ""))
    if critical and not ok:
        CRITICAL_OK = False


def check_python() -> None:
    ok = sys.version_info >= (3, 8)
    _report("Python >= 3.8", ok, f"current: {sys.version.split()[0]}")


def check_packages() -> None:
    for mod in ("requests", "yaml"):
        try:
            __import__(mod)
            _report(f"package '{mod}'", True)
        except ImportError as exc:
            _report(f"package '{mod}'", False, str(exc))


def check_identity() -> None:
    """The first and most important check: is there an active identity, and is
    it intact."""
    import identity as identity_mod

    _report(f"active identity: {identity_mod.describe(common.ACTIVE_IDENTITY)}", True)
    problems = identity_mod.validate(common.ACTIVE_IDENTITY)
    if problems:
        for p in problems:
            _report("identity structure", False, p)
    else:
        _report("identity structure", True)


def check_configs() -> dict:
    """Required keys must be present in the RESOLVED settings, not in one file.

    This used to read a single file per document and report missing keys. Once
    identities became a template copy plus a personal overlay, that check
    started failing on a perfectly healthy setup: the personal file holds only
    differences, so it has no tech_stack, and the template has no residency.
    Found 2026-08-06 while translating this file — two red FAIL lines against a
    configuration that was entirely correct, which is worse than no check at
    all, because a person learns to ignore them.
    """
    import settings

    configs = {}
    for name, required_keys in (
        ("profile.yaml", ["owner", "goal", "tech_stack", "employment_type_priority"]),
        # `weights` deliberately absent: the block was removed on 2026-08-05
        # because no line of code ever read it. The real weights are the caps of
        # each component (see the header of the criteria file).
        ("criteria.yaml", ["remote_location_fit", "classification_thresholds"]),
        ("sources.yaml", ["sources"]),
    ):
        document = name.rsplit(".", 1)[0]
        label = f"{common.ACTIVE_IDENTITY}: {name}"
        try:
            if document in ("profile", "criteria"):
                data, _ = settings.resolve(document, common.ACTIVE_IDENTITY)
            else:
                data = common.load_yaml(common.identity_config(name)) or {}
            missing = [k for k in required_keys if k not in data]
            _report(label, not missing, f"missing keys: {missing}" if missing else "")
            configs[name] = data
        except Exception as exc:  # noqa: BLE001
            _report(label, False, str(exc))
            configs[name] = {}
    return configs


def check_data_writable() -> None:
    try:
        common.ensure_dirs()
        probe = common.DATA_DIR / ".doctor_probe.tmp"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        _report("data/ is writable", True)
    except Exception as exc:  # noqa: BLE001
        _report("data/ is writable", False, str(exc))


def check_sources_reachable() -> None:
    import requests

    for src in common.load_sources():
        if not src.get("enabled", True) or src.get("kind") == "manual_ingest":
            continue
        url = src.get("url") or (src.get("urls") or [None])[0]
        if not url:
            continue
        try:
            resp = requests.get(
                url, headers={"User-Agent": common.USER_AGENT}, timeout=8, stream=True
            )
            ok = resp.status_code < 400
            _report(f"source '{src['name']}' reachable", ok, f"HTTP {resp.status_code}", critical=False)
        except Exception as exc:  # noqa: BLE001
            _report(f"source '{src['name']}' reachable", False, str(exc), critical=False)


def check_reputation_coverage() -> None:
    """How many companies at the head of the shortlist have no reputation result.

    Not critical for running: this is about the completeness of accumulated
    knowledge rather than the health of the environment. But the number is
    worth seeing — on 2026-08-06 the head of the shortlist held 55 companies
    and zero checks, and the only way to notice was to read the whole report.
    """
    import kb
    import reputation

    try:
        vacancies = kb.load_vacancies()
        companies = kb.load_companies()
    except Exception as exc:  # noqa: BLE001 — the database may not exist yet
        print(f"  [ SKIP ] company reputation: database unreadable "
              f"({type(exc).__name__})")
        return

    stats = reputation.coverage(vacancies, companies)
    if not stats["companies"]:
        print("  [ SKIP ] company reputation: nobody in the shortlist to check yet")
        return
    mark = "OK  " if not stats["unchecked"] else "WARN"
    print(f"  [ {mark} ] reputation of shortlist companies: "
          f"found {stats['found']}, too few sources {stats['insufficient']}, "
          f"NOT CHECKED {stats['unchecked']} of {stats['companies']}")
    if stats["unchecked"]:
        print("           close it: python tools/reputation.py worklist "
              f"--identity {common.ACTIVE_IDENTITY}")


def main() -> None:
    import identity as identity_mod

    parser = argparse.ArgumentParser(description="Work IDE environment self-check")
    parser.add_argument("--identity", default=None, help="Search identity prefix")
    args = parser.parse_args()

    try:
        identity_mod.activate(args.identity)
    except (identity_mod.IdentityError, common.NoActiveIdentityError) as exc:
        print("=== Work IDE: self-check ===\n")
        print(f"[FAIL] {exc}")
        sys.exit(1)

    print("=== Work IDE: self-check ===")
    print(identity_mod.banner(), "\n")
    check_identity()
    check_python()
    check_packages()
    check_configs()
    check_data_writable()
    check_reputation_coverage()
    print()
    print("--- Source reachability (not critical for operation) ---")
    check_sources_reachable()
    print()
    if CRITICAL_OK:
        print(
            "Result: the environment is sound; you can run "
            f"python tools/pipeline.py --identity {common.ACTIVE_IDENTITY}"
        )
        sys.exit(0)
    else:
        print("Result: there are critical problems; see the FAIL lines above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
