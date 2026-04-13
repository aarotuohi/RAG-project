"""
Excel cost estimation parser.

Supports the Finnish laskentapohja format:
  Header metadata rows (Tarjous nro, Nimi, Asiakas, …)
  Phase section header:  Vaihe X. <name> | Hlö | h/hlö | Tuntihinta | Alennus | Tuntihinta [€/h] | Tuntiarvio [h] | Hinta-arvio [€]
  Step data rows:        <num> | <name> | <persons> | <h/person> | <base_rate> | <discount> | <eff_rate> | <total_h> | <price>

Returns a list of CostStep records and the project grand total.
"""
from __future__ import annotations
import re
from pathlib import Path
from dataclasses import dataclass, field
import openpyxl
import pandas as pd

from backend.config import WORK_CATEGORIES

# Finnish metadata row labels → English keys
_META_LABEL_MAP = {
    "tarjous nro": "offer_number",
    "nimi":        "project_name",
    "asiakas":     "customer",
    "myyntivastuu":"salesperson",
    "päiväys":     "date",
    "kuvaus":      "description",
    "henkilöt":    "team",
}

# Finnish column header names (lower-cased) → semantic key
_COL_HEADER_MAP = {
    "hlö":               "persons",
    "h/hlö":             "hours_per_person",
    "tuntihinta [€/h]":  "rate",
    "tuntiarvio [h]":    "total_hours",
    "hinta-arvio [€]":   "price",
    # Description / notes columns (Finnish + English variants)
    "kuvaus":            "description",
    "selite":            "description",
    "tehtävä":           "description",
    "tehtäväkuvaus":     "description",
    "lisätieto":         "description",
    "notes":             "description",
    "description":       "description",
}

# Rows whose first cell matches these patterns are not data rows
_SKIP_PATTERNS = re.compile(
    r"^(arvioidut|yhteensä|total|grand|vaihe\s*\d+|phase)",
    re.IGNORECASE,
)


@dataclass
class CostStep:
    step_id: str          # e.g. "Vaihe 1 / 1.0"
    name: str
    category: str         # one of WORK_CATEGORIES
    hourly_rate: float    # effective hourly rate after discount
    hours: float          # total estimated hours
    persons: int = 1
    description: str = ""  # optional notes/description text from Excel
    total: float = field(init=False)

    def __post_init__(self):
        """Calculate the total cost from hourly_rate × hours × persons."""
        self.total = round(self.hourly_rate * self.hours * self.persons, 2)


@dataclass
class CostSubStep:
    name: str
    category: str
    hourly_rate: float
    hours: float          # hours per person
    persons: int = 1
    total: float = field(init=False)

    def __post_init__(self):
        self.total = round(self.hourly_rate * self.hours * self.persons, 2)


@dataclass
class CostStepGroup:
    step_id: str          # e.g. "STEP 1"
    name: str
    output: str           # deliverable / goal of this step
    sub_steps: list["CostSubStep"] = field(default_factory=list)
    total_hours: float = field(init=False)
    total_cost: float = field(init=False)

    def __post_init__(self):
        self.total_hours = round(sum(s.hours * s.persons for s in self.sub_steps), 2)
        self.total_cost = round(sum(s.total for s in self.sub_steps), 2)


def _infer_category(text: str) -> str:
    text_lower = text.lower()
    for cat in WORK_CATEGORIES:
        if cat.lower() in text_lower:
            return cat
    return "Service development"


def _safe_float(val) -> float:
    """Convert a cell value to float, handling European decimal commas,
    whitespace, currency symbols (€) and unit suffixes (h)."""
    try:
        cleaned = (
            str(val)
            .replace(",", ".")
            .replace(" ", "")
            .replace("€", "")
            .replace("h", "")
            .strip()
        )
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def _safe_int(val) -> int:
    """Convert a cell value to a positive integer. Returns 1 on failure."""
    try:
        return max(1, int(float(str(val).replace(",", "."))))
    except (ValueError, TypeError):
        return 1


