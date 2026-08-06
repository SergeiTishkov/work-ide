import normalize
import common


def test_strip_html_basic():
    html = "<p>Hello <b>World</b></p><br><li>item one</li><li>item two</li>"
    text = common.strip_html(html)
    assert "Hello" in text and "World" in text
    assert "item one" in text and "item two" in text
    assert "<" not in text and ">" not in text


def test_strip_html_removes_script_and_style():
    html = "<style>.x{color:red}</style><script>alert(1)</script><p>Real content</p>"
    text = common.strip_html(html)
    assert "Real content" in text
    assert "alert" not in text
    assert "color:red" not in text


def test_strip_html_handles_empty_and_none():
    assert common.strip_html(None) == ""
    assert common.strip_html("") == ""
    assert common.strip_html("   ") == ""


def test_strip_html_unescapes_entities():
    text = common.strip_html("Salary &amp; benefits &mdash; great &lt;team&gt;")
    assert "&amp;" not in text
    assert "Salary" in text and "benefits" in text


def test_normalize_record_rejects_missing_required_fields():
    assert normalize.normalize_record({}) is None
    assert normalize.normalize_record({"source": "x", "title": "y"}) is None
    assert (
        normalize.normalize_record(
            {"source": "x", "external_id": "1", "title": "t", "company": "c", "url": ""}
        )
        is None
    )


def test_normalize_record_rejects_blank_strings():
    # the fields exist but hold only whitespace — those must be discarded too
    raw = {
        "source": "x",
        "external_id": "1",
        "title": "   ",
        "company": "Acme",
        "url": "https://example.com/1",
    }
    assert normalize.normalize_record(raw) is None


def test_normalize_record_happy_path():
    raw = {
        "source": "arbeitnow",
        "external_id": "abc123",
        "title": "Senior .NET Developer",
        "company": "Acme Insurance",
        "url": "https://example.com/jobs/1",
        "location_raw": "Remote - Anywhere",
        "remote": True,
        "tags": ["dotnet", "legacy"],
        "description_html": "<p>Maintain <b>legacy</b> systems.</p>",
        "posted_at_epoch": 1700000000,
        "salary_raw": "$60-70/hr",
    }
    rec = normalize.normalize_record(raw)
    assert rec is not None
    assert rec["title"] == "Senior .NET Developer"
    assert rec["description_text"] == "Maintain legacy systems."
    assert rec["posted_at"] is not None
    assert rec["id"] == common.stable_id("arbeitnow", "abc123")


def test_normalize_record_id_is_stable_and_source_specific():
    raw1 = {
        "source": "arbeitnow",
        "external_id": "same-id",
        "title": "T",
        "company": "C",
        "url": "https://x/1",
    }
    raw2 = dict(raw1, source="remoteok")
    rec1 = normalize.normalize_record(raw1)
    rec2 = normalize.normalize_record(raw2)
    assert rec1["id"] != rec2["id"], "the same external_id from different sources must not collapse"


def test_normalize_record_truncates_huge_description():
    raw = {
        "source": "x",
        "external_id": "1",
        "title": "T",
        "company": "C",
        "url": "https://x/1",
        "description_text": "word " * 5000,
    }
    rec = normalize.normalize_record(raw)
    assert len(rec["description_text"]) <= 6050  # with room for "…[truncated]"


def test_normalize_record_handles_unicode_and_non_ascii():
    raw = {
        "source": "x",
        "external_id": "1",
        "title": "Développeur .NET Sénior — 保守",
        "company": "Société Générale",
        "url": "https://x/1",
        "description_html": "<p>Support required for a legacy system</p>",
    }
    rec = normalize.normalize_record(raw)
    assert rec is not None
    assert "保守" in rec["title"]
    assert "legacy" in rec["description_text"]


def test_normalize_batch_skips_bad_and_keeps_good():
    raws = [
        {"source": "x", "external_id": "1", "title": "Good", "company": "C", "url": "https://x/1"},
        {"source": "x", "external_id": "2", "title": "", "company": "C", "url": "https://x/2"},
        None,
        {"not": "a valid schema at all"},
    ]
    normalized, skipped = normalize.normalize_batch(raws)
    assert len(normalized) == 1
    assert skipped == 3


def test_normalize_record_tags_coerced_to_list_of_strings():
    raw = {
        "source": "x",
        "external_id": "1",
        "title": "T",
        "company": "C",
        "url": "https://x/1",
        "tags": "single-tag-not-a-list",
    }
    rec = normalize.normalize_record(raw)
    assert rec["tags"] == ["single-tag-not-a-list"]
