from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any
from models import RssItem
import calendar
import logging
import feedparser
import requests

from html_utils import strip_html_to_plain

logger = logging.getLogger(__name__)

_SUMMARY_MAX_CHARS = 800

def fetch_recent_articles(
    feeds: list[str],
    hours: int = 24,
    *,
    now: datetime | None = None,
    timeout_seconds: float = 30.0,
) -> list[RssItem]:
    """
    Fetch RSS feeds over HTTP and return entries published within the last ``hours``.

    Entries without a parseable publish/update time are skipped.
    """
    now_utc = _get_now_utc(now)
    cutoff = now_utc - timedelta(hours=hours)

    parsed_items: list[RssItem] = []
    for url in feeds:
        try:
            feed_content = _fetch_feed(url, timeout_seconds=timeout_seconds)
            parsed_feed = feedparser.parse(feed_content)
        except requests.RequestException as exc:
            logger.warning("RSS fetch failed for %s: %s", url, exc)
            continue

        feed_entries = getattr(parsed_feed, "entries", []) or []
        for entry in feed_entries:
            rss_item = _parse_entry(entry, cutoff=cutoff)
            if rss_item is not None:
                logger.info("Parsed RSS item: %s", rss_item)
                parsed_items.append(rss_item)

    return parsed_items

def _get_now_utc(now: datetime | None = None) -> datetime:
    now_utc = now if now is not None else datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    else:
        now_utc = now_utc.astimezone(timezone.utc)
    return now_utc


def _fetch_feed(url: str, timeout_seconds: float) -> feedparser.FeedParserDict:
    resp = requests.get(url, timeout=timeout_seconds)
    resp.raise_for_status()
    return resp.content

def _parse_entry(entry: Any, cutoff: datetime) -> RssItem | None:
    pub = _get_publication_time(entry)
    if pub is None or pub < cutoff:
        return None
    title = getattr(entry, "title", "") or ""
    link = getattr(entry, "link", "") or ""
    raw_summary = getattr(entry, "summary", None) or getattr(entry, "description", "") or ""
    summary = strip_html_to_plain(raw_summary, max_chars=_SUMMARY_MAX_CHARS)
    return RssItem(title=title, link=link, published=pub.isoformat(), summary=summary)


def _get_publication_time(entry: Any) -> datetime | None:
    """Best-effort UTC datetime from feedparser entry."""
    t = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if not t:
        return None
    return datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
