"""
Поисковые идентичности: реестр, валидация, разрешение активной.

ЗАЧЕМ ЭТО СУЩЕСТВУЕТ
--------------------
Проект обслуживает разных людей с разными профилями поиска. Смешение их данных —
худший из отказов: тихий, невидимый в отчёте, систематически портящий результат.
Поэтому "какая идентичность активна" — не удобная настройка, а обязательное
состояние, без которого система отказывается работать (Большая Конституция,
правило №0).

ЧТО ТАКОЕ ИДЕНТИЧНОСТЬ
----------------------
Папка `identities/<префикс>/`, где ВСЕ файлы начинаются с `<префикс>_`. Префикс —
короткая звучная латинская аббревиатура, осмысленно описывающая суть поиска
(например `kisel` = Keep It Simple, Easy, Legacy). Единое префиксование —
не косметика: два файла `notes.md` в разных папках агент однажды перепутает,
`kisel_notes.md` и `jvst_notes.md` — практически нет.

ГДЕ ЖИВЁТ "КАКАЯ ИДЕНТИЧНОСТЬ МОЯ"
-----------------------------------
В Малой Конституции — `local-constitution/`, которой нет в гите (у каждого
человека и каждой машины она своя). Её спецификация — в
`docs/LOCAL_CONSTITUTION.md`, скелет для копирования — в
`docs/templates/local-constitution/`.
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

# Префикс: 3-6 латинских строчных букв/цифр, начинается с буквы.
# Коротко — чтобы имена файлов оставались читаемыми; строчные — чтобы не
# зависеть от регистронезависимости файловой системы Windows.
PREFIX_RE = re.compile(r"^[a-z][a-z0-9]{2,5}$")

PREFIX_RULE_TEXT = (
    "Префикс идентичности: 3-6 символов, только строчные латинские буквы и цифры, "
    "первый символ — буква. Должен быть звучным и осмысленно описывать суть поиска "
    "(например: kisel = Keep It Simple, Easy, Legacy)."
)

# Имя папки идентичности: <префикс>-<расшифровка-через-дефис>.
# Например `kisel-keep-it-simple-easy-legacy`.
#
# ЗАЧЕМ ДВА УРОВНЯ ИМЕНОВАНИЯ. Папку видно в дереве проекта редко, но когда
# видно — по одному `kisel` невозможно вспомнить, что это за поиск и зачем он
# заводился. Расшифровка в имени папки отвечает на этот вопрос без открытия
# файлов. А вот ФАЙЛЫ внутри остаются короткими (`kisel_criteria.yaml`, а не
# `kisel-keep-it-simple-easy-legacy_criteria.yaml`): их имена встречаются в
# каждой команде, в выводе grep, во вкладках редактора и в путях внутри
# отчётов — длинное имя там только мешает читать.
FOLDER_RE = re.compile(r"^([a-z][a-z0-9]{2,5})(-[a-z0-9]+(?:-[a-z0-9]+)*)?$")

FOLDER_RULE_TEXT = (
    "Имя папки идентичности: <префикс>-<расшифровка через дефис>, только строчные "
    "латинские буквы, цифры и дефисы (например: kisel-keep-it-simple-easy-legacy). "
    "Расшифровка объясняет, что это за поиск; файлы внутри остаются короткими и "
    "начинаются с одного лишь префикса."
)

# Файлы, без которых идентичность считается неполной. Порядок = порядок проверки.
REQUIRED_FILES = (
    "identity.md",        # человекочитаемое описание: что это, для кого, как работает
    "profile.yaml",       # кто владелец идентичности и что он ищет
    "criteria.yaml",      # рубрика скоринга
    "sources.yaml",       # какие источники включены и с какими параметрами
    "questionnaire.yaml",  # заполненный вопросник — origin story идентичности
)

# Папки в identities/, которые идентичностями не являются.
NON_IDENTITY_DIRS = {"__pycache__"}


class IdentityError(RuntimeError):
    """Базовая ошибка системы идентичностей."""


class UnknownIdentityError(IdentityError):
    pass


class InvalidIdentityError(IdentityError):
    pass


class IdentityNotReadyError(IdentityError):
    """Идентичность структурно цела, но ещё не заполнена ответами человека.

    Отдельный класс, а не InvalidIdentityError: это не поломка, а нормальная
    стадия онбординга, и сообщение о ней должно звучать иначе — «осталось
    заполнить вот это», а не «что-то сломано».
    """


# --- Реестр ---------------------------------------------------------------

def folder_prefix(folder_name: str) -> Optional[str]:
    """'kisel-keep-it-simple-easy-legacy' -> 'kisel'. None, если имя не подходит."""
    m = FOLDER_RE.match(folder_name)
    return m.group(1) if m else None


def identity_folders() -> dict:
    """Отображение префикс -> папка. Единственное место, которое знает, что
    имя папки длиннее префикса; всё остальное работает с префиксами."""
    result = {}
    if not common.IDENTITIES_DIR.exists():
        return result
    for path in sorted(common.IDENTITIES_DIR.iterdir()):
        if not path.is_dir() or path.name.startswith("_") or path.name in NON_IDENTITY_DIRS:
            continue
        prefix = folder_prefix(path.name)
        if prefix is None:
            continue  # мусор в identities/ — про него скажет validate_layout()
        if prefix in result:
            # Две папки с одним префиксом — неразрешимая неоднозначность:
            # какая из них "та самая", определить нечем, а тихий выбор одной
            # из двух даст перемешанные данные.
            raise InvalidIdentityError(
                f"две папки с префиксом '{prefix}': {result[prefix].name} и {path.name}. "
                "Префикс обязан быть уникальным — переименуйте одну из папок."
            )
        result[prefix] = path
    return result


def list_identities(include_fixtures: bool = False) -> List[str]:
    """Префиксы всех идентичностей репозитория. Папки, начинающиеся с "_"
    (например `_template`), идентичностями не считаются — это заготовки."""
    found = []
    for prefix in identity_folders():
        if not include_fixtures and _read_kind(prefix) == "fixture":
            continue
        found.append(prefix)
    return found


def identity_dir(prefix: str) -> Path:
    """Папка идентичности по префиксу.

    Если папки ещё нет (её только собираются создать) — возвращается путь вида
    `identities/<префикс>`, без расшифровки: имя с расшифровкой знает только
    тот, кто создаёт идентичность, и передаёт его явно.
    """
    folder = identity_folders().get(prefix)
    return folder if folder is not None else common.IDENTITIES_DIR / prefix


def identity_file(prefix: str, name: str) -> Path:
    """('kisel', 'criteria.yaml') -> identities/kisel/kisel_criteria.yaml"""
    return identity_dir(prefix) / f"{prefix}_{name}"


def _read_kind(prefix: str) -> Optional[str]:
    """kind идентичности без её активации: personal | shared_example | fixture."""
    profile_path = identity_file(prefix, "profile.yaml")
    if not profile_path.exists():
        return None
    try:
        data = common.load_yaml(profile_path) or {}
        return (data.get("identity") or {}).get("kind")
    except Exception:  # noqa: BLE001 - битый YAML разберёт validate()
        return None


def describe(prefix: str) -> str:
    """Короткая строка для баннеров и сообщений об ошибке."""
    try:
        data = common.load_yaml(identity_file(prefix, "profile.yaml")) or {}
        meta = data.get("identity") or {}
        name = meta.get("display_name") or meta.get("name") or ""
        return f"{prefix} — {name}" if name else prefix
    except Exception:  # noqa: BLE001
        return prefix


# --- Валидация ------------------------------------------------------------

def validate(prefix: str, *, strict_prefix_check: bool = True) -> List[str]:
    """Возвращает список проблем (пустой = идентичность в порядке).

    Проверяет ровно то, что защищает от путаницы между идентичностями:
    формат префикса, наличие обязательных файлов, префиксование ВСЕХ файлов
    внутри папки, и отсутствие ссылок на чужие префиксы в содержимом.
    """
    problems: List[str] = []

    if not PREFIX_RE.match(prefix):
        problems.append(f"неверный формат префикса '{prefix}'. {PREFIX_RULE_TEXT}")
        return problems  # дальше проверять бессмысленно

    d = identity_dir(prefix)
    if not d.is_dir():
        problems.append(f"папка идентичности не найдена: {d}")
        return problems

    # Имя папки обязано содержать расшифровку: `kisel` не говорит ничего, а
    # `kisel-keep-it-simple-easy-legacy` объясняет, что это за поиск, прямо в
    # дереве проекта. Это единственное место, где длинное имя уместно.
    if folder_prefix(d.name) == d.name:
        problems.append(
            f"папка '{d.name}' названа одним префиксом, без расшифровки. {FOLDER_RULE_TEXT}"
        )

    for name in REQUIRED_FILES:
        path = identity_file(prefix, name)
        if not path.exists():
            problems.append(f"нет обязательного файла: {path.name} (ожидался в {d})")

    if strict_prefix_check:
        for path in sorted(d.iterdir()):
            if path.is_dir():
                problems.append(
                    f"вложенная папка '{path.name}' в идентичности — не поддерживается, "
                    "все файлы идентичности должны лежать плоско и иметь префикс"
                )
                continue
            if not path.name.startswith(f"{prefix}_"):
                problems.append(
                    f"файл '{path.name}' не начинается с '{prefix}_' — правило единого "
                    "префикса нарушено (именно оно защищает от путаницы между идентичностями)"
                )

    problems.extend(_check_foreign_prefix_leaks(prefix))
    return problems


# Начало сообщения о незаполненных ЛИЧНЫХ полях. Вынесено в константу, чтобы
# тесты и вызывающий код отличали «не хватает личных данных» (нормальная стадия
# на чужой машине) от «идентичность собрана неполно» (дефект самой идентичности),
# не завися от точной формулировки текста.
LOCAL_FIELDS_MISSING_PREFIX = "не заполнены личные поля"

# Плейсхолдер шаблона: `<что-то>` в угловых скобках. Ровно так размечены поля,
# которые человек должен заполнить своими ответами.
PLACEHOLDER_RE = re.compile(r"<[^<>\n]{2,80}>")

# Поля профиля, без которых поиск бессмысленен. Список намеренно короткий: это
# не «всё, что хорошо бы заполнить», а «без этого скоринг выдаёт мусор».
REQUIRED_PROFILE_FIELDS = (
    ("owner.languages", "языки — из них выводится языковой фильтр"),
    ("owner.location", "резидентство — из него выводятся гео-правила"),
    ("tech_stack.core", "core-стек — без него гейт релевантности пропускает всё подряд"),
)


def readiness_problems(prefix: str) -> List[str]:
    """Чего не хватает, чтобы идентичность можно было использовать для поиска.

    Отличается от validate(): та проверяет СТРУКТУРУ (файлы на месте, префиксы
    верные), а эта — СОДЕРЖАНИЕ (человек ответил на обязательные вопросы).
    Заготовка из шаблона структурно безупречна и при этом совершенно непригодна.
    """
    problems: List[str] = []
    d = identity_dir(prefix)
    if not d.is_dir():
        return [f"папка идентичности не найдена: {d}"]

    profile_raw = common.load_yaml(identity_file(prefix, "profile.yaml")) or {}
    profile, missing_local = common.resolve_local_fields(prefix, profile_raw)

    if missing_local:
        # Одной строкой, а не по строке на поле: на свежем клоне таких полей
        # семь, и семь одинаковых предложений с повторённым путём читаются
        # как стена текста вместо понятной задачи.
        overlay_path = common.personal_dir(prefix) / f"{prefix}_owner.yaml"
        problems.append(
            f"{LOCAL_FIELDS_MISSING_PREFIX} (помечены как `local`): "
            + ", ".join(missing_local)
            + f".\n    Их место — {overlay_path}"
            + "\n    Заготовку этого файла создаёт `python tools/identity.py "
            f"init-local --identity {prefix}`"
        )

    for dotted, why in REQUIRED_PROFILE_FIELDS:
        node = profile
        for part in dotted.split("."):
            node = (node or {}).get(part) if isinstance(node, dict) else None
        if not node:
            problems.append(f"не заполнено {dotted} ({why})")

    # Плейсхолдеры шаблона в ЗНАЧЕНИЯХ YAML-файлов идентичности.
    #
    # Именно в значениях, а не в тексте файла: угловые скобки сплошь и рядом
    # встречаются в комментариях как часть документации ("<token> подставьте
    # сюда", "<TZ> ±N часов"). Первая версия проверки читала файл целиком и
    # объявляла заполненную идентичность незаполненной. YAML-парсер отбрасывает
    # комментарии — этого достаточно, чтобы проверка стала точной.
    for path in sorted(d.glob("*.yaml")):
        try:
            data = common.load_yaml(path)
        except Exception:  # noqa: BLE001 — битый YAML разберёт validate()
            continue
        found = sorted(set(_placeholders_in_values(data)))
        if found:
            shown = ", ".join(found[:3]) + (" ..." if len(found) > 3 else "")
            problems.append(f"{path.name}: остались незаполненные плейсхолдеры ({shown})")

    return problems


def _placeholders_in_values(node):
    """Все плейсхолдеры шаблона среди строковых ЗНАЧЕНИЙ структуры."""
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
    """Ищет в файлах идентичности упоминания ЧУЖИХ префиксов вида `abcd_`.

    Ловит самую вероятную ошибку при создании новой идентичности — копипасту
    из чужой папки с недоправленными путями.
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
            continue  # бинарник или нечитаемый файл — не наше дело
        for other in others:
            token = f"{other}_"
            if token in text:
                problems.append(
                    f"в файле {path.name} встречается чужой префикс '{token}' — "
                    f"похоже на копипасту из идентичности '{other}'"
                )
    return problems


