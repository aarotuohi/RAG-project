"""
Tests for backend.chains.extraction_chain
"""
import pytest
from backend.chains.extraction_chain import (
    ProjectData,
    _clean_json,
    _split_transcript,
    _merge_partials,
    project_data_to_dict,
)


# ── _clean_json ───────────────────────────────────────────────────────────────

class TestCleanJson:
    def test_plain_json(self):
        assert _clean_json('{"a": 1}') == '{"a": 1}'

    def test_json_code_fence(self):
        assert _clean_json('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_code_fence_no_lang(self):
        assert _clean_json('```\n{"b": 2}\n```') == '{"b": 2}'

    def test_whitespace_around_fences(self):
        assert _clean_json('  ```json\n{"c": 3}\n```  ') == '{"c": 3}'

    def test_no_fences(self):
        raw = '{"name": "test"}'
        assert _clean_json(raw) == raw


# ── _split_transcript ─────────────────────────────────────────────────────────

class TestSplitTranscript:
    def test_short_text_single_chunk(self):
        text = "Hello world"
        chunks = _split_transcript(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_exact_chunk_size(self):
        text = "x" * 5000
        chunks = _split_transcript(text)
        assert len(chunks) == 1

    def test_just_over_chunk_size(self):
        text = "x" * 5001
        chunks = _split_transcript(text)
        assert len(chunks) == 2
        # First chunk is full size
        assert len(chunks[0]) == 5000
        # Second chunk starts at (5000 - 400)
        assert chunks[1] == text[4600:]

    def test_multiple_chunks_overlap(self):
        text = "x" * 12000
        chunks = _split_transcript(text)
        assert len(chunks) >= 3
        # Verify overlap: tail of chunk[0] == head of chunk[1]
        assert chunks[0][-400:] == chunks[1][:400]

    def test_empty_string(self):
        chunks = _split_transcript("")
        assert chunks == []


# ── _merge_partials ───────────────────────────────────────────────────────────

class TestMergePartials:
    def test_scalar_first_nonempty_wins(self):
        partials = [
            {"first_name": "", "last_name": "Smith"},
            {"first_name": "John", "last_name": "Doe"},
        ]
        merged = _merge_partials(partials)
        assert merged["first_name"] == "John"
        assert merged["last_name"] == "Smith"

    def test_text_fields_accumulated(self):
        partials = [
            {"goals": "Build API"},
            {"goals": "Build UI"},
            {"goals": "Build API"},  # duplicate
        ]
        merged = _merge_partials(partials)
        assert "Build API" in merged["goals"]
        assert "Build UI" in merged["goals"]
        # Should not have the duplicate
        assert merged["goals"].count("Build API") == 1

    def test_empty_partials(self):
        merged = _merge_partials([])
        assert merged.get("first_name") is None
        assert merged.get("goals", "") == ""

    def test_single_partial(self):
        partials = [{"company_name": "Acme", "goals": "Deliver widget"}]
        merged = _merge_partials(partials)
        assert merged["company_name"] == "Acme"
        assert merged["goals"] == "Deliver widget"


# ── ProjectData ───────────────────────────────────────────────────────────────

class TestProjectData:
    def test_default_values(self):
        pd = ProjectData()
        assert pd.first_name == ""
        assert pd.document_date == ""

    def test_custom_values(self):
        pd = ProjectData(first_name="Jane", company_name="Acme Oy")
        assert pd.first_name == "Jane"
        assert pd.company_name == "Acme Oy"

    def test_to_dict(self):
        pd = ProjectData(first_name="John", last_name="Doe")
        d = project_data_to_dict(pd)
        assert isinstance(d, dict)
        assert d["first_name"] == "John"
        assert d["last_name"] == "Doe"
        assert "goals" in d


# ── extract_from_transcript (mocked LLM) ─────────────────────────────────────

class TestExtractFromTranscript:
    def test_short_transcript(self, monkeypatch):
        fake_json = '{"first_name": "Matti", "company_name": "TestCo", "goals": "Build app"}'
        monkeypatch.setattr(
            "backend.chains.extraction_chain.get_llm",
            lambda: type("FakeLLM", (), {"invoke": lambda self, p: fake_json})(),
        )
        from backend.chains.extraction_chain import extract_from_transcript
        result = extract_from_transcript("Short meeting transcript")
        assert result.first_name == "Matti"
        assert result.company_name == "TestCo"

    def test_llm_returns_fenced_json(self, monkeypatch):
        fake_json = '```json\n{"first_name": "Anna", "last_name": "K"}\n```'
        monkeypatch.setattr(
            "backend.chains.extraction_chain.get_llm",
            lambda: type("FakeLLM", (), {"invoke": lambda self, p: fake_json})(),
        )
        from backend.chains.extraction_chain import extract_from_transcript
        result = extract_from_transcript("Transcript text")
        assert result.first_name == "Anna"
        assert result.last_name == "K"

    def test_llm_returns_garbage(self, monkeypatch):
        monkeypatch.setattr(
            "backend.chains.extraction_chain.get_llm",
            lambda: type("FakeLLM", (), {"invoke": lambda self, p: "not json at all"})(),
        )
        from backend.chains.extraction_chain import extract_from_transcript
        result = extract_from_transcript("Transcript text")
        # Should return empty ProjectData, not crash
        assert result.first_name == ""
