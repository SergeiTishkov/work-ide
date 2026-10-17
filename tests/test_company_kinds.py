"""Company kinds (tools/company_kinds.py, config/company_kinds.yaml): which
companies are freelance marketplaces, agencies or reposters, and under which
name the app's "Company" drop-down lists them."""
import pytest

import common
import company_kinds as ck


@pytest.mark.parametrize("raw, expected", [
    ("Proxify AB", "proxify"),
    ("JOBSTER PRIVATE LTD.", "jobster"),
    ("RECRUIT EXPRESS PTE LTD", "recruit express"),
    ("Lemon.io", "lemon io"),
    ("Fraser &amp; Co. Talent Partners Limited", "fraser and co talent partners"),
    ("Prime Staffing B.V.", "prime staffing"),
    ("Ltd", "ltd"),                      # a suffix alone is the whole name
    ("  ", ""),
    (None, ""),
])
def test_normalise(raw, expected):
    assert ck.normalise(raw) == expected


@pytest.mark.parametrize("company, kind, name", [
    ("Proxify", "marketplace", "Proxify"),
    ("Proxify AB", "marketplace", "Proxify"),
    ("Outlier AI", "marketplace", "Outlier"),
    ("Hays Specialist Recruitment Limited", "agency", "Hays"),
    ("HAYS SPECIALIST RECRUITMENT PTE. LTD.", "agency", "Hays"),
    ("Kforce Technology Staffing", "agency", "Kforce"),
    ("Nigel Frank International", "agency", "Tenth Revolution Group"),
    ("JOBSTER PRIVATE LTD.", "reposter", "Jobster"),
    ("Haystack People", "reposter", "Haystack"),
    # a keyword: listed under the company's own name, its legal suffix aside
    ("Deerfoot Recruitment Solutions Limited", "agency", "Deerfoot Recruitment Solutions"),
    ("Set2Recruit", "agency", "Set2Recruit"),
    ("Undisclosed agency (ContractorUK)", "agency", "Undisclosed agency (ContractorUK)"),
    ("Vivid Resourcing", "agency", "Vivid Resourcing"),
])
def test_intermediaries(company, kind, name):
    assert ck.classify(company) == {"kind": kind, "name": name}


@pytest.mark.parametrize("company", [
    "Stripe",
    "Turing Pharmaceuticals",            # "turing" is exact
    "Outlier Ventures",                  # so is "outlier"
    "Hexagon Manufacturing Intelligence",  # "turing" inside a word is no match
    "Hayes Software",                    # "hays" is a whole word
    "TALENT Software Services",          # "talent" is not a keyword
    "Société Générale",
    "",
    None,
])
def test_employers_are_other(company):
    assert ck.classify(company) is None


def test_mapping_holds_the_intermediaries_only_and_one_spelling_per_company():
    found = ck.mapping(["Stripe", "Proxify", "Proxify AB", "Spectrum IT Recruitment",
                        "Spectrum It Recruitment Limited", "Proxify", None, ""])
    assert set(found) == {"Proxify", "Proxify AB", "Spectrum IT Recruitment",
                          "Spectrum It Recruitment Limited"}
    assert {v["name"] for v in found.values()} == {"Proxify", "Spectrum IT Recruitment"}


def test_the_spelling_not_in_capitals_names_the_row():
    found = ck.mapping(["MADISON RECRUITMENT LTD", "Madison Recruitment"])
    assert {v["name"] for v in found.values()} == {"Madison Recruitment"}


def test_the_catalogue_is_consistent():
    config = common.load_yaml(common.shared_config("company_kinds.yaml"))
    assert set(config["kinds"]) == set(ck.KINDS)
    assert set(config["keywords"]) <= set(ck.KINDS)
    seen = {}
    for kind, entries in config["kinds"].items():
        for entry in entries:
            phrases = (entry.get("match") or []) + (entry.get("exact") or [])
            assert entry.get("name") and phrases, entry
            assert not set(entry) - {"name", "match", "exact"}, entry
            for phrase in phrases:
                norm = ck.normalise(str(phrase))
                assert norm, entry
                assert norm not in seen, f"{phrase!r} is in {seen.get(norm)} and {entry['name']}"
                seen[norm] = entry["name"]
            # a short prefix takes unrelated names: docs/TECH_MATCHING.md
            for phrase in entry.get("match") or []:
                assert len(ck.normalise(str(phrase))) >= 4, (entry["name"], phrase)


def test_every_entry_classifies_its_own_name():
    config = common.load_yaml(common.shared_config("company_kinds.yaml"))
    for kind, entries in config["kinds"].items():
        for entry in entries:
            for phrase in (entry.get("match") or []) + (entry.get("exact") or []):
                assert ck.classify(str(phrase)) == {"kind": kind, "name": entry["name"]}, phrase


def test_cli_prints_the_kind(capsys):
    assert ck.main(["Proxify AB", "Stripe"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert '"kind": "marketplace"' in out[0] and '"name": "Proxify"' in out[0]
    assert '"kind": "other"' in out[1]


def test_write_stores_the_kinds_without_a_selection(isolated_data_dir, capsys):
    import db
    import kb

    kb.save_vacancies({})
    with db.session() as conn:
        db.ensure_identity(conn)
        conn.execute("INSERT INTO vacancies (id, data) VALUES ('v1', '{}')")
        conn.execute("INSERT INTO vacancy_identity (identity_id, vacancy_id, view) "
                     "VALUES (?, 'v1', '{\"company\": \"Proxify AB\"}')", (db.identity(),))
    assert ck.main(["--write"]) == 0
    with db.session() as conn:
        (value,) = conn.execute("SELECT value FROM meta WHERE key = 'company_kinds'").fetchone()
    assert '"Proxify AB": {"kind": "marketplace", "name": "Proxify"}' in value
    assert "1 company names" in capsys.readouterr().out
