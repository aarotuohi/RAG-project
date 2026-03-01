"""
Boilerplate injector — reads static text files and returns their content verbatim.
Sections 4, 6, 7, 9 use this to ensure legal/compliance text is never hallucinated.
"""
from __future__ import annotations
from pathlib import Path
from langchain_core.prompts import PromptTemplate
from backend.config import BOILERPLATE_DIR, BOILERPLATE_FILES
from backend.ollama_client import get_llm
from backend.chains.extraction_chain import ProjectData


def read_boilerplate(key: str) -> str:
    """
    Read a boilerplate file by key (e.g. 'quality', 'delivery', 'documentation').
    Returns the file content or a placeholder if the file doesn't exist.
    """
    filename = BOILERPLATE_FILES.get(key)
    if not filename:
        return f"[Boilerplate '{key}' not configured.]"

    path = BOILERPLATE_DIR / filename
    if not path.exists():
        return (
            f"[Boilerplate file '{filename}' not found. "
            f"Please add it to {BOILERPLATE_DIR}]"
        )
    return path.read_text(encoding="utf-8", errors="ignore").strip()


def read_custom_boilerplate(filepath: Path) -> str:
    """Read any arbitrary boilerplate file."""
    if not filepath.exists():
        return f"[File not found: {filepath}]"
    return filepath.read_text(encoding="utf-8", errors="ignore").strip()


# ── LLM-assisted sections (light parameterization, not legal text) ────────────

_THANKYOU_PROMPT = PromptTemplate.from_template(
    """Write a short, warm, professional thank-you paragraph (2-3 sentences) for a sales offer document.
Thank the company for the meeting and express enthusiasm about the potential collaboration.

Customer company: {company_name}
Customer name: {first_name} {last_name}
Project: {project_name}

Thank-you paragraph:"""
)

_TIMETABLE_PROMPT = PromptTemplate.from_template(
    """Write a concise timetable section (2-4 sentences) for a sales offer document.
State when the project starts and ends, and mention any key milestones if known.

Project start: {project_start}
Project end: {project_end}
Other notes: {other_notes}

Timetable text:"""
)

_RESTRICTIONS_PROMPT = PromptTemplate.from_template(
    """Write a professional project restrictions and responsibilities section (3-5 sentences) 
for a sales offer document. Describe what work the project requires, 
state the payment model, and any customer responsibilities.

Payment type: {payment_type}
Constraints: {constraints}
Required work: {required_expertise}

Restrictions and responsibilities text:"""
)

_MATERIAL_PROMPT = PromptTemplate.from_template(
    """Write a concise material transformation section (2-4 sentences) for a sales offer document.
Describe what deliverables and materials the customer will receive.

Deliverables: {material_deliverables}
Project: {project_name}

Material transformation text:"""
)


def generate_thankyou(project: ProjectData, language: str = "en") -> str:
    lang_note = "Write the entire response in Finnish." 
    if language == "fi":
        "Write in Finnish"
    else: 
        "Write the entire response in English."
    llm = get_llm()
    prompt = _THANKYOU_PROMPT.format(
        company_name=project.company_name or "your company",
        first_name=project.first_name or "",
        last_name=project.last_name or "",
        project_name=project.project_name or "the project",
    ) + f"\n\n{lang_note}"
    return llm.invoke(prompt).strip()


def generate_timetable(project: ProjectData, language: str = "en") -> str:
    lang_note = "Write the entire response in Finnish." if language == "fi" else "Write the entire response in English."
    llm = get_llm()
    prompt = _TIMETABLE_PROMPT.format(
        project_start=project.project_start or "To be confirmed",
        project_end=project.project_end or "To be confirmed",
        other_notes=project.other_notes or "None",
    ) + f"\n\n{lang_note}"
    return llm.invoke(prompt).strip()


def generate_restrictions(project: ProjectData, language: str = "en") -> str:
    lang_note = "Write the entire response in Finnish." if language == "fi" else "Write the entire response in English."
    llm = get_llm()
    prompt = _RESTRICTIONS_PROMPT.format(
        payment_type=project.payment_type or "hourly",
        constraints=project.constraints or "None",
        required_expertise=project.required_expertise or "Not specified",
    ) + f"\n\n{lang_note}"
    return llm.invoke(prompt).strip()


def generate_material(project: ProjectData, language: str = "en") -> str:
    lang_note = "Write the entire response in Finnish." if language == "fi" else "Write the entire response in English."
    llm = get_llm()
    prompt = _MATERIAL_PROMPT.format(
        material_deliverables=project.material_deliverables or "To be confirmed",
        project_name=project.project_name or "the project",
    ) + f"\n\n{lang_note}"
    return llm.invoke(prompt).strip()


def generate_contact_text(project: ProjectData, language: str = "en", salesperson_contact: dict | None = None) -> str:
    """
    Returns a fully static, templated contact/closing section.
    Name, phone, email, and title come from salesperson_contact (loaded from contacts file).
    Falls back to project.salesperson_name if no contact record is found.
    """
    contact = salesperson_contact or {}
    name  = contact.get("name")  or project.salesperson_name or "Our Representative"
    phone = contact.get("phone") or "—"
    email = contact.get("email") or "—"
    title = contact.get("title") or ""

    if language == "fi":
        lines = [
            "Toivomme, että tarjouksemme sopii teille ja johtaa yhteistyöhön yritystemme välillä.\n",
            f"Tätä sopimusta koskevissa asioissa yhteyshenkilönä toimii {name}, "
            f"joka voi myös antaa lisätietoja tarjouksesta.\n",
            f"Puhelinnumero: {phone}",
            f"Sähköposti: {email}\n",
            "Kunnioittavasti\n",
            name,
        ]
    else:
        lines = [
            "We hope that our proposal will be suitable for you and lead to "
            f"cooperation between our companies.\n",
            f"The contact person for matters relating to the agreement is {name}, "
            f"who can also provide additional information about the proposal.\n",
            f"Phone number: {phone}",
            f"Email: {email}\n",
            "Respectfully\n",
            name,
        ]

    if title:
        lines.append(title)

    return "\n".join(lines).strip()
