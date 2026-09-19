"""The prompt pins the model to the context's main view — except for tables the context's own
instruction names (ebt: the totals table is the main view, the instruction sends per-division
questions to fact_ebt). Legacy contexts keep the pin, byte for byte."""

from sqlalchemy import create_engine, text

from app.services.ai import hybrid_flow


def _config(tmp_path, instruction):
    engine = create_engine(f"sqlite:///{tmp_path / 'config.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE schema_contexts (name TEXT, main_view TEXT, is_active INTEGER, source_id INTEGER, instruction_th TEXT)"))
        conn.execute(text("CREATE TABLE source_tables (source_id INTEGER, table_name TEXT, is_active INTEGER)"))
        conn.execute(text("INSERT INTO schema_contexts VALUES ('feed_e', 'feed_e_total', 1, 7, :i), ('revenue', 'revenue_search', 1, NULL, 'x')"),
                     {"i": instruction})
        conn.execute(text("INSERT INTO source_tables VALUES (7, 'feed_e_total', 1), (7, 'feed_e_fact', 1), (7, 'feed_e_dim', 1)"))
    return engine


def test_instructed_table_is_allowed(tmp_path):
    engine = _config(tmp_path, "ถ้าถามรายหน่วยงานให้ใช้ feed_e_fact (คอลัมน์: a, b)")
    rule = hybrid_flow.table_rule("feed_e_total", engine)
    assert "feed_e_total" in rule and "feed_e_fact" in rule and "feed_e_dim" not in rule and "เท่านั้น" not in rule


def test_pin_unchanged_without_instructed_tables(tmp_path):
    engine = _config(tmp_path, "ไม่ได้เอ่ยถึงตารางอื่น")
    assert hybrid_flow.table_rule("feed_e_total", engine) == "ต้องใช้ตาราง feed_e_total เท่านั้น"
    assert hybrid_flow.table_rule("revenue_search", engine) == "ต้องใช้ตาราง revenue_search เท่านั้น"  # legacy
    assert hybrid_flow.table_rule("t", create_engine("sqlite://")) == "ต้องใช้ตาราง t เท่านั้น"  # registry not migrated
