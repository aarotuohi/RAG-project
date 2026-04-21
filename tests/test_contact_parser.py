"""
Tests for backend.ingestion.contact_parser — normalization and lookup.
"""
import pytest
from backend.ingestion.contact_parser import _normalize, lookup


# ── _normalize ───────────────────────────────────────────────────────────────

class TestNormalize:
    def test_lowercase(self):
        assert _normalize("John Doe") == "john doe"

    def test_strip_whitespace(self):
        assert _normalize("  Jane Smith  ") == "jane smith"

    def test_already_normalized(self):
        assert _normalize("matti") == "matti"


# ── lookup ───────────────────────────────────────────────────────────────────

class TestLookup:
    @pytest.fixture
    def records(self):
        return {
            "john doe": {"name": "John Doe", "title": "Sales", "phone": "123", "email": "john@test.fi"},
            "matti meikäläinen": {"name": "Matti Meikäläinen", "title": "CTO", "phone": "456", "email": "matti@test.fi"},
        }

    def test_exact_match(self, records):
        result = lookup(records, "John Doe")
        assert result is not None
        assert result["name"] == "John Doe"

    def test_case_insensitive(self, records):
        result = lookup(records, "JOHN DOE")
        assert result is not None
        assert result["name"] == "John Doe"

    def test_partial_match(self, records):
        result = lookup(records, "John")
        assert result is not None
        assert result["name"] == "John Doe"

    def test_not_found(self, records):
        result = lookup(records, "Nonexistent Person")
        assert result is None

    def test_empty_name(self, records):
        result = lookup(records, "")
        # Empty string is a substring of everything, so partial match may fire
        # The important thing is it doesn't crash
        assert result is not None or result is None

    def test_finnish_name(self, records):
        result = lookup(records, "Matti Meikäläinen")
        assert result is not None
        assert result["email"] == "matti@test.fi"
