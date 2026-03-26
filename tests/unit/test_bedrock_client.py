"""Unit tests for bedrock_client (boto3 mocked)."""

import io
import json
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from bedrock_client import (
    CLAUDE_3_HAIKU_MODEL_ID,
    OPENAI_GPT_OSS_20B_MODEL_ID,
    BedrockThrottlingError,
    summarize_articles,
)


@patch("bedrock_client.boto3.client")
def test_summarize_sends_prompt_and_returns_text(mock_boto_client):
    mock_runtime = MagicMock()
    mock_boto_client.return_value = mock_runtime
    response_body = {
        "content": [{"type": "text", "text": "Summary output."}],
    }
    mock_runtime.invoke_model.return_value = {
        "body": io.BytesIO(json.dumps(response_body).encode("utf-8")),
    }

    articles = "Headline A\nHeadline B"
    system = "You are a newsletter bot."
    result = summarize_articles(articles, system, region_name="us-east-1")

    mock_boto_client.assert_called_once_with("bedrock-runtime", region_name="us-east-1")
    mock_runtime.invoke_model.assert_called_once()
    call_kw = mock_runtime.invoke_model.call_args.kwargs
    assert call_kw["modelId"] == CLAUDE_3_HAIKU_MODEL_ID
    body = json.loads(call_kw["body"])
    assert body["system"] == system
    assert body["messages"][0]["content"][0]["text"] == articles
    assert result == "Summary output."


@patch("bedrock_client.boto3.client")
def test_summarize_openai_chat_completions_format(mock_boto_client):
    mock_runtime = MagicMock()
    mock_boto_client.return_value = mock_runtime
    response_body = {
        "choices": [{"message": {"role": "assistant", "content": "OSS summary."}}],
    }
    mock_runtime.invoke_model.return_value = {
        "body": io.BytesIO(json.dumps(response_body).encode("utf-8")),
    }

    result = summarize_articles(
        "article text",
        "system instructions",
        region_name="eu-north-1",
        model_id=OPENAI_GPT_OSS_20B_MODEL_ID,
    )

    call_kw = mock_runtime.invoke_model.call_args.kwargs
    assert call_kw["modelId"] == OPENAI_GPT_OSS_20B_MODEL_ID
    body = json.loads(call_kw["body"])
    assert body["stream"] is False
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][0]["content"] == "system instructions"
    assert body["messages"][1]["content"] == "article text"
    assert result == "OSS summary."


@patch("bedrock_client.boto3.client")
def test_throttling_raises_bedrock_throttling_error(mock_boto_client):
    mock_runtime = MagicMock()
    mock_boto_client.return_value = mock_runtime
    error_response = {"Error": {"Code": "ThrottlingException", "Message": "Slow down"}}
    mock_runtime.invoke_model.side_effect = ClientError(error_response, "InvokeModel")

    with pytest.raises(BedrockThrottlingError):
        summarize_articles("x", "y")
