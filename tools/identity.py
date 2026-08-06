"""
Search identities: registry, validation, resolving the active one.

WHY THIS EXISTS
---------------
The project serves different people with different search profiles. Mixing
their data is the worst failure available to it: silent, invisible in the
report, and systematically wrong. So "which identity is active" is not a
convenience setting but a required state, without which the system refuses
to work at all (constitution, rule zero).

WHAT AN IDENTITY IS
-------------------
A folder under `local-identities/` in which EVERY file starts with the same
prefix. The prefix is a short, pronounceable Latin abbreviation that says
what the search is about (`kisel` = Keep It Simple, Easy, Legacy). Uniform
prefixing is not cosmetic: an agent will eventually confuse two files named
`notes.md` in different folders; it will practically never confuse
`kisel_notes.md` with `jvst_notes.md`.

WHERE "WHICH IDENTITY IS MINE" LIVES
------------------------------------
In the folders themselves. There is no registry file listing active
identities, deliberately: a list can drift away from what is on disk, and
folders cannot. Templates to clone from live in `identity-templates/`.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

# Prefix: 3-6 lowercase Latin letters or digits, starting with a letter.
# Short, so file names stay readable; lowercase, so nothing depends on the
# case-insensitivity of the Windows file system.
PREFIX_RE = re.compile(r"^[a-z][a-z0-9]{2,5}$")

PREFIX_RULE_TEXT = (
    "Identity prefix: 3-6 characters, lowercase Latin letters and digits only, "
    "first character a letter. It should be pronounceable and should describe "
    "what the search is about (for example: kisel = Keep It Simple, Easy, "
    "Legacy)."
)

# Identity folder name: <prefix>-<expansion-with-hyphens>, for example
# `kisel-keep-it-simple-easy-legacy`.
#
# WHY TWO LEVELS OF NAMING. A folder is seen rarely, but when it is, `kisel`
# alone gives no way to remember what that search was or why it was set up.
# The expansion in the folder name answers that without opening a file.
#
# The FILES inside stay short (`kisel_criteria.yaml`, not
# `kisel-keep-it-simple-easy-legacy_criteria.yaml`): their names appear in
# every command, in grep output, in editor tabs and in paths inside reports,
# where a long name only makes reading harder.
FOLDER_RE = re.compile(r"^([a-z][a-z0-9]{2,5})(-[a-z0-9]+(?:-[a-z0-9]+)*)?$")

FOLDER_RULE_TEXT = (
    "Identity folder name: <prefix>-<expansion with hyphens>, lowercase Latin "
    "letters, digits and hyphens only (for example: "
    "kisel-keep-it-simple-easy-legacy). The expansion explains what the search "
    "is; files inside stay short and start with the prefix alone."
)

# Files without which an identity is incomplete. Order is check order.
REQUIRED_FILES = (
    "identity.md",        # human-readable: what this is, for whom, how it works
    "profile.yaml",       # who the identity belongs to and what they seek
    "criteria.yaml",      # the scoring rubric
    "sources.yaml",       # which sources are enabled, and with what parameters
    "questionnaire.yaml",  # the filled-in questionnaire: the identity's origin story
)

# Folders that are not identities.
NON_IDENTITY_DIRS = {"__pycache__"}

# Housekeeping names inside a local identity. The single-prefix rule does not
# apply to them: they are identical across every identity and therefore
# cannot be confused with one another, which is the only thing that rule
# protects against.
KNOWN_SUBDIRS = {
    "template",    # verbatim copy of the template; never edited
    "documents",   # personal files (CVs and the like) under their own names
    "__pycache__",
}
KNOWN_FILES = {
    "identity.yaml",   # which template, which version
    "CHANGELOG.md",    # this identity's change log
}


class IdentityError(RuntimeError):
    """Base error of the identity system."""


class UnknownIdentityError(IdentityError):
    pass


class InvalidIdentityError(IdentityError):
    pass


class IdentityNotReadyError(IdentityError):
    """Structurally complete, but not yet filled in with the person's answers.

    A separate class rather than InvalidIdentityError: this is not damage but
    a normal stage of onboarding, and it should read as "here is what is left
    to fill in" rather than "something is broken".
    """


# --- Registry -------------------------------------------------------------

def folder_prefix(folder_name: str) -> Optional[str]:
    """'kisel-keep-it-simple-easy-legacy' -> 'kisel'. None if the name does not fit."""
    m = FOLDER_RE.match(folder_name)
    return m.group(1) if m else None


def identity_folders() -> dict:
    """Prefix -> folder. The only place that knows a folder name is longer than
    a prefix; everything else works with prefixes."""
    result = {}
    roots = [common.IDENTITIES_DIR, common.FIXTURES_DIR]
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.iterdir()):
            if not path.is_dir() or path.name.startswith("_") or path.name in NON_IDENTITY_DIRS:
                continue
            prefix = folder_prefix(path.name)
            if prefix is None:
                continue  # stray content: validate_layout() will report it
            if prefix in result:
                # Two folders with one prefix is an unresolvable ambiguity:
                # nothing can say which is "the" one, and silently picking
                # either would mix the two sets of data.
                raise InvalidIdentityError(
                    f"two folders share the prefix '{prefix}': "
                    f"{result[prefix].name} and {path.name}. A prefix must be "
                    "unique — rename one of them."
                )
            result[prefix] = path
    return result


def list_identities(include_fixtures: bool = False) -> List[str]:
    """Prefixes of every identity found. Folders starting with "_" are not
    identities — they are scaffolding."""
    found = []
    for prefix in identity_folders():
        if not include_fixtures and _read_kind(prefix) == "fixture":
            continue
        found.append(prefix)
    return found


def identity_dir(prefix: str) -> Path:
    """An identity's folder, by prefix.

    If the folder does not exist yet — it is about to be created — the path
    comes back without an expansion: only whoever creates the identity knows
    the expanded name, and they pass it explicitly.
    """
    folder = identity_folders().get(prefix)
    return folder if folder is not None else common.IDENTITIES_DIR / prefix


def identity_file(prefix: str, name: str) -> Path:
    """Path to an identity document, for READING.

    A document may sit in two places: at the folder root (personal settings)
    or in `template/` (the verbatim copy taken at clone time). Reading
    prefers the personal one and falls back to the template — which is what
    code needing a whole single file expects (validation, readiness, layout
    reporting).

    The fully layered value comes from settings.resolve(): the personal file
    holds differences only and must not be read as an entire profile.
    """
    folder = identity_dir(prefix)
    own = folder / f"{prefix}_{name}"
    if own.exists():
        return own
    from_template = folder / "template" / f"{prefix}_{name}"
    return from_template if from_template.exists() else own


def _read_kind(prefix: str) -> Optional[str]:
    """An identity's kind without activating it: personal | shared_example | fixture."""
    profile_path = identity_file(prefix, "profile.yaml")
    if not profile_path.exists():
        return None
    try:
        data = common.load_yaml(profile_path) or {}
        return (data.get("identity") or {}).get("kind")
    except Exception:  # noqa: BLE001 - broken YAML is validate()'s problem
        return None


