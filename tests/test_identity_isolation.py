"""
Тест непротекаемости — главная гарантия мультипользовательской архитектуры.

Проверяет, что после переключения с идентичности A на B ничего от A не осталось:
ни путей, ни данных, ни кэшей. Это тот отказ, который невозможно заметить глазами
(отчёт выглядит нормально, просто он неправильный), поэтому он должен ловиться
автоматически.

Обе используемые здесь идентичности — фикстуры во временных каталогах, чтобы тест
не зависел от того, какие идентичности реально лежат в репозитории.
"""
import shutil

import pytest

import common
import identity
import kb
import score


TEST_IDENTITY = "ftf"


@pytest.fixture
def two_identities(tmp_path, monkeypatch):
    """Создаёт две полноценные идентичности (aaaa и bbbb) во временной папке.

    aaaa: включён remote-only источник weworkremotely
    bbbb: включён НЕ remote-only источник arbeitnow
    Разные наборы нужны, чтобы поймать утечку кэша _remote_only_sources().
    """
    identities_dir = tmp_path / "identities"
    src = identity.identity_dir(TEST_IDENTITY)

    for prefix, sources_yaml in (
        ("aaaa", "sources:\n  - name: weworkremotely\n    enabled: true\n    remote_only: true\n"),
        ("bbbb", "sources:\n  - name: arbeitnow\n    enabled: true\n    remote_only: false\n"),
    ):
        # Имя папки — с расшифровкой (правило именования), файлы внутри —
        # с коротким префиксом.
        d = identities_dir / f"{prefix}-isolation-test-identity"
        d.mkdir(parents=True)
        # Профиль и критерии копируем из фикстуры — содержимое здесь неважно,
        # важна структура и изоляция.
        for name in ("profile.yaml", "criteria.yaml"):
            shutil.copy(src / f"{TEST_IDENTITY}_{name}", d / f"{prefix}_{name}")
        (d / f"{prefix}_sources.yaml").write_text(sources_yaml, encoding="utf-8")
        (d / f"{prefix}_identity.md").write_text(f"# {prefix}\n", encoding="utf-8")
        (d / f"{prefix}_questionnaire.yaml").write_text(
            f"schema_version: 1\nidentity_prefix: {prefix}\nanswers: []\n", encoding="utf-8"
        )

    monkeypatch.setattr(common, "IDENTITIES_DIR", identities_dir)
    # Фикстуры тоже находятся при обходе идентичностей; на время этого теста
    # их надо убрать, иначе в песочнице окажется ещё и ftf.
    monkeypatch.setattr(common, "FIXTURES_DIR", tmp_path / "no-fixtures")
    monkeypatch.setattr(common, "DATA_ROOT", tmp_path / "data")
    # И REPORTS_ROOT тоже. Реальный случай 2026-08-04: подменялся только
    # DATA_ROOT, и тест создавал reports/archive/aaaa и .../bbbb прямо в
    # настоящей папке отчётов человека. Пустые папки, но они месяцами
    # мозолили глаза в единственном месте, куда человек реально смотрит.
    monkeypatch.setattr(common, "REPORTS_ROOT", tmp_path / "reports")
    yield tmp_path
    # Возвращаем процесс в состояние, которое ожидают остальные тесты
    monkeypatch.undo()
    common.activate_identity(TEST_IDENTITY, allow_fixture=True)


def test_data_written_under_a_is_invisible_under_b(two_identities):
    common.activate_identity("aaaa", allow_fixture=True)
    common.ensure_dirs()
    kb.save_vacancies({"vac-1": {"id": "vac-1", "title": "Секрет идентичности A"}})
    assert len(kb.load_vacancies()) == 1

    common.activate_identity("bbbb", allow_fixture=True)
    common.ensure_dirs()
    assert kb.load_vacancies() == {}, "база B обязана быть пустой — данные A не её дело"


def _identity_paths() -> dict:
    return {
        "vacancies": common.VACANCIES_PATH,
        "companies": common.COMPANIES_PATH,
        "state": common.STATE_PATH,
        "reports_archive": common.REPORTS_ARCHIVE_DIR,
        "raw": common.RAW_DIR,
    }


def test_paths_of_two_identities_share_no_components(two_identities):
    common.activate_identity("aaaa", allow_fixture=True)
    a_paths = _identity_paths()

    common.activate_identity("bbbb", allow_fixture=True)
    b_paths = _identity_paths()

    for key in a_paths:
        assert a_paths[key] != b_paths[key], f"путь '{key}' совпал у двух идентичностей"
        assert "aaaa" not in str(b_paths[key]), f"в пути B '{key}' просочился префикс A"


def test_reports_folder_is_shared_but_files_are_not(two_identities):
    """Единственное намеренное исключение из изоляции путей.

    Папка `reports/` общая: человек открывает её руками и хочет видеть свежие
    подборки всех своих идентичностей рядом. Пересечения при этом нет — файлы
    различаются префиксом, а архив разложен по подпапкам.
    """
    common.activate_identity("aaaa", allow_fixture=True)
    a_dir, a_latest, a_archive = (
        common.REPORTS_DIR,
        common.REPORTS_DIR / f"{common.FILE_PREFIX}latest.md",
        common.REPORTS_ARCHIVE_DIR,
    )

    common.activate_identity("bbbb", allow_fixture=True)
    b_dir, b_latest, b_archive = (
        common.REPORTS_DIR,
        common.REPORTS_DIR / f"{common.FILE_PREFIX}latest.md",
        common.REPORTS_ARCHIVE_DIR,
    )

    assert a_dir == b_dir, "папка отчётов общая намеренно"
    assert a_latest != b_latest, "но сами файлы обязаны различаться префиксом"
    assert a_archive != b_archive, "архивы разложены по идентичностям"
    assert a_archive.name == "aaaa" and b_archive.name == "bbbb"


def test_remote_only_cache_does_not_leak_between_identities(two_identities):
    """Регрессия на конкретный баг: до рефакторинга _REMOTE_ONLY_SOURCES_CACHE был
    одним глобальным набором, заполняемым при первом вызове. Набор источников A
    управлял бы remote-гейтом B — а этот гейт решает 'дисквалифицировать вакансию
    или дать +4 балла'."""
    common.activate_identity("aaaa", allow_fixture=True)
    a_sources = score._remote_only_sources()
    assert a_sources == {"weworkremotely"}

    common.activate_identity("bbbb", allow_fixture=True)
    b_sources = score._remote_only_sources()
    assert b_sources == set(), "у B нет remote-only источников — кэш A протёк"
    assert "weworkremotely" not in b_sources


def test_criteria_and_profile_read_from_active_identity(two_identities):
    common.activate_identity("aaaa", allow_fixture=True)
    assert common.identity_config("criteria.yaml").name == "aaaa_criteria.yaml"

    common.activate_identity("bbbb", allow_fixture=True)
    assert common.identity_config("criteria.yaml").name == "bbbb_criteria.yaml"


def test_identity_hook_fires_on_every_activation(two_identities):
    """Модули с кэшами полагаются на этот hook. Если он перестанет вызываться,
    утечки вернутся молча."""
    calls = []
    common.register_identity_hook(lambda: calls.append(common.ACTIVE_IDENTITY))
    try:
        common.activate_identity("aaaa", allow_fixture=True)
        common.activate_identity("bbbb", allow_fixture=True)
        # hook вызывается ДО присвоения ACTIVE_IDENTITY? нет — после привязки путей,
        # поэтому в списке уже новые значения
        assert len(calls) >= 2
    finally:
        common._IDENTITY_HOOKS.pop()
