"""
Одноразовая миграция: конфигурация и данные одного пользователя → идентичность.

Переносит наследие «одного владельца» (config/*.yaml + data/knowledge + data/
reports + data/raw + data/state.json) в структуру идентичностей:

    config/profile.yaml            -> identities/<p>/<p>_profile.yaml
    config/criteria.yaml           -> identities/<p>/<p>_criteria.yaml
    config/sources.yaml            -> identities/<p>/<p>_sources.yaml
    config/ats_targets.yaml        -> identities/<p>/<p>_ats_targets.yaml
    data/knowledge/vacancies.json  -> data/<p>/knowledge/<p>_vacancies.json
    data/knowledge/companies.json  -> data/<p>/knowledge/<p>_companies.json
    data/knowledge/insights.md     -> data/<p>/knowledge/<p>_insights.md
    data/state.json                -> data/<p>/<p>_state.json
    data/reports/latest.md         -> reports/<p>_latest.md
    data/reports/<дата>.md         -> reports/archive/<p>/<дата>.md
    data/raw/<источник>/*.jsonl    -> data/<p>/raw/<источник>/*.jsonl

БЕЗОПАСНОСТЬ: по умолчанию — сухой прогон, ничего не трогает. Копирует, а не
перемещает; оригиналы удаляются только отдельным вызовом --cleanup и только
после того, как копии проверены. Накопленная база знаний — самый ценный
артефакт проекта, восстановить её неоткуда.

Скрипт идемпотентен: повторный --apply просто перезапишет копии.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

LEGACY_CONFIG_DIR = common.ROOT / "config"
LEGACY_DATA_DIR = common.ROOT / "data"

CONFIG_FILES = ("profile.yaml", "criteria.yaml", "sources.yaml", "ats_targets.yaml")
KNOWLEDGE_FILES = (
    ("vacancies.json", "vacancies.json"),
    ("companies.json", "companies.json"),
    ("recruiters.json", "recruiters.json"),
    ("insights.md", "insights.md"),
)


def plan_moves(prefix: str, data_root: Optional[Path] = None) -> List[Tuple[Path, Path]]:
    """Список (откуда, куда). Отсутствующие источники молча пропускаются:
    не у всех есть recruiters.json или архив отчётов."""
    root = data_root or common.DATA_ROOT
    identity_dir = common.IDENTITIES_DIR / prefix
    data_dir = root / prefix
    moves: List[Tuple[Path, Path]] = []

    for name in CONFIG_FILES:
        src = LEGACY_CONFIG_DIR / name
        if src.exists():
            moves.append((src, identity_dir / f"{prefix}_{name}"))

    for src_name, dst_name in KNOWLEDGE_FILES:
        src = LEGACY_DATA_DIR / "knowledge" / src_name
        if src.exists():
            moves.append((src, data_dir / "knowledge" / f"{prefix}_{dst_name}"))

    state = LEGACY_DATA_DIR / "state.json"
    if state.exists():
        moves.append((state, data_dir / f"{prefix}_state.json"))

    # Отчёты уезжают НЕ в data/<p>/, а в общую папку reports/ в корне
    # репозитория: это единственные файлы, которые человек открывает руками.
    reports_dir = LEGACY_DATA_DIR / "reports"
    if reports_dir.is_dir():
        for src in sorted(reports_dir.glob("*.md")):
            if src.name == "latest.md":
                moves.append((src, common.REPORTS_ROOT / f"{prefix}_latest.md"))
            else:
                # Датированные уходят в архив, разложенный по идентичностям:
                # в корне reports/ должны остаться только свежие подборки,
                # иначе через полгода там сотня файлов.
                moves.append((src, common.REPORTS_ROOT / "archive" / prefix / src.name))

    raw_dir = LEGACY_DATA_DIR / "raw"
    if raw_dir.is_dir():
        for src in sorted(raw_dir.rglob("*.jsonl")):
            moves.append((src, data_dir / "raw" / src.relative_to(raw_dir)))

    return moves


def verify_copy(src: Path, dst: Path) -> Optional[str]:
    """Проверяет копию: размер и, для JSON, разбираемость. Возвращает описание
    проблемы или None."""
    if not dst.exists():
        return "файл не создан"
    if src.stat().st_size != dst.stat().st_size:
        return f"размер не совпал: {src.stat().st_size} -> {dst.stat().st_size}"
    if dst.suffix == ".json":
        try:
            json.loads(dst.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            return f"копия не разбирается как JSON: {type(exc).__name__}"
    return None


def do_migration(prefix: str, moves: List[Tuple[Path, Path]], apply: bool) -> int:
    total_bytes = sum(src.stat().st_size for src, _ in moves)
    print(f"Файлов к переносу: {len(moves)} ({total_bytes / 1024 / 1024:.1f} МБ)")
    print()

    problems = 0
    for src, dst in moves:
        rel_src = src.relative_to(common.ROOT)
        rel_dst = dst.relative_to(common.ROOT) if common.ROOT in dst.parents else dst
        size_mb = src.stat().st_size / 1024 / 1024
        size_str = f"{size_mb:6.1f} МБ" if size_mb >= 0.1 else "        "

        if not apply:
            print(f"  [dry-run] {size_str}  {rel_src}  ->  {rel_dst}")
            continue

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        problem = verify_copy(src, dst)
        if problem:
            problems += 1
            print(f"  [FAIL]    {size_str}  {rel_src}  ->  {rel_dst}   {problem}")
        else:
            print(f"  [ok]      {size_str}  {rel_src}  ->  {rel_dst}")

    if apply and not problems:
        marker = (common.DATA_ROOT / prefix / ".identity")
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(f"{prefix}\n", encoding="utf-8")
        print(f"\n  [ok]      маркер владельца данных: {marker}")

    return problems


def do_cleanup(moves: List[Tuple[Path, Path]], apply: bool) -> int:
    """Удаляет оригиналы — только те, чьи копии на месте и целы."""
    removed = 0
    for src, dst in moves:
        problem = verify_copy(src, dst) if dst.exists() else "копии нет"
        if problem:
            print(f"  [SKIP] {src.relative_to(common.ROOT)} — копия не подтверждена ({problem})")
            continue
        if apply:
            src.unlink()
        removed += 1
        prefix_label = "[removed]" if apply else "[dry-run]"
        print(f"  {prefix_label} {src.relative_to(common.ROOT)}")
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Переносит конфигурацию и данные одного пользователя в идентичность"
    )
    parser.add_argument("--prefix", required=True, help="Префикс целевой идентичности")
    parser.add_argument("--apply", action="store_true",
                        help="Выполнить перенос (без флага — сухой прогон)")
    parser.add_argument("--cleanup", action="store_true",
                        help="Удалить оригиналы после подтверждённого переноса")
    args = parser.parse_args()

    moves = plan_moves(args.prefix)
    if not moves:
        print("Нечего переносить: старая раскладка не найдена.")
        return

    if args.cleanup:
        print(f"=== Удаление оригиналов ({'РЕАЛЬНО' if args.apply else 'сухой прогон'}) ===\n")
        removed = do_cleanup(moves, args.apply)
        print(f"\nГотово: {'удалено' if args.apply else 'будет удалено'} {removed} из {len(moves)}")
        if not args.apply:
            print("Для реального удаления добавьте --apply")
        return

    print(f"=== Перенос в идентичность '{args.prefix}' "
          f"({'РЕАЛЬНО' if args.apply else 'сухой прогон'}) ===\n")
    problems = do_migration(args.prefix, moves, args.apply)

    if not args.apply:
        print("\nЭто был сухой прогон. Для переноса добавьте --apply")
        print("Оригиналы НЕ удаляются: после проверки запустите с --cleanup --apply")
    elif problems:
        print(f"\nПРОБЛЕМ: {problems}. Оригиналы не тронуты, разберитесь перед --cleanup.")
        sys.exit(1)
    else:
        print("\nПеренос завершён, все копии проверены. Оригиналы на месте.")
        print(f"Дальше: python tools/doctor.py --identity {args.prefix}")


if __name__ == "__main__":
    main()
