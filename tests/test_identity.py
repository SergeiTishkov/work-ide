"""
Tests for the search-identity system.

These tests protect the central property of the multi-user architecture: an
agent working under identity A cannot accidentally touch identity B. Failure
here is quiet and expensive — a spoiled shortlist nobody notices — so the
checks are many and pedantic.
"""
import os

import pytest

import common
import identity


# --- Prefix format ---------------------------------------------------------

@pytest.mark.parametrize("prefix", ["kisel", "ftf", "abc", "a1b2c3", "jvst"])
def test_valid_prefixes_accepted(prefix):
    assert identity.PREFIX_RE.match(prefix), f"{prefix} should be accepted"


@pytest.mark.parametrize("prefix", [
    "ab",           # too short
    "abcdefg",      # too long
    "KISEL",        # uppercase: the Windows FS is case-insensitive, so confusion
                    # is guaranteed
    "1abc",         # starts with a digit
    "ka-lm",        # hyphen
    "ka lm",        # space
    "ка",           # Cyrillic: a prefix must be Latin script
    "",
])
def test_invalid_prefixes_rejected(prefix):
    assert not identity.PREFIX_RE.match(prefix), f"{prefix} should be rejected"


# --- Registry --------------------------------------------------------------

def test_template_dir_is_not_an_identity():
    # Folders starting with "_" are scaffolding, not identities. Otherwise the
    # agent would try to search for work using a template.
    assert identity.TEMPLATE_DIR_NAME not in identity.list_identities(
        include_fixtures=True)


def test_fixture_hidden_from_normal_listing():
    assert "ftf" in identity.list_identities(include_fixtures=True)
    assert "ftf" not in identity.list_identities(include_fixtures=False)


def test_identity_file_path_uses_prefix():
    """The FOLDER name is long and explanatory; the FILE names are short.

    The split is deliberate: a folder is seen rarely and you want its name to
    tell you what the search was; file names appear in every command and in
    grep output, where a long name only gets in the way.
    """
    path = identity.identity_file("kisel", "criteria.yaml")
    assert path.name == "kisel_criteria.yaml"
    assert path.parent.name == "kisel-keep-it-simple-easy-legacy"


# --- Validation ------------------------------------------------------------

def test_existing_identities_are_valid():
    """Every identity present must be structurally intact."""
    results = identity.validate_all()
    broken = {p: probs for p, probs in results.items() if probs}
    assert not broken, f"invalid identities present: {broken}"


def test_validate_rejects_unknown_prefix():
    problems = identity.validate("nosuch")
    assert problems
    assert any("not found" in p for p in problems)


def test_validate_rejects_bad_prefix_format():
    problems = identity.validate("BAD-PREFIX")
    assert problems
    assert any("prefix format" in p for p in problems)


def test_validate_catches_unprefixed_file(tmp_path, monkeypatch):
    """An unprefixed file inside an identity breaks the central rule."""
    identities_dir = tmp_path / "identities"
    (identities_dir / "abcd").mkdir(parents=True)
    monkeypatch.setattr(common, "IDENTITIES_DIR", identities_dir)

    d = identities_dir / "abcd"
    for name in identity.REQUIRED_FILES:
        (d / f"abcd_{name}").write_text("{}", encoding="utf-8")
    (d / "notes.md").write_text("a file with no prefix", encoding="utf-8")

    problems = identity.validate("abcd")
    assert any("notes.md" in p and "abcd_" in p for p in problems)


