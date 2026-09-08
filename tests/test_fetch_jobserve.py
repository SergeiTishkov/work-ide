"""
JobServe — the richest of the four UK sources, and the one that costs three
requests to reach.

Its search is ASP.NET WebForms, so a keyword search is a form submission:

    GET  the form                        -> hidden fields (__VIEWSTATE etc.)
    POST them back with the keyword      -> a redirect carrying a search id
    GET  JobListing.aspx?shid=...&ovrpp=jl -> 20 results

That is what a browser does with the page's own fields. Nothing here fakes a
browser or gets round a challenge.

TWO THINGS MEASURED ON 2026-09-08 THAT THE TESTS PIN

  * The field names must carry the WebForms control prefix. A bare "txtKey"
    and a bare "btnSearch" are accepted, ignored, and the same landing page
    comes back — a search that silently did not happen.

  * `&ovrpp=jl` is not optional. Without it the listing came back empty on one
    run in three; with it, three runs of three returned twenty. An
    intermittently empty source is worse than no source, because every empty
    run reads as "the markup changed" and teaches a person to ignore it.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import fetch_jobserve as js  # noqa: E402

LISTING = """
<div id="joblistingcollection" class="joblistingcollection">
<div class="jobSearchContainer">
<div class="jobListItem newjobsum" id="E7EB62E26BF96D1F7B">
  <div class="jobListHeaderPanel">
    <a href="/gb/en/find-jobs-in-United-Kingdom/DOTNET-DEVELOPER-AZURE-CSHARP-E7EB62E26BF96D1F7B/" title="Click here to view this .Net Developer, Azure, C# job" class="jobListPosition">.Net Developer, Azure, C#</a>
  </div>
  <div class="jobListDetailsPanel">
    <label class="jobListLabel left ">Location</label><span id="summlocation" class="jobListDetail left" title="Remote, UK">Remote, UK</span>
    <label class="jobListLabel left ">Rate</label><span id="summrate" class="jobListDetail left" title="&#163;450 - 550 day rate">&#163;450 - 550 day rate</span>
    <label class="jobListLabel left ">Type</label><span id="summtype" class="jobListDetail left" title="Contract">Contract</span>
    <label class="jobListLabel left">Employment Business</label><span class="jobListDetail left"><a href="/gb/en/Redirect/DirectoryUrl.jsrs?id=24A5E703EB" title="View more information about ARC IT Recruitment" target="_blank">ARC IT Recruitment</a></span>
  </div>
  <div class="jobListSkillsPanel"><p class="jobListSkills">.Net Developer, Azure, C# Initial 6-Month Contract - Outside IR35. A prestigious global business is hiring a C#, Azure developer.</p></div>
</div>
<div class="jobListItem newjobsum" id="A1B2C3D4E5F60718">
  <div class="jobListHeaderPanel">
    <a href="/gb/en/find-jobs-in-United-Kingdom/DOTNET-DEV-A1B2C3D4E5F60718/" title="Click here to view this job" class="jobListPosition">.NET Developer -TOP COMPANY!</a>
  </div>
  <div class="jobListDetailsPanel">
    <label class="jobListLabel left ">Location</label><span id="summlocation" class="jobListDetail left" title="London, UK">London, UK</span>
    <label class="jobListLabel left ">Type</label><span id="summtype" class="jobListDetail left" title="Permanent">Permanent</span>
  </div>
  <div class="jobListSkillsPanel"><p class="jobListSkills">A permanent .NET role in London working on a legacy platform.</p></div>
</div>
</div>
</div>
"""


def test_the_listing_parses_into_complete_records():
    records, note = js.parse_listing(LISTING)

    assert note is None
    assert len(records) == 2

    first = records[0]
    assert first["title"] == ".Net Developer, Azure, C#"
    assert first["external_id"] == "jobserve:E7EB62E26BF96D1F7B"
    assert first["url"].startswith("https://www.jobserve.com/gb/en/find-jobs-in-")
    assert first["source"] == "jobserve"


def test_the_agency_is_named_where_the_board_names_it():
    """The only one of the four UK sources that publishes the recruiter on the
    listing itself — which is what makes a reputation check possible at all."""
    records, _ = js.parse_listing(LISTING)

    assert records[0]["company"] == "ARC IT Recruitment"
    assert records[1]["company"] == "Undisclosed agency (JobServe)"


def test_the_location_keeps_the_boards_own_wording():
    """"Remote, UK" is the board saying something specific, and the location
    gate reads it. Rewriting it to "United Kingdom" here would throw away the
    only word that matters."""
    records, _ = js.parse_listing(LISTING)

    assert records[0]["location_raw"] == "Remote, UK"
    assert records[1]["location_raw"] == "London, UK"


def test_the_day_rate_survives_the_html_entity():
    """The board writes the pound sign as &#163;."""
    records, _ = js.parse_listing(LISTING)

    assert records[0]["salary_raw"] == "£450 - 550 day rate"
    assert records[1]["salary_raw"] is None, "no rate stated is not an empty string"


