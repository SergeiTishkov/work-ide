"""
Layered settings: deterministic merging, with provenance for every value.

THE PROBLEM
-----------
In an ordinary application, settings are assembled from several layers applied
in a fixed order. This project has layers too, but no mechanism applied them:
every override was hand-written at the place in the code that read it — twenty-
six such places in score.py alone.

Two consequences followed, both observed in practice:
  * the only way to learn where a value came from was to read the code;
  * two parts of the configuration could contradict each other, and whichever
    ran first won (real cases are recorded in docs/OVERRIDES.md).

WHAT THIS IS
------------
One layer order, one merge rule, and provenance for EVERY value:

    defaults   config/defaults/<document>.yaml          shared by everyone
    template   <identity>/template/<prefix>_<doc>.yaml  the type of search
    local      <identity>/<prefix>_<doc>.yaml           my own settings

The later layer wins. The order is fixed and does not depend on the caller —
that is the whole of the determinism.

MERGE RULES (each chosen deliberately, each closing a known trap)
-----------------------------------------------------------------
1. Dictionaries merge deeply. A layer can change one threshold without
   rewriting its neighbours.

2. Lists are REPLACED whole rather than appended to. Appending looks convenient
   right up to the first time something must be REMOVED from an inherited list
   — and then it turns out there is no syntax for that. Replacement is more
   verbose and reversible.

3. An explicit `null` deletes a key. The only way to say "I do not have this"
   when a lower layer provided it.

4. Frozen keys (config/settings_policy.yaml) cannot be changed by the local
   layer; the attempt fails loudly with an explanation. Layering without that
   exception would mean a file outside git could quietly lift, say, the ban on
   circumventing bot protection. Specific-beats-general is a rule about
   PREFERENCES, not about boundaries.

WHAT IS NOT HERE, AND WILL NOT BE
---------------------------------
Merging of prose. CLAUDE.md, docs/ and an identity's narrative are read by the
agent rather than by this module, and prose does not merge. The way to make
THAT deterministic is different: move decisions out of prose into data so they
end up here. See docs/OVERRIDES.md, the section on two kinds of settings.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

LAYER_ORDER = ("defaults", "template", "local")

DELETED = object()


class FrozenSettingError(Exception):
    """An upper layer tried to change a key that must not change."""


# --------------------------------------------------------------------------
#  Где лежат слои
# --------------------------------------------------------------------------

def layer_paths(document: str, prefix: str) -> List[Tuple[str, Path]]:
    """[(layer name, path)] in application order. Missing files are included:
    their absence is a fact worth seeing in `explain` too."""
    import identity as identity_mod

    folder = identity_mod.identity_dir(prefix)
    return [
        # Shared by everyone who uses the project.
        ("defaults", common.ROOT / "config" / "defaults" / f"{document}.yaml"),
        # The verbatim template copy taken at clone time. Never edited: a
        # template update replaces it whole (templates.apply_update).
        ("template", folder / "template" / f"{prefix}_{document}.yaml"),
        # My settings. This is where the person and the agent write.
        ("local", folder / f"{prefix}_{document}.yaml"),
    ]


def local_override_keys(prefix: str, documents=("profile", "criteria")) -> set:
    """Keys set personally, on top of the template. Needed when it updates."""
    keys = set()
    for document in documents:
        for layer, path in layer_paths(document, prefix):
            if layer == "local" and path.exists():
                keys |= set(_flatten(common.load_yaml(path) or {}))
    return keys


def frozen_keys() -> Dict[str, str]:
    """{dotted key: reason it is frozen} from the shared policy."""
    path = common.ROOT / "config" / "settings_policy.yaml"
    data = common.load_yaml(path) if path.exists() else {}
    return {k: str(v) for k, v in ((data or {}).get("frozen") or {}).items()}


# --------------------------------------------------------------------------
#  Слияние
# --------------------------------------------------------------------------

def _flatten(node, path: str = "") -> Dict[str, object]:
    """A dict -> {dotted key: value}. Lists are leaves (rule 2)."""
    flat = {}
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}" if path else str(key)
            if isinstance(value, dict) and value:
                flat.update(_flatten(value, child))
            else:
                flat[child] = value
    elif path:
        flat[path] = node
    return flat


def _merge_into(target: dict, source: dict) -> None:
    for key, value in (source or {}).items():
        if value is None:
            target.pop(key, None)          # rule 3: null deletes
        elif isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge_into(target[key], value)
        else:
            target[key] = copy.deepcopy(value)   # rule 2: a list is replaced


def resolve(document: str, prefix: str) -> Tuple[dict, Dict[str, str]]:
    """(resolved settings, {dotted key: the layer that supplied it}).

    Provenance is returned always rather than on request: the question "where
    did this number come from" is asked exactly when something has already
    gone wrong, and reaching for a separate tool at that moment is too late.
    """
    frozen = frozen_keys()
    merged: dict = {}
    provenance: Dict[str, str] = {}

    for layer, path in layer_paths(document, prefix):
        data = common.load_yaml(path) if path.exists() else {}
        if not data:
            continue

        # Freezing protects against files OUTSIDE GIT: the point is that an
        # unobserved file cannot quietly lift a boundary. Shared configuration,
        # the template copy and test fixtures live in the repository and are
        # reviewed like code — a fixture, for instance, must declare itself a
        # fixture or nothing can tell it from a live identity.
        if layer == "local":
            # What is forbidden is OVERRIDING, not declaring. If no lower layer
            # set the key, this is a first declaration, and there is neither a
            # way nor a reason to forbid it: an identity with no template copy
            # must declare its own kind, or a fixture cannot be told from a
            # live identity.
            #
            # That distinction is what makes freezing a rule about overrides
            # rather than a ban on mentioning a key.
            already = _flatten(merged)
            for key, value in _flatten(data).items():
                for frozen_key, reason in frozen.items():
                    if not (key == frozen_key or key.startswith(frozen_key + ".")):
                        continue
                    if key in already and already[key] != value:
                        raise FrozenSettingError(
                            f"Слой '{layer}' ({path}) меняет '{key}' "
                            f"с {already[key]!r} на {value!r}, а этот ключ "
                            f"заморожен.\n  Причина: {reason}\n"
                            "  Замороженные ключи перечислены в "
                            "config/settings_policy.yaml."
                        )

        _merge_into(merged, data)
        for key in _flatten(data):
            provenance[key] = layer

    # Keys deleted via null are absent from the result, so drop them from the
    # provenance map too.
    final = _flatten(merged)
    provenance = {k: v for k, v in provenance.items() if k in final}
    return merged, provenance


def explain(document: str, prefix: str, dotted_key: str) -> List[dict]:
    """A key's value at every layer: what each offered, and what won."""
    chain = []
    for layer, path in layer_paths(document, prefix):
        data = common.load_yaml(path) if path.exists() else {}
        flat = _flatten(data or {})
        chain.append({
            "layer": layer,
            "path": str(path),
            "exists": path.exists(),
            "has_key": dotted_key in flat,
            "value": flat.get(dotted_key),
        })
    return chain


