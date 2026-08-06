"""
Tests for merging the source catalogue with an identity's settings.

The split follows the boundary between «a fact about the world» and «a person's
preference»: the endpoint and the remote_only flag are properties of the board,
identical for everyone; enabled and params are one person's choice. An identity
cannot override an endpoint: a stale URL is a bug for everybody at once.
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

    # facts about the board came from the catalogue
    assert merged["alpha"]["url"] == "https://example.com/alpha"
    assert merged["alpha"]["remote_only"] is True
    # preferences came from the identity
    assert merged["alpha"]["params"]["hits_per_keyword"] == 25
    assert merged["beta"]["enabled"] is False


def test_unknown_source_name_fails_loudly(tmp_path, monkeypatch):
    """A typo in a source name must be caught at once rather than leading to the
    source silently never being queried."""
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
    assert "alpha" in str(exc.value), "the message should suggest the known names"


def test_identity_cannot_override_endpoint(tmp_path, monkeypatch):
    """An identity may set params, but the URL stays with the catalogue —
    otherwise a stale endpoint would have to be fixed by everyone separately."""
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
    """The url field in the config used to be dead: fetchers hard-coded their own
    API_URL, and the pipeline called fetch_fn() with no arguments at all."""
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
    """A config can move ahead of the code, or the other way round. One extra
    parameter is no reason to lose a whole source."""
    def picky_fetch():
        return [{"ok": True}], None

    records, err = pipeline.fetch_source_safely(
        "picky", picky_fetch, {"unknown_param": 1}
    )
    assert records == [{"ok": True}]
    assert err is None
    assert "does not accept some parameters" in capsys.readouterr().err


def test_himalayas_company_survives_a_renamed_api_field():
    """The board changed the shape of the field: `companyName`, then `company` as
    a string, and once a nested object. A real case, 2026-08-04: the parser read
    only `companyName`, the field went empty, and all 60 records from the source
    were silently discarded — at HTTP 200, from a «healthy» source."""
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
    """Measured 2026-08-04: the board returns companyName: "name" and
    companyLogo: "thumbnail_url" — literally the field names instead of the values.
    Vacancies from a company called «name» got into the database, and a person saw
    them in the report. A placeholder looks like a valid string and passes an
    """
    import fetch_himalayas

    assert fetch_himalayas._extract_company(
        {"companyName": "name", "companySlug": "micro1"}
    ) == "micro1"
    assert fetch_himalayas._extract_company(
        {"companyName": "Acme", "companySlug": "acme-inc"}
    ) == "Acme"
    assert fetch_himalayas._extract_company({"companyName": "name"}) == ""


def test_workable_and_smartrecruiters_parsers():
    """Two ATS providers added 2026-08-04. SmartRecruiters was verified against a
    live account (Visa, 2 vacancies); every Workable account checked returned an
    empty list, so its parser is pinned by a test against a sample response —
    otherwise its correctness would have stayed unverified."""
    import fetch_ats

    workable = {
        "name": "Acme Ltd",
        "jobs": [{
            "title": "Senior Backend Engineer",
            "url": "https://apply.workable.com/acme/j/ABC123/",
            "shortcode": "ABC123",
            "city": "Tel Aviv", "country": "Israel",
            "telecommuting": True,
            "department": "R&D",
            "description": "<p>Legacy .NET services</p>",
            "published_on": "2026-08-01",
        }],
    }
    records = fetch_ats._parse_workable(workable, "fallback", "acme")
    assert len(records) == 1
    rec = records[0]
    assert rec["company"] == "Acme Ltd", "the name from the response beats the one from the config"
    assert rec["location_raw"] == "Tel Aviv, Israel"
    assert rec["remote"] is True
    assert rec["external_id"] == "workable:acme:ABC123"

    smart = {
        "content": [{
            "id": "744000133907678",
            "name": "Senior Software Engineer",
            "location": {"city": "Austin", "country": "us", "remote": False},
            "department": {"label": "Technology"},
            "releasedDate": "2026-08-01",
        }],
    }
    records = fetch_ats._parse_smartrecruiters(smart, "Visa", "Visa")
    assert len(records) == 1
    assert records[0]["url"] == "https://jobs.smartrecruiters.com/Visa/744000133907678"
    assert records[0]["location_raw"] == "Austin, us"


def test_ats_parsers_skip_records_without_mandatory_fields():
    """Common to every ATS: a record without a title or a link is useless."""
    import fetch_ats

    assert fetch_ats._parse_workable({"jobs": [{"title": "", "url": "x"}]}, "c", "t") == []
    assert fetch_ats._parse_smartrecruiters({"content": [{"name": "X"}]}, "c", "t") == []
