"""Unit tests for rss_fetcher (HTTP mocked with responses)."""

from datetime import datetime, timezone

import requests
import responses

from rss_fetcher import fetch_recent_articles

FIXED_NOW = datetime(2025, 3, 25, 12, 0, 0, tzinfo=timezone.utc)

# Within last 24h relative to FIXED_NOW (12h ago)
RSS_TWO_ITEMS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test</title>
    <item>
      <title>Recent</title>
      <link>https://example.com/recent</link>
      <pubDate>Tue, 25 Mar 2025 00:00:00 GMT</pubDate>
      <description>Recent body</description>
    </item>
    <item>
      <title>Old</title>
      <link>https://example.com/old</link>
      <pubDate>Sun, 23 Mar 2025 12:00:00 GMT</pubDate>
      <description>Old body</description>
    </item>
  </channel>
</rss>
"""

RSS_EMPTY = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Empty</title>
  </channel>
</rss>
"""


@responses.activate
def test_filters_entries_by_published_time():
    url = "http://example.com/feed.xml"
    responses.add(responses.GET, url, body=RSS_TWO_ITEMS, status=200, content_type="application/xml")

    articles = fetch_recent_articles([url], hours=24, now=FIXED_NOW)

    titles = {a["title"] for a in articles}
    assert titles == {"Recent"}


@responses.activate
def test_empty_feed_returns_no_articles():
    url = "http://example.com/empty.xml"
    responses.add(responses.GET, url, body=RSS_EMPTY, status=200, content_type="application/xml")

    assert fetch_recent_articles([url], hours=24, now=FIXED_NOW) == []


@responses.activate
def test_fetch_timeout_skips_feed():
    url = "http://example.com/slow.xml"

    def _timeout(_request):
        raise requests.exceptions.Timeout()

    responses.add_callback(responses.GET, url, callback=_timeout)

    assert fetch_recent_articles([url], hours=24, now=FIXED_NOW) == []