def test_validate_catches_foreign_prefix_leak(tmp_path, monkeypatch):
    """The likeliest mistake when creating an identity is copy-pasting somebody
    else's files with the paths inside only half corrected."""
    identities_dir = tmp_path / "identities"
    for prefix in ("abcd", "efgh"):
        d = identities_dir / prefix
        d.mkdir(parents=True)
        for name in identity.REQUIRED_FILES:
            (d / f"{prefix}_{name}").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(common, "IDENTITIES_DIR", identities_dir)

    # A reference to an efgh file ended up in an abcd file — classic copy-paste
    (identities_dir / "abcd" / "abcd_identity.md").write_text(
        "see also efgh_criteria.yaml", encoding="utf-8"
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


# --- Resolving the active identity -----------------------------------------

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


# The test "a single entry in active.yaml is chosen silently" was removed
# 2026-08-05: there is no list of active identities any more. It was replaced
# by a registry that cannot lie — the folders in local-identities/ themselves.
# The equivalent behaviour is covered by
# test_a_single_identity_is_chosen_without_asking below.


def test_several_identities_without_a_choice_refuses(monkeypatch, tmp_path):
    """Silently choosing the wrong identity is precisely the failure this whole
    system was built to prevent. Better to refuse and ask.

    The source of truth is the FOLDERS in local-identities/, not a registry
    file: a registry can drift away from the disk, folders cannot.
    """
    monkeypatch.delenv("WORK_IDE_IDENTITY", raising=False)
    monkeypatch.setattr(common, "LOCAL_CONSTITUTION_DIR", tmp_path / "nonexistent")
    monkeypatch.setattr(identity, "list_identities", lambda *a, **k: ["aaaa", "bbbb"])

    with pytest.raises(identity.IdentityError) as exc:
        identity.resolve_identity()
    assert "aaaa" in str(exc.value) and "bbbb" in str(exc.value)


def test_a_single_identity_is_chosen_without_asking(monkeypatch, tmp_path):
    """One folder, no question: there is no ambiguity to resolve."""
    monkeypatch.delenv("WORK_IDE_IDENTITY", raising=False)
    monkeypatch.setattr(common, "LOCAL_CONSTITUTION_DIR", tmp_path / "nonexistent")
    monkeypatch.setattr(identity, "list_identities", lambda *a, **k: ["only"])
    assert identity.resolve_identity() == "only"


def test_no_identity_at_all_refuses_with_onboarding_hint(monkeypatch, tmp_path):
    monkeypatch.delenv("WORK_IDE_IDENTITY", raising=False)
    monkeypatch.setattr(common, "LOCAL_CONSTITUTION_DIR", tmp_path / "nonexistent")

    monkeypatch.setattr(identity, "list_identities", lambda *a, **k: [])

    with pytest.raises(identity.IdentityError) as exc:
        identity.resolve_identity()
    message = str(exc.value)
    assert "ONBOARDING" in message.upper()
    # A newcomer needs "here are the templates, here is how to clone one",
    # not "pass --identity".
    assert "templates.py clone" in message
    assert "blank" in message


# --- Activation ------------------------------------------------------------

def test_fixture_refused_without_explicit_flag():
    """A real search against the test fixture must be impossible."""
    with pytest.raises(identity.InvalidIdentityError) as exc:
        common.activate_identity("ftf")  # without allow_fixture
    assert "fixture" in str(exc.value).lower()
    # conftest activated ftf at module level — restore that state
    common.activate_identity("ftf", allow_fixture=True)


def test_activation_binds_all_paths(tmp_path):
    common.activate_identity("ftf", allow_fixture=True, data_root=tmp_path)
    try:
        assert common.ACTIVE_IDENTITY == "ftf"
        assert common.FILE_PREFIX == "ftf_"
        assert common.DATA_DIR == tmp_path / "ftf"
        assert common.VACANCIES_PATH.name == "ftf_vacancies.json"
        assert common.STATE_PATH.name == "ftf_state.json"
        # Reports live separately from accumulated data: a shared reports/
        # folder, with the archive inside it split per identity. On an isolated
        # run (data_root passed) the whole layout moves inside it — otherwise
        # the test would write reports into the real repository folder, over a
        # live shortlist.
        assert common.REPORTS_DIR == tmp_path / "reports"
        assert common.REPORTS_ARCHIVE_DIR == tmp_path / "reports" / "archive" / "ftf"
        assert common.USER_AGENT and "WorkIdeJobResearchBot" in common.USER_AGENT
    finally:
        common.activate_identity("ftf", allow_fixture=True)


def test_identity_config_resolves_to_prefixed_file():
    assert common.identity_config("criteria.yaml").name == "ftf_criteria.yaml"


def test_data_marker_detects_foreign_data_dir(tmp_path):
    """The data folder was renamed by hand and holds somebody else's database.
    The mistake is quiet and expensive; the check is cheap."""
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


# --- Refusal without an identity -------------------------------------------

def test_data_access_refused_without_identity():
    """Rule zero has to live in the code, not only in the documentation."""
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


# --- Creating an identity from the template --------------------------------
#
# This used to be a six-step procedure of manual `copy` commands, each renaming
# a file. That is exactly where the project got burned: a file referencing
# kisel_ ended up inside the ftf fixture. These tests protect the automation
# that makes the mistake impossible.

@pytest.fixture
def sandbox_identities(tmp_path, monkeypatch):
    """A separate identities/ folder holding a copy of the template, so that
    creation tests leave no litter in the real repository."""
    import shutil

    sandbox = tmp_path / "local-identities"
    sandbox.mkdir()
    templates_root = tmp_path / "identity-templates"
    templates_root.mkdir()
    shutil.copytree(common.TEMPLATES_DIR / identity.TEMPLATE_DIR_NAME,
                    templates_root / identity.TEMPLATE_DIR_NAME)
    monkeypatch.setattr(common, "TEMPLATES_DIR", templates_root)
    monkeypatch.setattr(common, "IDENTITIES_DIR", sandbox)
    monkeypatch.setattr(common, "FIXTURES_DIR", tmp_path / "no-fixtures")
    return sandbox


def test_scaffold_creates_all_required_files_with_prefix(sandbox_identities):
    created = identity.scaffold_identity("newp", "New Product Search")
    names = {p.name for p in created}
    assert created[0].parent.name == "newp-new-product-search"
    for required in identity.REQUIRED_FILES:
        assert f"newp_{required}" in names, f"required file {required} is missing"
    assert all(p.name.startswith("newp_") for p in created)


def test_scaffolded_identity_passes_validation(sandbox_identities):
    identity.scaffold_identity("newp", "New Product Search")
    assert identity.validate("newp") == [], \
        "scaffolding must be structurally correct straight away"


def test_scaffold_substitutes_template_placeholders(sandbox_identities):
    identity.scaffold_identity("newp", "New Product Search")
    for path in (sandbox_identities / "newp-new-product-search").iterdir():
        text = path.read_text(encoding="utf-8")
        assert f"{identity.TEMPLATE_PREFIX}_" not in text, \
            f"the template prefix is still in {path.name}"
        assert identity.TEMPLATE_PREFIX_PLACEHOLDER not in text, (
            f"the prefix placeholder is still in {path.name} — the agent would "
            "follow a broken path"
        )


def test_scaffold_refuses_to_overwrite_existing_identity(sandbox_identities):
    identity.scaffold_identity("newp", "New Product Search")
    # Same prefix, different expansion — still refused: a prefix has to be
    # unique, or there is no telling which of two folders is "the" one.
    with pytest.raises(identity.InvalidIdentityError) as exc:
        identity.scaffold_identity("newp", "Totally Different Search")
    assert "already exists" in str(exc.value)


@pytest.mark.parametrize("bad", ["ab", "KISEL", "1abc", "ka-lm", "blank"])
def test_scaffold_refuses_bad_prefix(sandbox_identities, bad):
    with pytest.raises(identity.InvalidIdentityError):
        identity.scaffold_identity(bad, "Some Search")


def test_scaffold_does_not_touch_the_local_constitution(sandbox_identities, tmp_path, monkeypatch):
    # Which identities are active is a person's deliberate decision, living
    # outside git. Creating scaffolding must not activate it silently.
    lc = tmp_path / "lc"
    lc.mkdir()
    monkeypatch.setattr(common, "LOCAL_CONSTITUTION_DIR", lc)
    identity.scaffold_identity("newp", "New Product Search")
    assert not (lc / "active.yaml").exists()
    assert identity.active_identities() == []


# --- Folder name: prefix plus expansion ------------------------------------
#
# The two levels of naming are deliberately different. A folder is seen rarely,
# and `kisel` alone gives no way to remember what that search was — hence the
# expansion right in the folder name. The files inside are the opposite:
# short, because their names appear in every command, in grep output and in
# paths inside reports.

@pytest.mark.parametrize("folder,expected", [
    ("kisel-keep-it-simple-easy-legacy", "kisel"),
    ("jvst-java-startup-onsite", "jvst"),
    ("ftf-frozen-test-fixture", "ftf"),
    ("abcd", "abcd"),                        # no expansion: recognised, but
                                             # validate() will complain
    ("blank-start-from-scratch", "blank"),   # the empty template is a valid name too
    ("Kisel-Keep-It", None),                 # uppercase
    ("kisel_keep_it", None),                 # underscores separate FILES, not folders
])
def test_folder_prefix_extraction(folder, expected):
    assert identity.folder_prefix(folder) == expected


@pytest.mark.parametrize("full_name,expected", [
    ("Keep It Simple, Easy, Legacy", "kisel-keep-it-simple-easy-legacy"),
    ("KISEL — Keep It Simple", "kisel-keep-it-simple"),   # the prefix is not doubled
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
    assert any("no " in p and "expansion" in p for p in problems)


def test_two_folders_with_the_same_prefix_are_refused(tmp_path, monkeypatch):
    """An unresolvable ambiguity: nothing can say which of the two folders is
    "the" one, and silently picking either mixes the two sets of data."""
    identities_dir = tmp_path / "identities"
    (identities_dir / "abcd-first-search").mkdir(parents=True)
    (identities_dir / "abcd-second-search").mkdir(parents=True)
    monkeypatch.setattr(common, "IDENTITIES_DIR", identities_dir)

    with pytest.raises(identity.InvalidIdentityError) as exc:
        identity.identity_folders()
    assert "abcd" in str(exc.value)


def test_files_keep_the_short_prefix_not_the_long_folder_name(sandbox_identities):
    """The key property of the split: the long name stays on the folder alone."""
    created = identity.scaffold_identity("newp", "New Product Search")
    assert created[0].parent.name == "newp-new-product-search"
    for path in created:
        assert path.name.startswith("newp_"), (
            f"{path.name} — a file name must be short, carrying just the prefix"
        )
        assert "new-product-search" not in path.name


# --- Identity readiness: filled in, not merely existing --------------------
#
# Found for real on a fresh-clone run, 2026-08-04: `identity.py new` plus
# `pipeline.py` ran to completion and wrote a report covering 1734 vacancies —
# with a placeholder in the title and scoring against an empty stack. Rule zero
# checked that an identity existed, but not that it was filled in.

def test_fresh_scaffold_is_not_ready(sandbox_identities):
    identity.scaffold_identity("newp", "New Product Search")
    problems = identity.readiness_problems("newp")
    assert problems, "template scaffolding cannot count as ready to search"
    assert any("tech_stack.core" in p for p in problems)


def test_activation_refuses_an_unfilled_identity(sandbox_identities, monkeypatch, tmp_path):
    identity.scaffold_identity("newp", "New Product Search")
    monkeypatch.setattr(common, "LOCAL_CONSTITUTION_DIR", tmp_path / "lc")
    with pytest.raises(identity.IdentityNotReadyError) as exc:
        common.activate_identity("newp", data_root=tmp_path / "data")
    assert "not filled in" in str(exc.value)
    assert "ONBOARDING" in str(exc.value)


def test_placeholders_are_looked_for_in_values_not_comments(sandbox_identities):
    """The first version of this check read the whole file and declared a
    filled-in identity unfilled: angle brackets appear constantly in comments
    as part of the documentation ("put <token> here")."""
    identity.scaffold_identity("newp", "New Product Search")
    d = sandbox_identities / "newp-new-product-search"
    (d / "newp_ats_targets.yaml").write_text(
        "# put the <token> from the careers page here\ntargets: []\n",
        encoding="utf-8"
    )
    problems = identity.readiness_problems("newp")
    assert not any("newp_ats_targets.yaml" in p for p in problems), (
        "a placeholder in a comment is documentation, not an unfilled field"
    )


def test_shipped_identity_is_complete_except_for_personal_data():
    """A shipped identity must be filled in COMPLETELY — apart from the personal
    fields, which have no business being in a shared repository at all.

    A fresh-clone run on 2026-08-04 exercised this: kisel came out "not ready",
    quite correctly, because the overlay holding personal data lives outside
    git. That is right behaviour rather than breakage — a new person has to
    supply their own. But everything else (stack, criteria, sources) must be
    ready to run immediately, or the gate is tuned too strictly and blocks the
    normal path.
    """
    problems = identity.readiness_problems("kisel")
    non_personal = [p for p in problems
                    if not p.startswith(identity.LOCAL_FIELDS_MISSING_PREFIX)]
    assert non_personal == [], (
        "nothing in the shared part of an identity should be left unfilled: "
        f"{non_personal}"
    )


# --- The personal-data overlay from the Local Constitution -----------------

def test_local_sentinel_is_resolved_from_the_local_constitution(tmp_path, monkeypatch):
    lc = tmp_path / "lc"
    (lc / "personal" / "abcd").mkdir(parents=True)
    (lc / "personal" / "abcd" / "abcd_owner.yaml").write_text(
        "owner:\n  name: Real Name\n  languages: [English]\n", encoding="utf-8"
    )
    monkeypatch.setattr(common, "LOCAL_CONSTITUTION_DIR", lc)

    profile = {"owner": {"name": "local", "languages": "local", "role": "Developer"}}
    merged, missing = common.resolve_local_fields("abcd", profile)

    assert merged["owner"]["name"] == "Real Name"
    assert merged["owner"]["languages"] == ["English"]
    assert merged["owner"]["role"] == "Developer", "non-personal fields are untouched"
    assert missing == []
    assert profile["owner"]["name"] == "local", "the source profile is not mutated"


def test_missing_local_value_is_reported_not_silently_empty(tmp_path, monkeypatch):
    """Silently substituting emptiness is the worst option: scoring would run
    against empty languages and produce plausible rubbish."""
    monkeypatch.setattr(common, "LOCAL_CONSTITUTION_DIR", tmp_path / "empty")
    merged, missing = common.resolve_local_fields("abcd", {"owner": {"name": "local"}})
    assert missing == ["owner.name"]


# --- init-local: setting up the Local Constitution -------------------------

def test_init_local_creates_the_folder_and_registers_the_identity(tmp_path, monkeypatch):
    lc = tmp_path / "lc"
    monkeypatch.setattr(common, "LOCAL_CONSTITUTION_DIR", lc)
    identity.init_local_constitution("abcd", note="test search")

    cfg = identity.load_local_constitution()
    prefixes = [e["prefix"] for e in cfg["active_identities"]]
    assert prefixes == ["abcd"]
    assert (lc / "personal" / "abcd").is_dir()


def test_init_local_does_not_rewrite_an_unchanged_file(tmp_path, monkeypatch):
    """active.yaml is written by a person and is full of comments, which a YAML
    dumper erases. It happened while the command was being built, 2026-08-04:
    a harmless repeat run wiped every line of documentation inside the file."""
    lc = tmp_path / "lc"
    monkeypatch.setattr(common, "LOCAL_CONSTITUTION_DIR", lc)
    identity.init_local_constitution("abcd")

    path = identity.local_constitution_path()
    handwritten = ("# my comment, which must not be lost\n"
                   + path.read_text(encoding="utf-8"))
    path.write_text(handwritten, encoding="utf-8")

    identity.init_local_constitution("abcd")
    assert path.read_text(encoding="utf-8") == handwritten


def test_init_local_sets_default_identity_when_a_second_one_appears(tmp_path, monkeypatch):
    """Without default_identity, a second identity breaks the FIRST one's
    commands — the ones that had been working until now."""
    lc = tmp_path / "lc"
    monkeypatch.setattr(common, "LOCAL_CONSTITUTION_DIR", lc)
    identity.init_local_constitution("abcd")
    assert identity.default_identity() is None, \
        "with one identity no default is needed"

    identity.init_local_constitution("efgh")
    assert identity.default_identity() == "abcd"


def test_init_local_backs_up_before_rewriting(tmp_path, monkeypatch):
    lc = tmp_path / "lc"
    monkeypatch.setattr(common, "LOCAL_CONSTITUTION_DIR", lc)
    identity.init_local_constitution("abcd")
    identity.init_local_constitution("efgh")   # this entry forces a rewrite
    assert (lc / "active.yaml.bak").exists()


def test_init_local_writes_an_owner_skeleton_for_the_local_fields(tmp_path, monkeypatch, sandbox_identities):
    """Handing a person a file with the fields THEY need is more useful than
    sending them off to build the structure from a specification."""
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
    assert "OUTSIDE GIT" in text


def test_owner_skeleton_never_overwrites_a_filled_file(tmp_path, monkeypatch, sandbox_identities):
    identity.scaffold_identity("newp", "New Product Search")
    monkeypatch.setattr(common, "LOCAL_CONSTITUTION_DIR", tmp_path / "lc")
    identity.init_local_constitution("newp")

    skeleton = common.personal_dir("newp") / "newp_owner.yaml"
    skeleton.write_text("owner:\n  name: Already filled in\n", encoding="utf-8")
    identity.init_local_constitution("newp")
    assert "Already filled in" in skeleton.read_text(encoding="utf-8")


# --- Cloning an identity ---------------------------------------------------
#
# A common case: the same search aimed at different countries. Stack,
# employment type and the marks of a suitable company are shared; the
# geography rules, languages and time zone are not. Building the second
# identity from scratch means answering fifty questions again to change three.

def test_clone_copies_every_file_under_the_new_prefix(sandbox_identities):
    identity.scaffold_identity("srcp", "Source Search")
    created = identity.clone_identity("srcp", "dstp", "Source Search for Germany")

    assert created[0].parent.name == "dstp-source-search-for-germany"
    names = {p.name for p in created}
    for required in identity.REQUIRED_FILES:
        assert f"dstp_{required}" in names


def test_clone_rewrites_internal_references_to_the_source(sandbox_identities):
    """Otherwise the clone would break the rule that one identity's files never
    reference another, and the validator would reject it."""
    identity.scaffold_identity("srcp", "Source Search")
    identity.identity_file("srcp", "identity.md").write_text(
        "# srcp\nsee srcp_criteria.yaml\n", encoding="utf-8"
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
    assert "already taken" in str(exc.value)


def test_clone_refuses_an_unknown_source(sandbox_identities):
    with pytest.raises(identity.UnknownIdentityError):
        identity.clone_identity("nosuch", "dstp", "Cloned Search")


def test_clone_refuses_the_frozen_fixture():
    """The fixture is calibrated for the tests rather than for a live search — a
    clone of it would inherit the calibration values and quietly search for the
    wrong thing."""
    with pytest.raises(identity.InvalidIdentityError) as exc:
        identity.clone_identity("ftf", "dstp", "Cloned Search")
    assert "fixture" in str(exc.value)
