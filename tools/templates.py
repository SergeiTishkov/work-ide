"""
Шаблоны идентичностей: клонирование, версии, обновление.

ПОЧЕМУ ШАБЛОН, А НЕ ИДЕНТИЧНОСТЬ В ГИТЕ
---------------------------------------
Раньше идентичности лежали в гите и были одновременно и общим достоянием, и
чьей-то личной настройкой. Из-за этого в общий репозиторий попадали
резидентство, зарплатные ожидания и прочие обстоятельства конкретного
человека, а разделять их приходилось третьим слоем (Малой Конституцией) с
сентинелом `local` — механизмом, на котором легко ошибиться слоем.

Теперь разделение проходит по границе гита:

    identity-templates/<папка>/   ТИП поиска, в гите, ни одного личного факта
    local-identities/<папка>/     МОЙ поиск, вне гита, здесь можно всё

ПОЧЕМУ КОПИЯ ШАБЛОНА ЛЕЖИТ ВНУТРИ ЛОКАЛЬНОЙ ИДЕНТИЧНОСТИ
--------------------------------------------------------
Ключевое решение, и оно избавляет от слияния текстов вообще.

При клонировании файлы шаблона кладутся в `<локальная>/template/` дословно, и
редактировать их нельзя. Свои изменения человек пишет в отдельные файлы
уровнем выше — они накладываются поверх (см. settings.py).

Из этого следует:

  * `git pull` не меняет поведение. Шаблон в репозитории обновился — копия
    внутри идентичности осталась прежней, выдача не поехала. Молчаливый дрейф
    конфигурации невозможен по устройству, а не по дисциплине.

  * обновление — это ЗАМЕНА ПАПКИ, а не слияние. Личные правки лежат отдельно
    и при замене не страдают. Никакого трёхстороннего merge, никаких решений
    "этот файл перезаписать, а этот подправить" — то есть ни одного места,
    где агент мог бы тихо потерять чужую настройку.

  * конфликт вычисляется точно: пересечение ключей, которые человек
    переопределил, с ключами, изменившимися между версиями. Это список, а не
    суждение.

ВЕРСИИ
------
Версия шаблона — число в `template.yaml`. `CHANGELOG.md` рядом объясняет
человеку, что изменилось, новыми версиями вверх. Сравнение версий — сравнение
чисел, а не разбор markdown: разбор прозы для принятия решения о запуске был
бы ровно той неявностью, которой здесь стараются избегать.
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
#  Шаблоны
# --------------------------------------------------------------------------

def template_folders() -> dict:
    """{имя шаблона: папка}. Имя шаблона — префикс из имени папки."""
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
        known = ", ".join(sorted(template_folders())) or "ни одного"
        raise TemplateError(
            f"Шаблон '{name}' не найден. Доступны: {known}.\n"
            f"  Список: python tools/templates.py list"
        )
    return folder


def template_manifest(name: str) -> dict:
    path = template_dir(name) / TEMPLATE_MANIFEST
    if not path.exists():
        raise TemplateError(
            f"У шаблона '{name}' нет {TEMPLATE_MANIFEST} — версию сравнить не с чем."
        )
    return common.load_yaml(path) or {}


def template_version(name: str) -> int:
    return int(template_manifest(name).get("version") or 1)


# --------------------------------------------------------------------------
#  Локальные идентичности
# --------------------------------------------------------------------------

def local_manifest_path(prefix: str) -> Path:
    import identity as identity_mod

    return identity_mod.identity_dir(prefix) / LOCAL_MANIFEST


def local_manifest(prefix: str) -> dict:
    path = local_manifest_path(prefix)
    return (common.load_yaml(path) or {}) if path.exists() else {}


def pinned_version(prefix: str) -> Optional[int]:
    """Версия шаблона, на которой стоит локальная идентичность."""
    value = local_manifest(prefix).get("template_version")
    return int(value) if value is not None else None


def template_of(prefix: str) -> Optional[str]:
    return local_manifest(prefix).get("template")


def update_available(prefix: str) -> Optional[dict]:
    """{template, from, to, entries} если шаблон ушёл вперёд, иначе None."""
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
    """Разделы CHANGELOG.md шаблона новее указанной версии.

    Разбор нужен только для того, чтобы ПОКАЗАТЬ человеку, что изменилось.
    Решение о наличии обновления принимается по числу в манифесте, поэтому
    сломанный или отстающий changelog не может привести к неверному запуску —
    в худшем случае человек увидит меньше пояснений.
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
#  Клонирование и обновление
# --------------------------------------------------------------------------

def _template_payload(name: str) -> List[Path]:
    """Файлы шаблона, которые копируются в локальную идентичность."""
    skip = {TEMPLATE_MANIFEST}
    return [p for p in sorted(template_dir(name).iterdir())
            if p.is_file() and p.name not in skip]


