# News Agent — project documentation

## Setup

- **Python**: use a virtual environment 

```bash
python3 -m venv .venv` && `source .venv/bin/activate`
```

- **CDK dependencies**: `pip install -r requirements.txt` (declares `aws-cdk-lib` and `constructs`).
- **Dev / test dependencies**: `pip install -r requirements-dev.txt` 
- **Lambda runtime dependencies**: see `lambda/requirements.txt` 
- **App entry**: `app.py` instantiates the CDK stack from `infra/news_agent_stack.py`. CDK reads `cdk.json` (`"app": "python3 app.py"`).
- **Sample config**: `config/feeds.json` and `config/system_prompt.txt` illustrate feed URLs and the summarization system prompt. Production values are intended to live in SSM in later phases.
- **Tests**: `pytest` with `pytest.ini` adding `lambda/` to `pythonpath` so modules import as `rss_fetcher`, `bedrock_client`, etc.

## Architecture

The target architecture is an AWS CDK–defined stack that runs a scheduled Lambda: EventBridge triggers the function on a cron; configuration (feeds, prompt, recipient email) is read from SSM Parameter Store; the Lambda fetches RSS, summarizes via Amazon Bedrock (Claude 3 Haiku), and sends email via SES.

Current repository layout:

| Path | Role |
| --- | --- |
| `app.py` | CDK application entry; synthesizes stacks. |
| `infra/news_agent_stack.py` | CDK stack definition (to be expanded with Lambda, IAM, EventBridge, SSM in a later phase). |
| `lambda/` | Python code intended for the Lambda deployment package (`handler.py`, RSS, Bedrock, SES helpers). |
| `config/` | Local examples of feeds and system prompt. |
| `tests/` | Pytest unit tests; infrastructure tests will be added in a later phase. |

CloudFormation templates are produced by `cdk synth`; deployment uses `cdk deploy` once the stack is fully defined.

## Ingestion and Summarization

### RSS ingestion and 24-hour filtering

- **Fetching**: `lambda/rss_fetcher.py` downloads each feed URL with `requests` (timeouts supported) and parses the body with `feedparser`.
- **Time window**: entries are kept only if `published_parsed` or, if missing, `updated_parsed` parses to a UTC datetime **on or after** `now - timedelta(hours=hours)` (default **24 hours**). Entries with no parseable time are skipped.
- **Robustness**: per-feed HTTP failures (including timeouts) are logged and that feed is skipped; other feeds still contribute entries.
- **Output shape**: each article is a dict with `title`, `link`, `published` (ISO 8601 UTC), and `summary` when present.

### Summarization via Bedrock

- **Client**: `lambda/bedrock_client.py` uses `boto3.client("bedrock-runtime")` and `invoke_model`.
- **Model**: Claude 3 Haiku on Bedrock (`anthropic.claude-3-haiku-20240307-v1:0`) with `anthropic_version` `bedrock-2023-05-31`.
- **Prompting**: the system prompt and concatenated article text are sent as the Messages API payload (`system` plus a single `user` message with text content).
- **Response**: the assistant text is read from the JSON response body (`content[0].text` when content is a list of blocks).
- **Throttling**: if Bedrock returns `ThrottlingException`, the client raises `BedrockThrottlingError` so callers can retry or degrade explicitly.

Quality of summaries depends on the system prompt, token limit (`max_tokens`, default 4096), and input size; trimming or chunking long inputs is a possible future improvement.
