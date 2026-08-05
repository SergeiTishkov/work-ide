"""
Общие утилиты для всех скриптов Work IDE.

Никакой бизнес-логики поиска/скоринга здесь нет — только "скучная" инфраструктура:
пути, чтение/запись JSON и YAML, безопасная запись файлов, нормализация текста,
хэширование id.

КЛЮЧЕВОЕ: пути к конфигам и данным ЗАВИСЯТ ОТ АКТИВНОЙ ИДЕНТИЧНОСТИ и до вызова
`activate_identity()` равны None. Это сделано намеренно: система обслуживает
разных людей, и попытка прочитать/записать данные без явно выбранной идентичности
— ошибка, а не повод взять "какие-нибудь" пути (Большая Конституция, правило №0).

Почему перепривязка модульных переменных, а не объект-контекст: ни одно место в
проекте не читает эти константы на этапе импорта — все обращения идут как
`common.X` во время вызова. Поэтому перепривязка не требует править ~30 мест
вызова и не ломает monkeypatch в тестах. Процесс однопоточный и односеансовый:
одна активная идентичность на запуск — это ровно то ограничение, которое нужно.

Совместимо с Python 3.9 (стандартная библиотека + requests + PyYAML).
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
except ImportError:  # pragma: no cover — проверяется отдельным тестом
    # Первое, что видит человек на свежем клоне, если забыл поставить
    # зависимости, — это сообщение. Раньше здесь был голый traceback
    # `ModuleNotFoundError: yaml`: проект, который умеет по-человечески
    # объяснять любой свой отказ, спотыкался ровно на первом шаге.
    sys.stderr.write(
        "\n  Не установлены зависимости проекта (не найден модуль PyYAML).\n\n"
        "  Установите их:\n"
        "      python -m venv .venv\n"
        "      # Windows:       .venv\\Scripts\\activate\n"
        "      # macOS / Linux: source .venv/bin/activate\n"
        "      python -m pip install -r requirements.txt\n\n"
        "  Затем повторите команду. Зависимостей всего три, ключи API не нужны.\n\n"
    )
    raise SystemExit(1)

# --- Пути уровня репозитория (не зависят от идентичности) ----------------

ROOT = Path(__file__).resolve().parent.parent
SHARED_CONFIG_DIR = ROOT / "config"  # только общая машинерия, ничего личного

# Шаблоны идентичностей — в гите, общие для всех, без единого личного факта.
# Из них КЛОНИРУЮТ, ими не пользуются напрямую.
TEMPLATES_DIR = ROOT / "identity-templates"

# Рабочие идентичности — вне гита. Их количество и есть количество подборок,
# которые делает система: отдельного реестра активных идентичностей нет и не
# должно быть, потому что реестр умеет расходиться с реальностью, а папки нет.
IDENTITIES_DIR = Path(
    os.environ.get("WORK_IDE_IDENTITIES") or (ROOT / "local-identities")
)

# Замороженные фикстуры лежат рядом с тем, что их использует. Они находятся
# при обходе так же, как рабочие идентичности, но клонировать их нельзя и
# в списке шаблонов их нет.
FIXTURES_DIR = ROOT / "tests" / "fixtures"

# Оба переопределяются переменными окружения — нужно для тестов и для случая,
# когда данные лежат вне репозитория (например на другом диске).
DATA_ROOT = Path(os.environ.get("WORK_IDE_DATA_ROOT") or (ROOT / "data"))

# Отчёты намеренно живут ОТДЕЛЬНО от накопленных данных, в корне репозитория.
# Причина простая и практическая: отчёт — единственный файл, который человек
# открывает руками, и искать его в data/<префикс>/reports/ неудобно. Здесь же
# рядом лежат свежие подборки всех идентичностей сразу.
REPORTS_ROOT = Path(os.environ.get("WORK_IDE_REPORTS_ROOT") or (ROOT / "reports"))
LOCAL_CONSTITUTION_DIR = Path(
    os.environ.get("WORK_IDE_LOCAL_CONSTITUTION") or (ROOT / "local-constitution")
)

# --- Пути уровня идентичности (None до активации) ------------------------
# ВНИМАНИЕ: `CONFIG_DIR` здесь намеренно отсутствует. Раньше он указывал на
# общий config/; если бы мы оставили его как алиас, забытое место вызова тихо
# читало бы чужой файл. Теперь такое место падает с AttributeError — громко.

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

DEFAULT_TIMEOUT = 15  # настоящая константа, от идентичности не зависит

_IDENTITY_HOOKS: List[Callable[[], None]] = []


class NoActiveIdentityError(RuntimeError):
    """Попытка работать с данными без активной идентичности."""


class IdentityDataMismatchError(RuntimeError):
    """Папка данных принадлежит другой идентичности."""


def register_identity_hook(fn: Callable[[], None]) -> None:
    """Регистрирует callback, вызываемый при каждой активации идентичности.

    Нужен модулям, которые кэшируют производные от конфига значения: кэш,
    переживший смену идентичности, — это межидентичностная утечка.
    """
    if fn not in _IDENTITY_HOOKS:
        _IDENTITY_HOOKS.append(fn)


def require_identity() -> None:
    """Страж правила №0. Вызывается перед любым доступом к конфигам и данным."""
    if ACTIVE_IDENTITY is None:
        raise NoActiveIdentityError(
            "Нет активной поисковой идентичности — работа с данными запрещена "
            "(Большая Конституция, правило №0).\n"
            "  Укажите её: --identity <префикс>, либо задайте в "
            f"{LOCAL_CONSTITUTION_DIR / 'active.yaml'}.\n"
            "  Если идентичности ещё нет — проведите онбординг по docs/ONBOARDING.md."
        )


def activate_identity(prefix: str, *, allow_fixture: bool = False,
                      data_root: Optional[Path] = None,
                      reports_root: Optional[Path] = None) -> None:
    """Активирует идентичность: проверяет её и перепривязывает все пути.

    allow_fixture — тестовые идентичности (kind: fixture) намеренно нельзя
    активировать в обычной работе, чтобы никто не искал вакансии по фикстуре.

    reports_root по умолчанию — общая папка `reports/` в корне репозитория.
    ВАЖНО: если передан data_root (изолированный прогон, тесты), отчёты уезжают
    внутрь него. Иначе тест, изолировавший данные, всё равно писал бы отчёты в
    настоящую папку репозитория и затирал живую подборку человека.
    """
    import identity as identity_mod  # локальный импорт: identity.py импортирует common

    problems = identity_mod.validate(prefix)
    if problems:
        raise identity_mod.InvalidIdentityError(
            f"Идентичность '{prefix}' не прошла проверку:\n"
            + "\n".join(f"  - {p}" for p in problems)
        )

    import settings
    raw_profile, _ = settings.resolve("profile", prefix)
    kind = (raw_profile.get("identity") or {}).get("kind")
    if kind == "fixture" and not allow_fixture:
        raise identity_mod.InvalidIdentityError(
            f"'{prefix}' — тестовая фикстура (kind: fixture), реальный поиск по ней "
            "запрещён. Она существует только для того, чтобы тесты не зависели от "
            "того, какую идентичность вы держите активной."
        )

    profile, _ = resolve_local_fields(prefix, raw_profile)

    # Заготовка — это ещё не идентичность. Реальная находка 2026-08-04 на
    # прогоне свежего клона: `identity.py new` + `pipeline.py` отработали и
    # записали отчёт на 1734 вакансии — с плейсхолдером в заголовке и скорингом
    # по пустому стеку. Правило №0 проверяло, что идентичность СУЩЕСТВУЕТ, но
    # не что она ЗАПОЛНЕНА, и человек получал правдоподобный мусор. Это ровно
    # тот тихий неверный результат, ради предотвращения которого построена вся
    # архитектура, поэтому проверка живёт в активации, а не в отдельной команде.
    if kind != "fixture":
        gaps = identity_mod.readiness_problems(prefix)
        if gaps:
            raise identity_mod.IdentityNotReadyError(
                f"Идентичность '{prefix}' ещё не заполнена — поиск по ней дал бы "
                "правдоподобный, но бессмысленный результат.\n"
                + "\n".join(f"  - {g}" for g in gaps)
                + "\n  Как заполнить: docs/ONBOARDING.md (вопросник -> профиль -> критерии)."
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

    # REPORTS_DIR — общая для всех идентичностей: там лежат свежие подборки
    # каждой, различаясь префиксом в имени (kisel_latest.md, jvst_latest.md).
    # Архив, наоборот, разложен по идентичностям: reports/archive/<префикс>/,
    # и внутри имена файлов — просто даты. Правило единого префикса действует
    # там, где файлы РАЗНЫХ идентичностей лежат в одной папке; когда папка сама
    # принадлежит одной идентичности, префикс в каждом имени избыточен.
    # Отчёт всё равно опознаёт себя первой строкой: "# Work IDE [kisel] — …".
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
    """Сбрасывает активную идентичность. Нужно тестам, проверяющим отказ."""
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
    """Папка личных файлов идентичности в Малой Конституции (вне гита)."""
    return LOCAL_CONSTITUTION_DIR / "personal" / prefix


def load_local_overlay(prefix: str) -> dict:
    """Личная часть профиля: то, что не должно попасть в общий репозиторий.

    Отсутствие файла — не ошибка сама по себе: профиль может вообще не
    использовать сентинел `local`. Ошибкой это становится только если профиль
    на него ссылается, и тогда об этом скажет resolve_local_fields().
    """
    overlay = {}
    path = personal_dir(prefix) / f"{prefix}_owner.yaml"
    if path.exists():
        overlay = load_yaml(path) or {}

    # Контакт исторически лежит в отдельном файле — он появился раньше общего
    # оверлея. Оставляем как есть: раскладка Малой Конституции описана в
    # docs/LOCAL_CONSTITUTION.md, и ломать её ради единообразия незачем.
    contact_path = personal_dir(prefix) / f"{prefix}_contact.yaml"
    if contact_path.exists():
        contact_cfg = load_yaml(contact_path) or {}
        value = (contact_cfg.get("user_agent_contact") or "").strip()
        if value:
            overlay.setdefault("contact", {}).setdefault("user_agent_contact", value)

    return overlay


def _walk_local_sentinels(node, path=""):
    """Все пути до значений, равных `local`, в виде 'owner.name'."""
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
    """Подмешивает личные данные из Малой Конституции в профиль идентичности.

    ЗАЧЕМ. Идентичность лежит в общем репозитории и описывает ПОИСК: стек,
    формат работы, признаки подходящей компании. Имя человека, его LinkedIn,
    резидентство, CV и зарплатные ожидания к описанию поиска не относятся и в
    общий репозиторий попадать не должны — иначе каждый, кто склонирует проект,
    получит личное дело автора.

    Механизм не новый: сентинел `local` уже использовался для контакта в
    User-Agent. Здесь он обобщён на любое поле профиля — в файле идентичности
    стоит `local`, реальное значение лежит в
    `local-constitution/personal/<префикс>/<префикс>_owner.yaml`.

    Возвращает (профиль_с_подставленными_значениями, список_незаполненного).
    Профиль не мутируется: у вызывающего может быть своя копия.
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
    """Профиль активной идентичности с подмешанными личными данными.

    Единственная точка чтения профиля — иначе часть кода видела бы сентинел
    `local` вместо настоящего значения и молча считала бы его строкой.
    """
    import identity as identity_mod

    if prefix is None:
        require_identity()
        prefix = ACTIVE_IDENTITY
    # Профиль СОБИРАЕТСЯ ИЗ СЛОЁВ: копия шаблона даёт тип поиска, личный файл
    # рядом — обстоятельства человека. Читать один файл нельзя: в шаблоне нет
    # резидентства, а в личном файле нет стека.
    import settings

    raw, _ = settings.resolve("profile", prefix)
    merged, _ = resolve_local_fields(prefix, raw)
    return merged


