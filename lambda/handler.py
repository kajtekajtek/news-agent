"""Lambda entrypoint: RSS fetch + Bedrock summarization + optional SES email."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

from bedrock_client import BedrockThrottlingError, CLAUDE_3_HAIKU_MODEL_ID, invoke_model
from models import RssItem
from rss_fetcher import fetch_recent_articles
from ses_sender import SesEmailRejectedError, send_summary_email

logger = logging.getLogger(__name__)

DEFAULT_HOURS = 24
DEFAULT_NEWSLETTER_SUBJECT = "Daily newsletter"

# Environment variable names (Lambda / deployment configuration)
ENV_FEEDS_JSON = "FEEDS_JSON"
ENV_SYSTEM_PROMPT = "SYSTEM_PROMPT"
ENV_BEDROCK_REGION = "BEDROCK_REGION"
ENV_AWS_REGION = "AWS_REGION"
ENV_BEDROCK_MODEL_ID = "BEDROCK_MODEL_ID"
# Optional: load config from SSM at runtime (names only; IAM must allow ssm:GetParameter)
ENV_FEEDS_SSM_PARAM = "FEEDS_SSM_PARAM"
ENV_SYSTEM_PROMPT_SSM_PARAM = "SYSTEM_PROMPT_SSM_PARAM"
# SES (optional — if sender and recipient are set, email is sent after summarization)
ENV_NEWSLETTER_SENDER_EMAIL = "NEWSLETTER_SENDER_EMAIL"
ENV_NEWSLETTER_RECIPIENT_EMAIL = "NEWSLETTER_RECIPIENT_EMAIL"
ENV_NEWSLETTER_SENDER_SSM_PARAM = "NEWSLETTER_SENDER_SSM_PARAM"
ENV_NEWSLETTER_RECIPIENT_SSM_PARAM = "NEWSLETTER_RECIPIENT_SSM_PARAM"
ENV_NEWSLETTER_SUBJECT = "NEWSLETTER_SUBJECT"
ENV_SES_REGION = "SES_REGION"


def handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    """
    Fetch recent RSS items, concatenate them into a prompt, summarize via Bedrock,
    and optionally send the summary by email (SES).

    Environment:

    - ``FEEDS_JSON``: JSON array of feed URLs or ``{"feeds": [...]}`` (unless ``FEEDS_SSM_PARAM`` is set).
    - ``FEEDS_SSM_PARAM``: optional SSM parameter name (e.g. ``/news-agent/feeds``) whose value is the same JSON as ``FEEDS_JSON``. Used when ``FEEDS_JSON`` is empty.
    - ``SYSTEM_PROMPT``: system instructions (unless ``SYSTEM_PROMPT_SSM_PARAM`` is set and env is empty).
    - ``SYSTEM_PROMPT_SSM_PARAM``: optional SSM parameter for the system prompt string.
    - ``NEWSLETTER_SENDER_EMAIL`` / ``NEWSLETTER_RECIPIENT_EMAIL``: if both resolve non-empty, summary is emailed via SES.
    - ``NEWSLETTER_SENDER_SSM_PARAM`` / ``NEWSLETTER_RECIPIENT_SSM_PARAM``: optional SSM parameter **names** used when the direct env vars are empty (runtime lookup).
    - ``NEWSLETTER_SUBJECT``: optional email subject (default: "Daily newsletter").
    - ``SES_REGION``: optional SES region (defaults to ``AWS_REGION``).
    - ``BEDROCK_REGION`` (optional): Bedrock region; defaults to ``AWS_REGION``.
    - ``BEDROCK_MODEL_ID`` (optional): Bedrock model or inference profile id.

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
    logger.debug("Feeds loaded: %s", feeds)

    system_prompt = _load_system_prompt()
    if not system_prompt:
        logger.warning("System prompt is not set")
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
    logger.debug("Articles fetched: %s", items)

    articles_text = _articles_to_prompt_text(items)
    try:
        logger.debug(
            "Calling invoke_model: region_name=%s model_id=%s",
            region_name,
            model_id,
        )
        summary = invoke_model(
            user_text=articles_text,
            system_prompt=system_prompt,
            region_name=region_name,
            model_id=model_id,
        )
        logger.debug("invoke_model returned (length=%s)", len(summary))
    except BedrockThrottlingError:
        logger.warning("Bedrock throttled")
        return _json_response(
            503,
            {"error": "Bedrock throttled", "articles": len(items)},
        )

    payload: dict[str, Any] = {
        "summary": summary,
        "articles": len(items),
        "hours": hours,
        "email_sent": False,
    }

    sender = _load_newsletter_sender_email()
    recipient = _load_newsletter_recipient_email()
    if sender and recipient:
        subject = _load_newsletter_subject()
        ses_region = _ses_region()
        try:
            message_id = send_summary_email(
                sender=sender,
                recipient=recipient,
                subject=subject,
                summary_text=summary,
                region_name=ses_region,
            )
            payload["email_sent"] = True
            payload["message_id"] = message_id
        except SesEmailRejectedError as exc:
            logger.warning("SES rejected email: %s", exc)
            return _json_response(
                502,
                {
                    "error": "SES rejected email",
                    "articles": len(items),
                    "summary": summary,
                },
            )

    return _json_response(200, payload)


