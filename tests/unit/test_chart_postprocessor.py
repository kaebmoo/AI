"""
Wave 1 (C1-C2): Categorical Axis Rule tests
=============================================
Line/area-family charts must only survive when category_column is a time
dimension. See plan/PLAN_UI_CHART_IMPROVEMENT.md Wave 1.
"""

from app.providers.chart_postprocessor import (
    enforce_categorical_axis_rule,
    enforce_time_series_rule,
    _suggest_available_types,
    _is_time_column,
    resolve_max_series_warning,
    enrich_chart_config,
    DEFAULT_MAX_SERIES,
)

TIME_COLS = ["year", "month"]


class TestEnforceCategoricalAxisRule:
    def test_line_chart_over_account_category_downgrades_to_bar_with_warning(self):
        """(ก) หมวดบัญชี + line_chart -> bar_chart พร้อม warning"""
        parsed = {
            "visualization": "line_chart",
            "chart_config": {"category_column": "account_category", "measure_column": "amount"},
        }
        result = enforce_categorical_axis_rule(parsed, time_columns=TIME_COLS)
        assert result["visualization"] == "bar_chart"
        assert result["chart_config"]["warning"]

    def test_line_chart_over_month_category_passes_through(self):
        """(ข) รายเดือน + line_chart -> ผ่านไม่ถูกแก้"""
        parsed = {
            "visualization": "line_chart",
            "chart_config": {"category_column": "month", "measure_column": "amount"},
        }
        result = enforce_categorical_axis_rule(parsed, time_columns=TIME_COLS)
        assert result["visualization"] == "line_chart"
        assert "warning" not in result["chart_config"]

    def test_multi_line_over_dimension_x_category_downgrades_to_grouped_bar(self):
        """(ค) มิติ x หมวด + multi_line -> grouped_bar"""
        parsed = {
            "visualization": "multi_line",
            "chart_config": {
                "category_column": "department",
                "series_column": "account_category",
                "measure_column": "amount",
            },
        }
        result = enforce_categorical_axis_rule(parsed, time_columns=TIME_COLS)
        assert result["visualization"] == "grouped_bar"
        assert result["chart_config"]["warning"]

    def test_area_downgrades_to_bar_chart(self):
        parsed = {
            "visualization": "area",
            "chart_config": {"category_column": "department", "measure_column": "amount"},
        }
        result = enforce_categorical_axis_rule(parsed, time_columns=TIME_COLS)
        assert result["visualization"] == "bar_chart"

    def test_stacked_area_downgrades_to_stacked_bar(self):
        parsed = {
            "visualization": "stacked_area",
            "chart_config": {"category_column": "department", "series_column": "account_category"},
        }
        result = enforce_categorical_axis_rule(parsed, time_columns=TIME_COLS)
        assert result["visualization"] == "stacked_bar"

    def test_mixed_bar_line_no_longer_a_recognized_temporal_type(self):
        """Wave 2 L8 removed mixed_bar_line (no ChartConfig shape supports a
        bar/line-per-series split) — it's outside TEMPORAL_TYPES now, so the
        rule no-ops on it rather than downgrading."""
        parsed = {
            "visualization": "mixed_bar_line",
            "chart_config": {"category_column": "department", "series_column": "account_category"},
        }
        result = enforce_categorical_axis_rule(parsed, time_columns=TIME_COLS)
        assert result["visualization"] == "mixed_bar_line"

    def test_non_temporal_visualization_is_untouched(self):
        parsed = {
            "visualization": "bar_chart",
            "chart_config": {"category_column": "account_category", "measure_column": "amount"},
        }
        result = enforce_categorical_axis_rule(parsed, time_columns=TIME_COLS)
        assert result["visualization"] == "bar_chart"
        assert "warning" not in result["chart_config"]

    def test_missing_time_columns_falls_back_to_time_keys_heuristic(self):
        """schema_metadata unavailable -> TIME_KEYS keyword fallback still recognizes 'เดือน'."""
        parsed = {
            "visualization": "line_chart",
            "chart_config": {"category_column": "เดือน", "measure_column": "amount"},
        }
        result = enforce_categorical_axis_rule(parsed, time_columns=None)
        assert result["visualization"] == "line_chart"

    def test_missing_category_column_downgrades(self):
        parsed = {"visualization": "line_chart", "chart_config": {"measure_column": "amount"}}
        result = enforce_categorical_axis_rule(parsed, time_columns=TIME_COLS)
        assert result["visualization"] == "bar_chart"

    def test_sql_aliased_time_column_not_in_schema_metadata_still_recognized(self):
        """SQL `month AS "เดือน"` — schema_metadata only knows the raw 'month'
        column, but the result column is aliased. _is_time_column must fall
        back to TIME_KEYS so a genuinely time-based chart isn't wrongly
        downgraded (regression guard for the exact-match-only either/or bug)."""
        parsed = {
            "visualization": "line_chart",
            "chart_config": {"category_column": "เดือน", "measure_column": "amount"},
        }
        result = enforce_categorical_axis_rule(parsed, time_columns=TIME_COLS)
        assert result["visualization"] == "line_chart"
        assert "warning" not in result["chart_config"]

    def test_runs_after_time_series_swap_recognizes_swapped_category(self):
        """series=month (time), category=department (not time) -> time_series_rule swaps
        them first, so by the time the categorical axis rule runs, category IS time -> no downgrade."""
        parsed = {
            "visualization": "line_chart",
            "chart_config": {"category_column": "department", "series_column": "month"},
        }
        swapped = enforce_time_series_rule(parsed, time_columns=TIME_COLS)
        result = enforce_categorical_axis_rule(swapped, time_columns=TIME_COLS)
        assert result["chart_config"]["category_column"] == "month"
        assert result["visualization"] == "line_chart"