def _build_user_agent(prefix: str, profile: dict) -> str:
    """Честный User-Agent с контактом — инженерное обязательство проекта
    (см. Большую Конституцию, раздел про вежливость к чужим серверам).

    Контакт приходит уже разрешённым (см. resolve_local_fields): в файле
    идентичности стоит `local`, значение лежит в Малой Конституции.
    """
    contact = ((profile.get("contact") or {}).get("user_agent_contact") or "").strip()
    if contact == LOCAL_SENTINEL:
        contact = ""  # оверлея нет — работаем без контакта, doctor предупредит

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
    """Путь к документу идентичности для чтения целиком.

    Документ может лежать в двух местах: личный файл в корне папки или копия
    шаблона в `template/`. Возвращается личный, если он есть, иначе шаблонный.

    Для документов, которые СОБИРАЮТСЯ ИЗ СЛОЁВ (профиль, критерии), этого
    недостаточно — там нужен settings.resolve(): личный файл содержит только
    отличия. Здесь путь нужен тем, кто читает документ целиком и без слоёв —
    например источники и ATS-цели.
    """
    require_identity()
    own = IDENTITY_DIR / f"{FILE_PREFIX}{name}"
    if own.exists():
        return own
    from_template = IDENTITY_DIR / "template" / f"{FILE_PREFIX}{name}"
    return from_template if from_template.exists() else own


