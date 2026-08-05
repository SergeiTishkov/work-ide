"""
Слоистые настройки: детерминированное наложение и происхождение значений.

ЗАДАЧА
------
Вопрос владельца 2026-08-05: в обычном приложении настройки собирают из
нескольких слоёв, накладывая один на другой в фиксированном порядке. Здесь
слоёв тоже три — Большая Конституция, идентичность, Малая Конституция, — но
наложения как механизма не было: каждое переопределение писалось руками в том
месте кода, которое его читает. Двадцать шесть разных мест в одном score.py.

Отсюда два следствия, оба наблюдались на практике:
  * узнать, откуда взялось значение, можно только чтением кода;
  * две части конфигурации могут противоречить друг другу, и побеждает та,
    что срабатывает раньше (реальные случаи — в docs/OVERRIDES.md).

ЧТО ЗДЕСЬ ЕСТЬ
--------------
Один порядок слоёв, одно правило слияния и происхождение КАЖДОГО значения:

    defaults   config/defaults/<документ>.yaml            общее для всех
    template   <локальная>/template/<префикс>_<док>.yaml   тип поиска (копия шаблона)
    local      <локальная>/<префикс>_<док>.yaml            мои настройки

Побеждает более поздний слой. Порядок фиксирован и не зависит от того, кто
вызывает — в этом вся суть детерминизма.

ПРАВИЛА СЛИЯНИЯ (выбраны сознательно, каждое закрывает известную ловушку)
------------------------------------------------------------------------
1. Словари сливаются вглубь. Слой может изменить один порог, не переписывая
   соседние.

2. Списки ЗАМЕНЯЮТСЯ целиком, а не дополняются. Дополнение выглядит удобным
   ровно до первого случая, когда из унаследованного списка нужно что-то
   УБРАТЬ, — и тогда оказывается, что синтаксиса для этого нет. Замена
   многословнее, но обратима.

3. Явный `null` удаляет ключ. Единственный способ сказать «у меня этого нет»,
   когда нижний слой это задал.

4. Замороженные ключи (config/settings_policy.yaml) ЛОКАЛЬНЫЙ слой менять НЕ
   может — попытка это сделать роняет загрузку с объяснением. Слоистость без
   такого исключения означала бы, что личный файл может отключить, например,
   запрет на обход антибот-защиты. Приоритет частного над общим — правило для
   ПРЕДПОЧТЕНИЙ, а не для границ.

ЧЕГО ЗДЕСЬ НЕТ И НЕ БУДЕТ
-------------------------
Слияния текстовых инструкций. CLAUDE.md, docs/ и <префикс>_identity.md
читает агент, а не этот модуль; проза не сливается. Способ сделать
детерминированной ЕЁ — другой: переносить решения из прозы в данные, чтобы
они попадали сюда. См. docs/OVERRIDES.md, раздел про два вида настроек.
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
    """Верхний слой попытался изменить ключ, который менять нельзя."""


# --------------------------------------------------------------------------
#  Где лежат слои
# --------------------------------------------------------------------------

def layer_paths(document: str, prefix: str) -> List[Tuple[str, Path]]:
    """[(имя слоя, путь)] в порядке наложения. Отсутствующие файлы включены —
    их отсутствие тоже факт, который полезно видеть в explain."""
    import identity as identity_mod

    folder = identity_mod.identity_dir(prefix)
    return [
        # Общее для всех пользователей проекта.
        ("defaults", common.ROOT / "config" / "defaults" / f"{document}.yaml"),
        # Дословная копия шаблона, снятая при клонировании. Не редактируется:
        # её целиком заменяет обновление шаблона (templates.apply_update).
        ("template", folder / "template" / f"{prefix}_{document}.yaml"),
        # Мои настройки. Именно сюда пишет человек и агент.
        ("local", folder / f"{prefix}_{document}.yaml"),
    ]


def local_override_keys(prefix: str, documents=("profile", "criteria")) -> set:
    """Ключи, заданные лично, поверх шаблона. Нужны при обновлении шаблона."""
    keys = set()
    for document in documents:
        for layer, path in layer_paths(document, prefix):
            if layer == "local" and path.exists():
                keys |= set(_flatten(common.load_yaml(path) or {}))
    return keys


def frozen_keys() -> Dict[str, str]:
    """{точечный ключ: причина заморозки} из общей политики."""
    path = common.ROOT / "config" / "settings_policy.yaml"
    data = common.load_yaml(path) if path.exists() else {}
    return {k: str(v) for k, v in ((data or {}).get("frozen") or {}).items()}


# --------------------------------------------------------------------------
#  Слияние
# --------------------------------------------------------------------------

def _flatten(node, path: str = "") -> Dict[str, object]:
    """Словарь -> {точечный ключ: значение}. Списки — листья (правило 2)."""
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
            target.pop(key, None)          # правило 3: null удаляет
        elif isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge_into(target[key], value)
        else:
            target[key] = copy.deepcopy(value)   # правило 2: список заменяется


def resolve(document: str, prefix: str) -> Tuple[dict, Dict[str, str]]:
    """(итоговые настройки, {точечный ключ: слой, который дал значение}).

    Происхождение возвращается всегда, а не по запросу: вопрос «откуда взялось
    это число» задаётся ровно тогда, когда что-то уже пошло не так, и в этот
    момент поднимать отдельный инструмент поздно.
    """
    frozen = frozen_keys()
    merged: dict = {}
    provenance: Dict[str, str] = {}

    for layer, path in layer_paths(document, prefix):
        data = common.load_yaml(path) if path.exists() else {}
        if not data:
            continue

        # Заморозка защищает от файлов ВНЕ ГИТА: смысл её в том, чтобы
        # ненаблюдаемый файл не мог тихо снять границу. Общая конфигурация,
        # копия шаблона и тестовые фикстуры лежат в репозитории и проходят
        # ревью наравне с кодом — фикстура, например, обязана объявить себя
        # фикстурой, иначе её нечем отличить от живой идентичности.
        if layer == "local":
            # Запрещено ПЕРЕОПРЕДЕЛЯТЬ, а не объявлять. Если ни один слой ниже
            # ключ не задавал, это первое объявление, и запрещать его нечем и
            # незачем: идентичность, у которой нет копии шаблона, обязана
            # объявить свой вид сама, иначе фикстуру нечем отличить от живой.
            #
            # Именно эта разница и делает заморозку правилом об override, а не
            # запретом на упоминание ключа.
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

    # Ключи, удалённые через null, в итоге отсутствуют — убираем и из карты.
    final = _flatten(merged)
    provenance = {k: v for k, v in provenance.items() if k in final}
    return merged, provenance


def explain(document: str, prefix: str, dotted_key: str) -> List[dict]:
    """Значение ключа на каждом слое: что предлагал, что победило."""
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
    """Ключи, которые задают несколько слоёв.

    Это не ошибки — переопределение и есть смысл слоёв. Но каждое из них
    должно быть намеренным, поэтому их полезно видеть списком: молчаливое
    переопределение и есть тот способ, которым две части конфигурации
    начинают противоречить друг другу.
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
        description="Слоистые настройки: что чем переопределено и откуда взялось"
    )
    identity_mod.add_identity_arg(parser)
    parser.add_argument("document", help="criteria | profile | sources | ...")
    parser.add_argument("key", nargs="?", help="Точечный ключ для explain")
    parser.add_argument("--conflicts", action="store_true",
                        help="Показать все ключи, заданные более чем одним слоем")
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)
    prefix = common.ACTIVE_IDENTITY

    if args.key:
        print(f"Ключ: {args.key}  (документ: {args.document})\n")
        winner = None
        for step in explain(args.document, prefix, args.key):
            mark = "  " if not step["has_key"] else "->"
            state = ("нет файла" if not step["exists"]
                     else "не задан" if not step["has_key"]
                     else repr(step["value"]))
            print(f" {mark} {step['layer']:<9} {state}")
            print(f"      {step['path']}")
            if step["has_key"]:
                winner = step
        print()
        print("Победило:", f"{winner['layer']} -> {winner['value']!r}" if winner
              else "ничего — ключ не задан ни на одном слое")
        return

    if args.conflicts:
        found = conflicts(args.document, prefix)
        if not found:
            print("Переопределений нет: каждый ключ задан ровно одним слоем.")
            return
        print(f"Ключей, заданных более чем одним слоем: {len(found)}\n")
        for item in found:
            chain = " -> ".join(f"{layer}={value!r}" for layer, value in item["setters"])
            print(f"  {item['key']}")
            print(f"      {chain}   (побеждает {item['winner']})")
        return

    merged, provenance = resolve(args.document, prefix)
    counts = {}
    for layer in provenance.values():
        counts[layer] = counts.get(layer, 0) + 1
    print(f"Документ '{args.document}', идентичность '{prefix}'")
    print(f"  ключей всего: {len(provenance)}")
    for layer in LAYER_ORDER:
        print(f"  из слоя {layer:<9} {counts.get(layer, 0)}")
    print("\nОткуда взялось конкретное значение:")
    print(f"  python tools/settings.py {args.document} <точечный.ключ>")


if __name__ == "__main__":
    main()
