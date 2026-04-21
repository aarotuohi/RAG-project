"""
Tests for backend.ingestion.cv_parser — pure text-processing functions.
"""
import pytest
from backend.ingestion.cv_parser import (
    _infer_skills,
    _infer_domains,
    _extract_name_from_segment,
    _split_by_headings,
    _split_by_separators,
)


# ── _infer_skills ────────────────────────────────────────────────────────────

class TestInferSkills:
    def test_detects_python(self):
        assert "Python" in _infer_skills("Experienced Python developer")

    def test_detects_multiple(self):
        skills = _infer_skills("Skills: Python, React, Docker, AWS")
        assert "Python" in skills
        assert "React" in skills
        assert "Docker" in skills
        assert "AWS" in skills

    def test_case_insensitive(self):
        skills = _infer_skills("experience with python and REACT")
        assert "Python" in skills
        assert "React" in skills

    def test_no_skills(self):
        assert _infer_skills("A person who likes cooking and hiking") == []

    def test_embedded(self):
        skills = _infer_skills("Built microservices with Kubernetes orchestration")
        assert "Kubernetes" in skills


# ── _infer_domains ───────────────────────────────────────────────────────────

class TestInferDomains:
    def test_software(self):
        assert "Software" in _infer_domains("Software engineering background")

    def test_multiple(self):
        domains = _infer_domains("Electronics and Mechanics expertise")
        assert "Electronics" in domains
        assert "Mechanics" in domains

    def test_no_match(self):
        assert _infer_domains("Artistic painting and sculpture") == []


# ── _extract_name_from_segment ───────────────────────────────────────────────

class TestExtractNameFromSegment:
    def test_standard_name(self):
        text = "Matti Meikäläinen\nSoftware Developer\nSkills: Python"
        assert _extract_name_from_segment(text) == "Matti Meikäläinen"

    def test_fallback_first_line(self):
        text = "some heading that is not a name\nnext line"
        name = _extract_name_from_segment(text)
        assert name == "some heading that is not a name"

    def test_empty_text(self):
        assert _extract_name_from_segment("") == "Unknown"

    def test_name_on_second_line(self):
        text = "CV\nAnna Korhonen\nTitle: Engineer"
        # CV line doesn't match name pattern, Anna Korhonen does
        assert _extract_name_from_segment(text) == "Anna Korhonen"


# ── _split_by_headings ──────────────────────────────────────────────────────

class TestSplitByHeadings:
    def test_cv_headings(self):
        text = "CV - John Doe\nSkills: Python\n\nCV - Jane Smith\nSkills: React"
        segments = _split_by_headings(text)
        assert len(segments) == 2

    def test_no_headings_returns_full(self):
        text = "Some random text without any CV headings"
        segments = _split_by_headings(text)
        assert len(segments) == 1
        assert segments[0] == text

    def test_name_headings(self):
        text = "Matti Meikäläinen\nSkills here\n\nAnna Virtanen\nMore skills"
        segments = _split_by_headings(text)
        assert len(segments) == 2


# ── _split_by_separators ────────────────────────────────────────────────────

class TestSplitBySeparators:
    def test_dash_separator(self):
        text = "Person A info\n---\nPerson B info"
        segments = _split_by_separators(text)
        assert len(segments) == 2

    def test_equals_separator(self):
        text = "Block 1\n===\nBlock 2"
        segments = _split_by_separators(text)
        assert len(segments) == 2

    def test_star_separator(self):
        text = "Block 1\n***\nBlock 2"
        segments = _split_by_separators(text)
        assert len(segments) == 2

    def test_no_separators(self):
        text = "Continuous text with no separator lines"
        segments = _split_by_separators(text)
        assert len(segments) == 1

    def test_empty_segments_filtered(self):
        text = "---\n\n---\nActual content\n---"
        segments = _split_by_separators(text)
        assert all(s.strip() for s in segments)
