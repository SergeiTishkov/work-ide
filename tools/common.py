"""
Shared utilities for every Work IDE script.

No search or scoring logic lives here — only the boring infrastructure: paths,
reading and writing JSON and YAML, safe file writes, text normalisation, id
hashing.

THE KEY POINT: the paths to configuration and data DEPEND ON THE ACTIVE
IDENTITY, and are None until `activate_identity()` is called. That is
deliberate: the system serves different people, and trying to read or write
data without an explicitly chosen identity is an error rather than a reason to
pick "some" paths (constitution, rule zero).

Why module-level variables are rebound instead of a context object: nowhere in
the project reads these constants at import time — every access goes through
`common.X` at call time. So rebinding needs no edits at ~30 call sites and does
not break monkeypatching in tests. The process is single-threaded and
single-session: one active identity per run is exactly the constraint wanted.

Compatible with Python 3.9 (standard library plus requests and PyYAML).
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Callable, List, Optional

try:
    import yaml
except ImportError:  # pragma: no cover — covered by a dedicated test
    # This message is the first thing a person sees on a fresh clone if they
    # forgot to install the dependencies. It used to be a bare
    # `ModuleNotFoundError: yaml` traceback: a project that explains every
    # one of its refusals in plain words stumbled at the very first step.
    sys.stderr.write(
        "\n  The project dependencies are not installed (PyYAML not found).\n\n"
        "  Install them:\n"
        "      python -m venv .venv\n"
        "      # Windows:       .venv\\Scripts\\activate\n"
        "      # macOS / Linux: source .venv/bin/activate\n"
        "      python -m pip install -r requirements.txt\n\n"
        "  Then run the command again. There are only three dependencies, and\n"
        "  no API keys are needed.\n\n"
    )
    raise SystemExit(1)

# --- Console output -------------------------------------------------------
# On Windows the console defaults to the system code page. It will take some
# scripts and not others: the tool died with UnicodeEncodeError while printing
# "Crédit Agricole CIB" AFTER it had successfully saved the data. The work was
# done, and the person saw a traceback and concluded nothing had been written.
#
# Company names arrive from the outside world and contain anything at all, so
# output is switched to UTF-8 with unrepresentable characters replaced.
# Replaced rather than refused: a message with a couple of question marks in
# it is more useful than no message.
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # a redirected or closed stream
            pass


# --- Repository-level paths (independent of any identity) -----------------

ROOT = Path(__file__).resolve().parent.parent
SHARED_CONFIG_DIR = ROOT / "config"  # shared machinery only, nothing personal

# Identity templates — in git, shared by everyone, not one personal fact among
# them. They are CLONED FROM, never used directly.
TEMPLATES_DIR = ROOT / "identity-templates"

# Working identities — outside git. How many there are is how many shortlists
# the system produces: there is no separate registry of active identities, and
# there must not be, because a registry can drift away from reality and
# folders cannot.
IDENTITIES_DIR = Path(
    os.environ.get("WORK_IDE_IDENTITIES") or (ROOT / "local-identities")
)

# Frozen fixtures live next to what uses them. They are discovered by the same
# scan as working identities, but they cannot be cloned and do not appear in
# the template list.
FIXTURES_DIR = ROOT / "tests" / "fixtures"

# Both are overridable by environment variable — needed for tests, and for the
# case where data lives outside the repository (on another drive, say).
DATA_ROOT = Path(os.environ.get("WORK_IDE_DATA_ROOT") or (ROOT / "data"))

# Reports deliberately live SEPARATELY from accumulated data, at the repository
# root. The reason is simple and practical: the report is the one file a person
# opens by hand, and hunting for it under data/<prefix>/reports/ is a nuisance.
# Here the latest shortlist of every identity sits side by side.
REPORTS_ROOT = Path(os.environ.get("WORK_IDE_REPORTS_ROOT") or (ROOT / "reports"))
LOCAL_CONSTITUTION_DIR = Path(
    os.environ.get("WORK_IDE_LOCAL_CONSTITUTION") or (ROOT / "local-constitution")
)

# --- Identity-level paths (None until activation) -------------------------
# NOTE: `CONFIG_DIR` is deliberately absent. It used to point at the shared
# config/; had it been kept as an alias, a forgotten call site would quietly
# read somebody else's file. Now such a site fails with AttributeError —
# loudly.

ACTIVE_IDENTITY: Optional[str] = None
IDENTITY_DIR: Optional[Path] = None
FILE_PREFIX: Optional[str] = None

DATA_DIR: Optional[Path] = None
KNOWLEDGE_DIR: Optional[Path] = None
RAW_DIR: Optional[Path] = None
REPORTS_DIR: Optional[Path] = None
REPORTS_ARCHIVE_DIR: Optional[Path] = None
STATE_PATH: Optional[Path] = None

VACANCIES_PATH: Optional[Path] = None
COMPANIES_PATH: Optional[Path] = None
RECRUITERS_PATH: Optional[Path] = None
INSIGHTS_PATH: Optional[Path] = None

USER_AGENT: Optional[str] = None

DEFAULT_TIMEOUT = 15  # a genuine constant, independent of any identity

_IDENTITY_HOOKS: List[Callable[[], None]] = []


class NoActiveIdentityError(RuntimeError):
    """An attempt to work with data with no active identity."""


class IdentityDataMismatchError(RuntimeError):
    """The data folder belongs to a different identity."""


def register_identity_hook(fn: Callable[[], None]) -> None:
    """Registers a callback invoked on every identity activation.

    Needed by modules that cache values derived from configuration: a cache
    surviving an identity switch is a leak between identities.
    """
    if fn not in _IDENTITY_HOOKS:
        _IDENTITY_HOOKS.append(fn)


def require_identity() -> None:
    """The guard for rule zero. Called before any access to config or data."""
    if ACTIVE_IDENTITY is None:
        raise NoActiveIdentityError(
            "No active search identity — working with data is not allowed "
            "(constitution, rule zero).\n"
            "  Name one: --identity <prefix>.\n"
            "  If no identity exists yet, run onboarding per docs/ONBOARDING.md."
        )


def activate_identity(prefix: str, *, allow_fixture: bool = False,
                      data_root: Optional[Path] = None,
                      reports_root: Optional[Path] = None) -> None:
    """Activates an identity: validates it and rebinds every path.

    allow_fixture — test identities (kind: fixture) deliberately cannot be
    activated during normal work, so that nobody searches for jobs against a
    fixture.

    reports_root defaults to the shared `reports/` folder at the repository
    root. IMPORTANT: when data_root is passed (an isolated run, tests), reports
    move inside it. Otherwise a test that isolated its data would still write
    reports into the real repository folder and overwrite a person's live
    shortlist.
    """
    import identity as identity_mod  # local import: identity.py imports common

    problems = identity_mod.validate(prefix)
    if problems:
        raise identity_mod.InvalidIdentityError(
            f"Identity '{prefix}' did not pass validation:\n"
            + "\n".join(f"  - {p}" for p in problems)
        )

    import settings
    raw_profile, _ = settings.resolve("profile", prefix)
    kind = (raw_profile.get("identity") or {}).get("kind")
    if kind == "fixture" and not allow_fixture:
        raise identity_mod.InvalidIdentityError(
            f"'{prefix}' is a test fixture (kind: fixture); a real search against "
            "it is not allowed. It exists purely so that the tests do not depend "
            "on which identity you happen to keep active."
        )

    profile, _ = resolve_local_fields(prefix, raw_profile)

    # Scaffolding is not yet an identity. Found for real on a fresh-clone run,
    # 2026-08-04: `identity.py new` plus `pipeline.py` ran to completion and
    # wrote a report covering 1734 vacancies — with a placeholder in the title
    # and scoring against an empty stack. Rule zero checked that an identity
    # EXISTED but not that it was FILLED IN, and the person got plausible
    # rubbish. That is exactly the quiet wrong answer this whole architecture
    # exists to prevent, so the check lives in activation rather than in a
    # separate command.
    if kind != "fixture":
        gaps = identity_mod.readiness_problems(prefix)
        if gaps:
            raise identity_mod.IdentityNotReadyError(
                f"Identity '{prefix}' is not filled in yet — searching with it "
                "would produce a plausible but meaningless result.\n"
                + "\n".join(f"  - {g}" for g in gaps)
                + "\n  How to fill it in: docs/ONBOARDING.md "
                  "(questionnaire -> profile -> criteria)."
            )

    global ACTIVE_IDENTITY, IDENTITY_DIR, FILE_PREFIX
    global DATA_DIR, KNOWLEDGE_DIR, RAW_DIR, REPORTS_DIR, REPORTS_ARCHIVE_DIR, STATE_PATH
    global VACANCIES_PATH, COMPANIES_PATH, RECRUITERS_PATH, INSIGHTS_PATH, USER_AGENT

    root = Path(data_root) if data_root else DATA_ROOT

    ACTIVE_IDENTITY = prefix
    IDENTITY_DIR = identity_mod.identity_dir(prefix)
    FILE_PREFIX = f"{prefix}_"

    DATA_DIR = root / prefix
    KNOWLEDGE_DIR = DATA_DIR / "knowledge"
    RAW_DIR = DATA_DIR / "raw"

    # REPORTS_DIR is shared by every identity: the latest shortlist of each sits
    # there, distinguished by the prefix in its name (kisel_latest.md,
    # jvst_latest.md). The archive, by contrast, is split per identity —
    # reports/archive/<prefix>/ — and inside it file names are just dates. The
    # single-prefix rule applies where files of DIFFERENT identities share a
    # folder; when the folder itself belongs to one identity, a prefix on every
    # name is redundant. The report identifies itself on its first line anyway:
    # "# Work IDE [kisel] — …".
    if reports_root is not None:
        reports_base = Path(reports_root)
    elif data_root is not None:
        reports_base = root / "reports"
    else:
        reports_base = REPORTS_ROOT
    REPORTS_DIR = reports_base
    REPORTS_ARCHIVE_DIR = reports_base / "archive" / prefix
    STATE_PATH = DATA_DIR / f"{FILE_PREFIX}state.json"

    VACANCIES_PATH = KNOWLEDGE_DIR / f"{FILE_PREFIX}vacancies.json"
    COMPANIES_PATH = KNOWLEDGE_DIR / f"{FILE_PREFIX}companies.json"
    RECRUITERS_PATH = KNOWLEDGE_DIR / f"{FILE_PREFIX}recruiters.json"
    INSIGHTS_PATH = KNOWLEDGE_DIR / f"{FILE_PREFIX}insights.md"

    USER_AGENT = _build_user_agent(prefix, profile)

    for hook in _IDENTITY_HOOKS:
        hook()


def deactivate_identity() -> None:
    """Clears the active identity. Needed by tests that check the refusal."""
    global ACTIVE_IDENTITY, IDENTITY_DIR, FILE_PREFIX
    global DATA_DIR, KNOWLEDGE_DIR, RAW_DIR, REPORTS_DIR, REPORTS_ARCHIVE_DIR, STATE_PATH
    global VACANCIES_PATH, COMPANIES_PATH, RECRUITERS_PATH, INSIGHTS_PATH, USER_AGENT

    ACTIVE_IDENTITY = IDENTITY_DIR = FILE_PREFIX = None
    DATA_DIR = KNOWLEDGE_DIR = RAW_DIR = REPORTS_DIR = REPORTS_ARCHIVE_DIR = STATE_PATH = None
    VACANCIES_PATH = COMPANIES_PATH = RECRUITERS_PATH = INSIGHTS_PATH = None
    USER_AGENT = None
    for hook in _IDENTITY_HOOKS:
        hook()


LOCAL_SENTINEL = "local"


def personal_dir(prefix: str) -> Path:
    """An identity's personal-files folder in the Local Constitution
    (outside git)."""
    return LOCAL_CONSTITUTION_DIR / "personal" / prefix


def load_local_overlay(prefix: str) -> dict:
    """The personal part of a profile: what must not reach the shared repository.

    A missing file is not an error in itself: a profile may not use the `local`
    sentinel at all. It becomes an error only if the profile does reference it,
    and then resolve_local_fields() says so.
    """
    overlay = {}
    path = personal_dir(prefix) / f"{prefix}_owner.yaml"
    if path.exists():
        overlay = load_yaml(path) or {}

    # The contact has historically lived in its own file — it predates the
    # general overlay. Left as it is: the Local Constitution's layout is
    # documented in docs/LOCAL_CONSTITUTION.md, and breaking it for the sake of
    # uniformity would buy nothing.
    contact_path = personal_dir(prefix) / f"{prefix}_contact.yaml"
    if contact_path.exists():
        contact_cfg = load_yaml(contact_path) or {}
        value = (contact_cfg.get("user_agent_contact") or "").strip()
        if value:
            overlay.setdefault("contact", {}).setdefault("user_agent_contact", value)

    return overlay


def _walk_local_sentinels(node, path=""):
    """Every path to a value equal to `local`, as 'owner.name'."""
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}" if path else str(key)
            if isinstance(value, str) and value.strip() == LOCAL_SENTINEL:
                yield child
            else:
                for found in _walk_local_sentinels(value, child):
                    yield found


def _dig(data: dict, dotted: str):
    node = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None, False
        node = node[part]
    return node, True


def _plant(data: dict, dotted: str, value) -> None:
    parts = dotted.split(".")
    node = data
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def resolve_local_fields(prefix: str, profile: dict):
    """Merges personal data from the Local Constitution into an identity profile.

    WHY. An identity describes a SEARCH: stack, working arrangement, the marks
    of a suitable company. A person's name, their LinkedIn, residency, CV and
    pay expectations are no part of describing a search and must not reach the
    shared repository — otherwise everyone who clones the project gets the
    author's personal file.

    The mechanism is not new: the `local` sentinel was already used for the
    User-Agent contact. Here it is generalised to any profile field — the
    identity file holds `local`, and the real value lives in
    `local-constitution/personal/<prefix>/<prefix>_owner.yaml`.

    Returns (profile_with_values_substituted, list_of_what_is_missing). The
    profile is not mutated: the caller may have their own copy.
    """
    import copy

    merged = copy.deepcopy(profile)
    overlay = load_local_overlay(prefix)
    missing = []

    for dotted in list(_walk_local_sentinels(profile)):
        value, found = _dig(overlay, dotted)
        if found and value not in (None, "", []):
            _plant(merged, dotted, value)
        else:
            missing.append(dotted)

    return merged, missing


def load_profile(prefix: Optional[str] = None) -> dict:
    """The active identity's profile with personal data merged in.

    The single place a profile is read — otherwise some code would see the
    `local` sentinel instead of the real value and quietly treat it as a
    string.
    """
    import identity as identity_mod

    if prefix is None:
        require_identity()
        prefix = ACTIVE_IDENTITY
    # A profile is ASSEMBLED FROM LAYERS: the template copy supplies the kind of
    # search, the personal file beside it supplies the person's circumstances.
    # Reading a single file will not do: the template has no residency, and the
    # personal file has no stack.
    import settings

    raw, _ = settings.resolve("profile", prefix)
    merged, _ = resolve_local_fields(prefix, raw)
    return merged


def _build_user_agent(prefix: str, profile: dict) -> str:
    """An honest User-Agent carrying a contact — an engineering commitment of
    the project (see the constitution, on politeness towards other people's
    servers).

    The contact arrives already resolved (see resolve_local_fields): the
    identity file holds `local`, the value lives in the Local Constitution.
    """
    contact = ((profile.get("contact") or {}).get("user_agent_contact") or "").strip()
    if contact == LOCAL_SENTINEL:
        contact = ""  # no overlay — run without a contact; doctor will warn

    if contact:
        return (
            "Mozilla/5.0 (compatible; WorkIdeJobResearchBot/1.0; "
            f"contact: {contact}; purpose: personal job search research)"
        )
    return (
        "Mozilla/5.0 (compatible; WorkIdeJobResearchBot/1.0; "
        "purpose: personal job search research)"
    )


def identity_config(name: str) -> Path:
    """Path to an identity document, for reading it whole.

    A document may sit in two places: the personal file at the folder root, or
    the template copy in `template/`. The personal one is returned if present,
    otherwise the template one.

    For documents ASSEMBLED FROM LAYERS (profile, criteria) that is not enough
    — those need settings.resolve(), because the personal file holds only
    differences. This path is for callers who read a document whole and
    unlayered: sources and ATS targets, for instance.
    """
    require_identity()
    own = IDENTITY_DIR / f"{FILE_PREFIX}{name}"
    if own.exists():
        return own
    from_template = IDENTITY_DIR / "template" / f"{FILE_PREFIX}{name}"
    return from_template if from_template.exists() else own


def shared_config(name: str) -> Path:
    """'sources.catalog.yaml' -> config/sources.catalog.yaml (shared machinery)."""
    return SHARED_CONFIG_DIR / name


def load_sources() -> list:
    """The single place the whole project reads source configuration from.

    Merges the shared source catalogue (endpoints, kind, remote_only,
    documentation — identical for everyone) with the active identity's
    settings (which sources are enabled, and with what parameters). An identity
    cannot override an endpoint: a stale URL is a bug for everybody rather than
    somebody's preference.

    If the catalogue does not exist yet, the identity file is read as
    self-contained — a transitional state, see docs/BUILDING_BLOCKS.md.
    """
    require_identity()
    identity_cfg = load_yaml(identity_config("sources.yaml")) or {}
    identity_sources = identity_cfg.get("sources") or []

    catalog_path = shared_config("sources.catalog.yaml")
    if not catalog_path.exists():
        return identity_sources

    catalog = load_yaml(catalog_path) or {}
    catalog_by_name = {s["name"]: s for s in (catalog.get("sources") or []) if s.get("name")}

    merged = []
    for entry in identity_sources:
        name = entry.get("name")
        if not name:
            continue
        base = catalog_by_name.get(name)
        if base is None:
            raise ValueError(
                f"Identity '{ACTIVE_IDENTITY}' references the unknown source "
                f"'{name}'. Known sources: {', '.join(sorted(catalog_by_name))}. "
                f"Either a typo in {identity_config('sources.yaml').name}, or the "
                "source needs adding to config/sources.catalog.yaml."
            )
        merged.append({**base, **entry})
    return merged


def ensure_dirs() -> None:
    require_identity()
    for d in (DATA_DIR, KNOWLEDGE_DIR, RAW_DIR, REPORTS_DIR, REPORTS_ARCHIVE_DIR):
        d.mkdir(parents=True, exist_ok=True)
    _ensure_identity_marker()


def _ensure_identity_marker() -> None:
    """Writes data/<prefix>/.identity and checks it on every run.

    Protection against "the data folder was renamed or moved by hand": the
    paths look right and somebody else's database sits inside. The mistake is
    quiet and expensive; the check is cheap.
    """
    marker = DATA_DIR / ".identity"
    if marker.exists():
        recorded = marker.read_text(encoding="utf-8").strip()
        if recorded and recorded != ACTIVE_IDENTITY:
            raise IdentityDataMismatchError(
                f"The data folder {DATA_DIR} belongs to identity '{recorded}', "
                f"but '{ACTIVE_IDENTITY}' is active. Nothing was touched. "
                "Sort this out by hand before continuing."
            )
    else:
        marker.write_text(f"{ACTIVE_IDENTITY}\n", encoding="utf-8")


# --- IO helpers ---------------------------------------------------------

def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def write_yaml(path: Path, data: dict) -> None:
    """Writes human-readable YAML.

    Used only for files the project generates itself (`local-constitution/
    active.yaml`, for one). Identity configs are edited by a person — rewriting
    them would erase the comments, and there the comments carry half the
    meaning.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()
        if not content:
            return default
        return json.loads(content)