def _detect_col_indices(row_vals: list[str]) -> dict[str, int]:
    """
    Given the raw string values of a phase-header row, return a mapping of
    semantic key → column index.  Unrecognised headers are ignored.
    """
    mapping: dict[str, int] = {}
    for idx, cell in enumerate(row_vals):
        key = _COL_HEADER_MAP.get(cell.lower().strip())
        if key:
            mapping[key] = idx
    return mapping


def parse_excel_metadata(file_path: Path) -> dict[str, str]:
    """
    Extract the offer header metadata (offer number, project name, customer …)
    from the top rows of the first sheet.

    Handles two common layouts:
      Layout A (label in col 0):  'Tarjous nro' | '3456' | ...
      Layout B (label in col 1):  None | 'Tarjous nro' | '3456' | ...
    """
    xl = pd.ExcelFile(str(file_path))
    df = xl.parse(xl.sheet_names[0], header=None).fillna("")
    meta: dict[str, str] = {}
    for _, row in df.iterrows():
        vals = [str(v).strip() for v in row.values]
        if not vals:
            continue
        # Stop at the first phase-header row (any column may contain it)
        if any(re.match(r"vaihe\s*\d+", v, re.IGNORECASE) for v in vals):
            break
        # Try label in col 0 (value in col 1), then label in col 1 (value in col 2)
        for label_idx, value_idx in ((0, 1), (1, 2)):
            label = vals[label_idx].lower() if len(vals) > label_idx else ""
            eng_key = _META_LABEL_MAP.get(label)
            if eng_key and len(vals) > value_idx:
                value = vals[value_idx]
                if value not in ("", "nan"):
                    meta[eng_key] = value
                    break
    return meta


def _latest_rev_sheet(sheet_names: list[str]) -> str | None:
    """
    If any sheets are named like revA / RevB / REV_C / rev1 etc., return the
    name of the alphabetically-last one (highest revision).  Returns None when
    no rev-style sheets are present so the caller falls back to all sheets.
    """
    rev_sheets = [s for s in sheet_names if re.match(r"^rev", s.strip(), re.IGNORECASE)]
    if not rev_sheets:
        return None
    # Sort by the suffix after the leading "rev" (case-insensitive) so that
    # revA < revB < revC regardless of mixed capitalisation.
    rev_sheets.sort(key=lambda s: re.sub(r"^rev", "", s, flags=re.IGNORECASE).lower())
    return rev_sheets[-1]


def parse_excel(file_path: Path) -> dict[str, list[CostStep]]:
    """
    Parse an Excel file and return {sheet_name: [CostStep, ...]}.

    When the workbook contains revision sheets (revA, revB, revC …) only the
    latest revision (alphabetically last suffix) is parsed.  This prevents
    outdated cost data from earlier revisions being ingested alongside the
    current one.
    """
    result: dict[str, list[CostStep]] = {}
    xl = pd.ExcelFile(str(file_path))

    latest_rev = _latest_rev_sheet(xl.sheet_names)
    sheets_to_parse = [latest_rev] if latest_rev else xl.sheet_names

    for sheet_name in sheets_to_parse:
        df = xl.parse(sheet_name, header=None).fillna("")
        steps: list[CostStep] = []

        current_phase = ""
        col_map: dict[str, int] = {}   # semantic key → column index

        for _, row in df.iterrows():
            row_vals = [str(v).strip() for v in row.values]
            first = row_vals[0] if row_vals else ""

            # ── Phase section header row ──────────────────────────────────────
            # Scan all columns — merged cells may push the label past column 0
            phase_cell = next(
                (v for v in row_vals if re.match(r"vaihe\s*\d+", v, re.IGNORECASE)),
                None,
            )
            if phase_cell and not re.match(r"^\d+\.?\d*$", first):
                current_phase = phase_cell
                col_map = _detect_col_indices(row_vals)
                continue

            # ── Skip non-data rows (totals, summaries, empty, metadata) ───────
            if not first or first.lower() == "nan" or _SKIP_PATTERNS.match(first):
                continue

            # ── Step data row: first cell must be a number (e.g. "1.0", "2") ──
            if not re.match(r"^\d+\.?\d*$", first):
                continue

            name = row_vals[1].strip() if len(row_vals) > 1 else first
            if not name or name == "nan":
                continue

            # Skip summary rows disguised as numbered steps (e.g. "Vaihe 1: Työpaja")
            if re.match(r"vaihe|yhteensä", name, re.IGNORECASE):
                continue

            # Resolve values by detected column positions when available,
            # otherwise fall back to fixed positional indices.
            def _get(key: str, fallback_idx: int) -> str:
                idx = col_map.get(key, fallback_idx)
                return row_vals[idx] if idx < len(row_vals) else "0"

            persons      = _safe_int(_get("persons", 2))
            hours_pp     = _safe_float(_get("hours_per_person", 3))
            eff_rate     = _safe_float(_get("rate", 6))
            total_hours  = _safe_float(_get("total_hours", 7))

            # Prefer the explicit total_hours cell; recompute if zero/missing
            hours = total_hours if total_hours > 0 else hours_pp
            # If persons is already baked into total_hours, set persons=1
            if total_hours > 0 and persons > 1:
                hours   = hours_pp   # keep per-person hours
            else:
                persons = max(persons, 1)

            category = _infer_category(f"{current_phase} {name}")

            # Description column (optional — not present in all templates)
            desc_idx = col_map.get("description")
            description = (
                row_vals[desc_idx].strip()
                if desc_idx is not None and desc_idx < len(row_vals)
                else ""
            )
            if description.lower() in ("nan", "0", "-"):
                description = ""

            steps.append(CostStep(
                step_id=f"{current_phase} / {first}" if current_phase else f"Step {first}",
                name=name,
                category=category,
                hourly_rate=eff_rate,
                hours=hours,
                persons=persons,
                description=description,
            ))

        if steps:
            result[sheet_name] = steps

    return result


