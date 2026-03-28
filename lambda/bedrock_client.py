"""Amazon Bedrock summarization (Anthropic Claude and OpenAI gpt-oss on Bedrock)."""

from __future__ import annotations

import json
import logging
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

CLAUDE_3_HAIKU_MODEL_ID     = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
OPENAI_GPT_OSS_20B_MODEL_ID = "openai.gpt-oss-20b-1:0"

MAX_TOKENS = 4096

class BedrockThrottlingError(Exception):
    """Raised when Bedrock returns ThrottlingException."""

def invoke_model(
    user_text: str,
    system_prompt: str,
    *,
    region_name: str | None = None,
    model_id: str = CLAUDE_3_HAIKU_MODEL_ID,
    max_tokens: int = MAX_TOKENS,
) -> str:
    """
    Summarize article text using a Bedrock chat model.

    Routes to the OpenAI chat-completions path or Anthropic Messages path based on ``model_id``.
    On ``ThrottlingException``, raises :class:`BedrockThrottlingError`.

    Raises:
        ValueError: if ``model_id`` is not a supported Bedrock model id.
    """
    client = boto3.client("bedrock-runtime", region_name=region_name)
    if _is_openai_bedrock_model(model_id):
        return _invoke_bedrock_openai_chat(
            client, model_id, user_text, system_prompt, max_tokens
        )
    if _is_anthropic_bedrock_model(model_id):
        return _invoke_bedrock_anthropic_messages(
            client, model_id, user_text, system_prompt, max_tokens
        )
    raise ValueError(f"Unsupported Bedrock model_id: {model_id!r}")

def _invoke_bedrock_openai_chat(
    client: Any,
    model_id: str,
    user_text: str,
    system_prompt: str,
    max_tokens: int,
) -> str:
    payload = _openai_chat_completion_body(
        model_id=model_id,
        system_prompt=system_prompt,
        user_text=user_text,
        max_completion_tokens=max_tokens,
    )
    parsed = _invoke_raw(client, model_id, json.dumps(payload))
    return _extract_openai_chat_completion_text(parsed)

def _invoke_bedrock_anthropic_messages(
    client: Any,
    model_id: str,
    user_text: str,
    system_prompt: str,
    max_tokens: int,
) -> str:
    payload = _anthropic_messages_body(
        system_prompt=system_prompt,
        user_text=user_text,
        max_tokens=max_tokens,
    )
    parsed = _invoke_raw(client, model_id, json.dumps(payload))
    return _extract_anthropic_messages_text(parsed)

def _invoke_raw(client: Any, model_id: str, body: str) -> dict[str, Any]:
    try:
        response = client.invoke_model(
            modelId=model_id,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "ThrottlingException":
            logger.warning("Bedrock throttled for model %s", model_id)
            raise BedrockThrottlingError("Bedrock model is throttled") from exc
        raise

    raw = response["body"].read()
    return json.loads(raw.decode("utf-8"))

def _is_openai_bedrock_model(model_id: str) -> bool:
    match model_id:
        case m if m == OPENAI_GPT_OSS_20B_MODEL_ID:
            return True
        case _:
            return False

def _is_anthropic_bedrock_model(model_id: str) -> bool:
    match model_id:
        case m if m == CLAUDE_3_HAIKU_MODEL_ID:
            return True
        case _:
            return False

def _openai_chat_completion_body(
    *,
    model_id: str,
    system_prompt: str,
    user_text: str,
    max_completion_tokens: int,
) -> dict[str, Any]:
    # Bedrock OpenAI models: Chat Completions shape; stream must be false for InvokeModel.
    return {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "max_completion_tokens": max_completion_tokens,
        "stream": False,
    }

def _extract_openai_chat_completion_text(body: dict[str, Any]) -> str:
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message")
        if isinstance(message, dict):
            text = message.get("content")
            if isinstance(text, str):
                return text
    return ""


def _anthropic_messages_body(
    *,
    system_prompt: str,
    user_text: str,
    max_tokens: int,
) -> dict[str, Any]:
    return {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": user_text}],
            }
        ],
    }

def _extract_anthropic_messages_text(body: dict[str, Any]) -> str:
    content = body.get("content")
    if isinstance(content, list) and content:
        block = content[0]
        if isinstance(block, dict) and "text" in block:
            return str(block["text"])
    if isinstance(content, str):
        return content
    return ""