def clone(name: str, prefix: str, full_name: str) -> Path:
    """Создаёт локальную идентичность из шаблона. Возвращает её папку."""
    import identity as identity_mod

    if prefix in identity_mod.identity_folders():
        raise TemplateError(
            f"Идентичность с префиксом '{prefix}' уже есть: "
            f"{identity_mod.identity_dir(prefix)}"
        )
    if not identity_mod.PREFIX_RE.match(prefix):
        raise TemplateError(
            f"неверный формат префикса '{prefix}'. {identity_mod.PREFIX_RULE_TEXT}")

    version = template_version(name)
    target = common.IDENTITIES_DIR / identity_mod.folder_name_for(prefix, full_name)
    (target / TEMPLATE_COPY_DIR).mkdir(parents=True)
    (target / DOCUMENTS_DIR).mkdir(exist_ok=True)

    template_prefix = name
    for src in _template_payload(name):
        # Имена файлов приводятся к префиксу новой идентичности: всё остальное
        # в проекте ищет файлы по шаблону "<префикс>_<документ>".
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
        f"# Журнал изменений идентичности «{full_name}»\n\n"
        "Новые записи добавляются СВЕРХУ. Локальные изменения всегда идут\n"
        "первым разделом: они по определению новее любой версии шаблона.\n\n"
        "## Локальные изменения\n\n"
        "_Пока нет._\n\n"
        f"## Создана из шаблона {name} v{version}\n\n"
        f"Копия шаблона лежит в `{TEMPLATE_COPY_DIR}/` и не редактируется.\n"
        "Свои настройки пишите файлами рядом — они накладываются поверх.\n",
        encoding="utf-8",
    )
    return target


def apply_update(prefix: str) -> dict:
    """Ставит локальную идентичность на текущую версию шаблона.

    Это ЗАМЕНА папки `template/`, а не слияние: личные настройки лежат
    отдельными файлами и не участвуют в операции вообще. Поэтому здесь нет и
    не может быть решения "что перезаписать, а что подправить".
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
        note = (f"## Обновлено до {name} v{info['to']}\n\n"
                + "\n".join(f"- {e['title']}" for e in info["entries"]) + "\n\n")
        marker = "## Локальные изменения"
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
    """Ключи, которые человек переопределил И которые изменил шаблон.

    Именно это и есть весь «конфликт» при обновлении — точный список, а не
    предмет для размышления. Переопределение продолжает действовать (оно
    сильнее), поэтому список информационный: человек решает, не устарела ли
    его правка.
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
        description="Шаблоны идентичностей: список, клонирование, обновление"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="Показать доступные шаблоны")

    p_clone = sub.add_parser("clone", help="Создать свою идентичность из шаблона")
    p_clone.add_argument("template", help="Имя шаблона (см. list)")
    p_clone.add_argument("prefix", help="Префикс новой идентичности")
    p_clone.add_argument("name", help="Расшифровка латиницей, для имени папки")

    p_check = sub.add_parser("check", help="Не ушёл ли шаблон вперёд")
    p_check.add_argument("--identity", required=True)

    p_update = sub.add_parser("update", help="Поставить на текущую версию шаблона")
    p_update.add_argument("--identity", required=True)

    args = parser.parse_args()

    if args.cmd == "list":
        found = template_folders()
        if not found:
            print(f"Шаблонов нет: {common.TEMPLATES_DIR} пуста.")
            return
        print(f"Шаблоны в {common.TEMPLATES_DIR}:\n")
        for name in sorted(found):
            manifest = template_manifest(name)
            summary = " ".join(str(manifest.get("summary") or "").split())
            print(f"  {name:<8} v{manifest.get('version', 1)}  {summary}")
            fits = " ".join(str(manifest.get("suitable_for") or "").split())
            if fits:
                print(f"           кому: {fits}")
        print("\n  Клонировать: python tools/templates.py clone <шаблон> <префикс> <расшифровка>")
        return

    if args.cmd == "clone":
        target = clone(args.template, args.prefix, args.name)
        print(f"Создана идентичность '{args.prefix}': {target}")
        print(f"  Копия шаблона:   {target / TEMPLATE_COPY_DIR}  (не редактировать)")
        print(f"  Ваши настройки:  {target / (args.prefix + '_profile.yaml')}")
        print(f"  Личные файлы:    {target / DOCUMENTS_DIR}")
        print("\n  Дальше — docs/ONBOARDING.md: заполнить профиль вместе с агентом.")
        return

    info = update_available(args.identity)
    if args.cmd == "check":
        if not info:
            pinned = pinned_version(args.identity)
            name = template_of(args.identity)
            print(f"Обновлений нет: '{args.identity}' стоит на {name} v{pinned}."
                  if name else f"'{args.identity}' не создана из шаблона — обновлять нечего.")
            return
        print(f"Шаблон '{info['template']}' ушёл вперёд: v{info['from']} -> v{info['to']}\n")
        for entry in info["entries"]:
            print(f"  {entry['title']}")
            for line in entry["lines"][:4]:
                print(f"      {line}")
        print(f"\n  Обновить: python tools/templates.py update --identity {args.identity}")
        return

    if args.cmd == "update":
        if not info:
            print("Обновлений нет.")
            return
        result = apply_update(args.identity)
        print(f"Обновлено: v{result['from']} -> v{result['to']}")
        if result.get("conflicts"):
            print("\n  Ваши переопределения продолжают действовать (они сильнее шаблона).")
            print("  Проверьте, не устарели ли они после обновления:")
            for key in result["conflicts"][:20]:
                print(f"    - {key}")


if __name__ == "__main__":
    main()
