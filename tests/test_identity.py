"""
Тесты системы поисковых идентичностей.

Эти тесты защищают главное свойство мультипользовательской архитектуры: агент,
работающий по идентичности A, не может случайно задеть идентичность B. Отказ
здесь тихий и дорогой (испорченная выдача, которую никто не заметит), поэтому
проверок много и они дотошные.
"""
import os

import pytest

import common
import identity


# --- Формат префикса -------------------------------------------------------

@pytest.mark.parametrize("prefix", ["kisel", "ftf", "abc", "a1b2c3", "jvst"])
def test_valid_prefixes_accepted(prefix):
    assert identity.PREFIX_RE.match(prefix), f"{prefix} должен считаться валидным"


@pytest.mark.parametrize("prefix", [
    "ab",           # слишком короткий
    "abcdefg",      # слишком длинный
    "KISEL",         # заглавные: на Windows ФС регистронезависима, путаница гарантирована
    "1abc",         # начинается с цифры
    "ka-lm",        # дефис
    "ka lm",        # пробел
    "ка",           # кириллица: префикс обязан быть латиницей
    "",
])
def test_invalid_prefixes_rejected(prefix):
    assert not identity.PREFIX_RE.match(prefix), f"{prefix} не должен считаться валидным"


# --- Реестр ---------------------------------------------------------------

def test_template_dir_is_not_an_identity():
    # Папки с "_" в начале — заготовки, а не идентичности. Иначе агент попытался
    # бы искать работу по шаблону.
    assert "_template" not in identity.list_identities(include_fixtures=True)


def test_fixture_hidden_from_normal_listing():
    assert "ftf" in identity.list_identities(include_fixtures=True)
    assert "ftf" not in identity.list_identities(include_fixtures=False)


def test_identity_file_path_uses_prefix():
    """Имя ПАПКИ длинное и объясняющее, имена ФАЙЛОВ — короткие.

    Разделение намеренное: папку видишь редко и хочешь понять по имени, что
    это за поиск; имена файлов встречаются в каждой команде и в выводе grep,
    и длинное имя там только мешает.
    """
    path = identity.identity_file("kisel", "criteria.yaml")
    assert path.name == "kisel_criteria.yaml"
    assert path.parent.name == "kisel-keep-it-simple-easy-legacy"


# --- Валидация ------------------------------------------------------------

def test_existing_identities_are_valid():
    """Все идентичности в репозитории обязаны быть структурно целыми."""
    results = identity.validate_all()
    broken = {p: probs for p, probs in results.items() if probs}
    assert not broken, f"есть невалидные идентичности: {broken}"


def test_validate_rejects_unknown_prefix():
    problems = identity.validate("nosuch")
    assert problems
    assert any("не найдена" in p for p in problems)


def test_validate_rejects_bad_prefix_format():
    problems = identity.validate("BAD-PREFIX")
    assert problems
    assert any("формат префикса" in p for p in problems)


def test_validate_catches_unprefixed_file(tmp_path, monkeypatch):
    """Файл без префикса внутри идентичности — нарушение главного правила."""
    identities_dir = tmp_path / "identities"
    (identities_dir / "abcd").mkdir(parents=True)
    monkeypatch.setattr(common, "IDENTITIES_DIR", identities_dir)

    d = identities_dir / "abcd"
    for name in identity.REQUIRED_FILES:
        (d / f"abcd_{name}").write_text("{}", encoding="utf-8")
    (d / "notes.md").write_text("файл без префикса", encoding="utf-8")

    problems = identity.validate("abcd")
    assert any("notes.md" in p and "abcd_" in p for p in problems)