def describe(prefix: str) -> str:
    """A short line for banners and error messages."""
    try:
        data = common.load_yaml(identity_file(prefix, "profile.yaml")) or {}
        meta = data.get("identity") or {}
        name = meta.get("display_name") or meta.get("name") or ""
        return f"{prefix} — {name}" if name else prefix
    except Exception:  # noqa: BLE001
        return prefix


# --- Validation -----------------------------------------------------------

def validate(prefix: str, *, strict_prefix_check: bool = True) -> List[str]:
    """Returns a list of problems; empty means the identity is sound.

    It checks exactly what protects against confusing one identity with
    another: prefix format, the presence of required files, prefixing of ALL
    files inside the folder, and the absence of references to other prefixes
    in their contents.
    """
    problems: List[str] = []

    if not PREFIX_RE.match(prefix):
        problems.append(f"invalid prefix format '{prefix}'. {PREFIX_RULE_TEXT}")
        return problems  # nothing further is worth checking

    d = identity_dir(prefix)
    if not d.is_dir():
        problems.append(f"identity folder not found: {d}")
        return problems

    # A folder name must carry an expansion: `kisel` says nothing, while
    # `kisel-keep-it-simple-easy-legacy` explains what the search is right in
    # the project tree. This is the one place a long name belongs.
    if folder_prefix(d.name) == d.name:
        problems.append(
            f"folder '{d.name}' is named by the prefix alone, with no "
            f"expansion. {FOLDER_RULE_TEXT}"
        )

    for name in REQUIRED_FILES:
        path = identity_file(prefix, name)
        if not path.exists():
            problems.append(f"required file missing: {path.name} (expected in {d})")

    if strict_prefix_check:
        for path in sorted(d.iterdir()):
            if path.is_dir():
                if path.name in KNOWN_SUBDIRS:
                    continue
                problems.append(
                    f"nested folder '{path.name}' inside an identity is not "
                    f"supported. Allowed: {', '.join(sorted(KNOWN_SUBDIRS))}"
                )
                continue
            if path.name in KNOWN_FILES:
                continue
            if not path.name.startswith(f"{prefix}_"):
                problems.append(
                    f"file '{path.name}' does not start with '{prefix}_' — the "
                    "single-prefix rule is broken, and that rule is the thing "
                    "protecting against mixing identities up"
                )

    problems.extend(_check_foreign_prefix_leaks(prefix))
    return problems


# The opening of the message about unfilled PERSONAL fields. Kept as a
# constant so that tests and calling code can tell "personal data is missing"
# — a normal stage on someone else's machine — from "the identity is
# assembled incompletely", which is a defect, without depending on the exact
# wording.
LOCAL_FIELDS_MISSING_PREFIX = "personal fields are not filled in"

# A template placeholder: `<something>` in angle brackets. That is exactly how
# fields awaiting the person's answers are marked.
PLACEHOLDER_RE = re.compile(r"<[^<>\n]{2,80}>")

# Profile fields without which a search is meaningless. The list is
# deliberately short: not "everything worth filling in" but "without this,
# scoring produces garbage".
REQUIRED_PROFILE_FIELDS = (
    ("owner.languages", "languages — the language filter is derived from them"),
    ("owner.location", "residency — the geography rules are derived from it"),
    ("tech_stack.core",
     "the core stack — without it the relevance gate lets everything through"),
)