def save_json_atomic(path: Path, data: Any) -> None:
    """Writes JSON atomically (temporary file plus rename), so that a crash
    mid-write can never leave the knowledge base in a broken state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")
    tmp.replace(path)


def append_jsonl(path: Path, records: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# --- Text ----------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_MULTI_WS_RE = re.compile(r"[ \t\r\f\v]+")
_MULTI_NL_RE = re.compile(r"\n{3,}")
_BLOCK_BREAK_RE = re.compile(
    r"</?(?:p|br|li|ul|ol|div|h[1-6]|tr)\b[^>]*>", re.IGNORECASE
)


def strip_html(raw: Optional[str]) -> str:
    """A crude but dependable HTML -> readable text converter, with no external
    dependency such as bs4 or lxml. For keyword scoring and reports,
    reliability matters more than perfect rendering."""
    if not raw:
        return ""
    text = _BLOCK_BREAK_RE.sub("\n", raw)
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = _MULTI_WS_RE.sub(" ", text)
    lines = [ln.strip() for ln in text.split("\n")]
    text = "\n".join(ln for ln in lines if ln)
    text = _MULTI_NL_RE.sub("\n\n", text)
    return text.strip()


def normalize_for_matching(text: Optional[str]) -> str:
    """Normalisation for keyword matching: lowercase, unicode NFKC, collapsed
    whitespace. Punctuation is kept — it matters for "c#" and "asp.net"."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.lower()
    text = _MULTI_WS_RE.sub(" ", text)
    return text.strip()


def normalize_company_name(name: Optional[str]) -> str:
    if not name:
        return "unknown-company"
    n = normalize_for_matching(name)
    n = re.sub(r"[^\w\s-]", "", n, flags=re.UNICODE)
    n = re.sub(r"\s+", "-", n).strip("-")
    return n or "unknown-company"


def truncate(text: str, limit: int = 6000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + " …[truncated]"


def stable_id(*parts: str) -> str:
    joined = "||".join(p or "" for p in parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:20]


def eprint(*args, **kwargs) -> None:
    print(*args, file=sys.stderr, **kwargs)
