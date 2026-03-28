"""Unit tests for ses_sender (moto SES + mocked rejection)."""

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from ses_sender import SesEmailRejectedError, send_summary_email, summary_to_html


def test_summary_to_html_escapes_and_wraps():
    html_out = summary_to_html("<script>alert(1)</script>\nLine")
    assert "&lt;script&gt;" in html_out
    assert "<script>" not in html_out
    assert "white-space:pre-wrap" in html_out


@mock_aws
def test_send_summary_email_returns_message_id():
    region = "eu-central-1"
    ses = __import__("boto3").client("ses", region_name=region)
    ses.verify_email_identity(EmailAddress="sender@example.com")

    mid = send_summary_email(
        sender="sender@example.com",
        recipient="sender@example.com",
        subject="Test",
        summary_text="Hello **world**",
        region_name=region,
    )
    assert len(mid) > 0


@patch("ses_sender.boto3.client")
def test_message_rejected_raises_ses_email_rejected(mock_client: MagicMock) -> None:
    mock_ses = MagicMock()
    mock_client.return_value = mock_ses
    mock_ses.send_email.side_effect = ClientError(
        {"Error": {"Code": "MessageRejected", "Message": "Address not verified"}},
        "SendEmail",
    )

    with pytest.raises(SesEmailRejectedError):
        send_summary_email(
            sender="a@example.com",
            recipient="b@example.com",
            subject="S",
            summary_text="Body",
            region_name="us-east-1",
        )
