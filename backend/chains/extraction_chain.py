"""
Extraction chain — parses a meeting transcript into a structured ProjectData object.
Uses Ollama with JSON mode to ensure deterministic field extraction.
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

from langchain_core.prompts import PromptTemplate

from backend.ollama_client import get_llm
from backend.ingestion.document_loader import load_file


@dataclass
class ProjectData:
    # Customer / offer header
    first_name: str = ""
    last_name: str = ""
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


_EXTRACTION_PROMPT = PromptTemplate.from_template(
    """You are an assistant that extracts structured information from sales meeting transcripts.
Extract ONLY the following fields and return valid JSON. Use empty string "" for missing fields.

Fields to extract:
- first_name: first name of the customer/recipient of the offer
- last_name: last name of the customer/recipient
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


def extract_from_transcript(transcript_text: str) -> ProjectData:
    llm = get_llm()
    prompt = _EXTRACTION_PROMPT.format(transcript=transcript_text[:8000])
    raw_output = llm.invoke(prompt)
    cleaned = _clean_json(raw_output)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Fallback: return empty ProjectData — user fills in manually
        data = {}

    return ProjectData(**{k: v for k, v in data.items() if k in ProjectData.__dataclass_fields__})


def extract_from_file(file_path: Path) -> ProjectData:
    docs = load_file(file_path)
    full_text = "\n".join(d.page_content for d in docs)
    return extract_from_transcript(full_text)


def project_data_to_dict(pd: ProjectData) -> dict:
    return asdict(pd)