def validate_all() -> dict:
    """Прогоняет validate() по всем идентичностям, включая фикстуры."""
    return {p: validate(p) for p in list_identities(include_fixtures=True)}


# --- Малая Конституция ----------------------------------------------------

def local_constitution_path() -> Path:
    return common.LOCAL_CONSTITUTION_DIR / "active.yaml"


def load_local_constitution() -> dict:
    """Читает local-constitution/active.yaml. Отсутствие файла — не ошибка:
    это нормальное состояние машины, где онбординг ещё не проводили."""
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


# --- Разрешение активной идентичности -------------------------------------

def resolve_identity(cli_value: Optional[str] = None) -> str:
    """Строгий приоритет, без встроенных дефолтов:

      1. --identity <префикс>            (явное намерение всегда побеждает)
      2. WORK_IDE_IDENTITY            (подпроцессы, CI, тесты)
      3. active.yaml -> default_identity
      4. active.yaml -> единственная активная
      5. отказ

    Никогда не угадывает при нескольких активных без дефолта: молчаливый выбор
    "не той" идентичности — ровно тот отказ, ради предотвращения которого вся
    эта система и построена.
    """
    if cli_value:
        return cli_value

    env_value = os.environ.get("WORK_IDE_IDENTITY")
    if env_value:
        return env_value

    default = default_identity()
    if default:
        return default

    active = active_identities()
    if len(active) == 1:
        return active[0]

    if not active:
        raise IdentityError(_no_identity_message())
    raise IdentityError(_ambiguous_identity_message(active))


