"""The lists written in Python, SQL and the app's JavaScript alike agree.

The app cannot import Python and the SQL schema cannot import either, so
statuses, classes, filter bands, task kinds and the identity pattern are
written in several files (task 0128 counted eight copies of the statuses).
They agree today; this test keeps them so. A deliberate difference is
named in its assertion with the reason.
"""
import re
from pathlib import Path

import cleanup
import company_kinds
import db
import documents
import identity
import report
import schedules
import selections
import taskd
import taskq

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _strings(text: str) -> list:
    return re.findall(r"'([^']*)'", text)


def js_list(relative: str, name: str) -> list:
    """The quoted strings of `const NAME = [...]` or `new Set([...])`."""
    match = re.search(rf"\bconst {name} = (?:new Set\()?\[([^\]]*)\]", _source(relative))
    assert match, f"{relative}: no list {name}"
    return _strings(match.group(1))


def js_keys(relative: str, name: str) -> list:
    """The keys of `const NAME = { key: ..., ... };`, in order."""
    match = re.search(rf"\bconst {name} = \{{(.*?)\n\s*\}};", _source(relative), re.S)
    assert match, f"{relative}: no object {name}"
    body = re.sub(r"//[^\n]*", "", match.group(1))
    return re.findall(r"(\w+):", body)


def js_pattern(relative: str, name: str) -> str:
    match = re.search(rf"\bconst {name} = /(.+)/;", _source(relative))
    assert match, f"{relative}: no pattern {name}"
    return match.group(1)


def test_the_statuses_agree_with_the_schema():
    check = re.search(r"CHECK \(feedback_status IN \((.*?)\)\)", _source("schemas/db.sql"), re.S)
    assert check
    schema = set(_strings(check.group(1)))
    assert set(db.FEEDBACK_STATUSES) == schema
    assert set(selections.STATUSES) == schema
    assert len(selections.STATUSES) == len(schema)


def test_the_status_groups_agree_between_python_and_the_app():
    assert js_list("app/renderer/funnel.js", "FUNNEL") == list(selections.FUNNEL)
    assert js_list("app/main/store.js", "NEW") == list(selections.NEW)
    assert js_list("app/main/store.js", "DENIED") == list(selections.DENIED)
    groups = re.search(r"const STATUS_GROUPS = \[(.*?)\n  \];", _source("app/renderer/app.js"), re.S)
    assert groups
    lists = [_strings(m) for m in re.findall(r"statuses: \[([^\]]*)\]", groups.group(1))]
    assert lists == [list(selections.NEW), list(selections.FUNNEL), list(selections.DENIED)]
    # the clean-up chooses among every status
    assert set(js_list("app/main/cleanup.js", "STATUSES")) == set(selections.STATUSES)
    # store.js STATUSES is deliberately shorter: the answers set directly,
    # the funnel beyond "applied" is reached step by step
    assert set(js_list("app/main/store.js", "STATUSES")) <= set(selections.STATUSES)


def test_the_filter_bands_agree_everywhere():
    for relative in ("app/main/cleanup.js", "app/main/store.js", "app/renderer/app.js"):
        assert js_list(relative, "AGES") == list(selections.AGES), relative
    assert cleanup.AGES == selections.AGES
    for name in ("FRESHNESS", "COMPANY_KINDS", "ROLES"):
        assert js_list("app/main/store.js", name) == list(getattr(selections, name)), name
    assert js_list("app/renderer/app.js", "FRESHNESS") == list(selections.FRESHNESS)
    assert selections.COMPANY_KINDS == company_kinds.KINDS + ("other",)


def test_the_classes_agree_between_the_scripts_the_clean_up_and_the_app():
    listed = list(report.LISTED_CLASSES)
    assert list(cleanup.CLASSES) == listed + ["low_priority", "rejected"]
    assert js_list("app/main/cleanup.js", "CLASSES") == list(cleanup.CLASSES)
    assert js_keys("app/renderer/app.js", "CLEANUP_CLASS_KEYS") == list(cleanup.CLASSES)
    unlisted = js_list("app/renderer/app.js", "UNLISTED_CLASSES")
    assert set(unlisted) <= set(listed)
    assert unlisted == list(selections.NOT_SHOWN)
    # the app's sections: the starred and the person's own picks first, then
    # the listed classes less the ones never listed (queries.sql), in the
    # app's own order ("Never say never" right after "Long shots", task 0136)
    sections = js_keys("app/renderer/app.js", "CLASS_KEYS")
    assert sections[:2] == [selections.STAR_CLASS, selections.HAND_CLASS]
    assert sorted(sections[2:]) == sorted(c for c in listed if c not in unlisted)
    assert len(sections) == len(set(sections))


def test_the_task_kinds_and_schedules_agree_between_the_queue_and_the_app():
    # "pipeline" is deliberately missing in the app: it is started by hand
    # from a terminal, never by a click
    assert set(js_list("app/main/queue.js", "KINDS")) == set(taskq.KINDS) - {"pipeline"}
    assert set(js_list("app/main/queue.js", "SCHEDULE_WHAT")) == set(schedules.WHAT)
    assert set(js_list("app/main/queue.js", "SCHEDULE_MISSED")) == set(schedules.MISSED)


def test_the_identity_and_vacancy_patterns_agree():
    assert taskq.PREFIX_RE.pattern == identity.PREFIX_RE.pattern
    for relative in ("app/main/cleanup.js", "app/main/documents.js", "app/main/main.js", "app/main/queue.js"):
        assert js_pattern(relative, "IDENTITY_PATTERN") == identity.PREFIX_RE.pattern, relative
    assert taskd.VACANCY_RE.pattern == documents.VACANCY_ID_RE.pattern
    for relative in ("app/main/documents.js", "app/main/queue.js"):
        assert js_pattern(relative, "VACANCY_PATTERN") == documents.VACANCY_ID_RE.pattern, relative
