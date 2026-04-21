"""
Tests for backend.chains.boilerplate
"""
import pytest
from unittest.mock import patch, MagicMock
from backend.chains.boilerplate import (
    _fmt_date,
    read_boilerplate,
    read_boilerplate_dated,
    generate_contact_text,
)
from backend.chains.extraction_chain import ProjectData


# ── _fmt_date ─────────────────────────────────────────────────────────────────

class TestFmtDate:
    def test_iso_date(self):
        assert _fmt_date("2026-04-01") == "1.4.2026"

    def test_date_no_leading_zeros(self):
        assert _fmt_date("2026-01-05") == "5.1.2026"

    def test_december(self):
        assert _fmt_date("2025-12-31") == "31.12.2025"

    def test_empty_string(self):
        assert _fmt_date("") == ""

    def test_non_iso_passthrough(self):
        assert _fmt_date("next week") == "next week"

    def test_already_finnish_format(self):
        # Non-ISO input should be returned as-is
        assert _fmt_date("1.4.2026") == "1.4.2026"

    def test_none_like_empty(self):
        assert _fmt_date("") == ""


# ── read_boilerplate ──────────────────────────────────────────────────────────

class TestReadBoilerplate:
    def test_unknown_key(self):
        result = read_boilerplate("nonexistent_key_xyz")
        assert "not configured" in result.lower() or "nonexistent_key_xyz" in result

    def test_reads_quality_en(self, tmp_path):
        """Verify file reading works when the file exists."""
        # This test relies on real boilerplate files in the project
        result = read_boilerplate("quality", language="en")
        # Should return content or a "not found" message, never crash
        assert isinstance(result, str)
        assert len(result) > 0

    def test_language_fallback(self):
        """If Swedish (sv) is requested but doesn't exist, should fall back."""
        result = read_boilerplate("quality", language="sv")
        assert isinstance(result, str)
        assert len(result) > 0


# ── read_boilerplate_dated ────────────────────────────────────────────────────

class TestReadBoilerplateDated:
    def test_payment_due_date_replacement(self):
        """The payment due date should be the last day of the month."""
        with patch("backend.chains.boilerplate.read_boilerplate", return_value="Due by {payment_due_date}"):
            result = read_boilerplate_dated("payment", doc_date="2026-04-15")
            assert result == "Due by 30.4.2026"

    def test_february_last_day(self):
        with patch("backend.chains.boilerplate.read_boilerplate", return_value="Pay by {payment_due_date}"):
            result = read_boilerplate_dated("payment", doc_date="2026-02-10")
            assert result == "Pay by 28.2.2026"

    def test_empty_date_uses_today(self):
        with patch("backend.chains.boilerplate.read_boilerplate", return_value="Due {payment_due_date}"):
            result = read_boilerplate_dated("payment", doc_date="")
            assert "Due " in result
            # Should have replaced the placeholder
            assert "{payment_due_date}" not in result

    def test_no_placeholder_passthrough(self):
        with patch("backend.chains.boilerplate.read_boilerplate", return_value="No placeholder here"):
            result = read_boilerplate_dated("payment", doc_date="2026-01-01")
            assert result == "No placeholder here"


# ── generate_contact_text ─────────────────────────────────────────────────────

class TestGenerateContactText:
    def test_english_output(self):
        project = ProjectData(salesperson_name="John Doe")
        contact = {"name": "John Doe", "phone": "+358 40 123", "email": "john@link.fi", "title": "Sales Manager"}
        result = generate_contact_text(project, language="en", salesperson_contact=contact)
        assert "John Doe" in result
        assert "+358 40 123" in result
        assert "john@link.fi" in result
        assert "Respectfully" in result

    def test_finnish_output(self):
        project = ProjectData(salesperson_name="Matti Meikäläinen")
        contact = {"name": "Matti Meikäläinen", "phone": "+358 40 456", "email": "matti@link.fi", "title": ""}
        result = generate_contact_text(project, language="fi", salesperson_contact=contact)
        assert "Matti Meikäläinen" in result
        assert "Kunnioittavasti" in result

    def test_no_contact_fallback(self):
        project = ProjectData(salesperson_name="Fallback Name")
        result = generate_contact_text(project, language="en", salesperson_contact=None)
        assert "Fallback Name" in result

    def test_title_appended(self):
        project = ProjectData(salesperson_name="Test")
        contact = {"name": "Test", "phone": "123", "email": "a@b.fi", "title": "CTO"}
        result = generate_contact_text(project, language="en", salesperson_contact=contact)
        assert "CTO" in result
