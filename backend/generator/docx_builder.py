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


def _parse_project_date(value: str) -> date:
    if not value:
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    try:
        day, month, year = (int(part) for part in value.split("."))
        return date(year, month, day)
    except Exception:
        return date.today()


def _set_default_font(doc: Document, font_name: str):
    """Apply font_name as the document-wide default for all styles and docDefaults."""
    # Document-level run defaults (w:docDefaults/w:rPrDefault)
    doc_defaults = doc.styles.element.find(qn('w:docDefaults'))
    if doc_defaults is not None:
        rpr_default = doc_defaults.find(qn('w:rPrDefault'))
        if rpr_default is None:
            rpr_default = OxmlElement('w:rPrDefault')
            doc_defaults.append(rpr_default)
        rpr = rpr_default.find(qn('w:rPr'))
        if rpr is None:
            rpr = OxmlElement('w:rPr')
            rpr_default.append(rpr)
        rfonts = rpr.find(qn('w:rFonts'))
        if rfonts is None:
            rfonts = OxmlElement('w:rFonts')
            rpr.insert(0, rfonts)
        rfonts.set(qn('w:ascii'), font_name)
        rfonts.set(qn('w:hAnsi'), font_name)
        rfonts.set(qn('w:cs'), font_name)
    # Normal style + headings
    for style_name in ['Normal'] + [f'Heading {i}' for i in range(1, 10)]:
        try:
            doc.styles[style_name].font.name = font_name
        except Exception:
            pass


def _add_heading(doc: Document, text: str, level: int):
    doc.add_heading(text, level=level)


def _clear_table_borders(table) -> None:
    """Remove all visible borders from a DOCX table."""
    tbl = table._tbl
    tblPr = tbl.find(qn('w:tblPr'))
    if tblPr is None:
        tblPr = OxmlElement('w:tblPr')
        tbl.insert(0, tblPr)
    tblBorders = tblPr.find(qn('w:tblBorders'))
    if tblBorders is not None:
        tblPr.remove(tblBorders)
    tblBorders = OxmlElement('w:tblBorders')
    for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        el = OxmlElement(f'w:{side}')
        el.set(qn('w:val'), 'none')
        el.set(qn('w:sz'), '0')
        el.set(qn('w:space'), '0')
        el.set(qn('w:color'), 'auto')
        tblBorders.append(el)
    tblPr.append(tblBorders)


def _add_paragraph(doc: Document, text: str, bold: bool = False, italic: bool = False):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = bold
    run.italic = italic
    run.font.name = OFFER_FONT
    return p


def _set_cell_text(cell, text: str, bold: bool = False, align_right: bool = False, font_name: str = OFFER_FONT):
    """Set cell text with optional bold and right-alignment."""
    para = cell.paragraphs[0]
    para.clear()
    run = para.add_run(text)
    run.bold = bold
    run.font.name = font_name
    if align_right:
        para.alignment = WD_ALIGN_PARAGRAPH.RIGHT


def _fmt_eur(value: float) -> str:
    """Format a Euro total as e.g. '8 000€' — no decimals, space as thousands separator."""
    return f"{int(round(value)):,}€".replace(",", "\u00a0")


