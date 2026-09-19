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


def _config_with_columns(tmp_path):
    engine = _config(tmp_path, "ถ้าถามรายหน่วยงานให้ใช้ feed_e_fact")
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE source_tables ADD COLUMN columns TEXT"))
        conn.execute(text("""UPDATE source_tables SET columns = CASE table_name
            WHEN 'feed_e_total' THEN '[{"name": "time_key"}, {"name": "ebt"}]'
            ELSE '[{"name": "time_key"}, {"name": "division"}, {"name": "cost_center"}, {"name": "amount"}]' END"""))
    return engine


def test_filter_the_main_view_cannot_apply_sends_the_query_to_the_table_that_can(tmp_path):
    """Asked for one cost center, Pass 2 dropped the filter (the totals main view has no such
    column) and answered the all-division total as that cost center's — silently."""
    engine = _config_with_columns(tmp_path)
    intent = {"filters": [{"column": "cost_center", "operator": "LIKE", "value": "%2P1%"},
                          {"column": "time_key", "operator": "=", "value": 202607}], "dimensions": ["Division"]}
    rule = hybrid_flow.unfilterable_rule(intent, "feed_e_total", engine)
    assert "cost_center" in rule and "division" in rule and "time_key" not in rule.split("→")[0]
    assert "feed_e_fact" in rule and "ห้ามทิ้ง" in rule


def test_no_rule_when_the_main_view_has_every_column_or_the_context_is_legacy(tmp_path):
    engine = _config_with_columns(tmp_path)
    assert hybrid_flow.unfilterable_rule({"filters": [{"column": "time_key", "operator": "=", "value": 1}]}, "feed_e_total", engine) == ""
    assert hybrid_flow.unfilterable_rule({"filters": [{"column": "anything", "operator": "=", "value": 1}]}, "revenue_search", engine) == ""
    assert hybrid_flow.unfilterable_rule({"filters": [{"column": "x"}]}, "t", create_engine("sqlite://")) == ""


def test_a_name_no_table_has_is_left_to_pass_2(tmp_path):
    """Pass 1 names columns loosely (business_unit for bu) and Pass 2 maps them — not an error."""
    engine = _config_with_columns(tmp_path)
    intent = {"filters": [{"column": "region", "operator": "=", "value": "N"}]}
    assert hybrid_flow.unfilterable_rule(intent, "feed_e_total", engine) == ""
    assert hybrid_flow.unfilterable_columns(intent, "feed_e_total", engine) == ([], [])


def test_sql_that_drops_the_filter_is_rejected():
    """The prompt line alone did not hold: 'EBT of division 1' still came back as the total."""
    total = "SELECT SUM(ebt) FROM feed_e_total WHERE time_key = 202607"
    assert "division" in hybrid_flow.dropped_filter_error(total, ["division"], "feed_e_total")
    assert hybrid_flow.dropped_filter_error("SELECT SUM(amount) FROM feed_e_fact WHERE Division LIKE '%1%'", ["division"], "feed_e_total") is None
    assert hybrid_flow.dropped_filter_error(total, [], "feed_e_total") is None  # legacy / nothing required
    assert hybrid_flow.dropped_filter_error(total, None, "feed_e_total") is None


def test_filter_pass_1_made_up_from_the_context_rules_is_not_required(tmp_path):
    """ebt 1.3.1 says the report covers two divisions; Pass 1 turned that into a division filter on
    a question that names none, and the guard rejected the correct totals SQL until retries ran out."""
    engine = _config_with_columns(tmp_path)
    made_up = {"filters": [{"column": "division", "operator": "IN", "value": ["สายงานขาย 1", "สายงานขาย 2"]}]}
    asked = {"filters": [{"column": "division", "operator": "LIKE", "value": "%สายงานขาย 1%"}]}
    total_q, division_q = "รายได้ตามรายงาน EBT สะสมถึงเดือนกันยายน 2568", "กำไร EBT ของสายงานขาย 1 เดือนกันยายน 2568"
    assert hybrid_flow.unfilterable_columns(made_up, "feed_e_total", engine, total_q) == ([], [])
    assert hybrid_flow.unfilterable_columns(asked, "feed_e_total", engine, division_q)[0] == ["division"]
    assert hybrid_flow.unfilterable_columns({"dimensions": ["division"]}, "feed_e_total", engine, "รายได้แยกตามสายงาน")[0] == ["division"]


def test_pass_1_is_told_the_columns_only_the_other_table_has(tmp_path):
    """Pass 1 saw '(ใช้ตาราง <main view>)' only, and on some runs left the division out of the
    intent altogether — nothing downstream can enforce a filter that was never extracted."""
    engine = _config_with_columns(tmp_path)
    hint = hybrid_flow.intent_table_hint("feed_e_total", engine)
    assert "feed_e_fact" in hint and "division" in hint and "cost_center" in hint
    assert "time_key" not in hint and "feed_e_dim" not in hint  # main-view columns / uninstructed tables add nothing
    assert hybrid_flow.intent_table_hint("revenue_search", engine) == ""  # legacy: prompt unchanged
    assert hybrid_flow.intent_table_hint("t", create_engine("sqlite://")) == ""
