"""
Tests for backend.generator.excel_builder — customer label formatting.
"""
import pytest
from backend.chains.extraction_chain import ProjectData
from backend.generator.excel_builder import _customer_label


class TestCustomerLabel:
    def test_company_and_name(self):
        p = ProjectData(first_name="John", last_name="Doe", company_name="Acme Oy")
        assert _customer_label(p) == "Acme Oy / John Doe"

    def test_company_only(self):
        p = ProjectData(company_name="Acme Oy")
        assert _customer_label(p) == "Acme Oy"

    def test_name_only(self):
        p = ProjectData(first_name="Jane", last_name="Smith")
        assert _customer_label(p) == "Jane Smith"

    def test_first_name_only(self):
        p = ProjectData(first_name="Jane", company_name="TestCo")
        assert _customer_label(p) == "TestCo / Jane"

    def test_all_empty(self):
        p = ProjectData()
        assert _customer_label(p) == ""
