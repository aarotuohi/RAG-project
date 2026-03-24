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
    """Guess the work category for a step. Falls back to 'Services'."""
    text_lower = text.lower()
    for cat in WORK_CATEGORIES:
        if cat.lower() in text_lower:
            return cat
    return "Services"


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
    """
    xl = pd.ExcelFile(str(file_path))
    df = xl.parse(xl.sheet_names[0], header=None).fillna("")
    meta: dict[str, str] = {}
    for _, row in df.iterrows():
        vals = [str(v).strip() for v in row.values]
        first = vals[0].lower() if vals else ""
        # Stop at the first phase-header row
        if re.match(r"vaihe\s*\d+", vals[0], re.IGNORECASE):
            break
        eng_key = _META_LABEL_MAP.get(first)
        if eng_key and len(vals) > 1 and vals[1] not in ("", "nan"):
            meta[eng_key] = vals[1]
    return meta


def parse_excel(file_path: Path) -> dict[str, list[CostStep]]:
    """
    Parse all sheets in an Excel file.
    Returns {sheet_name: [CostStep, ...]}
    """
    result: dict[str, list[CostStep]] = {}
    xl = pd.ExcelFile(str(file_path))

    for sheet_name in xl.sheet_names:
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

            steps.append(CostStep(
                step_id=f"{current_phase} / {first}" if current_phase else f"Step {first}",
                name=name,
                category=category,
                hourly_rate=eff_rate,
                hours=hours,
                persons=persons,
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
        lines.append(
            f"{s.step_id}: {s.name} | Category: {s.category} | "
            f"Rate: {s.hourly_rate}€/h | Hours: {s.hours}h | "
            f"Persons: {s.persons} | Total: {s.total}€"
        )
    lines.append(f"Grand Total: {grand_total(steps)}€")
    return "\n".join(lines)
