"""
Самопроверка окружения Work IDE. Запускать после клонирования репозитория
на новой машине или если пайплайн ведёт себя странно.

python tools/doctor.py --identity <префикс>

Возвращает exit code 0, если все КРИТИЧНЫЕ проверки (идентичность, Python,
зависимости, конфиги, запись в data/) прошли. Проверки доступности внешних
источников — предупреждения, а не фатальные ошибки (сеть может быть недоступна
прямо сейчас, это не повод считать окружение сломанным).
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
    _report("Python >= 3.8", ok, f"текущая: {sys.version.split()[0]}")


def check_packages() -> None:
    for mod in ("requests", "yaml"):
        try:
            __import__(mod)
            _report(f"пакет '{mod}'", True)
        except ImportError as exc:
            _report(f"пакет '{mod}'", False, str(exc))


def check_identity() -> None:
    """Первая и главная проверка: есть ли активная идентичность и цела ли она."""
    import identity as identity_mod

    _report(f"активная идентичность: {identity_mod.describe(common.ACTIVE_IDENTITY)}", True)
    problems = identity_mod.validate(common.ACTIVE_IDENTITY)
    if problems:
        for p in problems:
            _report("структура идентичности", False, p)
    else:
        _report("структура идентичности", True)


def check_configs() -> dict:
    configs = {}
    for name, required_keys in (
        ("profile.yaml", ["owner", "goal", "tech_stack", "employment_type_priority"]),
        ("criteria.yaml", ["weights", "remote_location_fit", "classification_thresholds"]),
        ("sources.yaml", ["sources"]),
    ):
        path = common.identity_config(name)
        label = f"identities/{common.ACTIVE_IDENTITY}/{path.name}"
        try:
            data = common.load_yaml(path) or {}
            missing = [k for k in required_keys if k not in data]
            ok = not missing
            _report(label, ok, f"отсутствуют ключи: {missing}" if missing else "")
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
        _report("data/ доступна для записи", True)
    except Exception as exc:  # noqa: BLE001
        _report("data/ доступна для записи", False, str(exc))


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
            _report(f"источник '{src['name']}' доступен", ok, f"HTTP {resp.status_code}", critical=False)
        except Exception as exc:  # noqa: BLE001
            _report(f"источник '{src['name']}' доступен", False, str(exc), critical=False)


def check_reputation_coverage() -> None:
    """Сколько компаний головы выдачи не имеет результата проверки репутации.

    Не критично для запуска — это про полноту накопленного знания, а не про
    работоспособность окружения. Но видеть цифру полезно: 2026-08-06 в голове
    выдачи было 55 компаний и ноль проверок, и заметить это можно было только
    прочитав отчёт целиком.
    """
    import kb
    import reputation

    try:
        vacancies = kb.load_vacancies()
        companies = kb.load_companies()
    except Exception as exc:  # noqa: BLE001 — база может быть ещё не собрана
        print(f"  [ SKIP ] репутация компаний: база не читается ({type(exc).__name__})")
        return

    stats = reputation.coverage(vacancies, companies)
    if not stats["companies"]:
        print("  [ SKIP ] репутация компаний: в выдаче пока некого проверять")
        return
    mark = "OK  " if not stats["unchecked"] else "WARN"
    print(f"  [ {mark} ] репутация компаний головы выдачи: "
          f"найдена {stats['found']}, источников мало {stats['insufficient']}, "
          f"НЕ ПРОВЕРЕНО {stats['unchecked']} из {stats['companies']}")
    if stats["unchecked"]:
        print("           закрыть: python tools/reputation.py worklist "
              f"--identity {common.ACTIVE_IDENTITY}")


def main() -> None:
    import identity as identity_mod

    parser = argparse.ArgumentParser(description="Самопроверка окружения Work IDE")
    parser.add_argument("--identity", default=None, help="Префикс поисковой идентичности")
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
    print("--- Проверка доступности источников (не критично для работы) ---")
    check_sources_reachable()
    print()
    if CRITICAL_OK:
        print(
            "Итог: окружение в порядке, можно запускать "
            f"python tools/pipeline.py --identity {common.ACTIVE_IDENTITY}"
        )
        sys.exit(0)
    else:
        print("Итог: есть критичные проблемы, см. FAIL выше.")
        sys.exit(1)


if __name__ == "__main__":
    main()
