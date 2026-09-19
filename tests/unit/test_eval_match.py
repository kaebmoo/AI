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


class TestExtraLabelColumns:
    """The model often answers 'EBT of division X' as SELECT division, ebt … — the value is right and
    the row says what it is about. Extra TEXT columns are tolerated (value_match, never exact_match);
    an extra number, a missing column or another row count is still a mismatch."""

    def test_label_next_to_the_expected_value(self):
        assert match_status([{"ebt": -214373476.47}], [{"division": "สายงาน 1", "EBT สะสม": -214373476.47}]) == "value_match"
        assert match_status([{"bu": "8.รายได้อื่น", "v": 5.0}], [{"bu": "8.รายได้อื่น", "period": "2569", "v": 5.0}]) == "value_match"

    def test_label_columns_on_every_row(self):
        expected = [{"total": 1.0}, {"total": 2.0}]
        actual = [{"name": "A", "total": 2.0}, {"name": "B", "total": 1.0}]
        assert match_status(expected, actual) == "value_match"

    def test_null_label_is_still_a_label(self):
        assert match_status([{"v": 1.0}], [{"note": None, "v": 1.0}]) == "value_match"

    def test_extra_number_is_not_a_label(self):
        assert match_status([{"a": 1}], [{"a": 1, "b": 1}]) == "mismatch"
        assert match_status([{"v": 1.0}], [{"division": "X", "v": 1.0, "v_ytd": 9.0}]) == "mismatch"

    def test_wrong_value_with_a_label_is_a_mismatch(self):
        assert match_status([{"v": 1.0}], [{"division": "X", "v": 2.0}]) == "mismatch"

    def test_label_cannot_stand_in_for_an_expected_text_value(self):
        assert match_status([{"bu": "A", "v": 1.0}], [{"bu": "B", "note": "A", "v": 1.0}]) == "mismatch"

    def test_missing_column_or_other_row_count(self):
        assert match_status([{"bu": "A", "v": 1.0}], [{"v": 1.0}]) == "mismatch"
        assert match_status([{"v": 1.0}], [{"d": "X", "v": 1.0}, {"d": "Y", "v": 1.0}]) == "mismatch"
