"""
Excel cost table builder — produces a laskentapohja-formatted .xlsx file
from generated section 2 data and project metadata.

Column layout (matching laskentapohja.xlsx):
  A — step index (narrow)
  B — name / label (wide)
  C — hourly rate  "88.0€/h"
  D — hours        "10 h"
  E — price        (number)
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime

import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from backend.config import OUTPUTS_DIR
from backend.chains.extraction_chain import ProjectData
from backend.ingestion.excel_parser import CostStepGroup


# ── Style helpers ─────────────────────────────────────────────────────────────

_BOLD = Font(bold=True)
_NORMAL = Font(bold=False)
_PHASE_FILL = PatternFill("solid", fgColor="D9E1F2")   # light blue — phase header
_TOTAL_FILL = PatternFill("solid", fgColor="F2F2F2")   # light grey — subtotal rows
_SUMMARY_FILL = PatternFill("solid", fgColor="BDD7EE")  # medium blue — summary


def _thin_border(bottom_only: bool = False) -> Border:
    thin = Side(style="thin")
    if bottom_only:
        return Border(bottom=thin)
    return Border(top=thin, bottom=thin, left=thin, right=thin)


def _set_cell(ws, row: int, col: int, value, bold: bool = False,
              fill: PatternFill | None = None, number_format: str | None = None,
              wrap: bool = False, align: str = "left"):
    cell = ws.cell(row=row, column=col, value=value)
    cell.font = Font(bold=bold)
    cell.alignment = Alignment(horizontal=align, vertical="top", wrap_text=wrap)
    if fill:
        cell.fill = fill
    if number_format:
        cell.number_format = number_format
    return cell


def _parse_project_datetime(value: str) -> datetime:
    if not value:
        return datetime.today()
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass
    try:
        day, month, year = (int(part) for part in value.split("."))
        return datetime(year, month, day)
    except Exception:
        return datetime.today()


# ── Main builder ─────────────────────────────────────────────────────────────

def build_cost_excel(project: ProjectData, section2: dict) -> Path:
    """
    Build a laskentapohja-style Excel workbook from project info and section2
    cost data.  Saves to OUTPUTS_DIR and returns the file path.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Laskenta"

    # Column widths (matching the template)
    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 85
    ws.column_dimensions["C"].width = 18
    ws.column_dimensions["D"].width = 16
    ws.column_dimensions["E"].width = 18

    steps: list[CostStepGroup] = section2.get("steps", [])
    grand_total: float = section2.get("grand_total", 0.0)

    _d = _parse_project_datetime(project.document_date)
    _date_fi = f"{_d.day}.{_d.month}.{_d.year}"

    # ── Metadata header (rows 1-7) ────────────────────────────────────────────
    meta_rows = [
        ("Tarjous nro",   project.project_number or ""),
        ("Nimi",          project.project_name or ""),
        ("Asiakas",       _customer_label(project)),
        ("Myyntivastuu",  project.salesperson_name or ""),
        ("Päiväys",       _date_fi),
        ("Kuvaus",        project.goals or ""),
        ("Henkilöt",      project.required_expertise or ""),
    ]
    for i, (label, value) in enumerate(meta_rows, start=1):
        _set_cell(ws, i, 2, label, bold=True, align="right")
        _set_cell(ws, i, 3, value, wrap=True)

    current_row = len(meta_rows) + 2  # blank separator row

    # ── Phase blocks ──────────────────────────────────────────────────────────
    for phase_num, sg in enumerate(steps, start=1):
        phase_label = f"Vaihe {phase_num}. {sg.name}"

        # Phase header row
        _set_cell(ws, current_row, 2, phase_label, bold=True, fill=_PHASE_FILL)
        _set_cell(ws, current_row, 3, "Tuntihinta [€/h]", bold=True,
                  fill=_PHASE_FILL, align="right")
        _set_cell(ws, current_row, 4, "Tuntiarvio [h]",   bold=True,
                  fill=_PHASE_FILL, align="right")
        _set_cell(ws, current_row, 5, "Hinta-arvio [€]",  bold=True,
                  fill=_PHASE_FILL, align="right")
        current_row += 1

        # Sub-step rows
        for idx, ss in enumerate(sg.sub_steps, start=1):
            effective_hours = round(ss.hours * ss.persons, 1)
            persons_note = f" (×{ss.persons})" if ss.persons > 1 else ""
            _set_cell(ws, current_row, 1, idx, align="center")
            _set_cell(ws, current_row, 2, ss.name, wrap=True)
            _set_cell(ws, current_row, 3, f"{ss.hourly_rate:.0f}€/h", align="right")
            _set_cell(ws, current_row, 4, f"{effective_hours:.1f} h{persons_note}", align="right")
            _set_cell(ws, current_row, 5, round(ss.total, 2),
                      number_format='#,##0.00 "€"', align="right")
            current_row += 1

        # Phase subtotal row
        _set_cell(ws, current_row, 2, "Arvioidut työkustannukset yhteensä",
                  bold=True, fill=_TOTAL_FILL)
        _set_cell(ws, current_row, 4, f"{sg.total_hours:.1f} h",
                  bold=True, fill=_TOTAL_FILL, align="right")
        _set_cell(ws, current_row, 5, round(sg.total_cost, 2),
                  bold=True, fill=_TOTAL_FILL,
                  number_format='#,##0.00 "€"', align="right")
        current_row += 1

        # Output row
        if sg.output:
            _set_cell(ws, current_row, 2, f"Output: {sg.output}", wrap=True)
            current_row += 1

        current_row += 1  # blank row between phases

    # ── Summary section ───────────────────────────────────────────────────────
    _set_cell(ws, current_row, 2, "Yhteensä",        bold=True, fill=_SUMMARY_FILL)
    _set_cell(ws, current_row, 4, "Tuntiarvio [h]",  bold=True, fill=_SUMMARY_FILL, align="right")
    _set_cell(ws, current_row, 5, "Hinta-arvio [€]", bold=True, fill=_SUMMARY_FILL, align="right")
    current_row += 1

    for i, sg in enumerate(steps, start=1):
        _set_cell(ws, current_row, 1, i, align="center")
        _set_cell(ws, current_row, 2, f"Vaihe {i}: {sg.name}", wrap=True)
        _set_cell(ws, current_row, 4, f"{sg.total_hours:.1f} h", align="right")
        _set_cell(ws, current_row, 5, round(sg.total_cost, 2),
                  number_format='#,##0.00 "€"', align="right")
        current_row += 1

    # Grand total row
    total_hours = sum(sg.total_hours for sg in steps)
    _set_cell(ws, current_row, 4, f"{total_hours:.1f} h",
              bold=True, fill=_SUMMARY_FILL, align="right")
    _set_cell(ws, current_row, 5, round(grand_total, 2),
              bold=True, fill=_SUMMARY_FILL,
              number_format='#,##0.00 "€"', align="right")

    # ── Save ──────────────────────────────────────────────────────────────────
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    stem = (project.project_name or "offer").replace(" ", "_")[:40]
    out_path = OUTPUTS_DIR / f"{stem}_cost_table.xlsx"

    # Avoid overwriting
    counter = 1
    while out_path.exists():
        out_path = OUTPUTS_DIR / f"{stem}_cost_table_{counter}.xlsx"
        counter += 1

    wb.save(str(out_path))
    return out_path


def _customer_label(project: ProjectData) -> str:
    """Build a display name for the customer field."""
    parts = [p for p in [project.first_name, project.last_name] if p]
    name = " ".join(parts) if parts else ""
    if project.company_name:
        return f"{project.company_name}{(' / ' + name) if name else ''}"
    return name