def grand_total(steps: list[CostStep]) -> float:
    """Sum the total cost of all steps and round to 2 decimal places."""
    return round(sum(s.total for s in steps), 2)


def steps_to_text(steps: list[CostStep], project_name: str = "", metadata: dict | None = None) -> str:
    """Serialize a list of CostSteps into a plain-text block suitable for
    embedding into ChromaDB.  Metadata (offer number, customer, date …) is
    prepended when provided so that retrieval can match on project context.
    """
    lines: list[str] = []

    # Prepend offer metadata for richer retrieval
    if metadata:
        if metadata.get("offer_number"):  lines.append(f"Offer number: {metadata['offer_number']}")
        if metadata.get("project_name"): lines.append(f"Project: {metadata['project_name']}")
        if metadata.get("customer"):     lines.append(f"Customer: {metadata['customer']}")
        if metadata.get("salesperson"):  lines.append(f"Salesperson: {metadata['salesperson']}")
        if metadata.get("date"):         lines.append(f"Date: {metadata['date']}")
        if metadata.get("description"):  lines.append(f"Description: {metadata['description']}")
    elif project_name:
        lines.append(f"Project: {project_name}")

    for s in steps:
        desc_part = f" | Notes: {s.description}" if s.description else ""
        lines.append(
            f"{s.step_id}: {s.name}{desc_part} | Category: {s.category} | "
            f"Rate: {s.hourly_rate}€/h | Hours: {s.hours}h | "
            f"Persons: {s.persons} | Total: {s.total}€"
        )
    lines.append(f"Grand Total: {grand_total(steps)}€")
    return "\n".join(lines)


def steps_by_phase(steps: list[CostStep]) -> "dict[str, list[CostStep]]":
    """
    Group steps by their phase prefix (the part before ' / ' in step_id).
    Returns an OrderedDict that preserves the original phase order.

    Example:
        "Vaihe 1 / 1.0"  →  phase key "Vaihe 1"
        "Vaihe 2 / 3.0"  →  phase key "Vaihe 2"
        "Step 1"         →  phase key "Steps"  (no ' / ' separator)
    """
    from collections import OrderedDict
    phases: "OrderedDict[str, list[CostStep]]" = OrderedDict()
    for s in steps:
        phase = s.step_id.split(" / ")[0].strip() if " / " in s.step_id else "Steps"
        phases.setdefault(phase, []).append(s)
    return phases
