"""
Tests for backend.generator.docx_builder — formatting helpers.
"""
import pytest
from backend.generator.docx_builder import _fmt_eur


# ── _fmt_eur ─────────────────────────────────────────────────────────────────

class TestFmtEur:
    def test_small_amount(self):
        assert _fmt_eur(500.0) == "500€"

    def test_thousands(self):
        result = _fmt_eur(8000.0)
        # Should have non-breaking space as thousands separator
        assert "8" in result
        assert "000" in result
        assert "€" in result

    def test_large_amount(self):
        result = _fmt_eur(150000.0)
        assert "€" in result
        assert "150" in result

    def test_rounding(self):
        assert _fmt_eur(999.7) == "1\u00a0000€"

    def test_zero(self):
        assert _fmt_eur(0.0) == "0€"

    def test_exact_boundary(self):
        assert _fmt_eur(1000.0) == "1\u00a0000€"
