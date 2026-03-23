"""Lambda entrypoint for the news agent workflow."""

def handler(event, context):
    """Orchestrate RSS fetch, summarization, and email sending"""
    return {
        "statusCode": 200,
        "body": "Phase 1 placeholder handler.",
    }
