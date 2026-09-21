"""The date block names the table's own time columns.

Every context used to get the same sentence — "ใช้ YEAR และ MONTH" — because get_date_format()
returned a constant and ignored the table. feed_ebt has only `time_key`, pl_costtype has
`report_year` / `report_month`: the prompt was telling the model to filter on columns that do not
exist (plan/archive/RESULT_F11.md §8).
"""

import json

from app.services.schema import prompt_builder


class _Service:
    def __init__(self, metadata=None, columns=None):
        self._metadata, self._columns = metadata, columns or []

    def get_schema_metadata(self, table_name):
        return self._metadata

    def get_table_info(self, table_name):
        return [{"name": c, "type": "TEXT"} for c in self._columns]


def _meta(*pairs):
    return [{"column_name": name, "is_summable": summable} for name, summable in pairs]


def test_names_the_tables_own_columns():
    service = _Service(_meta(("time_key", 0), ("division", 0), ("ebt", 1)))
    note = prompt_builder.build_date_instructions(service, "fact_monthly")
    columns = note.split("fact_monthly: ")[1].split(" — ")[0]
    assert columns == "time_key"  # not division, not ebt, and not the old YEAR / MONTH


def test_a_measure_is_never_a_time_column():
    """ebt_month is baht for the month, not the month — the name alone would take it."""
    service = _Service(_meta(("time_key", 0), ("ebt_month", 1), ("expense_month", 1)))
    note = prompt_builder.build_date_instructions(service, "t")
    assert "ebt_month" not in note and "expense_month" not in note and "time_key" in note


def test_a_declared_period_column_counts_however_it_is_named():
    service = _Service(_meta(("fiscal_key", 0), ("amount", 1)))
    note = prompt_builder.build_date_instructions(
        service, "t", json.dumps({"year_month": "fiscal_key"}))
    assert "fiscal_key" in note


def test_a_scope_key_that_is_not_a_period_is_left_out():
    """org_code → cost_center is a scope column, not a time column."""
    service = _Service(_meta(("time_key", 0), ("cost_center", 0)))
    note = prompt_builder.build_date_instructions(
        service, "t", json.dumps({"year_month": "time_key", "org_code": "cost_center"}))
    assert "time_key" in note and "cost_center" not in note


def test_without_metadata_it_falls_back_to_the_database():
    note = prompt_builder.build_date_instructions(_Service(columns=["report_year", "report_month", "amount"]), "v")
    assert "report_year" in note and "report_month" in note and "amount" not in note


def test_nothing_time_like_claims_nothing():
    note = prompt_builder.build_date_instructions(_Service(_meta(("a", 0), ("b", 1))), "t")
    assert "คอลัมน์เวลาของตาราง" not in note
    assert "พ.ศ." in note  # the language-level hint still applies
