"""
Тесты слияния каталога источников с настройками идентичности.

Разделение проведено по границе «факт о мире» / «предпочтение человека»:
эндпоинт и признак remote_only — свойства площадки, одинаковые для всех;
enabled и params — выбор конкретного человека. Идентичность не может
переопределить эндпоинт: устаревший URL это баг для всех сразу.
"""
import pytest

import common
import pipeline


def _write_catalog(tmp_path, monkeypatch, body: str):
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(exist_ok=True)
    (cfg_dir / "sources.catalog.yaml").write_text(body, encoding="utf-8")
    monkeypatch.setattr(common, "SHARED_CONFIG_DIR", cfg_dir)


def test_catalog_provides_endpoint_identity_provides_preference(tmp_path, monkeypatch):
    _write_catalog(tmp_path, monkeypatch, """
schema_version: 1
sources:
  - name: alpha
    kind: json_api
    remote_only: true
    url: "https://example.com/alpha"
  - name: beta
    kind: json_api
    remote_only: false
    url: "https://example.com/beta"
""")
    identity_dir = tmp_path / "identities" / "ftf"
    identity_dir.mkdir(parents=True)
    (identity_dir / "ftf_sources.yaml").write_text("""
sources:
  - name: alpha
    enabled: true
    params:
      hits_per_keyword: 25
  - name: beta
    enabled: false
""", encoding="utf-8")
    monkeypatch.setattr(common, "IDENTITY_DIR", identity_dir)

    merged = {s["name"]: s for s in common.load_sources()}

    # факты о площадке пришли из каталога
    assert merged["alpha"]["url"] == "https://example.com/alpha"
    assert merged["alpha"]["remote_only"] is True
    # предпочтения — из идентичности
    assert merged["alpha"]["params"]["hits_per_keyword"] == 25
    assert merged["beta"]["enabled"] is False


def test_unknown_source_name_fails_loudly(tmp_path, monkeypatch):
    """Опечатка в имени источника должна ловиться сразу, а не приводить к тому,
    что источник молча не опрашивается."""
    _write_catalog(tmp_path, monkeypatch, """
schema_version: 1
sources:
  - name: alpha
    kind: json_api
    url: "https://example.com/alpha"
""")
    identity_dir = tmp_path / "identities" / "ftf"
    identity_dir.mkdir(parents=True)
    (identity_dir / "ftf_sources.yaml").write_text(
        "sources:\n  - name: alfa\n    enabled: true\n", encoding="utf-8"
    )
    monkeypatch.setattr(common, "IDENTITY_DIR", identity_dir)

    with pytest.raises(ValueError) as exc:
        common.load_sources()
    assert "alfa" in str(exc.value)
    assert "alpha" in str(exc.value), "сообщение должно подсказывать известные имена"


def test_identity_cannot_override_endpoint(tmp_path, monkeypatch):
    """Идентичность может задать params, но URL остаётся за каталогом —
    иначе устаревший эндпоинт чинился бы у каждого отдельно."""
    _write_catalog(tmp_path, monkeypatch, """
schema_version: 1
sources:
  - name: alpha
    kind: json_api
    url: "https://canonical.example.com/api"
""")
    identity_dir = tmp_path / "identities" / "ftf"
    identity_dir.mkdir(parents=True)
    (identity_dir / "ftf_sources.yaml").write_text("""
sources:
  - name: alpha
    enabled: true
    params:
      hits_per_keyword: 10
""", encoding="utf-8")
    monkeypatch.setattr(common, "IDENTITY_DIR", identity_dir)

    merged = {s["name"]: s for s in common.load_sources()}
    assert merged["alpha"]["url"] == "https://canonical.example.com/api"


def test_fetch_params_passes_url_and_identity_params():
    """Раньше поле url в конфиге было мёртвым: фетчеры хардкодили свой API_URL,
    а пайплайн звал fetch_fn() вообще без аргументов."""
    src = {
        "name": "alpha",
        "url": "https://example.com/alpha",
        "params": {"hits_per_keyword": 7},
    }
    params = pipeline.fetch_params(src)
    assert params["url"] == "https://example.com/alpha"
    assert params["hits_per_keyword"] == 7


def test_fetch_params_identity_value_wins_over_catalog_default():
    src = {
        "name": "alpha",
        "url": "https://catalog.example.com",
        "params": {"url": "https://identity.example.com"},
    }
    assert pipeline.fetch_params(src)["url"] == "https://identity.example.com"


def test_fetcher_not_accepting_param_does_not_crash_pipeline(capsys):
    """Конфиг может уйти вперёд кода (или наоборот). Лишний параметр —
    не повод терять весь источник."""
    def picky_fetch():
        return [{"ok": True}], None

    records, err = pipeline.fetch_source_safely(
        "picky", picky_fetch, {"unknown_param": 1}
    )
    assert records == [{"ok": True}]
    assert err is None
    assert "не принимает часть параметров" in capsys.readouterr().err


def test_himalayas_company_survives_a_renamed_api_field():
    """Площадка меняла форму поля: `companyName`, потом `company` строкой,
    когда-то — вложенным объектом. Реальный случай 2026-08-04: парсер читал
    только `companyName`, поле стало пустым, и все 60 записей источника молча
    отбрасывались — при HTTP 200 и «здоровом» источнике."""
    import fetch_himalayas

    for payload in (
        {"companyName": "Acme"},
        {"company": "Acme"},
        {"company": {"name": "Acme"}},
        {"organization": "Acme"},
    ):
        assert fetch_himalayas._extract_company(payload) == "Acme", payload

    assert fetch_himalayas._extract_company({}) == ""


def test_himalayas_placeholder_company_falls_back_to_the_slug():
    """Замер 2026-08-04: площадка отдаёт companyName: "name" и
    companyLogo: "thumbnail_url" — буквально названия полей вместо значений.
    В базе завелись вакансии от компании «name», и человек увидел их в отчёте.
    Плейсхолдер выглядит валидной строкой и молча проходит проверку на пустоту.
    """
    import fetch_himalayas

    assert fetch_himalayas._extract_company(
        {"companyName": "name", "companySlug": "micro1"}
    ) == "micro1"
    assert fetch_himalayas._extract_company(
        {"companyName": "Acme", "companySlug": "acme-inc"}
    ) == "Acme"
    assert fetch_himalayas._extract_company({"companyName": "name"}) == ""
