"""HTML and Markdown helpers: plain text from HTML fragments; safe email HTML from Markdown."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

import markdown

# --- HTML fragment → plain text ---

_BLOCK_LIKE_TAGS = frozenset(
    {"p", "div", "li", "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article"}
)


class _HtmlToPlainTextParser(HTMLParser):
    """Collect visible text; skip script/style; separate blocks with a space."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        t = tag.lower()
        if t in ("script", "style"):
            self._skip = True
            return
        if self._skip:
            return
        if t == "br" or t in _BLOCK_LIKE_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in ("script", "style"):
            self._skip = False
            return
        if self._skip:
            return
        if t in _BLOCK_LIKE_TAGS or t == "br":
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def strip_html_to_plain(html: str, *, max_chars: int | None = None) -> str:
    """Return visible text from an HTML fragment; collapse whitespace to single spaces.

    If ``max_chars`` is set, the result is truncated to that length.
    """
    if not html or not html.strip():
        return ""
    parser = _HtmlToPlainTextParser()
    parser.feed(html)
    parser.close()
    plain = collapse_whitespace("".join(parser.parts))
    if max_chars is None or len(plain) <= max_chars:
        return plain
    return plain[:max_chars]


# --- Email: Markdown → HTML (strip tags that must not appear in HTML email) ---

MARKDOWN_EMAIL_EXTENSIONS = ("fenced_code", "sane_lists", "nl2br", "tables")

# Python-Markdown passes through raw HTML; mitigate script/embed in outbound mail.
_DANGEROUS_HTML_PATTERNS = (
    r"(?is)<script\b[^>]*>.*?</script>",
    r"(?is)<script\b[^>]*/>",
    r"(?is)<iframe\b[^>]*>.*?</iframe>",
    r"(?is)<object\b[^>]*>.*?</object>",
    r"(?is)<embed\b[^>]*/?>",
)


def strip_dangerous_html(fragment: str) -> str:
    """Remove script-like and embed-like tags from an HTML fragment."""
    out = fragment
    for pattern in _DANGEROUS_HTML_PATTERNS:
        out = re.sub(pattern, "", out)
    return out


def markdown_to_safe_html_fragment(markdown_text: str) -> str:
    """Render Markdown to HTML and strip dangerous tags (for embedding in email HTML)."""
    text = markdown_text.strip()
    if not text:
        return ""
    fragment = markdown.markdown(
        text,
        extensions=list(MARKDOWN_EMAIL_EXTENSIONS),
    )
    return strip_dangerous_html(fragment)
