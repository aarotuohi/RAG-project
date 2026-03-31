"""
DOCX builder — assembles the full offer document from section data.
Uses python-docx to build the document programmatically from the offer template.
"""
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

from backend.config import TEMPLATES_DIR, OUTPUTS_DIR
from backend.chains.extraction_chain import ProjectData
from backend.ingestion.excel_parser import CostStepGroup

OFFER_FONT = "Campton Book"


def _add_heading(doc: Document, text: str, level: int):
    doc.add_heading(text, level=level)


def _add_paragraph(doc: Document, text: str, bold: bool = False, italic: bool = False):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = bold
    run.italic = italic
    return p


def _add_cost_table(doc: Document, steps: list[CostStepGroup], grand_total: float, project_output: str = ""):
    """Add the hierarchical cost estimation table to the document."""
    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"

    # Header row
    headers = ["Step", "Hourly cost [\u20ac/h]", "Hours estimation [h]", "Cost estimation [\u20ac]"]
    hdr_cells = table.rows[0].cells
    for i, hdr in enumerate(headers):
        hdr_cells[i].text = hdr
        for paragraph in hdr_cells[i].paragraphs:
            for run in paragraph.runs:
                run.bold = True

    for grp_idx, step_group in enumerate(steps, 1):
        try:
            step_num = step_group.step_id.split()[-1]
        except Exception:
            step_num = str(grp_idx)

        # Main step row — bold, shows totals
        main_row = table.add_row().cells
        main_row[0].text = f"{step_group.step_id}: {step_group.name}"
        main_row[1].text = ""
        main_row[2].text = f"{step_group.total_hours:,.1f}"
        main_row[3].text = f"{step_group.total_cost:,.2f}"
        for cell in [main_row[0], main_row[2], main_row[3]]:
            for para in cell.paragraphs:
                for run in para.runs:
                    run.bold = True

        # Sub-step rows
        for sub_idx, sub in enumerate(step_group.sub_steps, 1):
            sub_row = table.add_row().cells
            sub_row[0].text = f"  {step_num}.{sub_idx}  {sub.name}"
            sub_row[1].text = f"{sub.hourly_rate:,.2f}"
            sub_row[2].text = f"{sub.hours * sub.persons:,.1f}"
            sub_row[3].text = f"{sub.total:,.2f}"

    # Grand total row
    total_hours = sum(sg.total_hours for sg in steps)
    total_row = table.add_row().cells
    total_row[0].text = "Estimated work expenses overall"
    if project_output:
        total_row[0].add_paragraph(f"Output: {project_output}")
    total_row[1].text = ""
    total_row[2].text = f"{total_hours:,.1f} h"
    total_row[3].text = f"{grand_total:,.2f} \u20ac"
    for cell in [total_row[0], total_row[2], total_row[3]]:
        for para in cell.paragraphs:
            for run in para.runs:
                run.bold = True


_HEADINGS: dict[str, list[str]] = {
    "en": [
        "OFFER",
        "1. Background and Goals",
        "2. Project Implementation and Cost Estimation",
        "3. Timetable",
        "4. Project Restrictions and Responsibilities",
        "5. Material Transformation",
        "6. Documentation",
        "7. Quality Assurance",
        "8. Project Team",
        "9. Generic Terms of Delivery",
        "10. Payment Terms",
        "11. Contact Information",
        "12. Attachments",
    ],
    "fi": [
        "TARJOUS",
        "1. Tausta ja tavoitteet",
        "2. Projektin toteutus ja kustannusarvio",
        "3. Aikataulu",
        "4. Projektin rajoitukset ja vastuut",
        "5. Aineistomuunnos",
        "6. Dokumentaatio",
        "7. Laadunvarmistus",
        "8. Projektitiimi",
        "9. Yleiset toimitusehdot",
        "10. Maksuehdot",
        "11. Yhteystiedot",
        "12. Liitteet",
    ],
}


