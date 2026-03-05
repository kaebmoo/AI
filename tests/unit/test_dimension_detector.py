"""Tests for dimension family auto-detection engine."""

import pytest
from app.services.dimension_detector import detect_families


class TestDetectFamilies:
    """Tests for detect_families()."""

    def test_empty_input(self):
        assert detect_families([]) == {}

    def test_singleton_excluded(self):
        """Single column with no relatives should not form a family."""
        result = detect_families(["DIVISION"])
        assert result == {}

    def test_section_family(self):
        """SECTION + SECTION_ABBR should form org_section family."""
        result = detect_families(["SECTION", "SECTION_ABBR"])
        assert "org_section" in result
        assert set(result["org_section"]) == {"SECTION", "SECTION_ABBR"}

    def test_gl_family(self):
        """GL_CODE + GL_NAME + GL_GROUP should form acct_gl family."""
        result = detect_families(["GL_CODE", "GL_NAME", "GL_GROUP"])
        assert "acct_gl" in result
        assert set(result["acct_gl"]) == {"GL_CODE", "GL_NAME", "GL_GROUP"}

    def test_product_family(self):
        """PRODUCT + PRODUCT_KEY + PRODUCT_NAME should form product family."""
        result = detect_families(["PRODUCT", "PRODUCT_KEY", "PRODUCT_NAME"])
        assert "product" in result
        assert set(result["product"]) == {"PRODUCT", "PRODUCT_KEY", "PRODUCT_NAME"}

    def test_time_family(self):
        """YEAR + MONTH + DATE should form time family."""
        result = detect_families(["YEAR", "MONTH", "DATE"])
        assert "time" in result
        assert set(result["time"]) == {"YEAR", "MONTH", "DATE"}

    def test_time_needs_two_members(self):
        """Single time column should not form a family."""
        result = detect_families(["YEAR", "DIVISION", "SECTION"])
        assert "time" not in result

    def test_thai_special_columns(self):
        """Thai columns get their own family names but need 2+ members."""
        # Single Thai column → no family (needs 2+)
        result = detect_families(["กลุ่มธุรกิจ"])
        assert result == {}

    def test_multiple_families(self):
        """Multiple families detected simultaneously."""
        cols = [
            "SECTION", "SECTION_ABBR",
            "GL_CODE", "GL_NAME",
            "YEAR", "MONTH", "DATE",
        ]
        result = detect_families(cols)
        assert "org_section" in result
        assert "acct_gl" in result
        assert "time" in result
        assert len(result) == 3

    def test_case_insensitive_grouping(self):
        """Case-insensitive stem matching."""
        result = detect_families(["Section", "SECTION_ABBR"])
        # Should still group together
        families_with_both = [
            g for g, cols in result.items()
            if "Section" in cols and "SECTION_ABBR" in cols
        ]
        assert len(families_with_both) == 1

    def test_original_case_preserved(self):
        """Output should preserve original column name casing."""
        result = detect_families(["Section", "SECTION_ABBR"])
        for cols in result.values():
            if "Section" in cols:
                assert "Section" in cols  # not "SECTION"

    def test_service_group_family(self):
        """SERVICE + SERVICE_GROUP should form product_service family."""
        result = detect_families(["SERVICE", "SERVICE_GROUP"])
        assert "product_service" in result

    def test_cost_center_family(self):
        """COST_CENTER + COST_CENTER_NAME should form org_cost_center."""
        result = detect_families(["COST_CENTER", "COST_CENTER_NAME"])
        assert "org_cost_center" in result

    def test_revenue_value_family(self):
        """REVENUE + REVENUE_VALUE should form value_revenue family."""
        result = detect_families(["REVENUE", "REVENUE_VALUE"])
        assert "value_revenue" in result

    def test_report_family(self):
        """REPORT + REPORT_CODE should form acct_report family."""
        result = detect_families(["REPORT", "REPORT_CODE"])
        assert "acct_report" in result

    def test_unknown_stem_uses_lowercase(self):
        """Unknown stems use lowercase stem as category."""
        result = detect_families(["WIDGET", "WIDGET_NAME", "WIDGET_CODE"])
        assert "widget" in result
        assert set(result["widget"]) == {"WIDGET", "WIDGET_NAME", "WIDGET_CODE"}

    def test_realistic_revenue_table(self):
        """Test with a realistic set of columns from revenue table."""
        cols = [
            "YEAR", "MONTH", "DATE",
            "DIVISION",
            "SECTION", "SECTION_ABBR",
            "COST_CENTER",
            "GL_CODE", "GL_NAME", "GL_GROUP",
            "PRODUCT", "PRODUCT_KEY", "PRODUCT_NAME",
            "REVENUE_VALUE", "AMOUNT",
            "กลุ่มธุรกิจ", "หมวดบัญชี",
        ]
        result = detect_families(cols)
        assert "time" in result
        assert "org_section" in result
        assert "acct_gl" in result
        assert "product" in result
        # DIVISION alone → no family (singleton)
        assert not any("DIVISION" in cols for g, cols in result.items() if g != "org_division")
