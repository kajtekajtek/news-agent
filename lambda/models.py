"""Shared domain models used across the Lambda code."""

from __future__ import annotations
from typing import TypedDict

class RssItem(TypedDict):
    """A single RSS entry after normalization for newsletter summarization."""

    title: str
    link: str
    published: str  # ISO 8601 UTC string
    summary: str