class TestIsTimeColumn:
    def test_union_not_either_or_alias_outside_time_columns_list_caught_by_heuristic(self):
        """time_columns=['month'] doesn't contain the alias 'เดือน', but TIME_KEYS does —
        union of both checks must still return True (not exact-match-only)."""
        assert _is_time_column("เดือน", time_columns=["month"]) is True

    def test_exact_match_in_time_columns_wins_even_without_keyword_hit(self):
        assert _is_time_column("period_id", time_columns=["period_id"]) is True

    def test_non_time_column_absent_from_both_returns_false(self):
        assert _is_time_column("account_category", time_columns=["month", "year"]) is False


class TestSuggestAvailableTypes:
    def test_excludes_line_family_without_time_axis(self):
        """(ง) available_types ไม่มี line เมื่อไม่มีแกนเวลา"""
        types = _suggest_available_types(n_categories=5, has_series=False, has_time_category=False)
        assert "line_chart" not in types
        assert "multi_line" not in types
        assert "area" not in types
        assert "stacked_area" not in types

    def test_excludes_line_family_without_time_axis_many_categories(self):
        types = _suggest_available_types(n_categories=12, has_series=False, has_time_category=False)
        assert "line_chart" not in types

    def test_excludes_line_family_with_series_but_no_time_axis(self):
        types = _suggest_available_types(n_categories=5, has_series=True, has_time_category=False)
        assert "line_chart" not in types
        assert "multi_line" not in types
        assert "area" not in types

    def test_keeps_line_family_with_time_axis(self):
        types = _suggest_available_types(n_categories=12, has_series=True, has_time_category=True)
        assert "line_chart" in types
        assert "multi_line" in types

    def test_matrix_untouched_by_time_axis_filter(self):
        types = _suggest_available_types(n_categories=5, has_series=True, has_time_category=False, is_matrix=True)
        assert types == ['heatmap', 'grouped_bar', 'stacked_bar', 'table']


def _rows(col, values):
    return [{col: v} for v in values]