def _no_identity_message() -> str:
    available = list_identities()
    available_str = ", ".join(available) if available else "(в репозитории пока нет ни одной)"
    return (
        "Не выбрана поисковая идентичность — работать без неё запрещено "
        "(Большая Конституция, правило №0).\n"
        f"  Идентичности в репозитории: {available_str}\n"
        f"  Малая Конституция ожидается здесь: {common.LOCAL_CONSTITUTION_DIR}\n"
        "  Что делать: провести онбординг по docs/ONBOARDING.md — спросить у человека "
        "CV/LinkedIn/описание, заполнить вопросник, создать идентичность и "
        "зарегистрировать её в local-constitution/active.yaml.\n"
        "  Разово можно указать явно: --identity <префикс>"
    )


def _ambiguous_identity_message(active: List[str]) -> str:
    lines = "\n".join(f"    - {describe(p)}" for p in active)
    return (
        "Активных идентичностей несколько, а default_identity не задан — "
        "угадывать нельзя.\n"
        f"{lines}\n"
        "  Укажите явно: --identity <префикс>, либо задайте default_identity "
        f"в {local_constitution_path()}"
    )


def activate(cli_value: Optional[str] = None, *, allow_fixture: bool = False) -> str:
    """Разрешает и активирует идентичность. Возвращает префикс."""
    prefix = resolve_identity(cli_value)
    common.activate_identity(prefix, allow_fixture=allow_fixture)
    return prefix


