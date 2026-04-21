"""
Tests for backend.chains.section8_chain — field parsing and ranking extraction.
"""
import pytest
from backend.chains.section8_chain import _parse_field, _extract_selected


# ── _parse_field ──────────────────────────────────────────────────────────────

class TestParseField:
    def test_single_label(self):
        text = "Name: John Doe\nTitle: Engineer"
        assert _parse_field(text, "Name") == "John Doe"

    def test_multiple_labels(self):
        text = "Nimi: Matti Meikäläinen"
        assert _parse_field(text, "Name", "Nimi") == "Matti Meikäläinen"

    def test_case_insensitive(self):
        text = "name: jane smith"
        assert _parse_field(text, "Name") == "jane smith"

    def test_dash_separator(self):
        text = "Title - Senior Developer"
        assert _parse_field(text, "Title") == "Senior Developer"

    def test_not_found(self):
        text = "Some random text"
        assert _parse_field(text, "Name", "Title") == ""


# ── _extract_selected ────────────────────────────────────────────────────────

class TestExtractSelected:
    def test_standard_format(self):
        text = """SELECTED EXPERTS:
1. John Doe — Lead developer for backend systems
2. Jane Smith — UI/UX designer for the frontend
"""
        result = _extract_selected(text)
        assert len(result) == 2
        assert result[0] == ("John Doe", "Lead developer for backend systems")
        assert result[1] == ("Jane Smith", "UI/UX designer for the frontend")

    def test_dash_separator(self):
        text = "1. Alice - Project manager\n2. Bob - Backend developer"
        result = _extract_selected(text)
        assert len(result) == 2
        assert result[0][0] == "Alice"
        assert result[1][0] == "Bob"

    def test_en_dash_separator(self):
        text = "1. Charlie – Systems architect"
        result = _extract_selected(text)
        assert len(result) == 1
        assert result[0][0] == "Charlie"

    def test_empty_input(self):
        assert _extract_selected("") == []

    def test_no_matches(self):
        text = "Just some random text\nNothing structured here"
        assert _extract_selected(text) == []

    def test_bullet_format(self):
        text = "- Expert One — Role description one\n* Expert Two — Role description two"
        result = _extract_selected(text)
        assert len(result) == 2