def readiness_problems(prefix: str) -> List[str]:
    """What is missing before this identity can be used for a search.

    Distinct from validate(): that checks STRUCTURE — files present, prefixes
    correct — while this checks CONTENT, meaning the person answered the
    required questions. Fresh scaffolding is structurally flawless and
    completely unusable.
    """
    problems: List[str] = []
    d = identity_dir(prefix)
    if not d.is_dir():
        return [f"identity folder not found: {d}"]

    # The profile is assembled FROM LAYERS: the template copy supplies the type
    # of search, the personal file beside it supplies the person's
    # circumstances. Checking one file is pointless — the template has no
    # residency by design, and the personal file has no stack.
    import settings

    profile, _ = settings.resolve("profile", prefix)
    profile, missing_local = common.resolve_local_fields(prefix, profile)

    if missing_local:
        # One line rather than one per field: on a fresh clone there are seven
        # of them, and seven identical sentences repeating the same path read
        # as a wall of text instead of a clear task.
        overlay_path = common.personal_dir(prefix) / f"{prefix}_owner.yaml"
        problems.append(
            f"{LOCAL_FIELDS_MISSING_PREFIX} (marked `local`): "
            + ", ".join(missing_local)
            + f".\n    They belong in {overlay_path}"
            + "\n    Scaffold that file with `python tools/identity.py "
            f"init-local --identity {prefix}`"
        )

    for dotted, why in REQUIRED_PROFILE_FIELDS:
        node = profile
        for part in dotted.split("."):
            node = (node or {}).get(part) if isinstance(node, dict) else None
        if not node:
            problems.append(f"{dotted} is not filled in ({why})")

    # Template placeholders in the VALUES of the identity's YAML files.
    #
    # In the values, not in the file text: angle brackets appear constantly in
    # comments as part of the documentation ("put <token> here", "<TZ> ±N
    # hours"). The first version of this check read the whole file and
    # declared a filled-in identity unfilled. A YAML parser discards comments,
    # which is all it takes to make the check exact.
    for path in sorted(d.glob("*.yaml")):
        try:
            data = common.load_yaml(path)
        except Exception:  # noqa: BLE001 — broken YAML is validate()'s problem
            continue
        found = sorted(set(_placeholders_in_values(data)))
        if found:
            shown = ", ".join(found[:3]) + (" ..." if len(found) > 3 else "")
            problems.append(f"{path.name}: placeholders left unfilled ({shown})")

    return problems


def _placeholders_in_values(node):
    """Every template placeholder among the string VALUES of a structure."""
    if isinstance(node, str):
        for found in PLACEHOLDER_RE.findall(node):
            yield found
    elif isinstance(node, dict):
        for value in node.values():
            for found in _placeholders_in_values(value):
                yield found
    elif isinstance(node, list):
        for item in node:
            for found in _placeholders_in_values(item):
                yield found


def _check_foreign_prefix_leaks(prefix: str) -> List[str]:
    """Looks for mentions of OTHER identities' prefixes, of the form `abcd_`.

    Catches the likeliest mistake when creating a new identity: copy-paste
    from someone else's folder with the paths only half corrected.
    """
    problems: List[str] = []
    others = [p for p in list_identities(include_fixtures=True) if p != prefix]
    if not others:
        return problems

    d = identity_dir(prefix)
    for path in sorted(d.glob("*")):
        if path.is_dir():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # a binary or unreadable file is not our business
        for other in others:
            token = f"{other}_"
            if token in text:
                problems.append(
                    f"file {path.name} mentions the foreign prefix '{token}' — "
                    f"this looks like copy-paste from identity '{other}'"
                )
    return problems


def validate_all() -> dict:
    """Runs validate() over every identity, fixtures included."""
    return {p: validate(p) for p in list_identities(include_fixtures=True)}


# --- Legacy local-constitution support -------------------------------------

def local_constitution_path() -> Path:
    return common.LOCAL_CONSTITUTION_DIR / "active.yaml"


def load_local_constitution() -> dict:
    """Reads the legacy local-constitution/active.yaml, if one still exists.

    Its absence is not an error: that is the normal state of a machine where
    onboarding has not been run, and of every machine created after the layer
    was retired (docs/LOCAL_CONSTITUTION.md)."""
    path = local_constitution_path()
    if not path.exists():
        return {}
    return common.load_yaml(path) or {}


def active_identities() -> List[str]:
    cfg = load_local_constitution()
    entries = cfg.get("active_identities") or []
    result = []
    for e in entries:
        prefix = e.get("prefix") if isinstance(e, dict) else e
        if prefix:
            result.append(prefix)
    return result


def default_identity() -> Optional[str]:
    return (load_local_constitution() or {}).get("default_identity")


# --- Resolving the active identity ----------------------------------------

def resolve_identity(cli_value: Optional[str] = None) -> str:
    """A strict order of precedence, with no built-in default:

      1. --identity <prefix>     (an explicit intent always wins)
      2. WORK_IDE_IDENTITY       (subprocesses, CI, tests)
      3. the only folder in local-identities/
      4. refusal

    There is deliberately no registry of active identities: a file listing
    them can drift away from what is on disk, and folders cannot.

    It never guesses when several exist and none is chosen: silently picking
    the wrong identity is precisely the failure this whole system exists to
    prevent.
    """
    if cli_value:
        return cli_value

    env_value = os.environ.get("WORK_IDE_IDENTITY")
    if env_value:
        return env_value

    # The retired local-constitution layer may still exist for anyone who has
    # not migrated; if it names a default explicitly, that is respected.
    default = default_identity()
    if default:
        return default

    available = list_identities()
    if len(available) == 1:
        return available[0]

    if not available:
        raise IdentityError(_no_identity_message())
    raise IdentityError(_ambiguous_identity_message(available))


