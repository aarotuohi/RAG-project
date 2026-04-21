"""
Tests for backend.ingestion.excel_parser — pure utility functions and dataclasses.
"""
import pytest
from collections import OrderedDict
from backend.ingestion.excel_parser import (
    CostStep,
    CostSubStep,
    CostStepGroup,
    _safe_float,
    _safe_int,
    _infer_category,
    _detect_col_indices,
    _latest_rev_sheet,
    grand_total,
    steps_to_text,
    steps_by_phase,
)


# ── _safe_float ───────────────────────────────────────────────────────────────

class TestSafeFloat:
    def test_integer(self):
        assert _safe_float(100) == 100.0

    def test_float(self):
        assert _safe_float(99.5) == 99.5

    def test_european_decimal(self):
        assert _safe_float("99,5") == 99.5

    def test_euro_symbol(self):
        assert _safe_float("150€") == 150.0

    def test_hour_suffix(self):
        assert _safe_float("8h") == 8.0

    def test_whitespace(self):
        assert _safe_float(" 1 000 ") == 1000.0

    def test_combined(self):
        assert _safe_float("1 500,50€") == 1500.50

    def test_garbage(self):
        assert _safe_float("abc") == 0.0

    def test_none(self):
        assert _safe_float(None) == 0.0

    def test_empty_string(self):
        assert _safe_float("") == 0.0


# ── _safe_int ─────────────────────────────────────────────────────────────────

class TestSafeInt:
    def test_positive_int(self):
        assert _safe_int(3) == 3

    def test_float_rounds_down(self):
        assert _safe_int(2.7) == 2

    def test_string(self):
        assert _safe_int("5") == 5

    def test_zero_becomes_one(self):
        assert _safe_int(0) == 1

    def test_negative_becomes_one(self):
        assert _safe_int(-3) == 1

    def test_garbage(self):
        assert _safe_int("abc") == 1

    def test_european_decimal(self):
        assert _safe_int("3,0") == 3


# ── _infer_category ──────────────────────────────────────────────────────────

class TestInferCategory:
    def test_software(self):
        assert _infer_category("Software development task") == "Software development"

    def test_default(self):
        assert _infer_category("Random task with no keywords") == "Service development"

    def test_case_insensitive(self):
        assert _infer_category("ELECTRONICS DESIGN") in ("Electronics", "Electronics design")


# ── _detect_col_indices ──────────────────────────────────────────────────────

class TestDetectColIndices:
    def test_standard_headers(self):
        row = ["", "Hlö", "h/hlö", "Tuntihinta [€/h]", "Tuntiarvio [h]", "Hinta-arvio [€]"]
        mapping = _detect_col_indices(row)
        assert mapping["persons"] == 1
        assert mapping["hours_per_person"] == 2
        assert mapping["rate"] == 3
        assert mapping["total_hours"] == 4
        assert mapping["price"] == 5

    def test_unknown_headers_ignored(self):
        row = ["Step", "Unknown", "More unknown"]
        mapping = _detect_col_indices(row)
        assert len(mapping) == 0

    def test_empty_row(self):
        assert _detect_col_indices([]) == {}


# ── _latest_rev_sheet ────────────────────────────────────────────────────────

class TestLatestRevSheet:
    def test_multiple_revisions(self):
        assert _latest_rev_sheet(["revA", "revB", "revC"]) == "revC"

    def test_mixed_case(self):
        assert _latest_rev_sheet(["RevA", "REVB", "revC"]) == "revC"

    def test_no_rev_sheets(self):
        assert _latest_rev_sheet(["Sheet1", "Data"]) is None

    def test_single_rev(self):
        assert _latest_rev_sheet(["revA", "Sheet1"]) == "revA"

    def test_rev_with_numbers(self):
        result = _latest_rev_sheet(["rev1", "rev2", "rev3"])
        assert result == "rev3"


# ── CostStep dataclass ──────────────────────────────────────────────────────

class TestCostStep:
    def test_total_calculation(self):
        step = CostStep(step_id="V1/1", name="Dev", category="Software development",
                        hourly_rate=100.0, hours=10.0, persons=2)
        assert step.total == 2000.0

    def test_single_person(self):
        step = CostStep(step_id="V1/1", name="Dev", category="Software development",
                        hourly_rate=80.0, hours=5.0)
        assert step.total == 400.0

    def test_zero_hours(self):
        step = CostStep(step_id="V1/1", name="Dev", category="Software development",
                        hourly_rate=100.0, hours=0.0)
        assert step.total == 0.0


# ── CostStepGroup dataclass ─────────────────────────────────────────────────

class TestCostStepGroup:
    def test_totals_from_substeps(self):
        subs = [
            CostSubStep(name="Task A", category="Software development", hourly_rate=100, hours=10, persons=1),
            CostSubStep(name="Task B", category="Software development", hourly_rate=80, hours=5, persons=2),
        ]
        group = CostStepGroup(step_id="STEP 1", name="Phase 1", output="Deliverable", sub_steps=subs)
        assert group.total_hours == 20.0  # 10*1 + 5*2
        assert group.total_cost == 1800.0  # 1000 + 800

    def test_empty_substeps(self):
        group = CostStepGroup(step_id="STEP 1", name="Empty", output="", sub_steps=[])
        assert group.total_hours == 0.0
        assert group.total_cost == 0.0


# ── grand_total ──────────────────────────────────────────────────────────────

class TestGrandTotal:
    def test_sum(self):
        steps = [
            CostStep(step_id="1", name="A", category="Software development", hourly_rate=100, hours=10),
            CostStep(step_id="2", name="B", category="Software development", hourly_rate=50, hours=20),
        ]
        assert grand_total(steps) == 2000.0  # 1000 + 1000

    def test_empty(self):
        assert grand_total([]) == 0.0


# ── steps_to_text ────────────────────────────────────────────────────────────

class TestStepsToText:
    def test_basic_output(self):
        steps = [
            CostStep(step_id="V1/1", name="Dev", category="Software development",
                     hourly_rate=100, hours=10),
        ]
        text = steps_to_text(steps, project_name="Test Project")
        assert "Project: Test Project" in text
        assert "Dev" in text
        assert "Grand Total:" in text

    def test_with_metadata(self):
        steps = [
            CostStep(step_id="V1/1", name="Dev", category="Software development",
                     hourly_rate=100, hours=10),
        ]
        meta = {"offer_number": "123", "customer": "Acme"}
        text = steps_to_text(steps, metadata=meta)
        assert "Offer number: 123" in text
        assert "Customer: Acme" in text


# ── steps_by_phase ───────────────────────────────────────────────────────────

class TestStepsByPhase:
    def test_grouping(self):
        steps = [
            CostStep(step_id="Vaihe 1 / 1.0", name="A", category="Software development", hourly_rate=100, hours=10),
            CostStep(step_id="Vaihe 1 / 2.0", name="B", category="Software development", hourly_rate=100, hours=5),
            CostStep(step_id="Vaihe 2 / 1.0", name="C", category="Software development", hourly_rate=80, hours=8),
        ]
        phases = steps_by_phase(steps)
        assert "Vaihe 1" in phases
        assert "Vaihe 2" in phases
        assert len(phases["Vaihe 1"]) == 2
        assert len(phases["Vaihe 2"]) == 1

    def test_no_separator(self):
        steps = [
            CostStep(step_id="Step 1", name="A", category="Software development", hourly_rate=100, hours=10),
        ]
        phases = steps_by_phase(steps)
        assert "Steps" in phases
