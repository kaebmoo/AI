"""
Plan 4: Chart Renderer Tests
==============================
Tests PNG chart generation from data.
"""

import pytest

try:
    import matplotlib
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

from app.telegram.chart_renderer import render_chart_to_png


class TestRenderBarChart:
    """Bar chart rendering."""

    @pytest.mark.skipif(not HAS_MATPLOTLIB, reason="matplotlib not installed")
    def test_bar_chart_returns_png(self):
        """Bar chart with valid data → non-empty PNG bytes."""
        data = [
            {"name": "A", "value": 100},
            {"name": "B", "value": 200},
            {"name": "C", "value": 150},
        ]
        result = render_chart_to_png(data, chart_type="bar", title="Test Bar")
        assert isinstance(result, bytes)
        assert len(result) > 100  # Not empty/trivial
        assert result[:4] == b"\x89PNG"  # PNG magic bytes


class TestRenderLineChart:
    """Line chart rendering."""

    @pytest.mark.skipif(not HAS_MATPLOTLIB, reason="matplotlib not installed")
    def test_line_chart_returns_png(self):
        """Line chart with valid data → PNG bytes."""
        data = [
            {"month": "Jan", "total": 100},
            {"month": "Feb", "total": 200},
            {"month": "Mar", "total": 180},
        ]
        result = render_chart_to_png(data, chart_type="line", title="Test Line")
        assert isinstance(result, bytes)
        assert len(result) > 100
        assert result[:4] == b"\x89PNG"


class TestRenderPieChart:
    """Pie chart rendering."""

    @pytest.mark.skipif(not HAS_MATPLOTLIB, reason="matplotlib not installed")
    def test_pie_chart_returns_png(self):
        """Pie chart with valid data → PNG bytes."""
        data = [
            {"category": "Mobile", "revenue": 500},
            {"category": "Fixed", "revenue": 300},
            {"category": "Other", "revenue": 200},
        ]
        result = render_chart_to_png(data, chart_type="pie", title="Test Pie")
        assert isinstance(result, bytes)
        assert len(result) > 100


class TestRenderEmptyData:
    """Edge cases: empty or invalid data."""

    def test_empty_data_returns_placeholder(self):
        """Empty data → placeholder PNG (not crash)."""
        result = render_chart_to_png([], chart_type="bar", title="Empty")
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_no_numeric_column_returns_placeholder(self):
        """Data with no numeric column → placeholder PNG."""
        data = [
            {"name": "A", "type": "B"},
            {"name": "C", "type": "D"},
        ]
        result = render_chart_to_png(data, chart_type="bar")
        assert isinstance(result, bytes)
        assert len(result) > 0
