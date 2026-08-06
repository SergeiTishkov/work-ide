"""
Identity templates: cloning, versions, updates.

WHY A TEMPLATE RATHER THAN AN IDENTITY IN GIT
---------------------------------------------
Identities used to live in git and were two things at once: shared property and
somebody's personal configuration. Residency, pay expectations and other
circumstances of a particular person ended up in the shared repository, and
separating them took a third layer (the Local Constitution) with a `local`
sentinel — a mechanism where picking the wrong layer was easy.

The split now follows the git boundary:

    identity-templates/<folder>/   the KIND of search, in git, no personal facts
    local-identities/<folder>/     MY search, outside git, anything goes

WHY THE TEMPLATE COPY LIVES INSIDE THE LOCAL IDENTITY
-----------------------------------------------------
This is the key decision, and it removes text merging altogether.

At clone time the template's files are placed in `<local>/template/` verbatim,
and they are never edited. Personal changes go into separate files one level up
and are layered on top (see settings.py).

Three consequences follow:

  * `git pull` cannot change behaviour. The template in the repository moved on;
    the copy inside the identity did not, so the shortlist did not shift. Silent
    configuration drift is impossible by construction rather than by discipline.

  * an update is a FOLDER REPLACEMENT, not a merge. Personal edits sit elsewhere
    and are untouched by the operation. No three-way merge, no decisions of the
    "overwrite this file but patch that one" kind — that is, no place where an
    agent could quietly lose somebody's setting.

  * a conflict is computed exactly: the intersection of the keys a person
    overrode with the keys that changed between versions. A list, not a
    judgement call.

VERSIONS
--------
A template's version is a number in `template.yaml`. The `CHANGELOG.md` beside
it explains to a person what changed, newest first. Comparing versions means
comparing numbers rather than parsing markdown: parsing prose to decide whether
to run would be exactly the kind of implicitness this project avoids.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

TEMPLATE_MANIFEST = "template.yaml"
CHANGELOG = "CHANGELOG.md"
LOCAL_MANIFEST = "identity.yaml"
TEMPLATE_COPY_DIR = "template"
DOCUMENTS_DIR = "documents"


class TemplateError(Exception):
    pass


# --------------------------------------------------------------------------
#  Templates
# --------------------------------------------------------------------------

def template_folders() -> dict:
    """{template name: folder}. The name is the prefix of the folder name."""
    import identity as identity_mod

    found = {}
    if not common.TEMPLATES_DIR.exists():
        return found
    for path in sorted(common.TEMPLATES_DIR.iterdir()):
        if not path.is_dir() or path.name.startswith("_"):
            continue
        name = identity_mod.folder_prefix(path.name)
        if name:
            found[name] = path
    return found


def template_dir(name: str) -> Path:
    folder = template_folders().get(name)
    if folder is None:
        known = ", ".join(sorted(template_folders())) or "none"
        raise TemplateError(
            f"Template '{name}' not found. Available: {known}.\n"
            f"  List them: python tools/templates.py list"
        )
    return folder


def template_manifest(name: str) -> dict:
    path = template_dir(name) / TEMPLATE_MANIFEST
    if not path.exists():
        raise TemplateError(
            f"Template '{name}' has no {TEMPLATE_MANIFEST} — nothing to compare "
            f"a version against."
        )
    return common.load_yaml(path) or {}


def template_version(name: str) -> int:
    return int(template_manifest(name).get("version") or 1)


# --------------------------------------------------------------------------
#  Local identities
# --------------------------------------------------------------------------

def local_manifest_path(prefix: str) -> Path:
    import identity as identity_mod

    return identity_mod.identity_dir(prefix) / LOCAL_MANIFEST


def local_manifest(prefix: str) -> dict:
    path = local_manifest_path(prefix)
    return (common.load_yaml(path) or {}) if path.exists() else {}


def pinned_version(prefix: str) -> Optional[int]:
    """The template version this local identity is pinned to."""
    value = local_manifest(prefix).get("template_version")
    return int(value) if value is not None else None


def template_of(prefix: str) -> Optional[str]:
    return local_manifest(prefix).get("template")


def update_available(prefix: str) -> Optional[dict]:
    """{template, from, to, entries} if the template moved ahead, else None."""
    name = template_of(prefix)
    if not name or name not in template_folders():
        return None
    pinned = pinned_version(prefix)
    latest = template_version(name)
    if pinned is None or latest <= pinned:
        return None
    return {
        "template": name,
        "from": pinned,
        "to": latest,
        "entries": changelog_entries(name, after=pinned),
    }


def changelog_entries(name: str, after: int = 0) -> List[dict]:
    """Sections of a template's CHANGELOG.md newer than the given version.

    Parsing is needed only to SHOW a person what changed. Whether an update
    exists at all is decided by the number in the manifest, so a broken or
    lagging changelog cannot cause a wrong run — at worst the person sees fewer
    explanations.
    """
    path = template_dir(name) / CHANGELOG
    if not path.exists():
        return []
    entries, current = [], None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            head = stripped[3:].strip()
            version = None
            if head.lower().startswith("v") and head[1:].split()[0].rstrip(".").isdigit():
                version = int(head[1:].split()[0].rstrip("."))
            current = {"version": version, "title": head, "lines": []}
            entries.append(current)
        elif current is not None and stripped:
            current["lines"].append(stripped)
    return [e for e in entries if e["version"] is not None and e["version"] > after]


# --------------------------------------------------------------------------
#  Cloning and updating
# --------------------------------------------------------------------------

def _template_payload(name: str) -> List[Path]:
    """The template files that get copied into a local identity."""
    skip = {TEMPLATE_MANIFEST}
    return [p for p in sorted(template_dir(name).iterdir())
            if p.is_file() and p.name not in skip]


def clone(name: str, prefix: str, full_name: str) -> Path:
    """Creates a local identity from a template. Returns its folder."""
    import identity as identity_mod

    if prefix in identity_mod.identity_folders():
        raise TemplateError(
            f"An identity with prefix '{prefix}' already exists: "
            f"{identity_mod.identity_dir(prefix)}"
        )
    if not identity_mod.PREFIX_RE.match(prefix):
        raise TemplateError(
            f"malformed prefix '{prefix}'. {identity_mod.PREFIX_RULE_TEXT}")

    version = template_version(name)
    target = common.IDENTITIES_DIR / identity_mod.folder_name_for(prefix, full_name)
    (target / TEMPLATE_COPY_DIR).mkdir(parents=True)
    (target / DOCUMENTS_DIR).mkdir(exist_ok=True)

    template_prefix = name
    for src in _template_payload(name):
        # File names are rewritten to the new identity's prefix: everything else
        # in the project looks for files matching "<prefix>_<document>".
        stem = src.name
        if stem.startswith(f"{template_prefix}_"):
            stem = f"{prefix}_{stem[len(template_prefix) + 1:]}"
        shutil.copy2(src, target / TEMPLATE_COPY_DIR / stem)

    common.write_yaml(target / LOCAL_MANIFEST, {
        "prefix": prefix,
        "display_name": full_name,
        "template": name,
        "template_version": version,
    })

    (target / CHANGELOG).write_text(
        f"# Change log for identity «{full_name}»\n\n"
        "New entries go on TOP. Local changes always come first: by definition\n"
        "they are newer than any template version.\n\n"
        "## Local changes\n\n"
        "_None yet._\n\n"
        f"## Created from template {name} v{version}\n\n"
        f"The template copy lives in `{TEMPLATE_COPY_DIR}/` and is never edited.\n"
        "Put your own settings in files beside it — they are layered on top.\n",
        encoding="utf-8",
    )
    return target


def apply_update(prefix: str) -> dict:
    """Moves a local identity onto the template's current version.

    This REPLACES the `template/` folder rather than merging into it: personal
    settings live in separate files and take no part in the operation at all.
    So there is not, and cannot be, a decision here about "what to overwrite
    and what to patch".
    """
    import identity as identity_mod

    info = update_available(prefix)
    if not info:
        return {"updated": False}

    name = info["template"]
    target = identity_mod.identity_dir(prefix)
    copy_dir = target / TEMPLATE_COPY_DIR
    if copy_dir.exists():
        shutil.rmtree(copy_dir)
    copy_dir.mkdir(parents=True)

    for src in _template_payload(name):
        stem = src.name
        if stem.startswith(f"{name}_"):
            stem = f"{prefix}_{stem[len(name) + 1:]}"
        shutil.copy2(src, copy_dir / stem)

    manifest = local_manifest(prefix)
    manifest["template_version"] = info["to"]
    common.write_yaml(local_manifest_path(prefix), manifest)

    changelog = target / CHANGELOG
    if changelog.exists():
        text = changelog.read_text(encoding="utf-8")
        note = (f"## Updated to {name} v{info['to']}\n\n"
                + "\n".join(f"- {e['title']}" for e in info["entries"]) + "\n\n")
        marker = "## Local changes"
        if marker in text:
            head, _, tail = text.partition(marker)
            end = tail.find("\n## ")
            block = tail[:end] if end != -1 else tail
            rest = tail[end:] if end != -1 else ""
            text = head + marker + block + note + rest
        else:
            text = text.rstrip() + "\n\n" + note
        changelog.write_text(text, encoding="utf-8")

    return {"updated": True, **info, "conflicts": overridden_keys_changed(prefix, info)}


def overridden_keys_changed(prefix: str, info: dict) -> List[str]:
    """Keys the person overrode AND the template changed.

    That intersection is the whole "conflict" of an update — an exact list
    rather than something to think about. The override keeps winning (it is the
    stronger layer), so the list is informational: the person decides whether
    their edit has gone stale.
    """
    import settings

    try:
        local_flat = settings.local_override_keys(prefix)
    except Exception:  # noqa: BLE001
        return []
    return sorted(local_flat)


# --------------------------------------------------------------------------
#  CLI
# --------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Identity templates: list, clone, update"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="Show the available templates")

    p_clone = sub.add_parser("clone", help="Create your own identity from a template")
    p_clone.add_argument("template", help="Template name (see list)")
    p_clone.add_argument("prefix", help="Prefix for the new identity")
    p_clone.add_argument("name", help="Latin-script expansion, used for the folder name")

    p_check = sub.add_parser("check", help="Has the template moved ahead")
    p_check.add_argument("--identity", required=True)

    p_update = sub.add_parser("update", help="Move onto the template's current version")
    p_update.add_argument("--identity", required=True)

    args = parser.parse_args()

    if args.cmd == "list":
        found = template_folders()
        if not found:
            print(f"No templates: {common.TEMPLATES_DIR} is empty.")
            return
        print(f"Templates in {common.TEMPLATES_DIR}:\n")
        for name in sorted(found):
            manifest = template_manifest(name)
            summary = " ".join(str(manifest.get("summary") or "").split())
            print(f"  {name:<8} v{manifest.get('version', 1)}  {summary}")
            fits = " ".join(str(manifest.get("suitable_for") or "").split())
            if fits:
                print(f"           for whom: {fits}")
        print("\n  Clone one: python tools/templates.py clone <template> <prefix> <expansion>")
        return

    if args.cmd == "clone":
        target = clone(args.template, args.prefix, args.name)
        print(f"Created identity '{args.prefix}': {target}")
        print(f"  Template copy:   {target / TEMPLATE_COPY_DIR}  (do not edit)")
        print(f"  Your settings:   {target / (args.prefix + '_profile.yaml')}")
        print(f"  Personal files:  {target / DOCUMENTS_DIR}")
        print("\n  Next — docs/ONBOARDING.md: fill in the profile together with the agent.")
        return

    info = update_available(args.identity)
    if args.cmd == "check":
        if not info:
            pinned = pinned_version(args.identity)
            name = template_of(args.identity)
            print(f"No updates: '{args.identity}' is on {name} v{pinned}."
                  if name else
                  f"'{args.identity}' was not created from a template — nothing to update.")
            return
        print(f"Template '{info['template']}' moved ahead: v{info['from']} -> v{info['to']}\n")
        for entry in info["entries"]:
            print(f"  {entry['title']}")
            for line in entry["lines"][:4]:
                print(f"      {line}")
        print(f"\n  Update: python tools/templates.py update --identity {args.identity}")
        return

    if args.cmd == "update":
        if not info:
            print("No updates.")
            return
        result = apply_update(args.identity)
        print(f"Updated: v{result['from']} -> v{result['to']}")
        if result.get("conflicts"):
            print("\n  Your overrides keep applying (they are stronger than the template).")
            print("  Check whether they have gone stale after the update:")
            for key in result["conflicts"][:20]:
                print(f"    - {key}")


if __name__ == "__main__":
    main()
