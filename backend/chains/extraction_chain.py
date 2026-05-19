"""
Extraction chain — parses a meeting transcript into a structured ProjectData object.
Uses Ollama with JSON mode to ensure deterministic field extraction.

For long transcripts the chain uses a map-reduce strategy:
  1. Split the transcript into overlapping chunks that fit the model's context window.
  2. Run the extraction prompt on every chunk individually.
  3. Merge the partial results: scalar fields take the first non-empty value;
     narrative fields (goals, constraints, …) accumulate unique content from all chunks.
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

from langchain_core.prompts import PromptTemplate

from backend.ollama_client import get_llm
from backend.ingestion.document_loader import load_file

# Characters per chunk sent to the model.
# 5 000 chars ≈ 1 250 tokens — safely fits in an 8 192-token context window
# alongside the prompt template (~150 tokens) and JSON response (~400 tokens).
_CHUNK_SIZE    = 5_000
_CHUNK_OVERLAP = 400   # overlap so nothing is lost at chunk boundaries


@dataclass
class ProjectData:
    # Customer / offer header
    customer_name: str = ""
    company_name: str = ""
    address: str = ""
    postal_code: str = ""

    # Project identifiers
    project_name: str = ""
    project_number: str = ""
    salesperson_name: str = ""

    # Dates
    document_date: str = ""   # ISO format YYYY-MM-DD; auto-filled if empty
    project_start: str = ""
    project_end: str = ""

    # Section content hints
    goals: str = ""
    constraints: str = ""
    payment_type: str = ""    # "hourly" | "fixed"
    material_deliverables: str = ""
    required_expertise: str = ""
    other_notes: str = ""

    # Salesperson contact details (populated from contacts file, not transcript extraction)
    salesperson_phone: str = ""
    salesperson_email: str = ""
    salesperson_title: str = ""


_EXTRACTION_PROMPT = PromptTemplate.from_template(
    """You are an assistant that extracts structured information from sales meeting transcripts.
Extract ONLY the following fields and return valid JSON. Use empty string "" for missing fields.

Fields to extract:
- customer_name: full name of the customer/recipient of the offer
- company_name: name of the customer company
- address: street address of the customer
- postal_code: postal code of the customer
- project_name: name or title of the project
- project_number: project number or reference code
- salesperson_name: name of the salesperson conducting the meeting
- project_start: expected start date (YYYY-MM-DD or free text)
- project_end: expected end date (YYYY-MM-DD or free text)
- goals: key goals and objectives of the project
- constraints: constraints, limitations, or special requirements
- payment_type: "hourly" or "fixed" (based on payment discussion)
- material_deliverables: what will be delivered (software, hardware, product, documentation, etc.)
- required_expertise: what kind of expertise or roles the project needs
- other_notes: any other relevant information

TRANSCRIPT:
{transcript}

Return ONLY a JSON object, no explanation."""
)


def _clean_json(text: str) -> str:
    """Strip markdown code fences if the model wrapped the JSON."""
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text.strip())
    return text.strip()


# ── Chunking helpers ──────────────────────────────────────────────────────────

def _split_transcript(text: str) -> list[str]:
    """Split *text* into overlapping chunks of at most _CHUNK_SIZE characters."""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + _CHUNK_SIZE
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - _CHUNK_OVERLAP
    return chunks


_SCALAR_FIELDS = {
    "customer_name", "company_name", "address", "postal_code",
    "project_name", "project_number", "salesperson_name",
    "document_date", "project_start", "project_end", "payment_type",
}
_TEXT_FIELDS = {
    "goals", "constraints", "material_deliverables", "required_expertise", "other_notes",
}


def _merge_partials(partials: list[dict]) -> dict:
    """
    Merge extraction results from multiple chunks.
    - Scalar fields: first non-empty value wins.
    - Narrative text fields: unique contributions from every chunk are joined.
    """
    merged: dict[str, str] = {}
    text_parts: dict[str, list[str]] = {f: [] for f in _TEXT_FIELDS}

    for partial in partials:
        for f in _SCALAR_FIELDS:
            val = str(partial.get(f, "")).strip()
            if val and f not in merged:
                merged[f] = val
        for f in _TEXT_FIELDS:
            val = str(partial.get(f, "")).strip()
            if val and val not in text_parts[f]:
                text_parts[f].append(val)

    for f, parts in text_parts.items():
        merged[f] = " ".join(parts)

    return merged


def _extract_chunk(chunk: str) -> dict:
    """Run the extraction prompt on a single text chunk and return a raw dict."""
    llm = get_llm()
    prompt = _EXTRACTION_PROMPT.format(transcript=chunk)
    raw = llm.invoke(prompt)
    try:
        return json.loads(_clean_json(raw))
    except json.JSONDecodeError:
        return {}


def extract_from_transcript(transcript_text: str) -> ProjectData:
    if len(transcript_text) <= _CHUNK_SIZE:
        # Short enough for a single pass
        data = _extract_chunk(transcript_text)
    else:
        chunks = _split_transcript(transcript_text)
        partials = [_extract_chunk(chunk) for chunk in chunks]
        data = _merge_partials(partials)

    return ProjectData(**{k: v for k, v in data.items() if k in ProjectData.__dataclass_fields__})


def extract_from_file(file_path: Path) -> ProjectData:
    docs = load_file(file_path)
    full_text = "\n".join(d.page_content for d in docs)
    return extract_from_transcript(full_text)


def project_data_to_dict(pd: ProjectData) -> dict:
    return asdict(pd)
