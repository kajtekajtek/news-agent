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

### Configuration

- Set `NEWS_AGENT_{SENDER/RECIPIENT}_EMAIL` environment variables with verified SES address emails for your AWS account. You can use `.env.example` to fill in your values. 
- If `FEEDS_JSON` / `SYSTEM_PROMPT` aren’t set, **feeds and system prompt** are copied from `config/feeds.json` and `config/system_prompt.txt` into SSM on deploy. Configuration can be changed before the deploy or in the SSM afterwards.

#### Amazon SES

Outbound mail uses [Amazon Simple Email Service (SES)](https://docs.aws.amazon.com/ses/latest/dg/Welcome.html). Configure SES in the **same AWS Region** you use for the Lambda (and optional `SES_REGION`), following the official guides:

- **Verified identities** - Every address you send *from* must be a verified identity (email or domain). Create and verify identities in the SES console or API as described in [Creating and verifying identities in Amazon SES](https://docs.aws.amazon.com/ses/latest/dg/creating-identities.html). 
- If your account is in the Amazon SES sandbox, you also need to verify any email addresses which you plan on sending email *to*

### Tests

```bash
pytest
```

### Run the Lambda locally

Requires AWS credentials configured in the environment.

```bash
./tests/run_handler_local.py
./tests/run_handler_local.py --hours 12
./tests/run_handler_local.py --debug
./tests/run_handler_local.py --no-email
```

### Deploy the stack

```bash
export NEWS_AGENT_SENDER_EMAIL='verified-sender@example.com'
export NEWS_AGENT_RECIPIENT_EMAIL='verified-recipient@example.com'
cdk deploy
```

## Project layout

| Path | Purpose |
| --- | --- |
| `lambda/` | Handler, RSS fetcher, Bedrock client, SES helper |
| `infra/` | CDK stack (Lambda, EventBridge, SSM, IAM) |
| `config/` | Example feeds + prompt |
| `tests/` | Pytest + local runner |
