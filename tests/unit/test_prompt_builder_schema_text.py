"""The schema table in the system prompt shows a column's meaning.

A contract column's description (synced by datafeed_knowledge) used to be invisible to the model: the table rendered
only display_name_th and special_notes, so "ฝ่ายไหนมี EBT สูงสุด" was answered at division level (2026-10-24)."""

from app.services.schema.prompt_builder import _build_schema_from_metadata


def _row(name, **kw):
    return {"column_name": name, "data_type": "string", "is_summable": 0, "is_groupable": 1, **kw}


def test_description_fills_the_notes_column_when_there_are_no_special_notes():
    text = _build_schema_from_metadata([
        _row("unit", description="ฝ่าย — ระดับ 3 ของโครงสร้างองค์กร"),
        _row("division", display_name_th="สายงาน", description="สายงาน — ระดับ 1", special_notes="EBT รวมเฉพาะ 2 สายงาน"),
        _row("cost_center"),
    ], "feed_ebt_fact_ebt")
    lines = {line.split(" | ")[0].strip("| "): line for line in text.splitlines() if line.startswith("| ")}
    assert lines["unit"].endswith("| ฝ่าย — ระดับ 3 ของโครงสร้างองค์กร |")
    assert lines["division"].endswith("| EBT รวมเฉพาะ 2 สายงาน |") and "ระดับ 1" not in lines["division"]
    assert lines["cost_center"].endswith("|  |")


def test_conversion_sql_still_appends_to_the_description():
    text = _build_schema_from_metadata([_row("time_key", description="งวด ค.ศ. YYYYMM", conversion_sql="CAST(time_key AS INTEGER)")],
                                       "feed_ebt_fact_ebt")
    assert "งวด ค.ศ. YYYYMM แปลงด้วย: `CAST(time_key AS INTEGER)`" in text
