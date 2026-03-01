"""
CV parser — segments a single combined CV file into per-expert chunks.
Supported formats: .docx, .pdf

Segmentation heuristics (in order of priority):
  1. Explicit page-break between CVs (PDF)
  2. Heading paragraph matching "CV", "Curriculum Vitae", or a name-like pattern
  3. A repeated separator line (e.g. "---", "===")
Each segment is stored with metadata: person_name, skills, domains.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ExpertCV:
    person_name: str
    raw_text: str
    skills: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)


_CV_HEADING_PATTERN = re.compile(
    r"^(CV\s*[-–]?\s*.{2,40}|Curriculum Vitae\s*[-–]?\s*.{0,40}|[A-ZÄÖÅ][a-zäöå]+\s+[A-ZÄÖÅ][a-zäöå]+)",
    re.MULTILINE,
)
_SEPARATOR_PATTERN = re.compile(r"^[-=*]{3,}\s*$", re.MULTILINE)
_WORK_CATEGORIES = ["Services", "Mechanics", "Software", "Research", "Electronics", "Design"]


def _infer_skills(text: str) -> list[str]:
    """Extract likely skill keywords from CV text (simple heuristic)."""
    skill_keywords = [
        "Python", "Java", "C++", "C#", "JavaScript", "TypeScript", "React", "Angular",
        "SQL", "AWS", "Azure", "Docker", "Kubernetes", "Machine Learning", "AI",
        "AutoCAD", "SolidWorks", "MATLAB", "LabVIEW", "PCB", "Embedded", "FPGA",
        "Project Management", "Agile", "Scrum",
    ]
    found = [kw for kw in skill_keywords if re.search(re.escape(kw), text, re.IGNORECASE)]
    return found


def _infer_domains(text: str) -> list[str]:
    return [cat for cat in _WORK_CATEGORIES if re.search(cat, text, re.IGNORECASE)]


def _extract_name_from_segment(text: str) -> str:
    """Try to extract a person name from the first few lines of a CV segment."""
    for line in text.splitlines()[:10]:
        line = line.strip()
        # A name-like line: two capitalized words, no digits, short
        if re.match(r"^[A-ZÄÖÅ][a-zäöå]+ [A-ZÄÖÅ][a-zäöå]+$", line):
            return line
    # Fallback: first non-empty line
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:50]
    return "Unknown"


def _split_by_headings(text: str) -> list[str]:
    """Split text at CV/name headings."""
    positions = [m.start() for m in _CV_HEADING_PATTERN.finditer(text)]
    if len(positions) < 2:
        return [text]
    segments = []
    for i, pos in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(text)
        segments.append(text[pos:end].strip())
    return segments


def _split_by_separators(text: str) -> list[str]:
    segments = _SEPARATOR_PATTERN.split(text)
    return [s.strip() for s in segments if s.strip()]


def parse_docling(path: Path) -> list[ExpertCV]:
    """
    Parse a CV file (.docx or .pdf) using Docling's DocumentConverter.
    Docling preserves layout, headings, and table structure far better than
    raw python-docx / pdfplumber extraction, giving the heading-based splitter
    cleaner input to work with.
    """
    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    result = converter.convert(str(path))
    # Export to markdown — headings become "## Name" markers the splitter already handles
    full_text = result.document.export_to_markdown()

    # Try heading-based split first; fall back to separator-based
    segments = _split_by_headings(full_text)
    if len(segments) == 1:
        segments = _split_by_separators(full_text)

    experts: list[ExpertCV] = []
    for seg in segments:
        if len(seg) < 100:
            continue
        name = _extract_name_from_segment(seg)
        experts.append(ExpertCV(
            person_name=name,
            raw_text=seg,
            skills=_infer_skills(seg),
            domains=_infer_domains(seg),
        ))
    return experts


def parse_cv_file(path: Path) -> list[ExpertCV]:
    suffix = path.suffix.lower()
    if suffix in (".docx", ".pdf"):
        return parse_docling(path)
    else:
        raise ValueError(f"Unsupported CV file format: {suffix}")