def test_validate_catches_foreign_prefix_leak(tmp_path, monkeypatch):
    """Самая вероятная ошибка при создании идентичности — копипаста чужих файлов
    с недоправленными путями внутри."""
    identities_dir = tmp_path / "identities"
    for prefix in ("abcd", "efgh"):
        d = identities_dir / prefix
        d.mkdir(parents=True)
        for name in identity.REQUIRED_FILES:
            (d / f"{prefix}_{name}").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(common, "IDENTITIES_DIR", identities_dir)

    # В файл abcd попала ссылка на файл efgh — типичная копипаста
    (identities_dir / "abcd" / "abcd_identity.md").write_text(
        "смотри также efgh_criteria.yaml", encoding="utf-8"
    )

    problems = identity.validate("abcd")
    assert any("efgh_" in p for p in problems)


def test_validate_catches_missing_required_file(tmp_path, monkeypatch):
    identities_dir = tmp_path / "identities"
    d = identities_dir / "abcd"
    d.mkdir(parents=True)
    for name in identity.REQUIRED_FILES:
        if name == "criteria.yaml":
            continue
        (d / f"abcd_{name}").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(common, "IDENTITIES_DIR", identities_dir)

    problems = identity.validate("abcd")
    assert any("abcd_criteria.yaml" in p for p in problems)


# --- Разрешение активной идентичности --------------------------------------

def test_cli_value_wins_over_everything(monkeypatch):
    monkeypatch.setenv("WORK_IDE_IDENTITY", "fromenv")
    assert identity.resolve_identity("fromcli") == "fromcli"


def test_env_used_when_no_cli(monkeypatch):
    monkeypatch.setenv("WORK_IDE_IDENTITY", "fromenv")
    assert identity.resolve_identity() == "fromenv"