def banner(prefix: Optional[str] = None) -> str:
    """Строка, которую каждый инструмент печатает первой. Активная идентичность
    никогда не должна быть невидимой."""
    prefix = prefix or common.ACTIVE_IDENTITY
    return f"[identity: {describe(prefix)}]"


def standalone_main(fetch_fn, source_name: str) -> None:
    """Точка входа для standalone-запуска фетчера: `python tools/fetch_x.py`.

    Фетчеры полезно уметь дёргать поодиночке при отладке источника, но они
    читают User-Agent и (некоторые) стек из активной идентичности — поэтому
    активировать её нужно и здесь.
    """
    parser = argparse.ArgumentParser(description=f"Одиночный запуск источника {source_name}")
    add_identity_arg(parser)
    args = parser.parse_args()
    activate_or_exit(args.identity)

    records, err = fetch_fn()
    print(f"{source_name}: fetched {len(records)} records" + (f" | note: {err}" if err else ""))


def add_identity_arg(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Добавляет --identity. Один вызов вместо копипасты в каждом инструменте."""
    parser.add_argument(
        "--identity", default=None,
        help="Префикс поисковой идентичности (по умолчанию — из Малой Конституции)",
    )
    return parser


def activate_or_exit(cli_value: Optional[str] = None, *, quiet: bool = False) -> str:
    """Активирует идентичность или завершает процесс с понятным объяснением.

    Стандартная точка входа для всех CLI-инструментов: отказ без идентичности
    должен быть громким и с инструкцией, а не трассировкой стека.
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
        print("В репозитории нет ни одной идентичности.")
        return
    active = set(active_identities())
    default = default_identity()
    print(f"Идентичности в {common.IDENTITIES_DIR}:")
    for prefix in identities:
        kind = _read_kind(prefix) or "?"
        marks = []
        if prefix in active:
            marks.append("активна")
        if prefix == default:
            marks.append("по умолчанию")
        mark_str = f"  [{', '.join(marks)}]" if marks else ""
        print(f"  {prefix:<8} kind={kind:<14} {describe(prefix)}{mark_str}")


def clone_identity(source: str, prefix: str, full_name: str) -> List[Path]:
    """Копирует существующую идентичность под новым префиксом.

    ЗАЧЕМ. Самый частый случай — один и тот же поиск, привязанный к разным
    странам: «то же самое, но для Германии» и «то же самое, но для Канады».
    Стек, тип занятости, признаки подходящей компании у них общие, а
    гео-правила, языковой фильтр и часовой пояс — разные. Собирать вторую
    идентичность с нуля значит переотвечать на 50 вопросов ради изменения трёх.

    Отличие от `new`: `new` даёт пустую заготовку, `clone` — заполненную копию,
    в которой нужно поправить только то, что действительно отличается.

    Все внутренние ссылки на префикс-источник переписываются на новый — иначе
    клон нарушил бы правило «файлы одной идентичности не ссылаются на другую»
    и был бы отвергнут валидатором.
    """
    if source == prefix:
        raise InvalidIdentityError("исходный и новый префиксы совпадают")
    src_dir = identity_folders().get(source)
    if src_dir is None:
        raise UnknownIdentityError(
            f"идентичность '{source}' не найдена. Доступные: "
            + (", ".join(list_identities(include_fixtures=True)) or "нет ни одной")
        )
    if _read_kind(source) == "fixture":
        raise InvalidIdentityError(
            f"'{source}' — замороженная тестовая фикстура, клонировать её нельзя: "
            "она откалибрована под тесты, а не под живой поиск"
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


TEMPLATE_DIR_NAME = "_template"
TEMPLATE_PREFIX = "tmpl"

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

    template = common.IDENTITIES_DIR / TEMPLATE_DIR_NAME
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