class TestResolveMaxSeriesWarning:
    def test_pie_over_threshold_warns_with_top_n_and_total(self):
        data = _rows("account", [f"cat{i}" for i in range(7)])
        warning = resolve_max_series_warning(data, "account", "", "pie_chart", max_series=5)
        assert warning is not None
        assert "Top-4" in warning
        assert "7 กลุ่ม" in warning
        assert "อื่นๆ" in warning

    def test_pie_at_threshold_no_warning(self):
        data = _rows("account", [f"cat{i}" for i in range(5)])
        assert resolve_max_series_warning(data, "account", "", "pie_chart", max_series=5) is None

    def test_pie_under_threshold_no_warning(self):
        data = _rows("account", [f"cat{i}" for i in range(3)])
        assert resolve_max_series_warning(data, "account", "", "pie_chart", max_series=5) is None

    def test_donut_same_as_pie(self):
        data = _rows("account", [f"cat{i}" for i in range(7)])
        assert resolve_max_series_warning(data, "account", "", "donut_chart", max_series=5) is not None

    def test_multi_series_over_threshold_warns(self):
        data = [{"dept": f"dept{i}", "month": "ม.ค."} for i in range(16)]
        warning = resolve_max_series_warning(data, "month", "dept", "grouped_bar", max_series=5)
        assert warning is not None
        assert "Top-4" in warning
        assert "16 กลุ่ม" in warning

    def test_multi_series_under_threshold_no_warning(self):
        data = [{"dept": f"dept{i}", "month": "ม.ค."} for i in range(3)]
        assert resolve_max_series_warning(data, "month", "dept", "stacked_bar", max_series=5) is None

    def test_single_series_bar_never_warns(self):
        """No series_column and not pie/donut — nothing to bucket."""
        data = _rows("account", [f"cat{i}" for i in range(20)])
        assert resolve_max_series_warning(data, "account", "", "bar_chart", max_series=5) is None

    def test_top_n_is_max_series_minus_one(self):
        data = _rows("account", [f"cat{i}" for i in range(10)])
        warning = resolve_max_series_warning(data, "account", "", "pie_chart", max_series=3)
        assert "Top-2" in warning


class TestEnrichChartConfigMaxSeries:
    def _parsed(self, viz, cat_col="account", ser_col=""):
        cfg = {"category_column": cat_col, "measure_column": "amount"}
        if ser_col:
            cfg["series_column"] = ser_col
        return {"visualization": viz, "chart_config": cfg}

    def test_default_max_series_when_not_passed(self):
        data = _rows("account", ["a", "b"])
        result = enrich_chart_config(self._parsed("bar_chart"), data)
        assert result["chart_config"]["max_series"] == DEFAULT_MAX_SERIES

    def test_custom_max_series_passed_through(self):
        data = _rows("account", ["a", "b"])
        result = enrich_chart_config(self._parsed("bar_chart"), data, max_series=8)
        assert result["chart_config"]["max_series"] == 8

    def test_warning_set_when_series_exceeds_max(self):
        data = [{"dept": f"dept{i}", "account": "x"} for i in range(16)]
        parsed = self._parsed("grouped_bar", ser_col="dept")
        result = enrich_chart_config(parsed, data, max_series=5)
        assert "warning" in result["chart_config"]
        assert "16 กลุ่ม" in result["chart_config"]["warning"]

    def test_pie_series_unsupported_warning_takes_priority(self):
        """Pie chart with a series_column set is a config error (pie doesn't
        support series) — that warning must win even if category count also
        happens to exceed max_series."""
        data = _rows("account", [f"cat{i}" for i in range(16)])
        parsed = self._parsed("pie_chart", ser_col="region")
        result = enrich_chart_config(parsed, data, max_series=5)
        assert "ไม่รองรับ series column" in result["chart_config"]["warning"]

    def test_no_warning_under_threshold(self):
        data = _rows("account", ["a", "b", "c"])
        result = enrich_chart_config(self._parsed("bar_chart"), data, max_series=5)
        assert "warning" not in result["chart_config"]