def _aws_region() -> str | None:
    return os.environ.get(ENV_AWS_REGION) or os.environ.get("AWS_DEFAULT_REGION")


def _get_ssm_parameter(name: str) -> str:
    client = boto3.client("ssm", region_name=_aws_region())
    try:
        resp = client.get_parameter(Name=name)
    except ClientError:
        logger.exception("SSM get_parameter failed for %s", name)
        return ""
    param = resp.get("Parameter") or {}
    return str(param.get("Value", "")).strip()


def _load_feed_urls() -> list[str]:
    """
    Read feed URLs from ``FEEDS_JSON`` or from SSM when ``FEEDS_SSM_PARAM`` is set
    and ``FEEDS_JSON`` is empty.
    """
    raw = os.environ.get(ENV_FEEDS_JSON, "").strip()
    if not raw:
        ssm_name = os.environ.get(ENV_FEEDS_SSM_PARAM, "").strip()
        if ssm_name:
            raw = _get_ssm_parameter(ssm_name)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.exception("%s / SSM feeds value is not valid JSON", ENV_FEEDS_JSON)
        return []
    if isinstance(data, list):
        return [str(u).strip() for u in data if str(u).strip()]
    if isinstance(data, dict):
        feeds = data.get("feeds")
        if isinstance(feeds, list):
            return [str(u).strip() for u in feeds if str(u).strip()]
    return []


def _load_system_prompt() -> str:
    prompt = os.environ.get(ENV_SYSTEM_PROMPT, "").strip()
    if prompt:
        return prompt
    ssm_name = os.environ.get(ENV_SYSTEM_PROMPT_SSM_PARAM, "").strip()
    if ssm_name:
        return _get_ssm_parameter(ssm_name)
    return ""


def _load_newsletter_sender_email() -> str:
    direct = os.environ.get(ENV_NEWSLETTER_SENDER_EMAIL, "").strip()
    if direct:
        return direct
    ssm_name = os.environ.get(ENV_NEWSLETTER_SENDER_SSM_PARAM, "").strip()
    if ssm_name:
        return _get_ssm_parameter(ssm_name)
    return ""


def _load_newsletter_recipient_email() -> str:
    direct = os.environ.get(ENV_NEWSLETTER_RECIPIENT_EMAIL, "").strip()
    if direct:
        return direct
    ssm_name = os.environ.get(ENV_NEWSLETTER_RECIPIENT_SSM_PARAM, "").strip()
    if ssm_name:
        return _get_ssm_parameter(ssm_name)
    return ""


def _load_newsletter_subject() -> str:
    subject = os.environ.get(ENV_NEWSLETTER_SUBJECT, DEFAULT_NEWSLETTER_SUBJECT).strip()
    return subject or DEFAULT_NEWSLETTER_SUBJECT


def _ses_region() -> str | None:
    return os.environ.get(ENV_SES_REGION) or os.environ.get(ENV_AWS_REGION)


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