def build_offer_document(
    project: ProjectData,
    sections: dict,
    salesperson_contact: dict | None = None,
    language: str = "en",
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

    h = _HEADINGS.get(language, _HEADINGS["en"])
    #_set_default_font(doc, OFFER_FONT)
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
    offer_run = offer_heading.add_run(h[0])
    offer_run.bold = True
    offer_run.font.size = Pt(28)
    #offer_run.font.name = OFFER_FONT
    offer_heading.alignment = WD_ALIGN_PARAGRAPH.LEFT
    doc.add_paragraph()

    # ── Project info ──────────────────────────────────────────────────────────
    _add_paragraph(doc, f"Project name: {project.project_name}", bold=True)
    _add_paragraph(doc, f"Project number: {project.project_number}", bold=True)
    _add_paragraph(doc, f"Salesperson: {project.salesperson_name}", bold=True)    
    if project.salesperson_phone:
        _add_paragraph(doc, f"Phone: {project.salesperson_phone}")
    if project.salesperson_email:
        _add_paragraph(doc, f"Email: {project.salesperson_email}")    
    doc.add_paragraph()

    # ── Thank-you paragraph ───────────────────────────────────────────────────
    _add_paragraph(doc, sections.get("thankyou", ""))
    doc.add_paragraph()

    # ── Section 1 ─────────────────────────────────────────────────────────────
    _add_heading(doc, h[1], 1)
    s1 = sections.get("section1", {})
    _add_paragraph(doc, s1.get("company_background", ""))
    doc.add_paragraph()
    _add_paragraph(doc, s1.get("goals_text", ""))
    doc.add_paragraph()

    # ── Section 2 ─────────────────────────────────────────────────────────────
    _add_heading(doc, h[2], 1)
    s2 = sections.get("section2", {})
    _add_paragraph(doc, s2.get("description_text", ""))
    doc.add_paragraph()
    steps = s2.get("steps", [])
    if steps:
        _add_cost_table(doc, steps, s2.get("grand_total", 0.0), s2.get("project_output", ""))
    doc.add_paragraph()

    # ── Section 3 ─────────────────────────────────────────────────────────────
    _add_heading(doc, h[3], 1)
    _add_paragraph(doc, sections.get("section3", ""))
    doc.add_paragraph()

    # ── Section 4 ─────────────────────────────────────────────────────────────
    _add_heading(doc, h[4], 1)
    _add_paragraph(doc, sections.get("section4", ""))
    doc.add_paragraph()

    # ── Section 5 ─────────────────────────────────────────────────────────────
    _add_heading(doc, h[5], 1)
    _add_paragraph(doc, sections.get("section5", ""))
    doc.add_paragraph()

    # ── Section 6 ─────────────────────────────────────────────────────────────
    _add_heading(doc, h[6], 1)
    _add_paragraph(doc, sections.get("section6", ""))
    doc.add_paragraph()

    # ── Section 7 ─────────────────────────────────────────────────────────────
    _add_heading(doc, h[7], 1)
    _add_paragraph(doc, sections.get("section7", ""))
    doc.add_paragraph()

    # ── Section 8 ─────────────────────────────────────────────────────────────
    _add_heading(doc, h[8], 1)
    s8 = sections.get("section8", {})
    _add_paragraph(doc, s8.get("intro_text", ""))
    for expert in s8.get("experts", []):
        doc.add_paragraph()
        _add_paragraph(doc, expert.get("name", ""), bold=True)
        _add_paragraph(doc, expert.get("cv_summary", ""))
    doc.add_paragraph()

    # ── Section 9 ─────────────────────────────────────────────────────────────
    _add_heading(doc, h[9], 1)
    _add_paragraph(doc, sections.get("section9", ""))
    doc.add_paragraph()    
    if sections.get("section9_payment"):
        _add_paragraph(doc, sections["section9_payment"])
    doc.add_paragraph()

    # ── Section 10 — Payment Terms ────────────────────────────────────────────
    _add_heading(doc, h[10], 1)
    _doc_date = date.fromisoformat(project.document_date) if project.document_date else date.today()
    _deadline = (_doc_date + timedelta(weeks=2)).strftime("%d.%m.%Y")
    payment_terms = (
        f"Hintoihin lisätään 25,5% arvonlisävero laskutettaessa. Maksuehto 14pv netto. "
        f"Tuntiveloitusperusteiset työt laskutetaan kuukausittain toteuman mukaan. "
        f"Viivästyskorko on Suomen Pankin ilmoittama viitekorko lisättynä korkolain mukaisella lisäkorolla. "
        f"Tarjouksemme on voimassa välimyyntivarauksiin {_deadline} klo 17.asti. "
        f"Tarjouksemme on luottamuksellinen eikä sitä tule saattaa kolmannen osapuolen tietoon."
    )
    _add_paragraph(doc, payment_terms)
    doc.add_paragraph()

    # ── Section 11 — Contact Information ──────────────────────────────────────
    _add_heading(doc, h[11], 1)
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

    # ── Section 12 — Attachments ──────────────────────────────────────────────
    _add_heading(doc, h[12], 1)
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
