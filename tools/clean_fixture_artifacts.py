"""
Уборка следов тестовых фикстур из папок реальных данных и отчётов.

ЗАЧЕМ ЭТО СУЩЕСТВУЕТ
--------------------
Тесты работают от имени замороженной фикстуры (`ftf`). Если тест забыл
изолировать пути, он пишет в НАСТОЯЩИЕ `reports/` и `data/` — те самые папки,
куда человек смотрит. Так в отчётах завелись `ftf_latest.md` и
`reports/archive/ftf/`, а до них — пустые `aaaa` и `bbbb` от тестов изоляции.

Страховка в `tests/conftest.py` такие записи ОБНАРУЖИВАЕТ и роняет прогон.
Практика показала, что этого мало: 2026-08-04 страховка честно отработала,
причину я устранил, а сам файл так и остался лежать — и человек нашёл его
через сутки. Обнаружение без уборки оставляет мусор ровно там, где он мешает.

ПРИНЦИП БЕЗОПАСНОСТИ
--------------------
Модуль удаляет только то, что заведомо является следом фикстуры:

  * префикс должен принадлежать идентичности с `kind: fixture`;
  * удаляются РОВНО два пути: `reports/<p>_latest.md` и `reports/archive/<p>/`,
    плюс `data/<p>/`, если он появился;
  * ничего с другими именами не трогается ни при каких условиях.

Живые идентичности (`kind: personal`) не удаляются никогда, даже если явно
передать их префикс: перепутать флаг проще, чем восстановить накопленную базу.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402


def fixture_prefixes() -> List[str]:
    """Префиксы всех идентичностей с kind: fixture."""
    import identity as identity_mod

    return [p for p in identity_mod.list_identities(include_fixtures=True)
            if identity_mod._read_kind(p) == "fixture"]


def artifact_paths(prefix: str) -> List[Path]:
    """Пути, которые фикстура может создать в реальных папках."""
    return [
        common.REPORTS_ROOT / f"{prefix}_latest.md",
        common.REPORTS_ROOT / "archive" / prefix,
        common.DATA_ROOT / prefix,
    ]


def clean(prefixes: List[str] = None, dry_run: bool = False) -> List[str]:
    """Удаляет следы фикстур. Возвращает список того, что убрано."""
    import identity as identity_mod

    prefixes = prefixes if prefixes is not None else fixture_prefixes()
    removed: List[str] = []

    for prefix in prefixes:
        # Двойная проверка вместо доверия аргументу: удаление данных живой
        # идентичности необратимо, а опечатка в префиксе — дело одной секунды.
        if identity_mod._read_kind(prefix) != "fixture":
            raise ValueError(
                f"'{prefix}' — не тестовая фикстура (kind != fixture). "
                "Этот инструмент удаляет только следы фикстур."
            )

        for path in artifact_paths(prefix):
            if not path.exists():
                continue
            if not dry_run:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            removed.append(str(path))

    return removed


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Убрать следы тестовых фикстур из reports/ и data/"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Показать, что было бы удалено, ничего не трогая")
    args = parser.parse_args()

    removed = clean(dry_run=args.dry_run)
    if not removed:
        print("Следов тестовых фикстур не найдено — чисто.")
        return
    verb = "было бы удалено" if args.dry_run else "удалено"
    print(f"{verb.capitalize()}:")
    for path in removed:
        print(f"  - {path}")


if __name__ == "__main__":
    main()
