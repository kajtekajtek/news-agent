# News Agent — project documentation

## Setup

- **Python**: use a virtual environment.

```bash
python3 -m venv .venv && source .venv/bin/activate
```

- **CDK dependencies**: `pip install -r requirements.txt` (declares `aws-cdk-lib` and `constructs`).
- **Dev / test dependencies**: `pip install -r requirements-dev.txt`.
- **Lambda runtime dependencies**: see `lambda/requirements.txt`.
- **App entry**: `app.py` instantiates the CDK stack from `infra/news_agent_stack.py`. CDK reads `cdk.json` (`"app": "python3 app.py"`).
- **Sample config**: `config/feeds.json` and `config/system_prompt.txt` illustrate feed URLs and the summarization system prompt. Production values are intended to move to SSM in a later phase.
- **Tests**: `pytest` with `pytest.ini` setting `pythonpath = lambda` so imports resolve (`rss_fetcher`, `bedrock_client`, `handler`, etc.).
- **Local handler run**: `tests/run_handler_local.py` invokes `handler` from the repo root, loads `config/` when env vars are unset, and prints pretty JSON (including a parsed `body` object). Requires network for RSS and AWS credentials for Bedrock when articles exist.

## Architecture

The target architecture is an AWS CDK–defined stack that runs a scheduled Lambda: EventBridge triggers the function on a cron; configuration (feeds, prompt, recipient email) is intended to live in SSM Parameter Store; the Lambda fetches RSS, summarizes via Amazon Bedrock, and (in a later phase) sends email via SES.

Current repository layout:

| Path | Role |
| --- | --- |
| `app.py` | CDK application entry; synthesizes stacks. |
| `infra/news_agent_stack.py` | CDK stack definition (to be expanded with Lambda, IAM, EventBridge, SSM). |
| `lambda/` | Lambda code: `handler.py` (orchestration), `rss_fetcher.py`, `bedrock_client.py`, `models.py` (`RssItem`), `ses_sender.py` (placeholder). |
| `config/` | Local examples of feeds and system prompt. |
| `tests/unit/` | Pytest unit tests. |
| `tests/run_handler_local.py` | Optional script to run the handler locally with formatted JSON output. |

CloudFormation templates are produced by `cdk synth`; deployment uses `cdk deploy` once the stack is fully defined.

## Lambda handler

**Handler**: `lambda/handler.py` → function `handler(event, context)`.

**Event (optional)**

| Field | Meaning |
| --- | --- |
| `hours` | RSS lookback window in hours (default **24**). Invalid or `< 1` falls back to 24. |

**Environment variables**

| Variable | Required | Meaning |
| --- | --- | --- |
| `FEEDS_JSON` | Yes | JSON string: either an array of feed URLs or `{"feeds": [...]}` (same shape as `config/feeds.json`). |
| `SYSTEM_PROMPT` | Yes | System instructions for the summarization model. |
| `BEDROCK_REGION` | No | Region for `bedrock-runtime`. Falls back to `AWS_REGION` (set automatically on Lambda). |
| `AWS_REGION` | — | Used when `BEDROCK_REGION` is unset. |
| `BEDROCK_MODEL_ID` | No | Bedrock **model id** or **inference profile id**. If unset, the default in `bedrock_client` is used (Anthropic Haiku inference profile). Set e.g. `openai.gpt-oss-20b-1:0` for OpenAI gpt-oss on Bedrock. |

Lambda **does not** populate `FEEDS_JSON` / `SYSTEM_PROMPT` for you: set them in the function configuration (or load from SSM in code later).

**Successful JSON response** (API Gateway–style): `statusCode`, `headers`, `body` where `body` is a **string** containing JSON with fields such as `summary`, `articles`, `hours`, or error fields.

**Local run**

```bash
# From repository root, with AWS credentials configured for Bedrock
export FEEDS_JSON="$(cat config/feeds.json)"
export SYSTEM_PROMPT="$(cat config/system_prompt.txt)"
./tests/run_handler_local.py --hours 24
```

Or rely on `tests/run_handler_local.py` to read `config/` when the env vars are empty.

## Ingestion and summarization

### RSS

- **Code**: `lambda/rss_fetcher.py` — `requests` + `feedparser`.
- **Window**: entries with `published_parsed` or `updated_parsed` **≥** `now - timedelta(hours)` (default **24**).
- **Output**: `RssItem` dicts: `title`, `link`, `published`, `summary`.

### Bedrock

- **Code**: `lambda/bedrock_client.py` — `boto3` `bedrock-runtime` `invoke_model`.
- **Anthropic (default)**: Messages API body (`anthropic_version` `bedrock-2023-05-31`), response text from `content` blocks. Default `model_id` is a **regional inference profile** (e.g. `eu.anthropic.claude-haiku-4-5-20251001-v1:0`); adjust in code for your region and [list-inference-profiles](https://docs.aws.amazon.com/cli/latest/reference/bedrock/list-inference-profiles.html) / console if `InvokeModel` rejects the foundation model id alone.
- **OpenAI on Bedrock** (`model_id` starting with `openai.`): Chat Completions–style body per [OpenAI models on Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-openai.html); response text from `choices[0].message.content`. Example id: `openai.gpt-oss-20b-1:0` (set `BEDROCK_MODEL_ID`).
- **Auth**: same as AWS CLI / SDK (e.g. `aws configure`). Lambda uses the execution role.
- **Access**: enable model access in the Bedrock console; Anthropic models may require **use case details** in addition to model access.
- **Errors**: `ThrottlingException` is mapped to `BedrockThrottlingError` in code; the handler returns HTTP 503 in that case.

## Viewing handler output

The handler returns JSON with a string `body`. For pretty printing, decode the inner JSON (see `tests/run_handler_local.py`) or use `jq` on **JSON** output (not Python `repr`). Example:

```bash
./tests/run_handler_local.py | jq .
```