def _no_identity_message() -> str:
    import templates as templates_mod

    known = ", ".join(sorted(templates_mod.template_folders())) or "(none)"
    return (
        "No search is set up — working without one is not allowed "
        "(constitution, rule zero).\n"
        f"  Searches are expected here: {common.IDENTITIES_DIR}\n"
        f"  Available templates: {known}\n"
        "\n"
        "  How to start (in full: docs/ONBOARDING.md):\n"
        "    1. python tools/templates.py list\n"
        "    2. python tools/templates.py clone <template> <prefix> \"<expansion>\"\n"
        "    3. fill in the personal layer together with the agent\n"
        "\n"
        "  If no template fits, take blank: a full set of files with comments\n"
        "  and no decisions made for you."
    )


def _ambiguous_identity_message(active: List[str]) -> str:
    lines = "\n".join(f"    - {describe(p)}" for p in active)
    return (
        "Several identities exist and none was chosen — guessing is not "
        "allowed.\n"
        f"{lines}\n"
        "  Name one explicitly: --identity <prefix>"
    )


def activate(cli_value: Optional[str] = None, *, allow_fixture: bool = False) -> str:
    """Resolves and activates an identity. Returns its prefix."""
    prefix = resolve_identity(cli_value)
    common.activate_identity(prefix, allow_fixture=allow_fixture)
    return prefix


def banner(prefix: Optional[str] = None) -> str:
    """The line every tool prints first. The active identity must never be
    invisible."""
    prefix = prefix or common.ACTIVE_IDENTITY
    return f"[identity: {describe(prefix)}]"


def standalone_main(fetch_fn, source_name: str) -> None:
    """Entry point for running a fetcher on its own: `python tools/fetch_x.py`.

    Being able to run a fetcher alone is useful when debugging a source, but
    fetchers read the User-Agent — and some of them the stack — from the
    active identity, so it has to be activated here too.
    """
    parser = argparse.ArgumentParser(
        description=f"Run the {source_name} source on its own")
    add_identity_arg(parser)
    args = parser.parse_args()
    activate_or_exit(args.identity)

    records, err = fetch_fn()
    print(f"{source_name}: fetched {len(records)} records" + (f" | note: {err}" if err else ""))


