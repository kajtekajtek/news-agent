"""Amazon Bedrock summarization (Anthropic Claude and OpenAI gpt-oss on Bedrock)."""

from __future__ import annotations

import json
import logging
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Default: Anthropic via regional inference profile (adjust per account/region).
CLAUDE_3_HAIKU_MODEL_ID = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
ANTHROPIC_VERSION = "bedrock-2023-05-31"

# OpenAI open-weight models on Bedrock (Chat Completions–style body; see AWS Bedrock OpenAI docs).
OPENAI_GPT_OSS_20B_MODEL_ID = "openai.gpt-oss-20b-1:0"


class BedrockThrottlingError(Exception):
    """Raised when Bedrock returns ThrottlingException."""


def summarize_articles(
    articles_text: str,
    system_prompt: str,
    *,
    region_name: str | None = None,
    model_id: str = CLAUDE_3_HAIKU_MODEL_ID,
    max_tokens: int = 4096,
) -> str:
    """
    Summarize article text using a Bedrock chat model.

    Uses **Anthropic Messages** JSON for ``anthropic.*`` / non-OpenAI ids, and **OpenAI chat
    completions** JSON for ``openai.*`` model ids (e.g. gpt-oss on Bedrock).

    On ``ThrottlingException``, raises :class:`BedrockThrottlingError`.
    """
    client = boto3.client("bedrock-runtime", region_name=region_name)

    if _is_openai_bedrock_model(model_id):
        body_obj = _openai_chat_completion_body(
            model_id=model_id,
            system_prompt=system_prompt,
            user_text=articles_text,
            max_completion_tokens=max_tokens,
        )
        extract = _extract_openai_chat_completion_text
    else:
        body_obj = _anthropic_messages_body(
            system_prompt=system_prompt,
            user_text=articles_text,
            max_tokens=max_tokens,
        )
        extract = _extract_anthropic_messages_text

    body = json.dumps(body_obj)

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
    parsed = json.loads(raw.decode("utf-8"))
    return extract(parsed)


def _is_openai_bedrock_model(model_id: str) -> bool:
    return model_id.startswith("openai.")


def _anthropic_messages_body(
    *,
    system_prompt: str,
    user_text: str,
    max_tokens: int,
) -> dict[str, Any]:
    return {
        "anthropic_version": ANTHROPIC_VERSION,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": user_text}],
            }
        ],
    }


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


def _extract_anthropic_messages_text(body: dict[str, Any]) -> str:
    content = body.get("content")
    if isinstance(content, list) and content:
        block = content[0]
        if isinstance(block, dict) and "text" in block:
            return str(block["text"])
    if isinstance(content, str):
        return content
    return ""


def _extract_openai_chat_completion_text(body: dict[str, Any]) -> str:
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message")
        if isinstance(message, dict):
            text = message.get("content")
            if isinstance(text, str):
                return text
    return ""
