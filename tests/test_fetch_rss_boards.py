"""
tools/fetch_rss_boards.py: WP Job Manager feeds (jobspresso).

The feed is trimmed from the live one of 2026-10-22. Until then the company
was taken from dc:creator, which on jobspresso is the company and the place
in one string of HTML, and every vacancy got the default place "Worldwide"
(task 0076).
"""
import xml.etree.ElementTree as ET

import fetch_rss_boards as rss
import normalize

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:job_listing="https://jobspresso.co">
<channel>
<item>
  <title>Content Reviewer</title>
  <link>https://jobspresso.co/job/telus-digital-us-ai-data-various-content-reviewer-us/</link>
  <dc:creator><![CDATA[TELUS Digital<br>⚲&nbsp;United States]]></dc:creator>
  <pubDate>Wed, 21 Oct 2026 09:00:37 +0000</pubDate>
  <job_listing:location><![CDATA[United States]]></job_listing:location>
  <job_listing:job_category><![CDATA[Part Time]]></job_listing:job_category>
  <job_listing:company><![CDATA[TELUS Digital]]></job_listing:company>
</item>
<item>
  <title>Senior Software Engineer, Platform</title>
  <link>https://jobspresso.co/job/senior-software-engineer-platform/</link>
  <dc:creator><![CDATA[Astronomer<br>⚲&nbsp;Europe]]></dc:creator>
  <job_listing:location><![CDATA[Europe]]></job_listing:location>
  <job_listing:job_category><![CDATA[Full Time]]></job_listing:job_category>
  <job_listing:company><![CDATA[Astronomer]]></job_listing:company>
  <job_listing:salary><![CDATA[€105k - €175k]]></job_listing:salary>
</item>
<item>
  <title>Forward Deployed Engineer</title>
  <link>https://jobspresso.co/job/forward-deployed-engineer/</link>
  <dc:creator><![CDATA[Spellbook<br>⚲&nbsp;Canada]]></dc:creator>
</item>
</channel>
</rss>"""


def records():
    items = ET.fromstring(FEED.encode("utf-8")).findall(".//item")
    return [rss._item_to_common_schema(item, "jobspresso", True, "Worldwide") for item in items]


def test_the_company_place_salary_and_engagement_come_from_the_listing_fields():
    telus, astronomer, _ = records()
    assert (telus["company"], telus["location_raw"], telus["salary_raw"]) == ("TELUS Digital", "United States", None)
    assert normalize.employment_types(telus["employment_types"]) == ["part-time"]
    assert (astronomer["company"], astronomer["location_raw"]) == ("Astronomer", "Europe")
    assert astronomer["salary_raw"] == "€105k - €175k"


def test_without_the_listing_fields_the_creator_is_split_into_company_and_place():
    spellbook = records()[2]
    assert (spellbook["company"], spellbook["location_raw"]) == ("Spellbook", "Canada")
    assert rss.split_creator("Acme") == ("Acme", "")
    assert rss.split_creator("A &amp; B<br />⚲&nbsp;Remote, Europe") == ("A & B", "Remote, Europe")


def test_a_title_naming_the_company_still_splits_when_no_field_names_it():
    assert rss._split_title_and_company("Senior Developer at Acme", "") == ("Senior Developer", "Acme")