def test_a_real_description_arrives_with_the_listing():
    """Unlike Reed and ContractorUK, this board gives a paragraph rather than a
    snippet — so the gates that read text are not working blind here."""
    records, _ = js.parse_listing(LISTING)

    assert "Outside IR35" in records[0]["description_text"]
    assert len(records[0]["description_text"]) > 80


def test_the_contract_type_becomes_a_tag():
    records, _ = js.parse_listing(LISTING)

    assert "Contract" in records[0]["tags"]
    assert "Permanent" in records[1]["tags"]
    assert "market:United Kingdom" in records[0]["tags"]


def test_remote_is_never_invented():
    records, _ = js.parse_listing(LISTING)

    assert all(r["remote"] is None for r in records)
    assert all(r["workplace_type"] is None for r in records), (
        "the board publishes no arrangement badge; the location text is where "
        "it says Remote, and reading it is the scoring's job, not the fetcher's")


# --- the form flow ---------------------------------------------------------

def test_the_form_fields_carry_the_webforms_prefix():
    """A bare "txtKey" is accepted, ignored, and the landing page comes back —
    a search that silently did not happen. Measured 2026-09-08."""
    assert js.KEYWORD_FIELD.startswith("ctl00$")
    assert js.SEARCH_BUTTON.startswith("ctl00$")


def test_the_listing_url_keeps_the_ovrpp_parameter():
    """Without it the listing came back empty on one run in three."""
    assert "ovrpp=jl" in js.LISTING_URL


def test_the_search_posts_the_pages_own_hidden_fields(monkeypatch):
    """WebForms will not run a search without its __VIEWSTATE back."""
    posted = {}

    class FakeResponse:
        def __init__(self, text="", url=""):
            self.text = text
            self.url = url

        def raise_for_status(self):
            return None

    class FakeSession:
        def get(self, url, timeout=None):
            if "Job-Search" in url:
                return FakeResponse(
                    '<input type="hidden" name="__VIEWSTATE" value="abc" />'
                    '<input type="hidden" name="__EVENTVALIDATION" value="def" />')
            return FakeResponse(LISTING)

        def post(self, url, data=None, timeout=None):
            posted.update(data or {})
            return FakeResponse(url="https://www.jobserve.com/x?shid=DEADBEEF01")

    body = js._search(FakeSession(), ".net developer", 10)

    assert posted["__VIEWSTATE"] == "abc"
    assert posted["__EVENTVALIDATION"] == "def"
    assert posted[js.KEYWORD_FIELD] == ".net developer"
    assert posted[js.SEARCH_BUTTON]
    assert "jobListItem" in body


def test_a_search_that_yields_no_handle_is_reported_not_guessed(monkeypatch):
    """No shid means the search did not run. Returning the landing page's
    suggested-jobs widget instead would fill the base with UK jobs nobody
    asked for — that widget shows the same 25 to everybody."""
    class FakeResponse:
        text = "<html></html>"
        url = "https://www.jobserve.com/gb/en/Job-Search/"

        def raise_for_status(self):
            return None

    class FakeSession:
        def get(self, url, timeout=None):
            return FakeResponse()

        def post(self, url, data=None, timeout=None):
            return FakeResponse()

    assert js._search(FakeSession(), "x", 10) == ""


# --- the obligation every HTML parser in this project carries --------------

def test_changed_markup_returns_zero_and_an_explicit_error():
    broken = LISTING.replace('class="jobListPosition"', 'class="jobTitle"')

    records, note = js.parse_listing(broken)

    assert records == []
    assert note and "markup changed" in note and "2 items" in note


def test_an_empty_listing_is_not_an_error():
    records, note = js.parse_listing("<div id='joblistingcollection'></div>")

    assert records == [] and note is None
