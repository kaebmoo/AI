"""P1 review fix: eval must not count different-column-name results as exact matches."""

from scripts.eval.run_eval import match_status


class TestMatchStatus:
    def test_same_values_same_columns_exact(self):
        assert match_status([{"total": 100.0}], [{"total": 100.0}]) == "exact_match"

    def test_same_values_different_column_names_is_value_match(self):
        # Previously counted as exact_match — now surfaced separately
        assert match_status([{"total": 100.0}], [{"amount": 100.0}]) == "value_match"

    def test_column_names_case_insensitive(self):
        assert match_status([{"TOTAL": 100.0}], [{"total": 100.0}]) == "exact_match"

    def test_different_values_mismatch(self):
        assert match_status([{"total": 100.0}], [{"total": 200.0}]) == "mismatch"

    def test_different_row_counts_mismatch(self):
        assert match_status([{"a": 1}], [{"a": 1}, {"a": 2}]) == "mismatch"

    def test_float_tolerance(self):
        assert match_status([{"t": 100.0}], [{"t": 100.0 + 1e-9}]) == "exact_match"

    def test_empty_both_exact(self):
        assert match_status([], []) == "exact_match"

    def test_column_count_mismatch(self):
        assert match_status([{"a": 1}], [{"a": 1, "b": 1}]) == "mismatch"
