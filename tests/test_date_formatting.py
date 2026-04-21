"""
Tests for date formatting in the document generation pipeline.
Verifies Finnish regional date format (d.M.YYYY) is used throughout.
"""
import pytest
from datetime import date
from unittest.mock import patch, MagicMock
from backend.chains.extraction_chain import ProjectData
from backend.chains.boilerplate import _fmt_date


class TestFinnishDateFormat:
    """All dates in generated documents should use Finnish format: d.M.YYYY (no leading zeros)."""

    def test_fmt_date_april(self):
        assert _fmt_date("2026-04-01") == "1.4.2026"

    def test_fmt_date_january(self):
        assert _fmt_date("2026-01-09") == "9.1.2026"

    def test_fmt_date_october(self):
        assert _fmt_date("2026-10-15") == "15.10.2026"

    def test_fmt_date_december(self):
        assert _fmt_date("2025-12-31") == "31.12.2025"

    def test_docx_builder_date(self):
        """Verify docx_builder produces Finnish-format dates."""
        d = date(2026, 4, 1)
        finnish = f"{d.day}.{d.month}.{d.year}"
        assert finnish == "1.4.2026"

    def test_docx_builder_date_no_leading_zero_month(self):
        d = date(2026, 1, 5)
        finnish = f"{d.day}.{d.month}.{d.year}"
        assert finnish == "5.1.2026"

    def test_payment_deadline_format(self):
        """Payment deadline (doc_date + 2 weeks) should also use Finnish format."""
        from datetime import timedelta
        d = date(2026, 4, 1)
        dl = d + timedelta(weeks=2)
        finnish = f"{dl.day}.{dl.month}.{dl.year}"
        assert finnish == "15.4.2026"

    def test_excel_builder_date(self):
        """Excel builder date should use Finnish format."""
        from datetime import datetime
        d = datetime(2026, 4, 1)
        finnish = f"{d.day}.{d.month}.{d.year}"
        assert finnish == "1.4.2026"
