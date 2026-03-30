"""Unit tests for html_utils."""

from html_utils import markdown_to_safe_html_fragment, strip_html_to_plain


def test_strip_html_to_plain():
    assert strip_html_to_plain("<p>a</p>") == "a"
    assert strip_html_to_plain("") == ""


def test_strip_html_to_plain_strips_tags_and_entities():
    html = '<p>Hello &amp; <b>world</b></p><script>ignore()</script>'
    assert strip_html_to_plain(html, max_chars=500) == "Hello & world"


def test_strip_html_to_plain_collapses_whitespace():
    assert strip_html_to_plain("  a  \n\tb  c  ", max_chars=500) == "a b c"


def test_strip_html_to_plain_truncates():
    long_text = "word " * 300
    out = strip_html_to_plain(long_text, max_chars=50)
    assert len(out) == 50
    assert out == long_text[:50]


def test_strip_html_to_plain_empty():
    assert strip_html_to_plain("", max_chars=100) == ""
    assert strip_html_to_plain("   ", max_chars=100) == ""


def test_markdown_to_safe_html_fragment_strips_script():
    out = markdown_to_safe_html_fragment("<script>x</script>\n**b**")
    assert "<script" not in out
    assert "<strong>b</strong>" in out or "<b>b</b>" in out
