"""CDK stack: scheduled Lambda, SSM parameters, SES + Bedrock + SSM IAM."""

from __future__ import annotations

import os
from pathlib import Path

from aws_cdk import BundlingOptions, Duration, Stack
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_ssm as ssm
from constructs import Construct

_ROOT = Path(__file__).resolve().parent.parent
_LAMBDA_DIR = str(_ROOT / "lambda")
_CONFIG = _ROOT / "config"

FEEDS_FILE_NAME = "feeds.json"
SYSTEM_PROMPT_FILE_NAME = "system_prompt.txt"

ENV_NEWS_AGENT_SENDER_EMAIL = "NEWS_AGENT_SENDER_EMAIL"
ENV_NEWS_AGENT_RECIPIENT_EMAIL = "NEWS_AGENT_RECIPIENT_EMAIL"

EVENT_SCHEDULE = {
    "minute": "0",
    "hour": "7",
    "month": "*",
    "week_day": "*",
    "year": "*",
}

def _read_config_file(name: str) -> str:
    return (_CONFIG / name).read_text(encoding="utf-8")

def _get_env_var(var_name: str) -> str:
    return os.environ.get(var_name, "").strip()

class NewsAgentStack(Stack):
    """RSS → Bedrock summary → optional SES email, triggered on a daily schedule."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # SSM parameters
        feeds_param = ssm.StringParameter(
            self,
            "FeedsJson",
            parameter_name="/news-agent/feeds",
            string_value=_read_config_file(FEEDS_FILE_NAME),
            description="JSON array of feed URLs or object with feeds key",
        )
        prompt_param = ssm.StringParameter(
            self,
            "SystemPrompt",
            parameter_name="/news-agent/system-prompt",
            string_value=_read_config_file(SYSTEM_PROMPT_FILE_NAME),
            description="System prompt for the summarization model",
        )
        sender_param = ssm.StringParameter(
            self,
            "SenderEmail",
            parameter_name="/news-agent/sender-email",
            string_value=_get_env_var(ENV_NEWS_AGENT_SENDER_EMAIL),
            description=(
                f"Verified SES sender; optional env {ENV_NEWS_AGENT_SENDER_EMAIL} at synthesis, "
                "or edit in Parameter Store"
            ),
        )
        recipient_param = ssm.StringParameter(
            self,
            "RecipientEmail",
            parameter_name="/news-agent/recipient-email",
            string_value=_get_env_var(ENV_NEWS_AGENT_RECIPIENT_EMAIL),
            description=(
                f"Newsletter recipient; optional env {ENV_NEWS_AGENT_RECIPIENT_EMAIL} at synthesis, "
                "or edit in Parameter Store (SES-verified)"
            ),
        )

        # Lambda function
        fn = lambda_.Function(
            self,
            "NewsAgentFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset(
                _LAMBDA_DIR,
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install --no-cache-dir -r requirements.txt -t /asset-output "
                        '&& for f in /asset-input/*.py; do cp "$f" /asset-output/; done',
                    ],
                ),
            ),
            timeout=Duration.seconds(180),
            memory_size=512,
            environment={
                "FEEDS_SSM_PARAM": feeds_param.parameter_name,
                "SYSTEM_PROMPT_SSM_PARAM": prompt_param.parameter_name,
                "NEWS_AGENT_SENDER_SSM_PARAM": sender_param.parameter_name,
                "NEWS_AGENT_RECIPIENT_SSM_PARAM": recipient_param.parameter_name,
            },
        )

        feeds_param.grant_read(fn)
        prompt_param.grant_read(fn)
        sender_param.grant_read(fn)
        recipient_param.grant_read(fn)

        fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=["*"],
            )
        )
        fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ses:SendEmail"],
                resources=["*"],
            )
        )

        # EventBridge schedule
        rule = events.Rule(
            self,
            "NewsAgentSchedule",
            schedule=events.Schedule.cron(
                minute=EVENT_SCHEDULE["minute"],
                hour=EVENT_SCHEDULE["hour"],
                month=EVENT_SCHEDULE["month"],
                week_day=EVENT_SCHEDULE["week_day"],
                year=EVENT_SCHEDULE["year"],
            ),
            description="Trigger news-agent Lambda daily (UTC)",
        )
        rule.add_target(targets.LambdaFunction(fn))
    