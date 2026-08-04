"""pytest-конфигурация.

Делает две вещи:

1. Кладёт tools/ в sys.path, чтобы модули импортировались плоско (`import common`),
   ровно как при standalone-запуске скриптов.

2. **Активирует тестовую идентичность `ftf` на уровне модуля**, а не фикстурой.
   Это принципиально: `tests/test_score.py` читает конфиг на уровне модуля
   (`CRITERIA = score.load_criteria()`), то есть во время СБОРА тестов — раньше,
   чем успела бы отработать любая фикстура. Без активации здесь сбор упал бы с
   NoActiveIdentityError.

   `ftf` — замороженная фикстура (см. identities/ftf/ftf_identity.md): тесты не
   должны зависеть от того, какую идентичность разработчик держит активной, и не
   должны краснеть, когда кто-то тюнит свои личные критерии.
"""
import os
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import common  # noqa: E402

TEST_IDENTITY = "ftf"

# Для подпроцессов и для инструментов, которые сами разрешают идентичность.
os.environ.setdefault("WORK_IDE_IDENTITY", TEST_IDENTITY)

# allow_fixture=True — единственное место в проекте, где фикстуру разрешено
# активировать. В обычной работе common.activate_identity() её отвергает.
common.activate_identity(TEST_IDENTITY, allow_fixture=True)


@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    """Перенаправляет все data/*-пути во временную директорию, чтобы тесты
    пайплайна/KB никогда не трогали реальную базу знаний.

    Имена файлов здесь префиксованы так же, как в бою: тест, где случайно
    захардкожено "vacancies.json", должен падать, а не молча работать.
    """
    data_dir = tmp_path / "data"
    knowledge_dir = data_dir / "knowledge"
    prefix = f"{TEST_IDENTITY}_"

    monkeypatch.setattr(common, "FILE_PREFIX", prefix)
    monkeypatch.setattr(common, "DATA_DIR", data_dir)
    monkeypatch.setattr(common, "KNOWLEDGE_DIR", knowledge_dir)
    monkeypatch.setattr(common, "RAW_DIR", data_dir / "raw")
    # Отчёты лежат отдельно от данных: общая папка reports/, архив внутри неё
    # разложен по идентичностям (см. common.activate_identity).
    reports_dir = tmp_path / "reports"
    monkeypatch.setattr(common, "REPORTS_DIR", reports_dir)
    monkeypatch.setattr(common, "REPORTS_ARCHIVE_DIR", reports_dir / "archive" / TEST_IDENTITY)
    monkeypatch.setattr(common, "STATE_PATH", data_dir / f"{prefix}state.json")
    monkeypatch.setattr(common, "VACANCIES_PATH", knowledge_dir / f"{prefix}vacancies.json")
    monkeypatch.setattr(common, "COMPANIES_PATH", knowledge_dir / f"{prefix}companies.json")
    monkeypatch.setattr(common, "RECRUITERS_PATH", knowledge_dir / f"{prefix}recruiters.json")
    monkeypatch.setattr(common, "INSIGHTS_PATH", knowledge_dir / f"{prefix}insights.md")
    common.ensure_dirs()
    return data_dir