def conflicts(document: str, prefix: str) -> List[dict]:
    """Keys set by more than one layer.

    These are not errors — overriding is the whole point of layers. But each
    one should be deliberate, so seeing them listed is useful: a silent
    override is exactly how two parts of a configuration start contradicting
    each other.
    """
    per_layer = {}
    for layer, path in layer_paths(document, prefix):
        per_layer[layer] = _flatten(common.load_yaml(path) or {}) if path.exists() else {}

    found = []
    for key in sorted(set().union(*[set(f) for f in per_layer.values()]) if per_layer else []):
        setters = [(layer, per_layer[layer][key])
                   for layer in LAYER_ORDER if key in per_layer.get(layer, {})]
        if len(setters) > 1:
            found.append({"key": key, "setters": setters, "winner": setters[-1][0]})
    return found


# --------------------------------------------------------------------------
#  CLI
# --------------------------------------------------------------------------

def main() -> None:
    import argparse
    import identity as identity_mod

    parser = argparse.ArgumentParser(
        description="Layered settings: what overrides what, and where it came from"
    )
    identity_mod.add_identity_arg(parser)
    parser.add_argument("document", help="criteria | profile | sources | ...")
    parser.add_argument("key", nargs="?", help="Dotted key to explain")
    parser.add_argument("--conflicts", action="store_true",
                        help="Show every key set by more than one layer")
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)
    prefix = common.ACTIVE_IDENTITY

    if args.key:
        print(f"Key: {args.key}  (document: {args.document})\n")
        winner = None
        for step in explain(args.document, prefix, args.key):
            mark = "  " if not step["has_key"] else "->"
            state = ("no file" if not step["exists"]
                     else "not set" if not step["has_key"]
                     else repr(step["value"]))
            print(f" {mark} {step['layer']:<9} {state}")
            print(f"      {step['path']}")
            if step["has_key"]:
                winner = step
        print()
        print("Winner:", f"{winner['layer']} -> {winner['value']!r}" if winner
              else "nothing — the key is set by no layer at all")
        return

    if args.conflicts:
        found = conflicts(args.document, prefix)
        if not found:
            print("No overrides: every key is set by exactly one layer.")
            return
        print(f"Keys set by more than one layer: {len(found)}\n")
        for item in found:
            chain = " -> ".join(f"{layer}={value!r}" for layer, value in item["setters"])
            print(f"  {item['key']}")
            print(f"      {chain}   (winner: {item['winner']})")
        return

    merged, provenance = resolve(args.document, prefix)
    counts = {}
    for layer in provenance.values():
        counts[layer] = counts.get(layer, 0) + 1
    print(f"Document '{args.document}', identity '{prefix}'")
    print(f"  keys in total: {len(provenance)}")
    for layer in LAYER_ORDER:
        print(f"  from layer {layer:<9} {counts.get(layer, 0)}")
    print("\nWhere a particular value came from:")
    print(f"  python tools/settings.py {args.document} <точечный.ключ>")


if __name__ == "__main__":
    main()