def _add_cost_table(
    doc: Document,
    steps: list[CostStepGroup],
    grand_total: float,
    project_output: str = "",
    language: str = "en",
):
    """Add the cost estimation table without borders, matching the offer layout."""
    is_fi = language == "fi"
    step_label      = "Vaihe"     if is_fi else "Step"
    grand_total_lbl = "Yhteens\u00e4" if is_fi else "Grand Total"
    output_lbl      = "Tuotos"    if is_fi else "Output"
    col_headers = (
        ["Vaihe", "Tuntihinta [\u20ac/h]", "Tuntiarvio [h]", "Hinta-arvio [\u20ac]"]
        if is_fi else
        ["Step", "Hourly cost [\u20ac/h]", "Hours estimation [h]", "Cost estimation [\u20ac]"]
    )

    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    _clear_table_borders(table)

    # Header row
    hdr_cells = table.rows[0].cells
    for i, hdr in enumerate(col_headers):
        _set_cell_text(hdr_cells[i], hdr, bold=True, align_right=(i > 0))

    for grp_idx, step_group in enumerate(steps, 1):
        # Extract numeric part from step_id regardless of LLM format
        # (handles "STEP 1", "VAIHE 1", "Vaihe 1", "1", etc.)
        import re as _re
        _m = _re.search(r'\d+', step_group.step_id)
        step_num = _m.group() if _m else str(grp_idx)

        # Step-group header row — bold, shows totals
        main_row = table.add_row().cells
        _set_cell_text(main_row[0], f"{step_label} {step_num}: {step_group.name}", bold=True)
        _set_cell_text(main_row[1], "", bold=True, align_right=True)
        _set_cell_text(main_row[2], f"{step_group.total_hours:,.1f}", bold=True, align_right=True)
        _set_cell_text(main_row[3], _fmt_eur(step_group.total_cost), bold=True, align_right=True)

        # Sub-step rows
        for sub_idx, sub in enumerate(step_group.sub_steps, 1):
            sub_row = table.add_row().cells
            _set_cell_text(sub_row[0], f"  {step_num}.{sub_idx}  {sub.name}")
            _set_cell_text(sub_row[1], f"{int(round(sub.hourly_rate))}", align_right=True)
            _set_cell_text(sub_row[2], f"{sub.hours * sub.persons:,.1f}", align_right=True)
            _set_cell_text(sub_row[3], f"{sub.total:,.2f}\u20ac", align_right=True)

    # Grand total row
    total_hours = sum(sg.total_hours for sg in steps)
    total_row = table.add_row().cells
    _set_cell_text(total_row[0], f"{grand_total_lbl}:", bold=True)
    if project_output:
        total_row[0].add_paragraph(f"{output_lbl}: {project_output}")
    _set_cell_text(total_row[1], "", bold=True, align_right=True)
    _set_cell_text(total_row[2], f"{total_hours:,.1f} h", bold=True, align_right=True)
    _set_cell_text(total_row[3], _fmt_eur(grand_total), bold=True, align_right=True)