def test_default_identity_used(monkeypatch, tmp_path):
    monkeypatch.delenv("WORK_IDE_IDENTITY", raising=False)
    lc = tmp_path / "local-constitution"
    lc.mkdir()
    (lc / "active.yaml").write_text(
        "default_identity: chosen\nactive_identities:\n  - prefix: chosen\n  - prefix: other\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(common, "LOCAL_CONSTITUTION_DIR", lc)
    assert identity.resolve_identity() == "chosen"


def test_single_active_identity_used_silently(monkeypatch, tmp_path):
    monkeypatch.delenv("WORK_IDE_IDENTITY", raising=False)
    lc = tmp_path / "local-constitution"
    lc.mkdir()
    (lc / "active.yaml").write_text(
        "active_identities:\n  - prefix: onlyone\n", encoding="utf-8"
    )
    monkeypatch.setattr(common, "LOCAL_CONSTITUTION_DIR", lc)
    assert identity.resolve_identity() == "onlyone"


def test_several_active_without_default_refuses(monkeypatch, tmp_path):
    """Молчаливый выбор 'не той' идентичности — ровно тот отказ, ради которого
    вся система и построена. Лучше отказать и спросить."""
    monkeypatch.delenv("WORK_IDE_IDENTITY", raising=False)
    lc = tmp_path / "local-constitution"
    lc.mkdir()
    (lc / "active.yaml").write_text(
        "active_identities:\n  - prefix: aaaa\n  - prefix: bbbb\n", encoding="utf-8"
    )
    monkeypatch.setattr(common, "LOCAL_CONSTITUTION_DIR", lc)

    with pytest.raises(identity.IdentityError) as exc:
        identity.resolve_identity()
    assert "aaaa" in str(exc.value) and "bbbb" in str(exc.value)


def test_no_identity_at_all_refuses_with_onboarding_hint(monkeypatch, tmp_path):
    monkeypatch.delenv("WORK_IDE_IDENTITY", raising=False)
    monkeypatch.setattr(common, "LOCAL_CONSTITUTION_DIR", tmp_path / "nonexistent")

    with pytest.raises(identity.IdentityError) as exc:
        identity.resolve_identity()
    message = str(exc.value)
    assert "ONBOARDING" in message.upper()
    assert "--identity" in message


# --- Активация ------------------------------------------------------------

def test_fixture_refused_without_explicit_flag():
    """Реальный поиск по тестовой фикстуре должен быть невозможен."""
    with pytest.raises(identity.InvalidIdentityError) as exc:
        common.activate_identity("ftf")  # без allow_fixture
    assert "fixture" in str(exc.value).lower()
    # conftest активировал ftf на уровне модуля — восстанавливаем состояние
    common.activate_identity("ftf", allow_fixture=True)


def test_activation_binds_all_paths(tmp_path):
    common.activate_identity("ftf", allow_fixture=True, data_root=tmp_path)
    try:
        assert common.ACTIVE_IDENTITY == "ftf"
        assert common.FILE_PREFIX == "ftf_"
        assert common.DATA_DIR == tmp_path / "ftf"
        assert common.VACANCIES_PATH.name == "ftf_vacancies.json"
        assert common.STATE_PATH.name == "ftf_state.json"
        # Отчёты живут отдельно от накопленных данных: общая папка reports/,
        # архив внутри неё разложен по идентичностям. При изолированном прогоне
        # (передан data_root) вся раскладка уезжает внутрь него — иначе тест
        # писал бы отчёты в настоящую папку репозитория поверх живой подборки.
        assert common.REPORTS_DIR == tmp_path / "reports"
        assert common.REPORTS_ARCHIVE_DIR == tmp_path / "reports" / "archive" / "ftf"
        assert common.USER_AGENT and "WorkIdeJobResearchBot" in common.USER_AGENT
    finally:
        common.activate_identity("ftf", allow_fixture=True)


def test_identity_config_resolves_to_prefixed_file():
    assert common.identity_config("criteria.yaml").name == "ftf_criteria.yaml"


def test_data_marker_detects_foreign_data_dir(tmp_path):
    """Папку данных переименовали руками — внутри чужая база. Ошибка тихая и
    дорогая, проверка дешёвая."""
    common.activate_identity("ftf", allow_fixture=True, data_root=tmp_path)
    try:
        common.ensure_dirs()
        marker = common.DATA_DIR / ".identity"
        assert marker.read_text(encoding="utf-8").strip() == "ftf"

        marker.write_text("someone_else\n", encoding="utf-8")
        with pytest.raises(common.IdentityDataMismatchError):
            common.ensure_dirs()
    finally:
        common.activate_identity("ftf", allow_fixture=True)


# --- Отказ без идентичности -------------------------------------------------

def test_data_access_refused_without_identity():
    """Правило №0 обязано быть в коде, а не только в документации."""
    import kb

    common.deactivate_identity()
    try:
        with pytest.raises(common.NoActiveIdentityError):
            kb.load_vacancies()
        with pytest.raises(common.NoActiveIdentityError):
            common.identity_config("criteria.yaml")
        with pytest.raises(common.NoActiveIdentityError):
            common.ensure_dirs()
    finally:
        common.activate_identity("ftf", allow_fixture=True)


def test_no_identity_error_message_is_actionable():
    common.deactivate_identity()
    try:
        with pytest.raises(common.NoActiveIdentityError) as exc:
            common.require_identity()
        message = str(exc.value)
        assert "--identity" in message
        assert "ONBOARDING" in message.upper()
    finally:
        common.activate_identity("ftf", allow_fixture=True)


# --- Создание идентичности из шаблона --------------------------------------
#
# Раньше это была процедура из шести ручных `copy` с переименованием каждого
# файла. Именно на ней проект обжёгся: в фикстуру ftf попал файл, ссылавшийся
# на kisel_. Эти тесты защищают автоматизацию, которая ту ошибку исключает.

@pytest.fixture
def sandbox_identities(tmp_path, monkeypatch):
    """Отдельная папка identities/ с копией шаблона — чтобы тесты создания
    не оставляли мусор в настоящем репозитории."""
    import shutil

    sandbox = tmp_path / "identities"
    sandbox.mkdir()
    shutil.copytree(common.IDENTITIES_DIR / "_template", sandbox / "_template")
    monkeypatch.setattr(common, "IDENTITIES_DIR", sandbox)
    return sandbox


def test_scaffold_creates_all_required_files_with_prefix(sandbox_identities):
    created = identity.scaffold_identity("newp", "New Product Search")
    names = {p.name for p in created}
    assert created[0].parent.name == "newp-new-product-search"
    for required in identity.REQUIRED_FILES:
        assert f"newp_{required}" in names, f"нет обязательного файла {required}"
    assert all(p.name.startswith("newp_") for p in created)


def test_scaffolded_identity_passes_validation(sandbox_identities):
    identity.scaffold_identity("newp", "New Product Search")
    assert identity.validate("newp") == [], "заготовка обязана быть структурно корректной сразу"


def test_scaffold_substitutes_template_placeholders(sandbox_identities):
    identity.scaffold_identity("newp", "New Product Search")
    for path in (sandbox_identities / "newp-new-product-search").iterdir():
        text = path.read_text(encoding="utf-8")
        assert "tmpl_" not in text, f"в {path.name} остался префикс шаблона"
        assert identity.TEMPLATE_PREFIX_PLACEHOLDER not in text, (
            f"в {path.name} остался плейсхолдер префикса — агент пойдёт по битому пути"
        )


def test_scaffold_refuses_to_overwrite_existing_identity(sandbox_identities):
    identity.scaffold_identity("newp", "New Product Search")
    # Тот же префикс, другая расшифровка — всё равно отказ: префикс обязан
    # быть уникальным, иначе непонятно, какая из двух папок "та самая".
    with pytest.raises(identity.InvalidIdentityError) as exc:
        identity.scaffold_identity("newp", "Totally Different Search")
    assert "уже существует" in str(exc.value)


@pytest.mark.parametrize("bad", ["ab", "KISEL", "1abc", "ka-lm", "tmpl"])
def test_scaffold_refuses_bad_prefix(sandbox_identities, bad):
    with pytest.raises(identity.InvalidIdentityError):
        identity.scaffold_identity(bad, "Some Search")


def test_scaffold_does_not_touch_the_local_constitution(sandbox_identities, tmp_path, monkeypatch):
    # Какие идентичности активны — осознанное решение человека, живущее вне
    # гита. Создание заготовки не должно активировать её молча.
    lc = tmp_path / "lc"
    lc.mkdir()
    monkeypatch.setattr(common, "LOCAL_CONSTITUTION_DIR", lc)
    identity.scaffold_identity("newp", "New Product Search")
    assert not (lc / "active.yaml").exists()
    assert identity.active_identities() == []


# --- Имя папки: префикс + расшифровка --------------------------------------
#
# Два уровня именования намеренно разные. Папку видишь редко, и по одному
# `kisel` невозможно вспомнить, что это был за поиск — поэтому расшифровка
# прямо в имени папки. Файлы внутри, наоборот, короткие: их имена встречаются
# в каждой команде, в выводе grep и в путях внутри отчётов.

@pytest.mark.parametrize("folder,expected", [
    ("kisel-keep-it-simple-easy-legacy", "kisel"),
    ("jvst-java-startup-onsite", "jvst"),
    ("ftf-frozen-test-fixture", "ftf"),
    ("abcd", "abcd"),                     # без расшифровки — распознаётся, но validate ругнётся
    ("_template", None),                  # заготовка
    ("Kisel-Keep-It", None),              # заглавные
    ("kisel_keep_it", None),              # подчёркивания — это разделитель ФАЙЛОВ, не папок
])
def test_folder_prefix_extraction(folder, expected):
    assert identity.folder_prefix(folder) == expected


@pytest.mark.parametrize("full_name,expected", [
    ("Keep It Simple, Easy, Legacy", "kisel-keep-it-simple-easy-legacy"),
    ("KISEL — Keep It Simple", "kisel-keep-it-simple"),   # префикс не задваивается
    ("Java  Startup / onsite", "kisel-java-startup-onsite"),
])
def test_folder_name_generated_from_a_spoken_phrase(full_name, expected):
    assert identity.folder_name_for("kisel", full_name) == expected


def test_folder_without_description_is_reported(tmp_path, monkeypatch):
    identities_dir = tmp_path / "identities"
    d = identities_dir / "abcd"
    d.mkdir(parents=True)
    for name in identity.REQUIRED_FILES:
        (d / f"abcd_{name}").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(common, "IDENTITIES_DIR", identities_dir)

    problems = identity.validate("abcd")
    assert any("без расшифровки" in p for p in problems)


def test_two_folders_with_the_same_prefix_are_refused(tmp_path, monkeypatch):
    """Неразрешимая неоднозначность: какая из двух папок «та самая» — определить
    нечем, а тихий выбор одной даст перемешанные данные."""
    identities_dir = tmp_path / "identities"
    (identities_dir / "abcd-first-search").mkdir(parents=True)
    (identities_dir / "abcd-second-search").mkdir(parents=True)
    monkeypatch.setattr(common, "IDENTITIES_DIR", identities_dir)

    with pytest.raises(identity.InvalidIdentityError) as exc:
        identity.identity_folders()
    assert "abcd" in str(exc.value)


def test_files_keep_the_short_prefix_not_the_long_folder_name(sandbox_identities):
    """Ключевое свойство разделения: длинное имя остаётся у папки и только."""
    created = identity.scaffold_identity("newp", "New Product Search")
    assert created[0].parent.name == "newp-new-product-search"
    for path in created:
        assert path.name.startswith("newp_"), (
            f"{path.name} — имя файла обязано быть коротким, с одним префиксом"
        )
        assert "new-product-search" not in path.name


# --- Готовность идентичности: заполнена, а не просто существует -------------
#
# Реальная находка 2026-08-04 на прогоне свежего клона: `identity.py new` плюс
# `pipeline.py` отработали и записали отчёт на 1734 вакансии — с плейсхолдером
# в заголовке и скорингом по пустому стеку. Правило №0 проверяло существование
# идентичности, но не её заполненность.

def test_fresh_scaffold_is_not_ready(sandbox_identities):
    identity.scaffold_identity("newp", "New Product Search")
    problems = identity.readiness_problems("newp")
    assert problems, "заготовка из шаблона не может считаться готовой к поиску"
    assert any("tech_stack.core" in p for p in problems)


def test_activation_refuses_an_unfilled_identity(sandbox_identities, monkeypatch, tmp_path):
    identity.scaffold_identity("newp", "New Product Search")
    monkeypatch.setattr(common, "LOCAL_CONSTITUTION_DIR", tmp_path / "lc")
    with pytest.raises(identity.IdentityNotReadyError) as exc:
        common.activate_identity("newp", data_root=tmp_path / "data")
    assert "не заполнена" in str(exc.value)
    assert "ONBOARDING" in str(exc.value)


def test_placeholders_are_looked_for_in_values_not_comments(sandbox_identities):
    """Первая версия проверки читала файл целиком и объявляла заполненную
    идентичность незаполненной: угловые скобки сплошь и рядом встречаются в
    комментариях как часть документации («<token> подставьте сюда»)."""
    identity.scaffold_identity("newp", "New Product Search")
    d = sandbox_identities / "newp-new-product-search"
    (d / "newp_ats_targets.yaml").write_text(
        "# укажите здесь <token> с карьерной страницы\ntargets: []\n", encoding="utf-8"
    )
    problems = identity.readiness_problems("newp")
    assert not any("newp_ats_targets.yaml" in p for p in problems), (
        "плейсхолдер в комментарии — это документация, а не незаполненное поле"
    )


def test_shipped_identity_is_complete_except_for_personal_data():
    """Идентичность из репозитория обязана быть заполнена ЦЕЛИКОМ — кроме
    личных полей, которых в общем репозитории быть и не должно.

    Проверку поймал прогон свежего клона 2026-08-04: там kisel закономерно
    оказалась «не готова», потому что оверлей с личными данными лежит вне
    гита. Это правильное поведение, а не поломка — новый человек обязан
    подставить свои. Но всё остальное (стек, критерии, источники) должно быть
    готово к работе сразу, иначе гейт настроен слишком строго и заблокирует
    нормальный сценарий.
    """
    problems = identity.readiness_problems("kisel")
    non_personal = [p for p in problems if "помечено как личное" not in p]
    assert non_personal == [], (
        "в общей части идентичности не должно остаться незаполненного: "
        f"{non_personal}"
    )


# --- Оверлей личных данных из Малой Конституции -----------------------------

def test_local_sentinel_is_resolved_from_the_local_constitution(tmp_path, monkeypatch):
    lc = tmp_path / "lc"
    (lc / "personal" / "abcd").mkdir(parents=True)
    (lc / "personal" / "abcd" / "abcd_owner.yaml").write_text(
        "owner:\n  name: Настоящее Имя\n  languages: [English]\n", encoding="utf-8"
    )
    monkeypatch.setattr(common, "LOCAL_CONSTITUTION_DIR", lc)

    profile = {"owner": {"name": "local", "languages": "local", "role": "Developer"}}
    merged, missing = common.resolve_local_fields("abcd", profile)

    assert merged["owner"]["name"] == "Настоящее Имя"
    assert merged["owner"]["languages"] == ["English"]
    assert merged["owner"]["role"] == "Developer", "не-личные поля не трогаются"
    assert missing == []
    assert profile["owner"]["name"] == "local", "исходный профиль не мутируется"


def test_missing_local_value_is_reported_not_silently_empty(tmp_path, monkeypatch):
    """Молча подставить пустоту — худший вариант: скоринг отработает на пустых
    языках и выдаст правдоподобный мусор."""
    monkeypatch.setattr(common, "LOCAL_CONSTITUTION_DIR", tmp_path / "empty")
    merged, missing = common.resolve_local_fields("abcd", {"owner": {"name": "local"}})
    assert missing == ["owner.name"]


# --- init-local: разворачивание Малой Конституции ---------------------------

def test_init_local_creates_the_folder_and_registers_the_identity(tmp_path, monkeypatch):
    lc = tmp_path / "lc"
    monkeypatch.setattr(common, "LOCAL_CONSTITUTION_DIR", lc)
    identity.init_local_constitution("abcd", note="тестовый поиск")

    cfg = identity.load_local_constitution()
    prefixes = [e["prefix"] for e in cfg["active_identities"]]
    assert prefixes == ["abcd"]
    assert (lc / "personal" / "abcd").is_dir()


def test_init_local_does_not_rewrite_an_unchanged_file(tmp_path, monkeypatch):
    """active.yaml пишет человек, и он полон комментариев — YAML-дампер их
    стирает. Реальный случай при разработке команды 2026-08-04: безобидный
    повторный запуск снёс всю документацию внутри файла."""
    lc = tmp_path / "lc"
    monkeypatch.setattr(common, "LOCAL_CONSTITUTION_DIR", lc)
    identity.init_local_constitution("abcd")

    path = identity.local_constitution_path()
    handwritten = "# мой комментарий, который нельзя терять\n" + path.read_text(encoding="utf-8")
    path.write_text(handwritten, encoding="utf-8")

    identity.init_local_constitution("abcd")
    assert path.read_text(encoding="utf-8") == handwritten


def test_init_local_sets_default_identity_when_a_second_one_appears(tmp_path, monkeypatch):
    """Без default_identity вторая идентичность ломает команды ПЕРВОЙ —
    той, что работала до сих пор."""
    lc = tmp_path / "lc"
    monkeypatch.setattr(common, "LOCAL_CONSTITUTION_DIR", lc)
    identity.init_local_constitution("abcd")
    assert identity.default_identity() is None, "с одной идентичностью дефолт не нужен"

    identity.init_local_constitution("efgh")
    assert identity.default_identity() == "abcd"


def test_init_local_backs_up_before_rewriting(tmp_path, monkeypatch):
    lc = tmp_path / "lc"
    monkeypatch.setattr(common, "LOCAL_CONSTITUTION_DIR", lc)
    identity.init_local_constitution("abcd")
    identity.init_local_constitution("efgh")   # эта запись требует перезаписи
    assert (lc / "active.yaml.bak").exists()


def test_init_local_writes_an_owner_skeleton_for_the_local_fields(tmp_path, monkeypatch, sandbox_identities):
    """Полезнее отдать человеку файл с нужными ему полями, чем отправить его
    собирать структуру по спецификации."""
    identity.scaffold_identity("newp", "New Product Search")
    profile_path = identity.identity_file("newp", "profile.yaml")
    profile_path.write_text(
        "identity:\n  kind: personal\nowner:\n  name: local\n  location: local\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(common, "LOCAL_CONSTITUTION_DIR", tmp_path / "lc")

    identity.init_local_constitution("newp")

    skeleton = common.personal_dir("newp") / "newp_owner.yaml"
    text = skeleton.read_text(encoding="utf-8")
    assert "owner:" in text and "name:" in text and "location:" in text
    assert "ВНЕ ГИТА" in text


def test_owner_skeleton_never_overwrites_a_filled_file(tmp_path, monkeypatch, sandbox_identities):
    identity.scaffold_identity("newp", "New Product Search")
    monkeypatch.setattr(common, "LOCAL_CONSTITUTION_DIR", tmp_path / "lc")
    identity.init_local_constitution("newp")

    skeleton = common.personal_dir("newp") / "newp_owner.yaml"
    skeleton.write_text("owner:\n  name: Уже заполнено\n", encoding="utf-8")
    identity.init_local_constitution("newp")
    assert "Уже заполнено" in skeleton.read_text(encoding="utf-8")


# --- Клонирование идентичности ----------------------------------------------
#
# Частый случай: один и тот же поиск для разных стран. Стек, тип занятости и
# признаки компании общие, различаются гео-правила, языки и часовой пояс.
# Собирать вторую идентичность с нуля — переотвечать на 50 вопросов ради трёх.

def test_clone_copies_every_file_under_the_new_prefix(sandbox_identities):
    identity.scaffold_identity("srcp", "Source Search")
    created = identity.clone_identity("srcp", "dstp", "Source Search for Germany")

    assert created[0].parent.name == "dstp-source-search-for-germany"
    names = {p.name for p in created}
    for required in identity.REQUIRED_FILES:
        assert f"dstp_{required}" in names


def test_clone_rewrites_internal_references_to_the_source(sandbox_identities):
    """Иначе клон нарушил бы правило «файлы одной идентичности не ссылаются на
    другую» и был бы отвергнут валидатором."""
    identity.scaffold_identity("srcp", "Source Search")
    identity.identity_file("srcp", "identity.md").write_text(
        "# srcp\nсмотри srcp_criteria.yaml\n", encoding="utf-8"
    )
    identity.clone_identity("srcp", "dstp", "Cloned Search")

    text = identity.identity_file("dstp", "identity.md").read_text(encoding="utf-8")
    assert "dstp_criteria.yaml" in text
    assert "srcp_" not in text
    assert identity.validate("dstp") == []


def test_clone_refuses_a_taken_prefix(sandbox_identities):
    identity.scaffold_identity("srcp", "Source Search")
    identity.scaffold_identity("dstp", "Other Search")
    with pytest.raises(identity.InvalidIdentityError) as exc:
        identity.clone_identity("srcp", "dstp", "Cloned Search")
    assert "занят" in str(exc.value)


def test_clone_refuses_an_unknown_source(sandbox_identities):
    with pytest.raises(identity.UnknownIdentityError):
        identity.clone_identity("nosuch", "dstp", "Cloned Search")


def test_clone_refuses_the_frozen_fixture():
    """Фикстура откалибрована под тесты, а не под живой поиск — клон от неё
    унаследовал бы калибровочные значения и молча искал бы не то."""
    with pytest.raises(identity.InvalidIdentityError) as exc:
        identity.clone_identity("ftf", "dstp", "Cloned Search")
    assert "фикстура" in str(exc.value)
