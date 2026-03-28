#!/usr/bin/env python3
"""
Run the Lambda handler locally and print a JSON response with a parsed ``body`` object.

Does not run under pytest. Usage from repository root::

    ./tests/run_handler_local.py
    ./tests/run_handler_local.py --hours 12

Requires network for RSS (and AWS credentials for Bedrock when summarizing).

If ``FEEDS_JSON`` / ``SYSTEM_PROMPT`` are unset, loads ``config/feeds.json`` and
``config/system_prompt.txt`` when present.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_LAMBDA = _REPO_ROOT / "lambda"
_CONFIG = _REPO_ROOT / "config"

if str(_LAMBDA) not in sys.path:
    sys.path.insert(0, str(_LAMBDA))


def main() -> int:
    parser = argparse.ArgumentParser(description="Invoke handler.handler locally.")
    parser.add_argument(
        "--hours",
        type=int,
        default=None,
        help="RSS lookback window (passed as event['hours']).",
    )
    args = parser.parse_args()

    _load_default_env()

    from handler import handler

    event: dict = {}
    if args.hours is not None:
        event["hours"] = args.hours

    result = handler(event, None)
    pretty = _pretty_payload(result)
    print(json.dumps(pretty, indent=2, ensure_ascii=False))
    return 0


def _load_default_env() -> None:
    """Fill missing handler env vars from ``config/`` files."""
    from handler import ENV_FEEDS_JSON, ENV_SYSTEM_PROMPT

    if not os.environ.get(ENV_FEEDS_JSON, "").strip():
        feeds_path = _CONFIG / "feeds.json"
        if feeds_path.is_file():
            os.environ[ENV_FEEDS_JSON] = feeds_path.read_text(encoding="utf-8")
    if not os.environ.get(ENV_SYSTEM_PROMPT, "").strip():
        prompt_path = _CONFIG / "system_prompt.txt"
        if prompt_path.is_file():
            os.environ[ENV_SYSTEM_PROMPT] = prompt_path.read_text(encoding="utf-8")


def _pretty_payload(result: dict) -> dict:
    """Return a copy of ``result`` with ``body`` decoded from JSON when possible."""
    out = dict(result)
    raw = out.get("body")
    if isinstance(raw, str):
        try:
            out["body"] = json.loads(raw)
        except json.JSONDecodeError:
            pass
    return out


if __name__ == "__main__":
    raise SystemExit(main())
