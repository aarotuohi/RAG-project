"""
Excel cost estimation parser.
Reads historical project Excels structured as:
  STEP X | Step Name | Hourly Rate [€/h] | Hours [h] | Persons | Price [€]
Returns a list of CostStep records and the project grand total.
"""
from __future__ import annotations
import re
from pathlib import Path
from dataclasses import dataclass, field
import openpyxl
import pandas as pd

from backend.config import WORK_CATEGORIES


@dataclass
class CostStep:
    step_id: str          # "STEP 1", "STEP 2", …
    name: str
    category: str         # one of WORK_CATEGORIES
    hourly_rate: float
    hours: float
    persons: int
    total: float = field(init=False)

    def __post_init__(self):
        # Always compute total programmatically — never trust the Excel cell value
        self.total = round(self.hourly_rate * self.hours * self.persons, 2)


def _infer_category(text: str) -> str:
    text_lower = text.lower()
    for cat in WORK_CATEGORIES:
        if cat.lower() in text_lower:
            return cat
    return "Services"  # default


def _safe_float(val) -> float:
    try:
        return float(str(val).replace(",", ".").replace(" ", "").replace("€", ""))
    except (ValueError, TypeError):
        return 0.0


def _safe_int(val) -> int:
    try:
        return max(1, int(float(str(val).replace(",", "."))))
    except (ValueError, TypeError):
        return 1


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

        for _, row in df.iterrows():
            row_vals = [str(v).strip() for v in row.values]
            # Look for a cell that matches "STEP X" pattern
            step_cell = next((v for v in row_vals if re.match(r"step\s*\d+", v, re.IGNORECASE)), None)
            if step_cell is None:
                continue

            # Try to extract the remaining columns positionally
            # Expected: step_id, name, category_or_name, rate, hours, persons
            non_empty = [v for v in row_vals if v not in ("", "nan")]
            if len(non_empty) < 4:
                continue

            step_id = step_cell
            name = non_empty[1] if len(non_empty) > 1 else step_id
            # Heuristic: last 3 numeric values are rate, hours, persons
            numerics = []
            for v in reversed(non_empty):
                try:
                    numerics.insert(0, _safe_float(v))
                    if len(numerics) == 3:
                        break
                except Exception:
                    pass

            if len(numerics) < 2:
                continue

            persons = _safe_int(numerics[2]) if len(numerics) >= 3 else 1
            hours   = numerics[1] if len(numerics) >= 2 else 0.0
            rate    = numerics[0] if len(numerics) >= 1 else 0.0
            category = _infer_category(name)

            steps.append(CostStep(
                step_id=step_id,
                name=name,
                category=category,
                hourly_rate=rate,
                hours=hours,
                persons=persons,
            ))

        if steps:
            result[sheet_name] = steps

    return result


def grand_total(steps: list[CostStep]) -> float:
    return round(sum(s.total for s in steps), 2)


def steps_to_text(steps: list[CostStep], project_name: str = "") -> str:
    """Convert steps to a readable text block for embedding into ChromaDB."""
    lines = [f"Project: {project_name}"] if project_name else []
    for s in steps:
        lines.append(
            f"{s.step_id}: {s.name} | Category: {s.category} | "
            f"Rate: {s.hourly_rate}€/h | Hours: {s.hours}h | "
            f"Persons: {s.persons} | Total: {s.total}€"
        )
    lines.append(f"Grand Total: {grand_total(steps)}€")
    return "\n".join(lines)
