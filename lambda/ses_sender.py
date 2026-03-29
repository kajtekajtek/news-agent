"""Send newsletter HTML email via Amazon SES."""

from __future__ import annotations

import logging
import re
from typing import Any
import boto3
import markdown
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

class SesEmailRejectedError(Exception):
    """Raised when SES rejects the message (e.g. unverified identity in sandbox)."""

_MARKDOWN_EXTENSIONS = ("fenced_code", "sane_lists", "nl2br", "tables")

# Stdlib-only mitigation: Python-Markdown passes through raw HTML; email clients may execute scripts.
_DANGEROUS_HTML = (
    r"(?is)<script\b[^>]*>.*?</script>",
    r"(?is)<script\b[^>]*/>",
    r"(?is)<iframe\b[^>]*>.*?</iframe>",
    r"(?is)<object\b[^>]*>.*?</object>",
    r"(?is)<embed\b[^>]*/?>",
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

def summary_to_html(summary_text: str) -> str:
    """Render Markdown ``summary_text`` into a minimal HTML email document."""
    inner = _convert_markdown_to_html(summary_text)
    wrapped = (
        f'<div style="max-width:40em;font-family:system-ui,Segoe UI,sans-serif;'
        f'line-height:1.5">{inner}</div>'
    )
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\" /></head>"
        f"<body>{wrapped}</body></html>"
    )

def _convert_markdown_to_html(summary_text: str) -> str:
    text = summary_text.strip()
    if not text:
        return ""
    fragment = markdown.markdown(
        text,
        extensions=list(_MARKDOWN_EXTENSIONS),
    )
    return _strip_dangerous_html(fragment)

def _strip_dangerous_html(fragment: str) -> str:
    out = fragment
    for pattern in _DANGEROUS_HTML:
        out = re.sub(pattern, "", out)
    return out
