"""
Tests for backend.chains.section1_chain — pure helper functions.
"""
import pytest
from backend.chains.section1_chain import (
    _strip_legal_suffix,
    _ascii_slug,
    _candidate_slugs,
    _extract_text_from_html,
    _find_about_url,
)


# ── _strip_legal_suffix ──────────────────────────────────────────────────────

class TestStripLegalSuffix:
    def test_oy(self):
        assert _strip_legal_suffix("Patria Oy") == "Patria"

    def test_oyj(self):
        assert _strip_legal_suffix("Nokia Oyj") == "Nokia"

    def test_ltd(self):
        assert _strip_legal_suffix("Acme Ltd") == "Acme"

    def test_ltd_dot(self):
        assert _strip_legal_suffix("Acme Ltd.") == "Acme"

    def test_gmbh(self):
        assert _strip_legal_suffix("Siemens GmbH") == "Siemens"

    def test_no_suffix(self):
        assert _strip_legal_suffix("Google") == "Google"

    def test_multi_word_name(self):
        assert _strip_legal_suffix("Link Design Oy") == "Link Design"

    def test_case_insensitive(self):
        assert _strip_legal_suffix("Test OY") == "Test"

    def test_ab(self):
        assert _strip_legal_suffix("Volvo AB") == "Volvo"


# ── _ascii_slug ───────────────────────────────────────────────────────────────

class TestAsciiSlug:
    def test_simple(self):
        assert _ascii_slug("Hello World") == "hello-world"

    def test_nordic_chars(self):
        assert _ascii_slug("Ääkkönen") == "aakkonen"

    def test_special_chars(self):
        assert _ascii_slug("Foo & Bar!") == "foo-bar"

    def test_already_slug(self):
        assert _ascii_slug("my-company") == "my-company"


# ── _candidate_slugs ─────────────────────────────────────────────────────────

class TestCandidateSlugs:
    def test_basic(self):
        slugs = _candidate_slugs("Patria Oyj")
        assert "patria" in slugs
        assert "patria-oyj" in slugs

    def test_no_duplicates(self):
        slugs = _candidate_slugs("Simple")
        assert len(slugs) == len(set(slugs))

    def test_multi_word(self):
        slugs = _candidate_slugs("Link Design Oy")
        assert "link-design" in slugs
        assert "linkdesign" in slugs


# ── _extract_text_from_html ──────────────────────────────────────────────────

class TestExtractTextFromHtml:
    def test_extracts_paragraphs(self):
        html = "<html><body><p>This is a meaningful paragraph that is long enough to pass the filter limit.</p></body></html>"
        text = _extract_text_from_html(html)
        assert "meaningful paragraph" in text

    def test_strips_scripts(self):
        html = "<script>var x = 1;</script><p>This paragraph should be extracted because it is long enough for the filter.</p>"
        text = _extract_text_from_html(html)
        assert "var x" not in text
        assert "paragraph should be extracted" in text

    def test_strips_nav_header_footer(self):
        html = "<nav>Menu items here</nav><p>This content paragraph is long enough to pass the minimum length filter bar.</p>"
        text = _extract_text_from_html(html)
        assert "Menu items" not in text

    def test_short_paragraphs_filtered(self):
        html = "<p>Short</p><p>This is a significantly longer paragraph that definitely passes the 40-char minimum.</p>"
        text = _extract_text_from_html(html)
        assert "Short" not in text
        assert "significantly longer" in text

    def test_deduplication(self):
        para = "This is a repeated paragraph that is long enough to pass the minimum character filter."
        html = f"<p>{para}</p><p>{para}</p>"
        text = _extract_text_from_html(html)
        assert text.count(para) == 1


# ── _find_about_url ──────────────────────────────────────────────────────────

class TestFindAboutUrl:
    def test_finds_about_link(self):
        html = '<a href="/about-us">About</a>'
        result = _find_about_url("https://example.com", html)
        assert result == "https://example.com/about-us"

    def test_finds_yritys_link(self):
        html = '<a href="/yritys">Yritys</a>'
        result = _find_about_url("https://example.fi", html)
        assert result == "https://example.fi/yritys"

    def test_ignores_external_links(self):
        html = '<a href="https://other.com/about">About</a>'
        result = _find_about_url("https://example.com", html)
        assert result is None

    def test_no_about_link(self):
        html = '<a href="/products">Products</a>'
        result = _find_about_url("https://example.com", html)
        assert result is None
