# news-agent

Scheduled AWS Lambda function that turns RSS feeds into a personal newsletter.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### Requirements

- [CDK CLI](https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html) 
- Docker (for `cdk deploy`)

## Usage

### Tests

```bash
pytest
```

### Run the Lambda locally

```bash
./tests/run_handler_local.py
./tests/run_handler_local.py --hours 12
./tests/run_handler_local.py --debug
./tests/run_handler_local.py --no-email
```

If `FEEDS_JSON` / `SYSTEM_PROMPT` aren’t set, the script looks for them from `config/`. The handler expects **verified SES sender and recipient** in the environment / SSM; use **`--no-email`** to skip SES.

Requires valid AWS credentials set.

### Deploy the stack

Set NEWS_AGENT_{SENDER/RECIPIENT}_EMAIL with verified SES address emails for your AWS account. You can use `.env.example` to fill in your values.

```bash
source .env
cdk deploy
```

Feeds and system prompt are copied from `config/feeds.json` and `config/system_prompt.txt` into SSM on deploy. Configuration can be changed before the deploy or in the SSM afterwards.

## Project layout

| Path | Purpose |
| --- | --- |
| `lambda/` | Handler, RSS fetcher, Bedrock client, SES helper |
| `infra/` | CDK stack (Lambda, EventBridge, SSM, IAM) |
| `config/` | Example feeds + prompt |
| `tests/` | Pytest + local runner |
