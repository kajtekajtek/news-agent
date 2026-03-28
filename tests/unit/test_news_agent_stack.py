"""CDK template assertions for NewsAgentStack (bundling skipped for unit tests)."""

from __future__ import annotations

import aws_cdk as core
import aws_cdk.assertions as assertions

from infra.news_agent_stack import NewsAgentStack

def _template() -> assertions.Template:
    app = core.App()
    # avoid Docker bundling
    app.node.set_context("@aws-cdk/aws-lambda:skipBundling", True)
    stack = NewsAgentStack(app, "TestNewsAgentStack")
    return assertions.Template.from_stack(stack)


def test_lambda_function_python312_and_timeout():
    template = _template()
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Runtime": "python3.12",
            "Timeout": 180,
        },
    )


def test_eventbridge_rule_daily_schedule():
    template = _template()
    template.resource_count_is("AWS::Events::Rule", 1)
    template.has_resource_properties(
        "AWS::Events::Rule",
        {
            "ScheduleExpression": assertions.Match.string_like_regexp(r"^cron\(.+\)$"),
        },
    )


def test_ssm_parameters_under_news_agent_prefix():
    template = _template()
    template.resource_count_is("AWS::SSM::Parameter", 4)
    for name in (
        "/news-agent/feeds",
        "/news-agent/system-prompt",
        "/news-agent/sender-email",
        "/news-agent/recipient-email",
    ):
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {"Name": name},
        )


def test_iam_policy_actions_are_not_wildcard():
    template = _template()
    tmpl = template.to_json()
    resources = tmpl.get("Resources", {})
    for rid, rdef in resources.items():
        if rdef.get("Type") != "AWS::IAM::Policy":
            continue
        props = rdef.get("Properties", {})
        doc = props.get("PolicyDocument", {})
        statements = doc.get("Statement", [])
        if isinstance(statements, dict):
            statements = [statements]
        for stmt in statements:
            actions = stmt.get("Action")
            if actions == "*":
                raise AssertionError(
                    f"Policy {rid} uses Action '*' (least privilege: use explicit actions)"
                )
            if isinstance(actions, list) and "*" in actions:
                raise AssertionError(
                    f"Policy {rid} lists '*' in Action"
                )
