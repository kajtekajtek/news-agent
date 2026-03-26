"""Lambda entrypoint: RSS fetch + Bedrock summarization."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from bedrock_client import BedrockThrottlingError, CLAUDE_3_HAIKU_MODEL_ID, summarize_articles
from models import RssItem
from rss_fetcher import fetch_recent_articles

logger = logging.getLogger(__name__)

DEFAULT_HOURS = 24

# Environment variable names (Lambda / deployment configuration)
ENV_FEEDS_JSON = "FEEDS_JSON"
ENV_SYSTEM_PROMPT = "SYSTEM_PROMPT"
ENV_BEDROCK_REGION = "BEDROCK_REGION"
ENV_AWS_REGION = "AWS_REGION"
# Optional: Bedrock model id (Anthropic inference profile, openai.gpt-oss-*, etc.)
ENV_BEDROCK_MODEL_ID = "BEDROCK_MODEL_ID"


def handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    """
    Fetch recent RSS items, concatenate them into a prompt, and summarize via Bedrock.

    Environment:

    - ``FEEDS_JSON``: JSON array of feed URLs or ``{"feeds": [...]}``.
    - ``SYSTEM_PROMPT``: system instructions for the model.
    - ``BEDROCK_REGION`` (optional): Bedrock region; defaults to ``AWS_REGION``.
    - ``BEDROCK_MODEL_ID`` (optional): Model or inference profile id (e.g. OpenAI on Bedrock:
      ``openai.gpt-oss-20b-1:0``). Defaults to the Anthropic Haiku profile in code.

    Event (optional):

    - ``hours``: lookback window for RSS filtering (default ``24``).
    """
    event = event or {}
    try:
        hours = int(event.get("hours", DEFAULT_HOURS))
    except (TypeError, ValueError):
        hours = DEFAULT_HOURS
    if hours < 1:
        hours = DEFAULT_HOURS

    feeds = _load_feed_urls()
    if not feeds:
        logger.warning("No feeds configured")
        return _json_response(
            400,
            {"error": "FEEDS_JSON is missing or empty"},
        )

    system_prompt = _load_system_prompt()
    if not system_prompt:
        logger.warning("%s is not set", ENV_SYSTEM_PROMPT)
        return _json_response(
            400,
            {"error": "SYSTEM_PROMPT is not set"},
        )

    region_name = os.environ.get(ENV_BEDROCK_REGION) or os.environ.get(ENV_AWS_REGION)
    model_id = (os.environ.get(ENV_BEDROCK_MODEL_ID) or "").strip() or CLAUDE_3_HAIKU_MODEL_ID

    items = fetch_recent_articles(feeds, hours=hours)
    if not items:
        logger.info("No articles in the last %s hours", hours)
        return _json_response(
            200,
            {"message": "No recent articles", "hours": hours, "articles": 0},
        )

    articles_text = _articles_to_prompt_text(items)
    try:
        summary = summarize_articles(
            articles_text,
            system_prompt,
            region_name=region_name,
            model_id=model_id,
        )
    except BedrockThrottlingError:
        logger.warning("Bedrock throttled")
        return _json_response(
            503,
            {"error": "Bedrock throttled", "articles": len(items)},
        )

    return _json_response(
        200,
        {
            "summary": summary,
            "articles": len(items),
            "hours": hours,
        },
    )


def _load_feed_urls() -> list[str]:
    """
    Read feed URLs from env (see ``ENV_FEEDS_JSON``).

    Accepts either a JSON array of strings or an object ``{"feeds": [...]}``
    (same shape as ``config/feeds.json``).
    """
    raw = os.environ.get(ENV_FEEDS_JSON, "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.exception("%s is not valid JSON", ENV_FEEDS_JSON)
        return []
    if isinstance(data, list):
        return [str(u).strip() for u in data if str(u).strip()]
    if isinstance(data, dict):
        feeds = data.get("feeds")
        if isinstance(feeds, list):
            return [str(u).strip() for u in feeds if str(u).strip()]
    return []


def _load_system_prompt() -> str:
    return os.environ.get(ENV_SYSTEM_PROMPT, "").strip()


def _articles_to_prompt_text(items: list[RssItem]) -> str:
    parts: list[str] = []
    for it in items:
        title = it.get("title", "")
        link = it.get("link", "")
        summary = it.get("summary", "")
        published = it.get("published", "")
        parts.append(f"## {title}\nPublished: {published}\nURL: {link}\n{summary}\n")
    return "\n".join(parts)


def _json_response(status_code: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }
