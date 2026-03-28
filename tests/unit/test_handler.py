"""Unit tests for lambda handler (RSS + Bedrock mocked)."""

import json
from unittest.mock import patch

import pytest

from handler import (
    ENV_AWS_REGION,
    ENV_BEDROCK_MODEL_ID,
    ENV_FEEDS_JSON,
    ENV_SYSTEM_PROMPT,
    handler,
)


@pytest.fixture
def env_feeds_and_prompt(monkeypatch):
    feeds = json.dumps(
        {
            "feeds": [
                "https://example.com/a.xml",
            ]
        }
    )
    monkeypatch.setenv(ENV_FEEDS_JSON, feeds)
    monkeypatch.setenv(ENV_SYSTEM_PROMPT, "You summarize RSS.")


@patch("handler.invoke_model")
@patch("handler.fetch_recent_articles")
def test_handler_returns_summary(mock_fetch, mock_summarize, env_feeds_and_prompt, monkeypatch):
    monkeypatch.setenv(ENV_AWS_REGION, "eu-central-1")
    mock_fetch.return_value = [
        {
            "title": "T",
            "link": "https://x",
            "published": "2025-01-01T00:00:00+00:00",
            "summary": "S",
        }
    ]
    mock_summarize.return_value = "Daily digest."

    out = handler({"hours": 12}, None)

    assert out["statusCode"] == 200
    body = json.loads(out["body"])
    assert body["summary"] == "Daily digest."
    assert body["articles"] == 1
    assert body["hours"] == 12
    mock_fetch.assert_called_once()
    mock_summarize.assert_called_once()
    assert mock_summarize.call_args.kwargs["system_prompt"] == "You summarize RSS."
    assert mock_summarize.call_args.kwargs.get("region_name") == "eu-central-1"


@patch("handler.invoke_model")
@patch("handler.fetch_recent_articles")
def test_handler_passes_bedrock_model_id_from_env(
    mock_fetch, mock_summarize, env_feeds_and_prompt, monkeypatch,
):
    monkeypatch.setenv(ENV_BEDROCK_MODEL_ID, "openai.gpt-oss-20b-1:0")
    mock_fetch.return_value = [
        {"title": "t", "link": "l", "published": "p", "summary": "s"},
    ]
    mock_summarize.return_value = "ok"

    handler({}, None)

    assert mock_summarize.call_args[1].get("model_id") == "openai.gpt-oss-20b-1:0"


@patch("handler.fetch_recent_articles")
def test_handler_no_articles_skips_bedrock(mock_fetch, env_feeds_and_prompt):
    mock_fetch.return_value = []

    out = handler({}, None)

    assert out["statusCode"] == 200
    body = json.loads(out["body"])
    assert body["articles"] == 0
    assert "message" in body


def test_handler_missing_feeds(monkeypatch):
    monkeypatch.delenv(ENV_FEEDS_JSON, raising=False)
    monkeypatch.setenv(ENV_SYSTEM_PROMPT, "x")

    out = handler({}, None)

    assert out["statusCode"] == 400


def test_handler_missing_system_prompt(env_feeds_and_prompt, monkeypatch):
    monkeypatch.delenv(ENV_SYSTEM_PROMPT, raising=False)

    out = handler({}, None)

    assert out["statusCode"] == 400
