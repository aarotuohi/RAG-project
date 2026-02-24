"""
DOCX builder — assembles the full offer document from section data.
Uses python-docx to build the document programmatically from the offer template.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

from backend.config import TEMPLATES_DIR, OUTPUTS_DIR
from backend.chains.extraction_chain import ProjectData
from backend.ingestion.excel_parser import CostStep


def _add_heading(doc: Document, text: str, level: int):
    doc.add_heading(text, level=level)


def _add_paragraph(doc: Document, text: str, bold: bool = False, italic: bool = False):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = bold
    run.italic = italic
    return p


def _add_cost_table(doc: Document, steps: list[CostStep], grand_total: float):
    """Add the cost estimation table to the document."""
    table = doc.add_table(rows=1, cols=7)
    table.style = "Table Grid"

    # Header row
    headers = ["Step", "Description", "Category", "Rate [€/h]", "Hours [h]", "Persons", "Total [€]"]
    hdr_cells = table.rows[0].cells
    for i, hdr in enumerate(headers):
        hdr_cells[i].text = hdr
        for paragraph in hdr_cells[i].paragraphs:
            for run in paragraph.runs:
                run.bold = True

    # Data rows
    for step in steps:
        row_cells = table.add_row().cells
        row_cells[0].text = step.step_id
        row_cells[1].text = step.name
        row_cells[2].text = step.category
        row_cells[3].text = f"{step.hourly_rate:,.2f}"
        row_cells[4].text = f"{step.hours:,.1f}"
        row_cells[5].text = str(step.persons)
        row_cells[6].text = f"{step.total:,.2f}"

    # Grand total row
    total_row = table.add_row().cells
    total_row[0].text = ""
    total_row[1].text = ""
    total_row[2].text = ""
    total_row[3].text = ""
    total_row[4].text = ""
    total_row[5].text = "TOTAL"
    total_row[6].text = f"{grand_total:,.2f} €"
    for cell in [total_row[5], total_row[6]]:
        for para in cell.paragraphs:
            for run in para.runs:
                run.bold = True


def build_offer_document(
    project: ProjectData,
    sections: dict,
    salesperson_contact: dict | None = None,
) -> Path:
    """
    Build the complete offer .docx file.
    
    `sections` dict keys:
      thankyou, section1, section2, section3, section4,
      section5, section6, section7, section8, section9, section10
    
    Returns the Path of the generated .docx file.
    """
    # Try to load template, fall back to blank document
    template_path = TEMPLATES_DIR / "offer_template.docx"
    if template_path.exists():
        doc = Document(str(template_path))
        # Clear template body content
        for element in list(doc.element.body):
            tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag
            if tag in ("p", "tbl"):
                doc.element.body.remove(element)
    else:
        doc = Document()
        # Set margins
        for section in doc.sections:
            section.top_margin = Cm(2.5)
            section.bottom_margin = Cm(2.5)
            section.left_margin = Cm(3)
            section.right_margin = Cm(2.5)

    doc_date = project.document_date or date.today().isoformat()

    # ── Header block ─────────────────────────────────────────────────────────
    _add_paragraph(doc, doc_date)
    _add_paragraph(doc, f"{project.first_name} {project.last_name}".strip())
    _add_paragraph(doc, project.company_name)
    _add_paragraph(doc, project.address)
    _add_paragraph(doc, project.postal_code)
    doc.add_paragraph()

    # ── OFFER heading ─────────────────────────────────────────────────────────
    offer_heading = doc.add_paragraph()
    offer_run = offer_heading.add_run("OFFER")
    offer_run.bold = True
    offer_run.font.size = Pt(28)
    offer_heading.alignment = WD_ALIGN_PARAGRAPH.LEFT
    doc.add_paragraph()

    # ── Project info ──────────────────────────────────────────────────────────
    _add_paragraph(doc, f"Project name: {project.project_name}", bold=True)
    _add_paragraph(doc, f"Project number: {project.project_number}", bold=True)
    _add_paragraph(doc, f"Salesperson: {project.salesperson_name}", bold=True)
    doc.add_paragraph()

    # ── Thank-you paragraph ───────────────────────────────────────────────────
    _add_paragraph(doc, sections.get("thankyou", ""))
    doc.add_paragraph()

    # ── Section 1 ─────────────────────────────────────────────────────────────
    _add_heading(doc, "1. Background and Goals", 1)
    s1 = sections.get("section1", {})
    _add_paragraph(doc, s1.get("company_background", ""))
    doc.add_paragraph()
    _add_paragraph(doc, s1.get("goals_text", ""))
    doc.add_paragraph()

    # ── Section 2 ─────────────────────────────────────────────────────────────
    _add_heading(doc, "2. Project Implementation and Cost Estimation", 1)
    s2 = sections.get("section2", {})
    _add_paragraph(doc, s2.get("description_text", ""))
    doc.add_paragraph()
    steps: list[CostStep] = s2.get("steps", [])
    if steps:
        _add_cost_table(doc, steps, s2.get("grand_total", 0.0))
    doc.add_paragraph()

    # ── Section 3 ─────────────────────────────────────────────────────────────
    _add_heading(doc, "3. Timetable", 1)
    _add_paragraph(doc, sections.get("section3", ""))
    doc.add_paragraph()

    # ── Section 4 ─────────────────────────────────────────────────────────────
    _add_heading(doc, "4. Project Restrictions and Responsibilities", 1)
    _add_paragraph(doc, sections.get("section4", ""))
    doc.add_paragraph()

    # ── Section 5 ─────────────────────────────────────────────────────────────
    _add_heading(doc, "5. Material Transformation", 1)
    _add_paragraph(doc, sections.get("section5", ""))
    doc.add_paragraph()

    # ── Section 6 ─────────────────────────────────────────────────────────────
    _add_heading(doc, "6. Documentation", 1)
    _add_paragraph(doc, sections.get("section6", ""))
    doc.add_paragraph()

    # ── Section 7 ─────────────────────────────────────────────────────────────
    _add_heading(doc, "7. Quality Assurance", 1)
    _add_paragraph(doc, sections.get("section7", ""))
    doc.add_paragraph()

    # ── Section 8 ─────────────────────────────────────────────────────────────
    _add_heading(doc, "8. Project Team", 1)
    s8 = sections.get("section8", {})
    _add_paragraph(doc, s8.get("intro_text", ""))
    for expert in s8.get("experts", []):
        doc.add_paragraph()
        _add_paragraph(doc, expert.get("name", ""), bold=True)
        _add_paragraph(doc, expert.get("cv_summary", ""))
    doc.add_paragraph()

    # ── Section 9 ─────────────────────────────────────────────────────────────
    _add_heading(doc, "9. Generic Terms of Delivery", 1)
    _add_paragraph(doc, sections.get("section9", ""))
    doc.add_paragraph()

    # ── Section 10 ────────────────────────────────────────────────────────────
    _add_heading(doc, "10. Contact Information", 1)
    _add_paragraph(doc, sections.get("section10_text", ""))
    doc.add_paragraph()
    if salesperson_contact:
        _add_paragraph(doc, salesperson_contact.get("name", ""), bold=True)
        if salesperson_contact.get("title"):
            _add_paragraph(doc, salesperson_contact["title"])
        if salesperson_contact.get("email"):
            _add_paragraph(doc, f"Email: {salesperson_contact['email']}")
        if salesperson_contact.get("phone"):
            _add_paragraph(doc, f"Phone: {salesperson_contact['phone']}")
    doc.add_paragraph()

    # ── Section 11 — Attachments ──────────────────────────────────────────────
    _add_heading(doc, "11. Attachments", 1)
    attachments = [
        "1. General terms and conditions",
        "2. Consulting service contract terms",
        "3. Constraints",
        "4. Cost estimate calculations",
    ]
    experts = s8.get("experts", [])
    expert_names = [e.get("name", "") for e in experts]
    if expert_names:
        attachments.append(f"5. Expert CVs: {', '.join(expert_names)}")
    else:
        attachments.append("5. Expert CVs")

    for att in attachments:
        doc.add_paragraph(att, style="List Number")

    # ── Save ──────────────────────────────────────────────────────────────────
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_project = (project.project_name or "offer").replace(" ", "_").replace("/", "-")[:40]
    out_path = OUTPUTS_DIR / f"offer_{safe_project}_{date.today().isoformat()}.docx"
    doc.save(str(out_path))
    return out_path