def add_identity_arg(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Adds --identity. One call instead of copy-paste in every tool."""
    parser.add_argument(
        "--identity", default=None,
        help="Search identity prefix (defaults to the only one present)",
    )
    return parser


def activate_or_exit(cli_value: Optional[str] = None, *, quiet: bool = False) -> str:
    """Activates an identity, or exits with a comprehensible explanation.

    The standard entry point for every CLI tool: a refusal for want of an
    identity should be loud and instructive, not a stack trace.
    """
    try:
        prefix = activate(cli_value)
    except (IdentityError, common.NoActiveIdentityError) as exc:
        common.eprint(str(exc))
        sys.exit(1)
    if not quiet:
        print(banner(prefix))
    return prefix


# --- CLI ------------------------------------------------------------------

def cmd_list(_args) -> None:
    identities = list_identities(include_fixtures=True)
    if not identities:
        print("No identities are set up.")
        return
    active = set(active_identities())
    default = default_identity()
    print(f"Identities in {common.IDENTITIES_DIR}:")
    for prefix in identities:
        kind = _read_kind(prefix) or "?"
        marks = []
        if prefix in active:
            marks.append("active")
        if prefix == default:
            marks.append("default")
        mark_str = f"  [{', '.join(marks)}]" if marks else ""
        print(f"  {prefix:<8} kind={kind:<14} {describe(prefix)}{mark_str}")


def clone_identity(source: str, prefix: str, full_name: str) -> List[Path]:
    """Copies an existing identity under a new prefix.

    Why. The commonest case is the same search tied to different countries:
    "the same thing but for Germany", "the same but for Canada". Stack,
    employment type and the signs of a suitable company are shared; geography
    rules, the language filter and the time zone are not. Building the second
    identity from scratch means answering fifty questions again to change
    three.

    The difference from `new`: `new` produces empty scaffolding, `clone`
    produces a filled copy in which only the genuinely different parts need
    changing.

    Every internal reference to the source prefix is rewritten to the new one;
    otherwise the clone would break the rule that one identity's files never
    reference another, and the validator would reject it.
    """
    if source == prefix:
        raise InvalidIdentityError("source and new prefix are the same")
    src_dir = identity_folders().get(source)
    if src_dir is None:
        raise UnknownIdentityError(
            f"identity '{source}' not found. Available: "
            + (", ".join(list_identities(include_fixtures=True)) or "none")
        )
    if _read_kind(source) == "fixture":
        raise InvalidIdentityError(
            f"'{source}' is a frozen test fixture and cannot be cloned: it is "
            "calibrated for the tests rather than for a live search"
        )
    if not PREFIX_RE.match(prefix):
        raise InvalidIdentityError(f"неверный формат префикса '{prefix}'. {PREFIX_RULE_TEXT}")
    if prefix in identity_folders():
        raise InvalidIdentityError(f"префикс '{prefix}' уже занят")

    target = common.IDENTITIES_DIR / folder_name_for(prefix, full_name)
    if target.exists():
        raise InvalidIdentityError(f"папка {target} уже существует")

    target.mkdir(parents=True)
    created: List[Path] = []
    for src in sorted(src_dir.iterdir()):
        if not src.is_file() or not src.name.startswith(f"{source}_"):
            continue
        text = src.read_text(encoding="utf-8").replace(f"{source}_", f"{prefix}_")
        dest = target / f"{prefix}_{src.name[len(source) + 1:]}"
        dest.write_text(text, encoding="utf-8")
        created.append(dest)
    return created


def cmd_clone(args) -> None:
    try:
        created = clone_identity(args.source, args.prefix, args.name)
    except IdentityError as exc:
        common.eprint(str(exc))
        sys.exit(1)

    print(f"Идентичность '{args.prefix}' склонирована из '{args.source}': "
          f"{identity_dir(args.prefix)}")
    for path in created:
        print(f"  + {path.name}")

    problems = validate(args.prefix)
    if problems:
        print("\n[FAIL] структурная проверка не прошла:")
        for p in problems:
            print(f"       - {p}")
        sys.exit(1)
    print("\n[ OK ] структура корректна (префиксы, обязательные файлы, чужие ссылки)")

    print(
        "\nЭто ПОЛНАЯ КОПИЯ — сейчас она ищет ровно то же, что и оригинал.\n"
        "Проверьте и поправьте то, что должно отличаться:\n"
        f"  1. {args.prefix}_profile.yaml -> identity.display_name, abbreviation,\n"
        "     scoring_philosophy, target_regions;\n"
        f"  2. {args.prefix}_criteria.yaml -> гео-блоки (restrictive_region_signal,\n"
        "     acceptable_region_signal, hard_dealbreakers, timezone_gate,\n"
        "     ambiguous_place_names) и языковой фильтр;\n"
        f"  3. {args.prefix}_identity.md -> чем этот поиск отличается от исходного;\n"
        f"  4. {args.prefix}_questionnaire.yaml -> ответы, которые изменились.\n"
        "\nГео-правила ВЫВОДЯТСЯ по таблицам config/derivation/, а не правятся\n"
        "на глаз: для резидента США фраза 'US only' — плюс, для нерезидента —\n"
        "полная дисквалификация. Скопированное правило с неверным знаком тихо\n"
        "выбросит половину рынка.\n"
        f"\nДанные не копируются: у '{args.prefix}' своя пустая база.\n"
        f"Активировать: python tools/identity.py init-local --identity {args.prefix}"
    )


def cmd_new(args) -> None:
    prefix = args.prefix
    try:
        created = scaffold_identity(prefix, args.name)
    except IdentityError as exc:
        common.eprint(str(exc))
        sys.exit(1)

    print(f"Создана идентичность '{prefix}': {identity_dir(prefix)}")
    for path in created:
        print(f"  + {path.name}")

    problems = validate(prefix)
    if problems:
        print("\n[FAIL] структурная проверка не прошла:")
        for p in problems:
            print(f"       - {p}")
        sys.exit(1)
    print("\n[ OK ] структура корректна (префиксы, обязательные файлы, чужие ссылки)")

    print(
        "\nЭто ЗАГОТОВКА, а не готовая идентичность: в файлах стоят плейсхолдеры.\n"
        "Дальше по docs/ONBOARDING.md:\n"
        f"  1. заполнить {prefix}_questionnaire.yaml вместе с человеком "
        "(docs/QUESTIONNAIRE.md);\n"
        f"  2. по ответам заполнить {prefix}_profile.yaml и {prefix}_criteria.yaml;\n"
        "     гео-правила и языковые фильтры ВЫВОДЯТСЯ из резидентства и языков\n"
        "     человека по таблицам config/derivation/, а не копируются у соседа;\n"
        "  3. зарегистрировать идентичность в local-constitution/active.yaml."
    )

    # Ловушка, которую иначе обнаруживают только по сломавшимся командам:
    # пока активна одна идентичность, инструменты берут её молча. Как только
    # активных становится две, а default_identity не задан, КАЖДЫЙ вызов без
    # --identity начинает падать — включая те, что годами работали у первой
    # идентичности.
    already_active = active_identities()
    if already_active and prefix not in already_active:
        current_default = default_identity()
        print(
            f"\nВНИМАНИЕ: на этой машине уже активны: {', '.join(already_active)}.\n"
            f"Как только вы добавите '{prefix}' в active.yaml, активных станет "
            f"{len(already_active) + 1}."
        )
        if not current_default:
            print(
                "  default_identity сейчас НЕ задан. С двумя активными идентичностями\n"
                "  он становится обязательным: иначе любая команда без --identity\n"
                "  начнёт отказываться работать — в том числе для уже настроенной\n"
                f"  идентичности '{already_active[0]}'.\n"
                "  Задайте default_identity одновременно с добавлением записи."
            )
        else:
            print(
                f"  default_identity задан ('{current_default}') — команды без --identity\n"
                f"  продолжат работать с ним. Для '{prefix}' указывайте флаг явно."
            )


def init_local_constitution(prefix: Optional[str] = None, note: str = "") -> List[str]:
    """Разворачивает Малую Конституцию и регистрирует в ней идентичность.

    Раньше это была инструкция «скопируйте docs/templates/local-constitution
    через xcopy, затем отредактируйте active.yaml руками» — то есть команда,
    работающая только на Windows, плюс ручное редактирование YAML в том самом
    месте, где ошибка тише всего: `default_identity` обязателен при двух
    активных идентичностях, и без него ломаются команды ПЕРВОЙ из них.

    Идемпотентна: существующие файлы не перезаписываются, повторная
    регистрация того же префикса ничего не портит.
    """
    import shutil

    actions: List[str] = []
    lc = common.LOCAL_CONSTITUTION_DIR
    template = common.ROOT / "docs" / "templates" / "local-constitution"

    if not lc.exists():
        lc.mkdir(parents=True)
        actions.append(f"создана папка {lc}")

    if template.is_dir():
        for src in sorted(template.rglob("*")):
            if src.is_dir() or src.name == ".gitkeep":
                continue
            # active.example.yaml — образец, а не рабочий файл; настоящий
            # active.yaml собирается ниже из реальных данных.
            if src.name == "active.example.yaml":
                continue
            dest = lc / src.relative_to(template)
            if dest.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            actions.append(f"скопирован {dest.relative_to(lc)}")

    if prefix:
        personal = common.personal_dir(prefix)
        if not personal.exists():
            personal.mkdir(parents=True)
            actions.append(f"создана папка личных файлов {personal}")
        actions.extend(_write_owner_skeleton(prefix))
        actions.extend(_register_identity_locally(prefix, note))

    return actions


def _write_owner_skeleton(prefix: str) -> List[str]:
    """Создаёт заготовку `<p>_owner.yaml` ровно под те поля, которые данная
    идентичность помечает сентинелом `local`.

    Список полей не универсален: у каждой идентичности он свой. Гораздо
    полезнее отдать человеку файл, где перечислено именно то, что нужно ему,
    чем отправить его читать спецификацию и собирать структуру руками.
    """
    path = common.personal_dir(prefix) / f"{prefix}_owner.yaml"
    if path.exists():
        return []

    profile_path = identity_file(prefix, "profile.yaml")
    if not profile_path.exists():
        return []
    profile = common.load_yaml(profile_path) or {}
    fields = sorted(common._walk_local_sentinels(profile))
    if not fields:
        return []

    lines = [
        f"# Личная часть профиля идентичности `{prefix}`. ВНЕ ГИТА.",
        "#",
        "# Здесь лежит то, что относится к КОНКРЕТНОМУ ЧЕЛОВЕКУ, а не к типу",
        "# поиска: имя, резидентство, языки, CV, зарплатные ожидания. В общем",
        "# репозитории на этих местах стоит `local`.",
        "#",
        "# Заполните значения ниже — пути совпадают с путями в профиле.",
        "# Спецификация: docs/LOCAL_CONSTITUTION.md",
        "",
        "schema_version: 1",
        "",
    ]
    tree: dict = {}
    for dotted in fields:
        node = tree
        parts = dotted.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = None

    def render(node: dict, indent: int = 0):
        for key, value in node.items():
            pad = "  " * indent
            if isinstance(value, dict):
                lines.append(f"{pad}{key}:")
                render(value, indent + 1)
            else:
                lines.append(f"{pad}{key}:      # заполните")

    render(tree)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [f"создана заготовка {path.name} ({len(fields)} полей для заполнения)"]


def _register_identity_locally(prefix: str, note: str = "") -> List[str]:
    """Дописывает идентичность в active.yaml, сохраняя уже записанное."""
    import datetime

    actions: List[str] = []
    path = local_constitution_path()
    cfg = load_local_constitution() or {}
    entries = cfg.get("active_identities") or []

    already_registered = any(
        (e.get("prefix") if isinstance(e, dict) else e) == prefix for e in entries
    )
    needs_default = len(entries) > 1 and not cfg.get("default_identity")

    # НИЧЕГО НЕ МЕНЯЕТСЯ — ничего и не пишем. Это не микрооптимизация: файл
    # написан человеком и полон комментариев, а перезапись через YAML-дампер
    # их стирает. Реальный случай при разработке этой команды 2026-08-04:
    # безобидный повторный запуск снёс всю документацию внутри active.yaml.
    if already_registered and not needs_default:
        return [f"'{prefix}' уже зарегистрирована в active.yaml — файл не тронут"]

    if already_registered:
        actions.append(f"'{prefix}' уже зарегистрирована в active.yaml")
    else:
        entries.append({
            "prefix": prefix,
            "activated_at": datetime.date.today().isoformat(),
            "relationship": "owner",
            "personal_dir": f"personal/{prefix}",
            "note": note or "",
        })
        cfg["active_identities"] = entries
        actions.append(f"'{prefix}' добавлена в active.yaml")

    cfg.setdefault("schema_version", 1)

    # Ключевой момент, ради которого команда и существует. Пока идентичность
    # одна, инструменты берут её молча. В тот момент, когда появляется вторая
    # без default_identity, отказывать начинают команды ПЕРВОЙ — той, что
    # работала месяцами. Проставляем дефолт ровно тогда, когда он становится
    # обязательным.
    if len(cfg["active_identities"]) > 1 and not cfg.get("default_identity"):
        first = cfg["active_identities"][0]
        cfg["default_identity"] = first.get("prefix") if isinstance(first, dict) else first
        actions.append(
            f"задан default_identity: {cfg['default_identity']} "
            "(обязателен при двух и более активных — иначе команды без --identity "
            "перестают работать у ранее настроенной идентичности)"
        )

    # Файл переписывается только когда без этого не обойтись, и тогда рядом
    # остаётся копия: человеческие комментарии из него пережить перезапись не
    # могут, а терять чужой текст молча нельзя.
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_suffix(".yaml.bak")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        actions.append(
            f"прежняя версия сохранена в {backup.name} "
            "(перезапись стирает комментарии — сверьтесь и удалите копию)"
        )
    common.write_yaml(path, cfg)
    return actions


def cmd_init_local(args) -> None:
    actions = init_local_constitution(args.identity, note=args.note or "")
    print(f"Малая Конституция: {common.LOCAL_CONSTITUTION_DIR}")
    for a in actions:
        print(f"  + {a}")
    if not actions:
        print("  (всё уже на месте — ничего менять не пришлось)")
    print(
        "\nЧто дальше:\n"
        "  - положите CV в personal/<префикс>/ (под его собственным именем);\n"
        "  - личные поля профиля (имя, резидентство, языки, зарплата) — в\n"
        "    personal/<префикс>/<префикс>_owner.yaml, см. docs/LOCAL_CONSTITUTION.md;\n"
        "  - папка в гит не попадает и попасть не должна."
    )


def cmd_validate(args) -> None:
    targets = [args.identity] if args.identity else list_identities(include_fixtures=True)
    if not targets:
        print("Нечего проверять: идентичностей нет.")
        return
    total_problems = 0
    for prefix in targets:
        problems = validate(prefix)
        total_problems += len(problems)
        if problems:
            print(f"[FAIL] {prefix}")
            for p in problems:
                print(f"       - {p}")
        else:
            print(f"[ OK ] {prefix}")
    if total_problems:
        print(f"\nПроблем: {total_problems}")
        sys.exit(1)
    print("\nВсе идентичности в порядке.")


TEMPLATE_DIR_NAME = "blank-start-from-scratch"
TEMPLATE_PREFIX = "blank"

# Плейсхолдер префикса внутри файлов шаблона.
TEMPLATE_PREFIX_PLACEHOLDER = "<префикс>"


def folder_name_for(prefix: str, full_name: str) -> str:
    """('kisel', 'Keep It Simple, Easy, Legacy') -> 'kisel-keep-it-simple-easy-legacy'.

    Расшифровку человек диктует как обычную фразу; приводить её к виду имени
    папки — работа инструмента, а не человека.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", full_name.strip().lower()).strip("-")
    if not slug:
        raise InvalidIdentityError(
            "расшифровка пуста или состоит только из символов, непригодных для имени папки"
        )
    # Расшифровка часто начинается с самого префикса ("KISEL — Keep It Simple"),
    # и тогда он не должен задваиваться в имени папки.
    if slug == prefix or slug.startswith(f"{prefix}-"):
        slug = slug[len(prefix):].lstrip("-")
    folder = f"{prefix}-{slug}" if slug else prefix
    if folder_prefix(folder) != prefix:
        raise InvalidIdentityError(
            f"из расшифровки '{full_name}' получилось некорректное имя папки '{folder}'. "
            f"{FOLDER_RULE_TEXT}"
        )
    return folder


def scaffold_identity(prefix: str, full_name: str) -> List[Path]:
    """Создаёт папку идентичности из шаблона. Возвращает созданные файлы.

    Почему это код, а не список команд в документации. Раньше `ONBOARDING.md`
    предлагал шесть `copy` с переименованием каждого файла вручную. Именно на
    этом шаге проект уже обжигался: при создании фикстуры `ftf` в неё попал
    файл, ссылающийся на `kisel_` — ровно та копипаста, от которой защищает
    правило префиксов. Ручная процедура из шести шагов, выполняемая по памяти,
    рано или поздно даёт такую ошибку; функция — нет.

    Малую Конституцию функция НЕ трогает: "какие идентичности активны на этой
    машине" — отдельное осознанное решение человека, и оно живёт вне гита.
    """
    if not PREFIX_RE.match(prefix):
        raise InvalidIdentityError(f"неверный формат префикса '{prefix}'. {PREFIX_RULE_TEXT}")
    if prefix == TEMPLATE_PREFIX:
        raise InvalidIdentityError(
            f"'{TEMPLATE_PREFIX}' — префикс шаблона, его нельзя использовать для идентичности"
        )

    existing = identity_folders().get(prefix)
    if existing is not None:
        raise InvalidIdentityError(
            f"папка {existing} уже существует (префикс '{prefix}' занят). Идентичность "
            "не перезаписывается: если нужно начать заново, человек должен удалить папку сам"
        )

    target = common.IDENTITIES_DIR / folder_name_for(prefix, full_name)
    if target.exists():
        raise InvalidIdentityError(f"папка {target} уже существует")

    template = common.TEMPLATES_DIR / TEMPLATE_DIR_NAME
    if not template.is_dir():
        raise InvalidIdentityError(f"нет папки шаблона: {template}")

    sources = sorted(p for p in template.iterdir() if p.is_file())
    if not sources:
        raise InvalidIdentityError(f"папка шаблона пуста: {template}")

    target.mkdir(parents=True)
    created: List[Path] = []
    for src in sources:
        if not src.name.startswith(f"{TEMPLATE_PREFIX}_"):
            continue  # README шаблона и прочее в идентичность не копируем
        new_name = f"{prefix}_{src.name[len(TEMPLATE_PREFIX) + 1:]}"
        text = src.read_text(encoding="utf-8")
        # Подставляем префикс и в имена файлов, и в тексте: ссылки вида
        # "<префикс>_criteria.yaml" внутри документации идентичности должны
        # сразу указывать на реальные файлы, иначе агент пойдёт по битым путям.
        text = text.replace(f"{TEMPLATE_PREFIX}_", f"{prefix}_")
        text = text.replace(TEMPLATE_PREFIX_PLACEHOLDER, prefix)
        dest = target / new_name
        dest.write_text(text, encoding="utf-8")
        created.append(dest)
    return created


def _flatten_keys(data, prefix: str = "") -> set:
    """Множество путей до всех ключей вложенного словаря: 'a.b.c'.

    Сравниваем именно СТРУКТУРУ, а не значения: значения у каждой идентичности
    свои и обязаны различаться, а вот отсутствующий ключ означает, что до
    идентичности не доехало улучшение машинерии.
    """
    keys = set()
    if isinstance(data, dict):
        for k, v in data.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            keys.add(path)
            keys |= _flatten_keys(v, path)
    return keys


def diff_template(prefix: str, config_name: str = "criteria.yaml") -> dict:
    """Структурное сравнение конфига идентичности с шаблоном.

    Только отчёт, никогда не автослияние: решение, нужен ли идентичности новый
    блок машинерии, принимает человек — иначе тихая правка может изменить
    поведение чужого поиска.
    """
    template_path = common.IDENTITIES_DIR / TEMPLATE_DIR_NAME / f"{TEMPLATE_PREFIX}_{config_name}"
    identity_path = identity_file(prefix, config_name)

    if not template_path.exists():
        raise IdentityError(f"нет шаблона: {template_path}")
    if not identity_path.exists():
        raise IdentityError(f"нет файла идентичности: {identity_path}")

    template_data = common.load_yaml(template_path) or {}
    identity_data = common.load_yaml(identity_path) or {}

    template_keys = _flatten_keys(template_data)
    identity_keys = _flatten_keys(identity_data)

    return {
        "config": config_name,
        "missing": sorted(template_keys - identity_keys),   # не доехало из шаблона
        "extra": sorted(identity_keys - template_keys),     # личные расширения
        "template_schema_version": template_data.get("schema_version"),
        "identity_schema_version": identity_data.get("schema_version"),
    }


def cmd_diff_template(args) -> None:
    targets = [args.identity] if args.identity else list_identities(include_fixtures=True)
    for prefix in targets:
        try:
            result = diff_template(prefix, args.config)
        except IdentityError as exc:
            print(f"[{prefix}] {exc}")
            continue

        print(f"\n=== {describe(prefix)} — {result['config']} ===")
        if result["missing"]:
            print("  Есть в шаблоне, нет у идентичности "
                  "(вероятно, не доехало улучшение машинерии):")
            for key in result["missing"]:
                print(f"    - {key}")
        if result["extra"]:
            print("  Есть у идентичности, нет в шаблоне (личные расширения — это нормально):")
            for key in result["extra"][:15]:
                print(f"    + {key}")
            if len(result["extra"]) > 15:
                print(f"    ... ещё {len(result['extra']) - 15}")
        if not result["missing"] and not result["extra"]:
            print("  Структура совпадает с шаблоном.")

    print("\nЭто отчёт, а не автослияние: что именно перенести — решает человек.")


def cmd_which(args) -> None:
    """Показывает, какая идентичность была бы выбрана прямо сейчас и почему."""
    try:
        prefix = resolve_identity(args.identity)
    except IdentityError as exc:
        print(str(exc))
        sys.exit(1)

    if args.identity:
        reason = "явно указана через --identity"
    elif os.environ.get("WORK_IDE_IDENTITY"):
        reason = "переменная окружения WORK_IDE_IDENTITY"
    elif default_identity():
        reason = f"default_identity в {local_constitution_path()}"
    else:
        reason = "единственная активная в Малой Конституции"
    print(f"{describe(prefix)}\n  причина: {reason}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Управление поисковыми идентичностями")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="Показать все идентичности репозитория").set_defaults(func=cmd_list)

    p_new = sub.add_parser(
        "new",
        help="Создать заготовку идентичности из шаблона (первую или очередную)",
    )
    p_new.add_argument("--prefix", required=True, help="Префикс: 3-6 строчных латинских символов")
    p_new.add_argument(
        "--name", required=True,
        help='Расшифровка префикса обычной фразой, например "Keep It Simple, Easy, Legacy". '
             "Станет частью имени папки: identities/<префикс>-<расшифровка>",
    )
    p_new.set_defaults(func=cmd_new)

    p_clone = sub.add_parser(
        "clone",
        help="Скопировать существующую идентичность под новым префиксом",
    )
    p_clone.add_argument("--from", dest="source", required=True,
                         help="Префикс идентичности-источника")
    p_clone.add_argument("--prefix", required=True, help="Префикс новой идентичности")
    p_clone.add_argument("--name", required=True,
                         help='Расшифровка фразой, например "KISEL for Germany"')
    p_clone.set_defaults(func=cmd_clone)

    p_init = sub.add_parser(
        "init-local",
        help="Развернуть Малую Конституцию и зарегистрировать в ней идентичность",
    )
    p_init.add_argument("--identity", default=None,
                        help="Префикс, который нужно активировать на этой машине")
    p_init.add_argument("--note", default=None, help="Зачем вам эта идентичность")
    p_init.set_defaults(func=cmd_init_local)

    p_val = sub.add_parser("validate", help="Проверить структуру идентичности (или всех)")
    p_val.add_argument("--identity", default=None)
    p_val.set_defaults(func=cmd_validate)

    p_which = sub.add_parser("which", help="Какая идентичность будет выбрана и почему")
    p_which.add_argument("--identity", default=None)
    p_which.set_defaults(func=cmd_which)

    p_diff = sub.add_parser(
        "diff-template",
        help="Сравнить структуру конфига идентичности с шаблоном (отчёт, не слияние)",
    )
    p_diff.add_argument("--identity", default=None)
    p_diff.add_argument("--config", default="criteria.yaml",
                        help="Какой файл сравнивать (по умолчанию criteria.yaml)")
    p_diff.set_defaults(func=cmd_diff_template)

    return p


def main(argv: Optional[list] = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
