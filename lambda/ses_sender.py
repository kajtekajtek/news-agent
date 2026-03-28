"""Send newsletter HTML email via Amazon SES."""

from __future__ import annotations

import html
import logging
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class SesEmailRejectedError(Exception):
    """Raised when SES rejects the message (e.g. unverified identity in sandbox)."""


def summary_to_html(summary_text: str) -> str:
    """Wrap plain / markdown-like summary in a minimal HTML body (escaped)."""
    escaped = html.escape(summary_text.strip(), quote=True)
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\" /></head>"
        "<body style=\"font-family:system-ui,Segoe UI,sans-serif;line-height:1.5\">"
        f"<div style=\"white-space:pre-wrap\">{escaped}</div>"
        "</body></html>"
    )


def send_summary_email(
    *,
    sender: str,
    recipient: str,
    subject: str,
    summary_text: str,
    region_name: str | None = None,
) -> str:
    """
    Send ``summary_text`` as HTML (and plain-text copy) via SES ``send_email``.

    Returns:
        SES MessageId string.

    Raises:
        SesEmailRejectedError: on ``MessageRejected`` (e.g. unverified address in sandbox).
        ClientError: other AWS API errors.
    """
    client = boto3.client("ses", region_name=region_name)
    body_html = summary_to_html(summary_text)
    body_text = summary_text.strip()

    try:
        response: dict[str, Any] = client.send_email(
            Source=sender,
            Destination={"ToAddresses": [recipient]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": body_text, "Charset": "UTF-8"},
                    "Html": {"Data": body_html, "Charset": "UTF-8"},
                },
            },
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "MessageRejected":
            logger.warning("SES MessageRejected for recipient=%s", recipient)
            raise SesEmailRejectedError("SES rejected the email (verify identities in sandbox)") from exc
        raise

    message_id = response.get("MessageId", "")
    logger.info("SES send_email MessageId=%s", message_id)
    return str(message_id)