def shared_config(name: str) -> Path:
    """'sources.catalog.yaml' -> config/sources.catalog.yaml (общая машинерия)."""
    return SHARED_CONFIG_DIR / name


def load_sources() -> list:
    """Единая точка чтения конфигурации источников для всего проекта.

    Сливает общий каталог источников (эндпоинты, тип, remote_only, документация —
    одинаковы для всех) с настройками активной идентичности (какие источники
    включены и с какими параметрами). Идентичность не может переопределить
    эндпоинт: устаревший URL — это баг для всех, а не чья-то настройка.

    Если каталога ещё нет, файл идентичности читается как самодостаточный —
    это состояние переходного периода, см. docs/BUILDING_BLOCKS.md.
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
                f"Идентичность '{ACTIVE_IDENTITY}' ссылается на неизвестный источник "
                f"'{name}'. Известные: {', '.join(sorted(catalog_by_name))}. "
                f"Опечатка в {identity_config('sources.yaml').name} или источник "
                "нужно добавить в config/sources.catalog.yaml."
            )
        merged.append({**base, **entry})
    return merged


def ensure_dirs() -> None:
    require_identity()
    for d in (DATA_DIR, KNOWLEDGE_DIR, RAW_DIR, REPORTS_DIR, REPORTS_ARCHIVE_DIR):
        d.mkdir(parents=True, exist_ok=True)
    _ensure_identity_marker()


def _ensure_identity_marker() -> None:
    """Кладёт data/<prefix>/.identity и сверяет его при каждом запуске.

    Защита от сценария "папку данных переименовали/перенесли руками": пути
    выглядят правильно, а внутри чужая база. Ошибка тихая и дорогая, проверка
    дешёвая.
    """
    marker = DATA_DIR / ".identity"
    if marker.exists():
        recorded = marker.read_text(encoding="utf-8").strip()
        if recorded and recorded != ACTIVE_IDENTITY:
            raise IdentityDataMismatchError(
                f"Папка данных {DATA_DIR} принадлежит идентичности '{recorded}', "
                f"а активна '{ACTIVE_IDENTITY}'. Данные не тронуты. "
                "Разберитесь вручную, прежде чем продолжать."
            )
    else:
        marker.write_text(f"{ACTIVE_IDENTITY}\n", encoding="utf-8")


# --- IO helpers ---------------------------------------------------------

def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def write_yaml(path: Path, data: dict) -> None:
    """Запись YAML, читаемого человеком.

    Используется только для файлов, которые генерирует сам проект (например
    `local-constitution/active.yaml`). Конфиги идентичностей правит человек —
    их перезапись стёрла бы комментарии, а комментарии там несут половину
    смысла.
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
    """Пишет JSON атомарно (через временный файл + rename), чтобы падение
    посреди записи никогда не оставило базу знаний в битом состоянии."""
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


# --- Текст ---------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_MULTI_WS_RE = re.compile(r"[ \t\r\f\v]+")
_MULTI_NL_RE = re.compile(r"\n{3,}")
_BLOCK_BREAK_RE = re.compile(
    r"</?(?:p|br|li|ul|ol|div|h[1-6]|tr)\b[^>]*>", re.IGNORECASE
)


def strip_html(raw: Optional[str]) -> str:
    """Грубый, но надёжный (без внешних зависимостей вроде bs4/lxml) конвертер
    HTML -> читаемый текст. Для целей keyword-скоринга и отчётов точность
    важнее, чем идеальный рендеринг."""
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
    """Нормализация для поиска ключевых слов: нижний регистр, unicode NFKC,
    схлопнутые пробелы. Не убирает пунктуацию (важно для "c#", "asp.net")."""
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