def _setup_header_footer(doc: Document, language: str, logo_path: Path | None = None) -> None:
    """Add Confidential header and company name footer to every page."""
    confidential = "Luottamuksellinen" if language == "fi" else "Confidential"

    for sec in doc.sections:
        sec.different_first_page_header = True

        # ── First page header: Confidential (left) + logo (right) ─────────────
        # Clear all existing content from the first-page header element so
        # template leftovers don't interfere.
        fp_header = sec.first_page_header
        hdr_el = fp_header._element
        for child in list(hdr_el):
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag in ("p", "tbl"):
                hdr_el.remove(child)

        # A 2-column borderless table is the reliable way to place content on
        # the left and right of the same header line.
        tbl = fp_header.add_table(rows=1, cols=2, width=Cm(15.5))
        _clear_table_borders(tbl)

        left_cell = tbl.rows[0].cells[0]
        lp = left_cell.paragraphs[0]
        run_l = lp.add_run(confidential)
        run_l.font.name = OFFER_FONT

        right_cell = tbl.rows[0].cells[1]
        rp = right_cell.paragraphs[0]
        rp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        if logo_path and logo_path.exists():
            rp.add_run().add_picture(str(logo_path), width=Cm(4))
        elif logo_path:
            import warnings
            warnings.warn(f"Logo file not found: {logo_path}", stacklevel=2)

        # OOXML requires every header/footer to end with a <w:p> element.
        # Without it Word silently drops the entire header content.
        fp_header._element.append(OxmlElement('w:p'))

        # ── Default header (pages 2+): Confidential (left) ────────────────────
        hp = sec.header.paragraphs[0]
        hp.clear()
        run_h = hp.add_run(confidential)
        run_h.font.name = OFFER_FONT

        # ── First page footer: 4-column company info block ────────────────────
        fp_footer = sec.first_page_footer
        fp_ftr_el = fp_footer._element
        for child in list(fp_ftr_el):
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag in ("p", "tbl"):
                fp_ftr_el.remove(child)

        # Spacer paragraph to separate footer table from document body
        spacer = fp_footer.add_paragraph()
        spacer.paragraph_format.space_before = Pt(0)
        spacer.paragraph_format.space_after = Pt(8)

        ftbl = fp_footer.add_table(rows=1, cols=4, width=Cm(15.5))
        _clear_table_borders(ftbl)

        col1_lines = [("Link Design Oy", True)]
        col2_lines = [("Espoon toimipiste", True), ("Innopoli 1", False),
                      ("Tekniikantie 12", False), ("02150", False), ("Espoo", False)]
        col3_lines = [("Salon toimipiste", True), ("Salo IoT Campus", False),
                      ("Joensuunkatu 7", False), ("24100", False), ("Salo", False)]
        col4_lines = [("+358 40 8399 313", False), ("info@linkdesign.fi", False),
                      ("VAT: FI2251285-9", False), ("linkdesign.fi", False)]

        for col_idx, lines in enumerate([col1_lines, col2_lines, col3_lines, col4_lines]):
            cell = ftbl.rows[0].cells[col_idx]
            for line_idx, (text, bold) in enumerate(lines):
                if line_idx == 0:
                    para = cell.paragraphs[0]
                else:
                    para = cell.add_paragraph()
                # Remove paragraph spacing so lines sit tight together
                para.paragraph_format.space_before = Pt(0)
                para.paragraph_format.space_after = Pt(0)
                para.paragraph_format.line_spacing = Pt(11)
                run_c = para.add_run(text)
                run_c.bold = bold
                run_c.font.name = OFFER_FONT
                run_c.font.size = Pt(9)

        fp_footer._element.append(OxmlElement('w:p'))

        # ── Default footer (pages 2+): bold company name (left) ───────────────
        pf = sec.footer.paragraphs[0]
        pf.clear()
        run_f = pf.add_run("Link Design Oy")
        run_f.bold = True
        run_f.font.name = OFFER_FONT


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

    _set_default_font(doc, OFFER_FONT)
    _setup_header_footer(doc, language, TEMPLATES_DIR / "LINK_LOGO.png")
    _raw_date = _parse_project_date(project.document_date)
    doc_date = f"{_raw_date.day}.{_raw_date.month}.{_raw_date.year}"

    # ── Header block ─────────────────────────────────────────────────────────
    _add_paragraph(doc, doc_date)
    _add_paragraph(doc, project.customer_name)
    _add_paragraph(doc, project.company_name)
    _add_paragraph(doc, project.address)
    _add_paragraph(doc, project.postal_code)
    doc.add_paragraph()

    # ── OFFER heading ─────────────────────────────────────────────────────────
    offer_heading = doc.add_paragraph()
    offer_run = offer_heading.add_run("OFFER")
    offer_run.bold = True
    offer_run.font.size = Pt(28)
    offer_run.font.name = OFFER_FONT
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
    steps = s2.get("steps", [])
    if steps:
        _add_cost_table(doc, steps, s2.get("grand_total", 0.0), s2.get("project_output", ""), language)
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
    if sections.get("section9_payment"):
        _add_paragraph(doc, sections["section9_payment"])
    doc.add_paragraph()

    # ── Section 10 — Payment Terms ────────────────────────────────────────────
    _add_heading(doc, "10. Payment Terms", 1)
    _doc_date = _parse_project_date(project.document_date)
    _dl = _doc_date + timedelta(weeks=2)
    _deadline = f"{_dl.day}.{_dl.month}.{_dl.year}"
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
    _add_heading(doc, "11. Contact Information", 1)
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
    _add_heading(doc, "12. Attachments", 1)
    att_prefix = "Liite" if language == "fi" else "Appendix"
    attachments = [
        f"{att_prefix} 1. General terms and conditions",
        f"{att_prefix} 2. Consulting service contract terms",
        f"{att_prefix} 3. Constraints",
        f"{att_prefix} 4. Cost estimate calculations",
    ]
    experts = s8.get("experts", [])
    expert_names = [e.get("name", "") for e in experts]
    if expert_names:
        attachments.append(f"{att_prefix} 5. Expert CVs: {', '.join(expert_names)}")
    else:
        attachments.append(f"{att_prefix} 5. Expert CVs")

    for att in attachments:
        doc.add_paragraph(att, style="List Number")

    # ── Save ──────────────────────────────────────────────────────────────────
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_project = (project.project_name or "offer").replace(" ", "_").replace("/", "-")[:40]
    out_path = OUTPUTS_DIR / f"offer_{safe_project}_{doc_date}.docx"
    doc.save(str(out_path))
    return out_path
